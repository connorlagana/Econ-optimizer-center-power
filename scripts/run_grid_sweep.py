"""The experiment the V1 run implies: when does flexibility start paying?

The unconstrained-grid run answers "never" — infrastructure is a rounding error
next to GPU capital, so giving up compute to save it is a bad trade. But an
unconstrained 125 MW interconnection is not a thing a 2026 project can buy; it
is a queue position with a multi-year date on it.

So sweep the constraint. For each ceiling on interconnection size, size the
system twice — once with rigid compute, once with the measured power cap — and
watch where the two diverge. The crossover is the answer to "when is compute
flexibility worth it", and it is a statement about *scarcity of grid capacity*,
not about energy.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, optimise
from tecopt.site import DALLAS, coincident_peak_window, gpu_curve, pv_capacity_factor, weather_frame

YEAR = 2019
GRID_CEILINGS = [125.0, 60.0, 30.0, 10.0, 0.0]
RUNS = [("rigid", 1.00), ("powercap", 0.96)]


def main() -> None:
    lat, lon = DALLAS
    base = Scenario()
    curve = gpu_curve(base.gpus.curve_name)
    cf = pv_capacity_factor(lat, lon, YEAR)
    cp_mask = coincident_peak_window(weather_frame(lat, lon, YEAR).index)

    rows = []
    for ceiling in GRID_CEILINGS:
        scenario = replace(base, limits=replace(base.limits, max_grid_mw=ceiling))
        for mode, target in RUNS:
            t0 = time.perf_counter()
            try:
                r = optimise(
                    scenario, cf, curve,
                    flexibility=mode,
                    compute_target_fraction=target,
                    coincident_peak_mask=cp_mask,
                )
            except RuntimeError as exc:
                print(f"grid<={ceiling:5.0f} {mode:9s}: {exc}")
                rows.append({"grid_ceiling_mw": ceiling, "mode": mode, "status": "infeasible"})
                continue
            infra = r.annual_cost - r.cost_breakdown["gpu_capital"]
            rows.append({
                "grid_ceiling_mw": ceiling, "mode": mode, "target": target,
                "status": r.status,
                "pv_mw": r.design.pv_mw, "bess_mw": r.design.bess_mw,
                "bess_mwh": r.design.bess_mwh, "grid_mw": r.design.grid_mw,
                "gen_mw": r.design.gen_mw, "gen_run_hours": r.gen_run_hours,
                "infra_cost": infra, "annual_cost": r.annual_cost,
                "compute_fraction": r.compute_unit_hours / cf.size,
                "lcoc": r.lcoc_per_gpu_hour,
                "pv_curtailed_fraction": r.pv_curtailed_fraction,
                "seconds": time.perf_counter() - t0,
            })
            d = r.design
            print(f"grid<={ceiling:5.0f} {mode:9s} -> PV {d.pv_mw:6.1f} | BESS {d.bess_mw:6.1f}MW/{d.bess_mwh:7.1f}MWh"
                  f" | grid {d.grid_mw:6.1f} | gen {d.gen_mw:5.1f}MW ({r.gen_run_hours:.0f}h)"
                  f" | infra ${infra/1e6:6.1f}M | LCOC ${r.lcoc_per_gpu_hour:.4f}"
                  f"  [{time.perf_counter()-t0:.0f}s]", flush=True)

    out = Path(__file__).resolve().parents[1] / "results" / "grid_sweep.json"
    out.write_text(json.dumps(rows, indent=2) + "\n")

    print("\n" + "=" * 92)
    print(f"{'grid cap':>9s} {'rigid infra':>12s} {'flex infra':>12s} {'infra delta':>12s} "
          f"{'rigid LCOC':>11s} {'flex LCOC':>11s} {'LCOC delta':>11s}")
    by_ceiling: dict[float, dict[str, dict]] = {}
    for row in rows:
        if row.get("status") == "infeasible":
            continue
        by_ceiling.setdefault(row["grid_ceiling_mw"], {})[row["mode"]] = row
    for ceiling, pair in sorted(by_ceiling.items(), reverse=True):
        if len(pair) < 2:
            continue
        rg, fx = pair["rigid"], pair["powercap"]
        print(f"{ceiling:8.0f}M {rg['infra_cost']/1e6:11.1f}M {fx['infra_cost']/1e6:11.1f}M "
              f"{(fx['infra_cost']/rg['infra_cost']-1)*100:11.1f}% "
              f"{rg['lcoc']:11.4f} {fx['lcoc']:11.4f} "
              f"{(fx['lcoc']/rg['lcoc']-1)*100:10.2f}%")
    print("=" * 92)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
