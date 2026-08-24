"""V4: what survives when the controller stops being clairvoyant.

For each design, three rungs against the same weather year:

  annual   the planning LP's own answer (perfect foresight, whole year)
  perfect  receding 48 h horizon, exact forecast  -> cost of a finite horizon
  noisy    receding 48 h horizon, forecast calibrated to 10% realised
           day-ahead nRMSE                        -> cost of forecast error

The designs are the ones the earlier sweeps made decision-relevant: the rigid
reference and the LCOC optimum at a 60 MW interconnection, plus the fully
islanded case, where foresight should matter most because there is no grid to
absorb a mistake.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, optimise
from tecopt import operate
from tecopt.site import DALLAS, coincident_peak_window, gpu_curve, pv_capacity_factor, weather_frame

YEAR = 2019
HORIZON_HOURS = 48
NRMSE_PCT = 10.0          # project 1's REFERENCE_NRMSE_24H_PCT

CASES = [
    ("60 MW grid, rigid @100%", 60.0, "rigid", 1.00),
    ("60 MW grid, powercap @98%", 60.0, "powercap", 0.98),
    ("islanded, powercap @96%", 0.0, "powercap", 0.96),
]


def main() -> None:
    from flexcompute import forecast as fc   # project 1's error model

    lat, lon = DALLAS
    base = Scenario()
    curve = gpu_curve(base.gpus.curve_name)
    cf = pv_capacity_factor(lat, lon, YEAR)
    mask = coincident_peak_window(weather_frame(lat, lon, YEAR).index)

    out = []
    for label, ceiling, mode, target in CASES:
        sc = replace(base, limits=replace(base.limits, max_grid_mw=ceiling))
        print(f"\n=== {label} ===", flush=True)

        t0 = time.perf_counter()
        plan = optimise(sc, cf, curve, flexibility=mode,
                        compute_target_fraction=target, coincident_peak_mask=mask)
        d = plan.design
        print(f"  plan: PV {d.pv_mw:6.1f} | BESS {d.bess_mw:6.1f}MW/{d.bess_mwh:7.1f}MWh | "
              f"grid {d.grid_mw:5.1f} | gen {d.gen_mw:6.1f}MW   [{time.perf_counter()-t0:.0f}s]", flush=True)
        # Sunk capacity: an unproduced compute-unit-hour costs the GPU capital
        # that was paid for regardless. Uniform across designs, so net value is
        # comparable between them. The planner's shadow price is reported only
        # as a diagnostic — it is a planning quantity and is degenerately zero
        # for the rigid design, where compute is not a decision.
        compute_price = plan.cost_breakdown["gpu_capital"] / cf.size
        print(f"  compute priced at ${compute_price:,.0f}/unit-hour (stranded GPU capital); "
              f"planner shadow price ${plan.compute_shadow_price:,.0f}", flush=True)

        pv_plant = cf * d.pv_mw
        forecasts = [
            ("perfect", fc.PerfectSolarForecast(pv_plant)),
            ("noisy", fc.forecast_at_realised_nrmse(pv_plant, NRMSE_PCT)),
        ]

        row = {
            "label": label, "grid_ceiling_mw": ceiling, "mode": mode, "target": target,
            "design": {"pv_mw": d.pv_mw, "bess_mw": d.bess_mw, "bess_mwh": d.bess_mwh,
                       "grid_mw": d.grid_mw, "gen_mw": d.gen_mw},
            "shadow_price": plan.compute_shadow_price,
            "compute_price": compute_price,
            "annual": {"compute_fraction": plan.compute_unit_hours / cf.size,
                       "gen_energy_mwh": float(plan.dispatch["gen_mw"].sum()),
                       "coincident_peak_mw": plan.coincident_peak_mw,
                       "variable_cost": plan.variable_cost,
                       "net_value": compute_price * plan.compute_unit_hours - plan.variable_cost},
            "runs": [],
        }

        for name, forecaster in forecasts:
            t0 = time.perf_counter()
            r = operate.simulate(
                sc, d, curve, pv_plant, forecaster,
                flexibility=mode,
                compute_price=compute_price,
                planned_compute_fraction=plan.compute_unit_hours / cf.size,
                planned_coincident_peak_mw=plan.coincident_peak_mw,
                coincident_peak_mask=mask,
                horizon_hours=HORIZON_HOURS,
                label=f"{label} / {name}",
            )
            secs = time.perf_counter() - t0
            nrmse = (forecaster.realised_nrmse_24h_pct()
                     if hasattr(forecaster, "realised_nrmse_24h_pct") else 0.0)
            plan_net = compute_price * plan.compute_unit_hours - plan.variable_cost
            lost = (plan_net - r.net_value) / plan_net * 100 if plan_net else float("nan")
            print(f"  {name:8s} compute {r.compute_fraction:7.3%} | "
                  f"varcost ${r.variable_cost/1e6:6.1f}M | "
                  f"net value ${r.net_value/1e6:8.1f}M ({lost:+.3f}% vs annual LP) | "
                  f"unserved {r.unserved_mwh:7.1f} MWh/{r.unserved_hours:3d}h | "
                  f"gen {r.gen_energy_mwh:7.0f}/{r.gen_budget_mwh:.0f} MWh | "
                  f"4CP {r.coincident_peak_mw:5.1f} MW  [{secs:.0f}s]", flush=True)
            row["runs"].append({
                "forecast": name, "realised_nrmse_pct": nrmse,
                "compute_fraction": r.compute_fraction,
                "shortfall_pp": r.compute_shortfall_pct,
                "unserved_mwh": r.unserved_mwh, "unserved_hours": r.unserved_hours,
                "gen_energy_mwh": r.gen_energy_mwh, "gen_budget_mwh": r.gen_budget_mwh,
                "variable_cost": r.variable_cost, "net_value": r.net_value,
                "net_value_loss_pct": lost,
                "coincident_peak_mw": r.coincident_peak_mw,
                "mean_it_power_fraction": r.mean_it_power_fraction,
                "pv_curtailed_fraction": r.pv_curtailed_fraction,
                "seconds": secs,
            })
        out.append(row)

    path = Path(__file__).resolve().parents[1] / "results" / "foresight.json"
    path.write_text(json.dumps(out, indent=2) + "\n")

    print("\n" + "=" * 100)
    print("Net value lost against the annual LP, decomposed. Capacity is sunk and")
    print("identical across rungs, so it cancels and only operation is compared.\n")
    print(f"{'design':28s} {'planned':>8s} {'perfect':>8s} {'noisy':>8s} | "
          f"{'horizon':>8s} {'forecast':>9s} {'total':>8s}")
    for row in out:
        pf, nz = row["runs"][0], row["runs"][1]
        ann = row["annual"]["net_value"]
        h_loss = (ann - pf["net_value"]) / ann * 100
        f_loss = (pf["net_value"] - nz["net_value"]) / ann * 100
        print(f"{row['label']:28s} {row['annual']['compute_fraction']:7.2%} "
              f"{pf['compute_fraction']:7.2%} {nz['compute_fraction']:7.2%} | "
              f"{h_loss:7.3f}% {f_loss:8.3f}% {h_loss+f_loss:7.3f}%")
    print("=" * 100)
    print("compute columns: annual LP plan vs what each controller delivered")
    print("loss columns: net value forgone, as a % of the annual LP's. Positive = worse.")
    print("  horizon  = cost of a 48 h horizon, forecast exact")
    print("  forecast = additional cost of 10% realised day-ahead nRMSE")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
