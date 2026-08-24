"""Where flexibility starts paying, and how much of it to buy.

Two questions the first sweep raised but could not answer.

**Where is the crossover?** Flexibility loses at an unconstrained 125 MW
interconnection and wins at 60 MW. The sign change is the headline result, so
it needs a location, not a bracket.

**How much flexibility?** The sweep fixed the compute target at 96% by
assertion. The right answer is whatever minimises levelised cost, which means
sweeping the target and reading the minimum off the frontier — the same sweep
that produces the cost-vs-compute Pareto curve.
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
CROSSOVER_CEILINGS = [110.0, 95.0, 80.0]
FRONTIER_CEILING = 60.0
FRONTIER_TARGETS = [1.00, 0.99, 0.98, 0.97, 0.96, 0.94, 0.92, 0.90]


def run(scenario, cf, curve, mask, mode, target):
    t0 = time.perf_counter()
    r = optimise(scenario, cf, curve, flexibility=mode,
                 compute_target_fraction=target, coincident_peak_mask=mask)
    infra = r.annual_cost - r.cost_breakdown["gpu_capital"]
    return r, infra, time.perf_counter() - t0


def main() -> None:
    lat, lon = DALLAS
    base = Scenario()
    curve = gpu_curve(base.gpus.curve_name)
    cf = pv_capacity_factor(lat, lon, YEAR)
    mask = coincident_peak_window(weather_frame(lat, lon, YEAR).index)
    out = {"crossover": [], "frontier": []}

    print("--- crossover: rigid @100% vs powercap @96% ---", flush=True)
    for ceiling in CROSSOVER_CEILINGS:
        sc = replace(base, limits=replace(base.limits, max_grid_mw=ceiling))
        pair = {}
        for mode, target in (("rigid", 1.00), ("powercap", 0.96)):
            r, infra, secs = run(sc, cf, curve, mask, mode, target)
            pair[mode] = {"infra": infra, "lcoc": r.lcoc_per_gpu_hour,
                          "bess_mwh": r.design.bess_mwh, "gen_mw": r.design.gen_mw,
                          "pv_mw": r.design.pv_mw}
            print(f"  grid<={ceiling:5.0f} {mode:9s} infra ${infra/1e6:6.1f}M  "
                  f"LCOC ${r.lcoc_per_gpu_hour:.4f}  BESS {r.design.bess_mwh:7.1f}MWh  "
                  f"gen {r.design.gen_mw:6.1f}MW  [{secs:.0f}s]", flush=True)
        delta = (pair["powercap"]["lcoc"] / pair["rigid"]["lcoc"] - 1) * 100
        print(f"  grid<={ceiling:5.0f} LCOC delta {delta:+.2f}%\n", flush=True)
        out["crossover"].append({"grid_ceiling_mw": ceiling, "lcoc_delta_pct": delta, **pair})

    print(f"--- frontier at grid <= {FRONTIER_CEILING:.0f} MW ---", flush=True)
    sc = replace(base, limits=replace(base.limits, max_grid_mw=FRONTIER_CEILING))
    for target in FRONTIER_TARGETS:
        mode = "rigid" if target == 1.00 else "powercap"
        r, infra, secs = run(sc, cf, curve, mask, mode, target)
        d = r.design
        out["frontier"].append({
            "target": target, "mode": mode, "infra": infra, "lcoc": r.lcoc_per_gpu_hour,
            "pv_mw": d.pv_mw, "bess_mw": d.bess_mw, "bess_mwh": d.bess_mwh,
            "gen_mw": d.gen_mw, "gen_run_hours": r.gen_run_hours,
            "compute_fraction": r.compute_unit_hours / cf.size,
            "mean_it_power_fraction": r.mean_it_power_fraction,
        })
        print(f"  compute>={target:.0%} ({mode:8s}) PV {d.pv_mw:6.1f} BESS {d.bess_mwh:7.1f}MWh "
              f"gen {d.gen_mw:6.1f}MW  infra ${infra/1e6:6.1f}M  LCOC ${r.lcoc_per_gpu_hour:.4f}  "
              f"[{secs:.0f}s]", flush=True)

    best = min(out["frontier"], key=lambda r: r["lcoc"])
    print(f"\nLCOC-optimal compute target at {FRONTIER_CEILING:.0f} MW grid: "
          f"{best['target']:.0%}  (LCOC ${best['lcoc']:.4f})")

    path = Path(__file__).resolve().parents[1] / "results" / "crossover.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
