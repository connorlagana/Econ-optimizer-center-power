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
    solver: str = "HIGHS",
    verbose: bool = False,
) -> Result:
    """Co-optimise capacity and dispatch for one weather year.

    ``pv_capacity_factor`` is AC output per unit of installed DC nameplate, on a
    scale common to every weather year (project 1's ``pv_model`` correction —
    per-year renormalisation silently rescales and reorders years).

    ``compute_target_fraction`` is a floor on annual compute as a fraction of
    what the fleet would produce running unconstrained every hour of the year.
    """
    cf = np.asarray(pv_capacity_factor, dtype=float)
    T = cf.size
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
    p_it = cp.Variable(T, nonneg=True)
    compute = cp.Variable(T, nonneg=True)
    cp_demand = cp.Variable(nonneg=True, name="coincident_peak_mw")

    cons: list = []

    # Solar: use no more than the array produced. The slack is curtailment,
    # which is free here because export is not modelled (behind-the-meter).
    cons.append(pv_use <= cp.multiply(cf, pv_mw))
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
    cons.append(imports <= grid_mw)
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
    if flexibility == "rigid":
        cons += [p_it == it_max, compute == 1.0]
    else:
        cons += [p_it <= it_max, p_it >= curve.idle_power_fraction * it_max]
        if flexibility == "curtail":
            # Park racks, do not power-cap them: work falls off proportionally.
            # Isolates the value of *doing less* from the value of the curve.
            cons.append(compute <= p_it / it_max)
        elif flexibility == "powercap":
            for slope, intercept in concave_hull_segments(curve):
                cons.append(compute <= slope * p_it / it_max + intercept)
        else:
            raise ValueError(f"unknown flexibility mode {flexibility!r}")
        cons.append(compute <= 1.0)

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
    ann_energy = cp.sum(imports) * c.energy_price_per_mwh
    ann_fuel = cp.sum(gen_out) * (c.gen_heat_rate_mmbtu_per_mwh * c.gas_price_per_mmbtu + c.gen_vom_per_mwh)
    # Constant in the design, decisive in the ratio: an hour of compute forgone
    # strands GPU capital that is being paid for whether it computes or not.
    ann_gpu = g.total_capex * crf(fin.discount_rate, fin.gpu_life_years)

    total = ann_pv + ann_bess + ann_gen + ann_grid + ann_energy + ann_fuel + ann_gpu
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
    }
    gpu_hours = compute_hours * g.gpu_count

    return Result(
        scenario=s,
        flexibility=flexibility,
        compute_target_fraction=compute_target_fraction,
        status=problem.status,
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
        },
        variable_cost=float(ann_energy.value) + float(ann_fuel.value),
        net_value=shadow * compute_hours - (float(ann_energy.value) + float(ann_fuel.value)),
        peak_import_mw=float(arr(imports).max()),
        coincident_peak_mw=v(cp_demand),
        gen_run_hours=float((arr(gen_out) > 1e-6).sum()),
        pv_curtailed_fraction=float(curtailed / pv_available.sum()) if pv_available.sum() > 0 else 0.0,
        mean_it_power_fraction=float(arr(p_it).mean() / it_max),
    )
