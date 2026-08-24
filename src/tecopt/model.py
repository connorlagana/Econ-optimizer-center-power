"""Capacity and dispatch, co-optimised in one linear program.

Why an LP and not a search over candidate designs
-------------------------------------------------
The natural way to write this study is the way the brief describes it: pick
designs A-E, simulate each hour by hour, compare. That is what project 1 does,
inheriting upstream's Latin-hypercube-plus-differential-evolution search over
(solar MW, battery MW), with an 8760-hour simulator in the loop.

It does not extend. Adding battery duration, grid size and generator size takes
the search from 2 dimensions to 5, and a derivative-free search over a
simulator needs samples exponential in dimension to say anything about an
optimum. Worse, it can only ever report the best design it happened to try.

But every term in this problem is linear in the decision variables:

* capital cost is ``$/MW x MW``;
* a capacity constraint is ``flow[t] <= capacity``, and ``capacity`` being a
  variable rather than a constant does not change that;
* storage state is an equality in the variables;
* and the GPU power-performance curve is **concave**, so
  ``compute <= m_k * power + c_k`` for each hull segment, maximised, traces the
  curve exactly — with no binaries.

That last point is the one that makes this tractable, and project 1 already
established it (``gpu.PowerPerformanceCurve.concave_hull``). So sizing and
8760-hour dispatch solve *simultaneously*, exactly, in one LP — seconds, not a
sampling budget — and the answer is the optimum rather than the best guess.

What this formulation costs you
-------------------------------
**Perfect foresight.** The LP sees all 8760 hours at once. A real controller
does not, and a design sized under perfect foresight is systematically
under-built: it holds less storage than a forecast-driven operator needs. This
number is a *lower bound* on required infrastructure. Project 1 already has the
machinery to close the gap — ``forecast_mpc`` with error calibrated to realised
day-ahead nRMSE — and the intended workflow is: size here, validate there,
report the degradation. Never quote an LP sizing as a buildable design.

Objective
---------
Minimise total annualised system cost subject to delivering at least a target
quantity of compute. The brief's other formulation — minimise cost *per unit
compute* — is a linear-fractional program, not an LP. It does not need special
handling, because sweeping the compute target and reading the cost off each
solve produces the whole cost-vs-compute frontier, of which minimum unit cost
is one point. The frontier was the deliverable anyway; the ratio is a column in
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import cvxpy as cp
import numpy as np

from .inputs import Scenario, crf
from .workload import WorkloadMix, _windows, diurnal_inference_profile

Flexibility = Literal["rigid", "curtail", "powercap"]


@dataclass(frozen=True)
class Design:
    """What the optimiser decided to build."""

    pv_mw: float
    bess_mw: float
    bess_mwh: float
    grid_mw: float
    gen_mw: float

    @property
    def bess_duration_h(self) -> float:
        return self.bess_mwh / self.bess_mw if self.bess_mw > 1e-6 else 0.0


@dataclass(frozen=True)
class Result:
    scenario: Scenario
    flexibility: Flexibility
    compute_target_fraction: float
    status: str
    price_basis: dict
    workload: dict | None
    design: Design
    annual_cost: float
    cost_breakdown: dict
    compute_unit_hours: float
    lcoc_per_gpu_hour: float
    compute_shadow_price: float
    dispatch: dict
    variable_cost: float
    net_value: float
    peak_import_mw: float
    coincident_peak_mw: float
    gen_run_hours: float
    pv_curtailed_fraction: float
    mean_it_power_fraction: float


def _allocation(active, hours: int) -> np.ndarray:
    """Per-hour MW assigned to a class, whether it was a variable or a constant."""
    if isinstance(active, (int, float)):
        return np.full(hours, float(active))
    return np.asarray(active.value, dtype=float)


def concave_hull_segments(curve) -> list[tuple[float, float]]:
    """``(slope, intercept)`` of each line whose lower envelope is the curve.

    For a concave piecewise-linear ``f``, ``f(x) = min_k (m_k x + c_k)`` over
    the lines through consecutive hull points. Imposing ``y <= m_k x + c_k`` for
    every ``k`` and letting the objective push ``y`` up therefore reproduces the
    curve exactly, with no integer variables and no interpolation code.
    """
    hull = curve.concave_hull()
    xs = np.asarray(hull.power_fraction, dtype=float)
    ys = np.asarray(hull.compute_fraction, dtype=float)
    segments = []
    for i in range(len(xs) - 1):
        slope = (ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i])
        segments.append((float(slope), float(ys[i] - slope * xs[i])))
    return segments


def optimise(
    scenario: Scenario,
    pv_capacity_factor: np.ndarray,
    curve,
    *,
    flexibility: Flexibility = "powercap",
    compute_target_fraction: float = 1.0,
    coincident_peak_mask: np.ndarray | None = None,
    energy_price_per_mwh: float | np.ndarray | None = None,
    allow_export: bool = False,
    workload: WorkloadMix | None = None,
    local_hour: np.ndarray | None = None,
    solver: str = "HIGHS",
    verbose: bool = False,
) -> Result:
    """Co-optimise capacity and dispatch for one weather year.

    ``pv_capacity_factor`` is AC output per unit of installed DC nameplate, on a
    scale common to every weather year (project 1's ``pv_model`` correction —
    per-year renormalisation silently rescales and reorders years).

    ``compute_target_fraction`` is a floor on annual compute as a fraction of
    what the fleet would produce running unconstrained every hour of the year.

    ``energy_price_per_mwh`` may be a scalar or an 8760-hour array. Passing an
    array is what V3 is for: a flat price cannot express that abundant solar and
    cheap energy are the same hours, and that correlation is the single most
    important structure in the problem (README landmine 6). ``None`` falls back
    to the scenario's flat placeholder, which is what V1 and V2 used.

    ``allow_export`` sells surplus PV at the same hourly price (README landmine
    8). It is off by default because V1 and V2 assumed behind-the-meter, and
    turning it on moves the optimal PV size by a factor rather than a margin.
    Export is restricted to PV: exporting generator output is a merchant power
    plant with a different permit, and exporting stored energy is price
    arbitrage that deserves to be studied on its own rather than smuggled in
    as a side effect of sizing a data center.

    ``workload`` replaces the single fungible compute pool with a mix of classes
    that have deadlines and service levels (V5). ``None`` keeps V1 through V4's
    pool exactly, so every earlier result reproduces. ``local_hour`` is the
    hour-of-day for each step, needed to place the inference arrival profile;
    it defaults to a plain 24-hour cycle from midnight.
    """
    cf = np.asarray(pv_capacity_factor, dtype=float)
    T = cf.size

    price = (
        scenario.costs.energy_price_per_mwh
        if energy_price_per_mwh is None
        else energy_price_per_mwh
    )
    price = np.broadcast_to(np.asarray(price, dtype=float), (T,)).astype(float)
    s, c, g, f, st, lim = (
        scenario, scenario.costs, scenario.gpus,
        scenario.facility, scenario.storage, scenario.limits,
    )

    it_max = g.it_nameplate_mw
    overhead_fixed = f.fixed_overhead_mw(it_max)
    overhead_mult = f.variable_multiplier()

    # --- capacity (what we are choosing to build) ------------------------
    pv_mw = cp.Variable(nonneg=True, name="pv_mw")
    bess_mw = cp.Variable(nonneg=True, name="bess_mw")
    bess_mwh = cp.Variable(nonneg=True, name="bess_mwh")
    grid_mw = cp.Variable(nonneg=True, name="grid_mw")
    gen_mw = cp.Variable(nonneg=True, name="gen_mw")

    # --- dispatch --------------------------------------------------------
    pv_use = cp.Variable(T, nonneg=True)
    charge = cp.Variable(T, nonneg=True)
    discharge = cp.Variable(T, nonneg=True)
    soc = cp.Variable(T + 1, nonneg=True)
    imports = cp.Variable(T, nonneg=True)
    gen_out = cp.Variable(T, nonneg=True)
    exports = cp.Variable(T, nonneg=True)
    # ``p_it`` and ``compute`` are plain variables for the single-pool model and
    # *expressions* over the per-class variables for the workload model. Binding
    # them with equality constraints instead would add 2xT redundant rows that
    # alias one variable to another, which HiGHS pays for at every iteration.
    if workload is None:
        p_it = cp.Variable(T, nonneg=True)
        compute = cp.Variable(T, nonneg=True)
    cp_demand = cp.Variable(nonneg=True, name="coincident_peak_mw")

    cons: list = []

    # Solar: use no more than the array produced. The slack is curtailment,
    # which is free here because export is not modelled (behind-the-meter).
    if allow_export:
        # Export plus an unbounded interconnection and unbounded land is not a
        # data-center study: it is a merchant solar farm with unlimited upside,
        # and the LP will correctly report "unbounded" rather than a design.
        # Whether it does depends on the price year, which is the point --
        # at 2019 LZ_NORTH prices a merchant array clears its own cost by a few
        # thousand dollars per MW-year, and at 2024 prices it misses by fifty.
        # Refuse the ambiguous case explicitly rather than let the solver do it.
        if lim.max_grid_mw is None and lim.max_pv_mw is None:
            raise ValueError(
                "allow_export=True requires Limits.max_grid_mw or Limits.max_pv_mw. "
                "With export rights, an unlimited interconnection and unlimited land, "
                "building solar is a separate business with no upper bound, and the "
                "LP is unbounded whenever merchant PV happens to clear its cost in "
                "the chosen price year. Set the interconnection the project can "
                "actually procure (README landmine 10)."
            )
        cons.append(pv_use + exports <= cp.multiply(cf, pv_mw))
    else:
        cons += [pv_use <= cp.multiply(cf, pv_mw), exports == 0]
    if lim.max_pv_mw is not None:
        cons.append(pv_mw <= lim.max_pv_mw)

    # Storage. Cyclic SOC: a year must hand the next year the state it was
    # given, or the optimiser finances the project with free stored energy.
    cons += [
        charge <= bess_mw,
        discharge <= bess_mw,
        soc <= st.soc_max_fraction * bess_mwh,
        soc >= st.soc_min_fraction * bess_mwh,
        soc[1:] == soc[:-1] + st.charge_efficiency * charge - discharge / st.discharge_efficiency,
        soc[0] == soc[T],
    ]

    # Grid. Interconnection size is a decision; the coincident-peak charge is
    # levied on the highest import inside the charging window, which is the
    # quantity flexibility can actually defend against.
    # One interconnection, used in one direction at a time: the transformer does
    # not care which way the power flows, and sizing it on imports alone would
    # let export ride for free on a wire the study never charged for.
    cons.append(imports + exports <= grid_mw)
    if lim.max_grid_mw is not None:
        cons.append(grid_mw <= lim.max_grid_mw)
    if coincident_peak_mask is not None and coincident_peak_mask.any():
        cons.append(imports[coincident_peak_mask] <= cp_demand)
    else:
        cons.append(cp_demand == 0)

    # Backup generation. The energy cap stands in for an air permit's run-hour
    # limit; without it the optimiser builds an unpermittable merchant plant and
    # reports that gas dominates. It is a *proxy* -- equivalent full-load hours,
    # not operating hours, because the latter needs a binary per hour. See
    # Limits.gen_annual_full_load_hours.
    cons += [gen_out <= gen_mw, cp.sum(gen_out) <= lim.gen_annual_full_load_hours * gen_mw]

    # Compute demand and what it produces.
    segments = concave_hull_segments(curve)
    if flexibility not in ("rigid", "curtail", "powercap"):
        raise ValueError(f"unknown flexibility mode {flexibility!r}")

    class_vars: dict[str, dict] = {}

    if workload is None:
        # V1 through V4: one fungible pool with an annual target.
        if flexibility == "rigid":
            cons += [p_it == it_max, compute == 1.0]
        else:
            cons += [p_it <= it_max, p_it >= curve.idle_power_fraction * it_max]
            if flexibility == "curtail":
                # Park racks, do not power-cap them: work falls off proportionally.
                # Isolates the value of *doing less* from the value of the curve.
                cons.append(compute <= p_it / it_max)
            else:
                for slope, intercept in segments:
                    cons.append(compute <= slope * p_it / it_max + intercept)
            cons.append(compute <= 1.0)

        compute_floor = cp.sum(compute) >= compute_target_fraction * T
        cons.append(compute_floor)
    else:
        # V5: the fleet is shared between classes, hour by hour, and each
        # class's work is tied to time differently.
        #
        # Allocation is *per hour*, not a fixed partition of the fleet. That is
        # what a cluster scheduler actually does -- preemptible batch work
        # backfills the capacity inference is not using at 4am -- and a fixed
        # partition gets the physics wrong in a way that matters: it makes a
        # peaky inference arrival profile infeasible against rigid compute,
        # because a constant per-class output cannot follow a varying demand.
        #
        # ``active[k][t]`` is the nameplate MW assigned to class k in hour t.
        # The concave hull stays linear in it because it is written absolutely:
        # compute <= m·power + c·active, both products of a constant and a
        # variable. See workload.py.
        hours = (
            np.arange(T) % 24 if local_hour is None
            else np.asarray(local_hour, dtype=float)
        )
        idle = curve.idle_power_fraction
        single = len(workload.classes) == 1

        for spec in workload.classes:
            # Allocation is an equality across classes, not an inequality.
            # Assigning a GPU to a class is free and weakly increases what that
            # class can produce -- the concave curve rewards spreading a fixed
            # power budget over more silicon -- so an optimal solution always
            # exists with the fleet fully allocated. Leaving it slack adds 8,760
            # zero-cost directions and a family of alternate optima that the
            # simplex has to walk through to reach the same answer.
            #
            # With one class the allocation is not a decision at all, so it is a
            # constant and the formulation collapses exactly onto V1's.
            active = it_max if single else cp.Variable(T, nonneg=True, name=f"active_{spec.name}")
            power = cp.Variable(T, nonneg=True, name=f"power_{spec.name}")
            produced = cp.Variable(T, nonneg=True, name=f"compute_{spec.name}")

            if flexibility == "rigid":
                cons += [power == active, produced == active / it_max]
            else:
                cons += [power <= active, power >= idle * active]
                if flexibility == "curtail":
                    cons.append(produced <= power / it_max)
                else:
                    # The last hull segment passes through (1, 1), so it already
                    # implies produced <= active/it_max; stating that separately
                    # would be a redundant row per hour per class.
                    for slope, intercept in segments:
                        cons.append(
                            produced <= slope * power / it_max
                            + intercept * active / it_max
                        )

            required = spec.share_of_compute * T * compute_target_fraction
            if spec.kind == "batch":
                cons.append(cp.sum(produced) >= required)
            elif spec.kind == "deadline":
                for window in _windows(T, spec.window_hours):
                    span = window.stop - window.start
                    cons.append(
                        cp.sum(produced[window])
                        >= spec.share_of_compute * span * compute_target_fraction
                    )
            elif spec.kind == "inference":
                shape = (
                    diurnal_inference_profile(hours)
                    if spec.arrival_profile is None
                    else np.asarray(spec.arrival_profile, dtype=float)
                )
                arrivals = shape / shape.sum() * spec.share_of_compute * T
                cons.append(
                    produced >= spec.sla_fraction * arrivals * compute_target_fraction
                )
            else:  # pragma: no cover - guarded by WorkloadClass
                raise ValueError(f"unknown workload kind {spec.kind!r}")

            class_vars[spec.name] = {
                "spec": spec, "active": active,
                "power": power, "compute": produced,
            }

        if not single:
            cons.append(sum(cell["active"] for cell in class_vars.values()) == it_max)
        p_it = sum(cell["power"] for cell in class_vars.values())
        compute = sum(cell["compute"] for cell in class_vars.values())

        compute_floor = cp.sum(compute) >= compute_target_fraction * T
        cons.append(compute_floor)

    # Power balance. Non-IT load carries a fixed component that a throttle does
    # not shed — see Facility in inputs.py.
    facility = overhead_fixed + overhead_mult * p_it
    cons.append(pv_use + discharge + imports + gen_out == facility + charge)


    # --- objective, annualised real USD ----------------------------------
    fin = s.financing
    ann_pv = 1000.0 * pv_mw * (c.pv_capex_per_kw_dc * crf(fin.discount_rate, fin.pv_life_years) + c.pv_fom_per_kw_yr)
    ann_bess = 1000.0 * (
        bess_mw * (c.bess_capex_per_kw * crf(fin.discount_rate, fin.bess_life_years) + c.bess_fom_per_kw_yr)
        + bess_mwh * c.bess_capex_per_kwh * crf(fin.discount_rate, fin.bess_life_years)
    )
    ann_gen = 1000.0 * gen_mw * (c.gen_capex_per_kw * crf(fin.discount_rate, fin.gen_life_years) + c.gen_fom_per_kw_yr)
    ann_grid = 1000.0 * (
        grid_mw * (c.interconnect_capex_per_kw * crf(fin.discount_rate, fin.grid_life_years) + c.transmission_fom_per_kw_yr)
        + cp_demand * c.coincident_peak_per_kw_yr
    )
    ann_energy = cp.sum(cp.multiply(price, imports))
    ann_export_revenue = cp.sum(cp.multiply(price, exports))
    ann_fuel = cp.sum(gen_out) * (c.gen_heat_rate_mmbtu_per_mwh * c.gas_price_per_mmbtu + c.gen_vom_per_mwh)
    # Constant in the design, decisive in the ratio: an hour of compute forgone
    # strands GPU capital that is being paid for whether it computes or not.
    ann_gpu = g.total_capex * crf(fin.discount_rate, fin.gpu_life_years)

    total = (
        ann_pv + ann_bess + ann_gen + ann_grid + ann_energy + ann_fuel + ann_gpu
        - ann_export_revenue
    )
    problem = cp.Problem(cp.Minimize(total), cons)
    problem.solve(solver=solver, verbose=verbose)

    if problem.status not in ("optimal", "optimal_inaccurate"):
        raise RuntimeError(f"LP did not solve: {problem.status}")

    v = lambda x: float(np.asarray(x.value).item())
    arr = lambda x: np.asarray(x.value, dtype=float)

    pv_available = cf * v(pv_mw)
    pv_used = arr(pv_use)
    curtailed = pv_available.sum() - pv_used.sum()
    compute_hours = float(arr(compute).sum())

    # Dual of the compute floor: what the last compute-unit-hour cost the
    # planner at the margin, in dollars. This is the price at which an operator
    # should be indifferent between producing a unit and not, and it is what
    # operate.py values compute at — not a tuned parameter but the planner's own
    # marginal cost, recovered from the solve that set the design.
    shadow = compute_floor.dual_value
    shadow = abs(float(np.asarray(shadow).item())) if shadow is not None else float("nan")

    design = Design(v(pv_mw), v(bess_mw), v(bess_mwh), v(grid_mw), v(gen_mw))
    breakdown = {
        "pv": float(ann_pv.value),
        "bess": float(ann_bess.value),
        "generator": float(ann_gen.value),
        "grid_capacity": float(ann_grid.value),
        "grid_energy": float(ann_energy.value),
        "fuel": float(ann_fuel.value),
        "gpu_capital": float(ann_gpu),
        "export_revenue": -float(ann_export_revenue.value),
    }
    gpu_hours = compute_hours * g.gpu_count

    return Result(
        scenario=s,
        flexibility=flexibility,
        compute_target_fraction=compute_target_fraction,
        status=problem.status,
        workload=(
            None if workload is None
            else {
                "classes": workload.describe(),
                "mean_allocation_mw": {
                    name: float(np.mean(_allocation(cell["active"], T)))
                    for name, cell in class_vars.items()
                },
                "peak_allocation_mw": {
                    name: float(np.max(_allocation(cell["active"], T)))
                    for name, cell in class_vars.items()
                },
                "delivered_fraction_of_fleet_year": {
                    name: float(arr(cell["compute"]).sum()) / T
                    for name, cell in class_vars.items()
                },
                "mean_power_fraction": {
                    name: (
                        float(arr(cell["power"]).sum() / _allocation(cell["active"], T).sum())
                        if _allocation(cell["active"], T).sum() > 1e-6 else 0.0
                    )
                    for name, cell in class_vars.items()
                },
            }
        ),
        price_basis={
            "hourly": bool(np.ptp(price) > 0),
            "mean_per_mwh": float(price.mean()),
            "min_per_mwh": float(price.min()),
            "max_per_mwh": float(price.max()),
            "negative_hours": int((price < 0).sum()),
            "allow_export": bool(allow_export),
        },
        design=design,
        annual_cost=float(problem.value),
        cost_breakdown=breakdown,
        compute_unit_hours=compute_hours,
        compute_shadow_price=shadow,
        lcoc_per_gpu_hour=float(problem.value) / gpu_hours if gpu_hours > 0 else float("inf"),
        dispatch={
            "pv_used_mwh": pv_used,
            "pv_available_mwh": pv_available,
            "charge_mw": arr(charge),
            "discharge_mw": arr(discharge),
            "soc_mwh": arr(soc),
            "import_mw": arr(imports),
            "gen_mw": arr(gen_out),
            "it_power_mw": arr(p_it),
            "compute_fraction": arr(compute),
            "export_mw": arr(exports),
        },
        variable_cost=float(ann_energy.value) + float(ann_fuel.value)
        - float(ann_export_revenue.value),
        net_value=shadow * compute_hours
        - (float(ann_energy.value) + float(ann_fuel.value) - float(ann_export_revenue.value)),
        peak_import_mw=float(arr(imports).max()),
        coincident_peak_mw=v(cp_demand),
        gen_run_hours=float((arr(gen_out) > 1e-6).sum()),
        pv_curtailed_fraction=float(curtailed / pv_available.sum()) if pv_available.sum() > 0 else 0.0,
        mean_it_power_fraction=float(arr(p_it).mean() / it_max),
    )
