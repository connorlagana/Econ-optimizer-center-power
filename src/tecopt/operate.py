"""Operate a fixed design without foresight, and see what it actually delivers.

The planning LP in ``model.py`` sees all 8760 hours at once. Its sizing is
therefore a *lower bound* on the plant a real site needs, and its compute
figure is an *upper bound* on what that plant will produce. Neither bound is
useful until the gap is measured, and the gap is what this module measures.

Three rungs, differing only in what the controller knows:

``annual``   the planning LP itself — the promise, and the ceiling.
``perfect``  receding horizon, exact forecast. Isolates the cost of a *finite
             horizon*: a controller that cannot see past 48 hours gives
             something up even when what it does see is exactly right.
``noisy``    receding horizon, forecast calibrated to a stated realised
             day-ahead nRMSE. The deployable case. The extra loss over
             ``perfect`` is the cost of *forecast error*, cleanly separated.

Keeping ``perfect`` in the middle is the whole point of the ladder. A study
that reports only annual-LP versus realistic-MPC cannot say whether the loss
came from not seeing far enough or from seeing wrongly, and those have
different fixes — a longer horizon is cheap, a better forecast is not.

Design choices worth arguing with
---------------------------------
**Hourly re-planning.** The forecast model has exactly zero error at lead zero,
because a site measures its own irradiance. Re-planning every hour therefore
means the hour being committed is always known exactly, and no recourse step is
needed to reconcile a plan made under forecast with a reality that differed.
Stepping less often would require one, and the recourse rule would then be
doing some of the work the experiment is trying to measure.

**Terminal value of stored energy.** A finite-horizon controller drains the
battery at the horizon edge unless the energy left in it is worth something.
Valued here at the compute it could produce if spent at the curve's most
efficient operating point and never curtailed — an *upper* bound, which makes
the controller appropriately reluctant to empty the battery. Same reasoning as
project 1's ``PlantModel.marginal_compute_per_battery_mwh``.

**Compute is priced at stranded GPU capital, not at the planner's shadow
price.** The operational objective needs a value for a compute-unit-hour, and
the planner's dual on the annual compute floor is the wrong one: it is the
marginal cost of *buying more plant* to raise the floor, which is a planning
quantity. Once capacity is sunk the only thing an unproduced compute-unit-hour
costs is the GPU capital that was amortised whether it computed or not —
``gpu_capital_per_year / 8760``. That is also uniform across designs, which is
what makes net value comparable between them; the shadow price is not, and for
the rigid design it is degenerately zero because compute is not a decision
there at all.

**The coincident-peak defence is a number, not a forecast.** A real operator
does not know which hour sets the 4CP charge; they set an import target and
defend it. The controller here gets a hard import cap during the risk window,
equal to the peak the planner assumed. That is one scalar of plan, not hourly
foresight, and it is what makes the 4CP saving in the planning result something
an operator could actually realise.

**Generator rationing is a heuristic and is flagged as one.** The annual energy
budget is a year-long constraint that a 48-hour controller cannot see. It is
rationed pro-rata over the hours remaining, with slack. A better controller
would price the budget rather than ration it; that is a V5 item.
"""

from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np

from .inputs import Scenario
from .model import Design, Flexibility, concave_hull_segments

#: How much of the pro-rata generator ration a single window may spend. Pure
#: heuristic: 1.0 forbids saving fuel for a bad week, large values let the
#: controller burn the year's budget in January.
GEN_RATION_SLACK = 3.0

#: Penalty on unserved load, $/MWh, as an **absolute** figure.
#:
#: It was briefly expressed as a multiple of the compute price, which is a trap:
#: the rigid design's compute price is legitimately zero — compute is not a
#: decision there, so the planner's dual on the compute floor is degenerate —
#: and a zero-scaled penalty made shedding the entire year's load free. Any
#: penalty that can be scaled to zero by a legitimate input is not a penalty.
#: Absolute, and far above any real cost in the model.
UNSERVED_PENALTY_PER_MWH = 1e7


@dataclass(frozen=True)
class OperationResult:
    label: str
    flexibility: Flexibility
    forecast_name: str
    horizon_hours: int
    compute_unit_hours: float
    compute_fraction: float
    planned_compute_fraction: float
    unserved_mwh: float
    unserved_hours: int
    import_cost: float
    fuel_cost: float
    variable_cost: float
    net_value: float
    gen_energy_mwh: float
    gen_budget_mwh: float
    import_energy_mwh: float
    peak_import_mw: float
    coincident_peak_mw: float
    pv_curtailed_fraction: float
    mean_it_power_fraction: float
    series: dict

    @property
    def compute_shortfall_pct(self) -> float:
        """Percentage points of annual compute below the plan's floor.

        Negative means the operator beat the floor, which is the normal case
        and not a paradox: the floor was a *constraint* the planner priced
        capacity against, and once that capacity is sunk the operator produces
        until marginal cost meets marginal value. Judge the operator on
        :attr:`net_value`, not on this.
        """
        return (self.planned_compute_fraction - self.compute_fraction) * 100.0


class _WindowLP:
    """One compiled horizon LP, re-solved every hour against new parameters.

    Compiled once through cvxpy's DPP path so that 8,760 solves cost one
    canonicalisation rather than 8,760 of them. Everything that changes hour to
    hour — available PV, opening state of charge, remaining fuel budget, the
    import cap — enters as a Parameter.
    """

    def __init__(
        self,
        scenario: Scenario,
        design: Design,
        curve,
        flexibility: Flexibility,
        horizon: int,
        compute_price: float,
        storage_value: float,
    ) -> None:
        c, g, f, st = scenario.costs, scenario.gpus, scenario.facility, scenario.storage
        it_max = g.it_nameplate_mw
        overhead_fixed = f.fixed_overhead_mw(it_max)
        overhead_mult = f.variable_multiplier()
        H = horizon

        self.pv_avail = cp.Parameter(H, nonneg=True)
        self.imp_cap = cp.Parameter(H, nonneg=True)
        self.soc_init = cp.Parameter(nonneg=True)
        self.gen_budget = cp.Parameter(nonneg=True)

        pv_use = cp.Variable(H, nonneg=True)
        charge = cp.Variable(H, nonneg=True)
        discharge = cp.Variable(H, nonneg=True)
        soc = cp.Variable(H + 1, nonneg=True)
        imports = cp.Variable(H, nonneg=True)
        gen_out = cp.Variable(H, nonneg=True)
        p_it = cp.Variable(H, nonneg=True)
        compute = cp.Variable(H, nonneg=True)
        unserved = cp.Variable(H, nonneg=True)

        cons = [
            pv_use <= self.pv_avail,
            charge <= design.bess_mw,
            discharge <= design.bess_mw,
            soc <= st.soc_max_fraction * design.bess_mwh,
            soc >= st.soc_min_fraction * design.bess_mwh,
            soc[0] == self.soc_init,
            soc[1:] == soc[:-1] + st.charge_efficiency * charge - discharge / st.discharge_efficiency,
            imports <= self.imp_cap,
            gen_out <= design.gen_mw,
            cp.sum(gen_out) <= self.gen_budget,
        ]

        cons += [p_it <= it_max, p_it >= curve.idle_power_fraction * it_max, compute <= 1.0]
        if flexibility == "powercap":
            for slope, intercept in concave_hull_segments(curve):
                cons.append(compute <= slope * p_it / it_max + intercept)
        else:
            # "rigid" and "curtail" share their *operational* physics: work falls
            # off in proportion to power, with no efficiency gained by throttling.
            # What separates them is a planning permission — whether the design
            # was allowed to buy less than 100% compute — not anything the
            # hardware does at run time.
            #
            # Rigid must NOT be encoded here as `p_it == it_max, compute == 1`,
            # which is how the planner states it. In the planner that is exact,
            # because the plant is sized so the case never arises. In operation
            # it credits full compute for an hour the plant could not power,
            # with the shortfall disappearing into the unserved-load slack: the
            # rigid design scored 100% compute across 834 hours of blackout.
            cons.append(compute <= p_it / it_max)

        facility = overhead_fixed + overhead_mult * p_it
        cons.append(pv_use + discharge + imports + gen_out + unserved == facility + charge)

        fuel_rate = c.gen_heat_rate_mmbtu_per_mwh * c.gas_price_per_mmbtu + c.gen_vom_per_mwh
        value = (
            compute_price * cp.sum(compute)
            - c.energy_price_per_mwh * cp.sum(imports)
            - fuel_rate * cp.sum(gen_out)
            - UNSERVED_PENALTY_PER_MWH * cp.sum(unserved)
            + storage_value * soc[H]
        )

        self.problem = cp.Problem(cp.Maximize(value), cons)
        self.vars = {
            "pv_use": pv_use, "charge": charge, "discharge": discharge, "soc": soc,
            "imports": imports, "gen_out": gen_out, "p_it": p_it,
            "compute": compute, "unserved": unserved,
        }
        assert self.problem.is_dcp(dpp=True), "window LP lost its DPP structure"

    def solve(self, pv, imp_cap, soc0, budget, solver: str) -> dict:
        self.pv_avail.value = pv
        self.imp_cap.value = imp_cap
        self.soc_init.value = soc0
        self.gen_budget.value = budget
        self.problem.solve(solver=solver, warm_start=True)
        if self.problem.status not in ("optimal", "optimal_inaccurate"):
            raise RuntimeError(f"window LP failed: {self.problem.status}")
        return {k: np.asarray(v.value, dtype=float) for k, v in self.vars.items()}


def storage_terminal_value(scenario: Scenario, curve, compute_price: float) -> float:
    """What one stored MWh is worth, in dollars, at the horizon edge.

    One MWh in the battery becomes ``eta_d`` MWh at the bus; the bus supports
    ``1/overhead_mult`` MWh of IT load once fixed cooling is paid for; and IT
    energy converts to compute at the curve's best compute-per-power ratio,
    which is an upper bound and deliberately so.
    """
    hull = curve.concave_hull()
    x = np.asarray(hull.power_fraction, dtype=float)
    y = np.asarray(hull.compute_fraction, dtype=float)
    best = float(np.max(np.where(x > 0, y / np.where(x > 0, x, 1.0), 0.0)))
    it_max = scenario.gpus.it_nameplate_mw
    overhead_mult = scenario.facility.variable_multiplier()
    return compute_price * scenario.storage.discharge_efficiency * best / (it_max * overhead_mult)


def simulate(
    scenario: Scenario,
    design: Design,
    curve,
    pv_actual_mw: np.ndarray,
    forecast,
    *,
    flexibility: Flexibility,
    compute_price: float,
    planned_compute_fraction: float,
    planned_coincident_peak_mw: float,
    coincident_peak_mask: np.ndarray,
    horizon_hours: int = 48,
    soc_start_mwh: float | None = None,
    label: str = "",
    solver: str = "HIGHS",
) -> OperationResult:
    """Run one weather year hour by hour under a receding-horizon controller."""
    pv_actual = np.asarray(pv_actual_mw, dtype=float)
    T = pv_actual.size
    st = scenario.storage
    it_max = scenario.gpus.it_nameplate_mw
    overhead_mult = scenario.facility.variable_multiplier()

    storage_value = storage_terminal_value(scenario, curve, compute_price)
    gen_budget_total = scenario.limits.gen_annual_full_load_hours * design.gen_mw

    compiled = _WindowLP(
        scenario, design, curve, flexibility, horizon_hours, compute_price, storage_value
    )

    # Import ceiling: nameplate interconnection, except inside the coincident-peak
    # risk window where the operator defends the peak the planner assumed.
    imp_cap_year = np.full(T, design.grid_mw, dtype=float)
    imp_cap_year[coincident_peak_mask] = min(design.grid_mw, planned_coincident_peak_mw)

    # Open where the planner opened. The planning LP's state of charge is
    # cyclic — the year hands the next year the state it was given — so starting
    # the operator empty would charge it for a first winter the design never
    # assumed. One scalar of plan, not hourly foresight.
    soc = (st.soc_min_fraction * design.bess_mwh
           if soc_start_mwh is None else float(soc_start_mwh))
    soc = min(max(soc, st.soc_min_fraction * design.bess_mwh), design.bess_mwh)
    gen_remaining = gen_budget_total
    rec = {k: np.zeros(T) for k in
           ("pv_use", "charge", "discharge", "soc", "imports", "gen_out", "p_it", "compute", "unserved")}

    for t in range(T):
        hours_left = T - t
        H = min(horizon_hours, hours_left)
        pv_belief = np.asarray(forecast.horizon(t, H), dtype=float)
        pv_belief = np.clip(pv_belief, 0.0, None)

        ration = gen_remaining * min(1.0, (H / hours_left) * GEN_RATION_SLACK)

        if H == horizon_hours:
            sol = compiled.solve(pv_belief, imp_cap_year[t:t + H], soc, ration, solver)
        else:
            # Year-end tail: too few hours left for the compiled horizon. Rebuilt
            # per hour rather than zero-padded, because padding invents a
            # week-long December night and makes the controller hoard.
            tail = _WindowLP(scenario, design, curve, flexibility, H, compute_price, storage_value)
            sol = tail.solve(pv_belief, imp_cap_year[t:t + H], soc, ration, solver)

        for key in rec:
            if key == "soc":
                continue
            rec[key][t] = sol[key][0]
        # Hour 0 is committed under an exact forecast (lead-zero error is zero),
        # so the plan's first step is physically realisable as-is.
        soc = float(sol["soc"][1])
        rec["soc"][t] = soc
        gen_remaining = max(0.0, gen_remaining - rec["gen_out"][t])

    compute_hours = float(rec["compute"].sum())
    pv_curtailed = pv_actual.sum() - rec["pv_use"].sum()

    # Net value is the quantity all three rungs are actually competing on:
    # what the compute produced is worth at the planner's own shadow price,
    # less what it cost to run the plant. Capacity is sunk and identical across
    # rungs, so it cancels — which is what makes the comparison clean. The
    # annual LP maximises this by construction, so annual >= perfect >= noisy,
    # and the two gaps are the price of a finite horizon and of forecast error.
    c = scenario.costs
    fuel_rate = c.gen_heat_rate_mmbtu_per_mwh * c.gas_price_per_mmbtu + c.gen_vom_per_mwh
    import_cost = float(rec["imports"].sum()) * c.energy_price_per_mwh
    fuel_cost = float(rec["gen_out"].sum()) * fuel_rate
    variable_cost = import_cost + fuel_cost

    return OperationResult(
        label=label,
        flexibility=flexibility,
        forecast_name=getattr(forecast, "name", "unknown"),
        horizon_hours=horizon_hours,
        compute_unit_hours=compute_hours,
        compute_fraction=compute_hours / T,
        planned_compute_fraction=planned_compute_fraction,
        unserved_mwh=float(rec["unserved"].sum()),
        unserved_hours=int((rec["unserved"] > 1e-6).sum()),
        import_cost=import_cost,
        fuel_cost=fuel_cost,
        variable_cost=variable_cost,
        net_value=compute_price * compute_hours - variable_cost,
        gen_energy_mwh=float(rec["gen_out"].sum()),
        gen_budget_mwh=gen_budget_total,
        import_energy_mwh=float(rec["imports"].sum()),
        peak_import_mw=float(rec["imports"].max()),
        coincident_peak_mw=float(rec["imports"][coincident_peak_mask].max())
            if coincident_peak_mask.any() else 0.0,
        pv_curtailed_fraction=float(pv_curtailed / pv_actual.sum()) if pv_actual.sum() > 0 else 0.0,
        mean_it_power_fraction=float(rec["p_it"].mean() / it_max),
        series=rec,
    )
