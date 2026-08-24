"""V5: how much of flexibility's value survives a deadline.

Every number V2 and V3 report about compute flexibility rests on an assumption
stated nowhere in them: that annual compute is one fungible pool, so a
megawatt-hour of work given up in August can be made good in November. That is
the most flexible workload that can exist, which makes every earlier result an
*upper bound* on the value of flexibility (README landmine 12).

This puts deadlines on the work and measures how much of the bound is real.

Two sweeps, at the interconnection where V2 and V3 agree flexibility pays:

**A. Deadline tightness.** All work is deadline-bound, and the delivery window
shrinks from a year to six hours. The annual window is V1's pool exactly, so the
sweep starts from the old assumption and walks away from it.

**B. Inference share.** Part of the fleet serves an arrival profile it cannot
defer at all, peaking at 19:00 local -- inside ERCOT's coincident-peak window.
The rest stays weekly-deadline training.

The rigid design is solved once, not once per mix: a plant that never throttles
has no scheduling problem, so workload structure cannot reach it. That the
optimiser agrees is worth checking rather than assuming, and the script checks
it.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, optimise, prices, workload
from tecopt.inputs import Limits
from tecopt.site import DALLAS, coincident_peak_window, gpu_curve, pv_capacity_factor, weather_frame

YEAR = 2019
SETTLEMENT_POINT = "LZ_NORTH"
GRID_CEILING = 60.0
COMPUTE_TARGET = 0.98
WORKERS = 5

DEADLINE_WINDOWS = [8760, 730, 168, 24, 6]
DEADLINE_SHARES = [0.50, 0.75, 0.90]
INFERENCE_SHARES = [0.30, 0.60]

RESULTS = Path(__file__).resolve().parents[1] / "results" / "v5_workload.json"


def _context():
    base = replace(Scenario(), limits=Limits(max_grid_mw=GRID_CEILING))
    lat, lon = DALLAS
    index = weather_frame(lat, lon, YEAR).index
    return {
        "scenario": base,
        "cf": pv_capacity_factor(lat, lon, YEAR),
        "curve": gpu_curve(base.gpus.curve_name),
        "coincident_peak_mask": coincident_peak_window(index),
        "local_hour": np.asarray(index.hour),
        "energy_price_per_mwh": prices.energy_price_series(YEAR, SETTLEMENT_POINT),
    }


def _solve(job):
    label, mode, target, mix = job
    ctx = _context()
    scenario = ctx.pop("scenario")
    cf, curve = ctx.pop("cf"), ctx.pop("curve")

    t0 = time.perf_counter()
    r = optimise(
        scenario, cf, curve,
        flexibility=mode,
        compute_target_fraction=target,
        workload=mix,
        **ctx,
    )
    infra = r.annual_cost - r.cost_breakdown["gpu_capital"]
    return {
        "label": label,
        "mode": mode,
        "compute_target": target,
        "lcoc": r.lcoc_per_gpu_hour,
        "infra_per_year": infra,
        "pv_mw": r.design.pv_mw,
        "bess_mw": r.design.bess_mw,
        "bess_mwh": r.design.bess_mwh,
        "gen_mw": r.design.gen_mw,
        "coincident_peak_mw": r.coincident_peak_mw,
        "mean_it_power_fraction": r.mean_it_power_fraction,
        "workload": r.workload,
        "solve_seconds": time.perf_counter() - t0,
    }


def main() -> None:
    jobs: list = [
        ("rigid (no workload structure)", "rigid", 1.00, None),
        ("pool -- V1 through V4", "powercap", COMPUTE_TARGET, None),
    ]
    # Sweep A: all work deadline-bound, window shrinking. One class, so these
    # are cheap, and they bracket the effect at its strongest.
    for window in DEADLINE_WINDOWS:
        jobs.append(
            (f"100% deadline, {window}h window", "powercap", COMPUTE_TARGET,
             workload.default_mix(inference_share=0.0, deadline_share=1.0,
                                  window_hours=window))
        )
    # Sweep B: how much of the work has to be deadline-bound before it bites?
    # The rest is batch, so these are two classes.
    for share in DEADLINE_SHARES:
        jobs.append(
            (f"{share:.0%} deadline (weekly) + batch", "powercap", COMPUTE_TARGET,
             workload.default_mix(inference_share=0.0, deadline_share=share,
                                  window_hours=168))
        )
    # Sweep C: non-deferrable inference against fully flexible batch.
    for share in INFERENCE_SHARES:
        jobs.append(
            (f"{share:.0%} inference + batch", "powercap", COMPUTE_TARGET,
             workload.default_mix(inference_share=share, deadline_share=0.0,
                                  window_hours=168))
        )
    # One three-class reference point, and the rigid control that shows workload
    # structure cannot reach a plant that never throttles.
    jobs.append(("30% inference + 50% weekly + 20% batch", "powercap", COMPUTE_TARGET,
                 workload.default_mix(0.30, 0.50, 168)))
    jobs.append(("rigid (3-class mix)", "rigid", 1.00,
                 workload.default_mix(0.30, 0.50, 168)))

    print(f"{len(jobs)} solves on {WORKERS} workers", flush=True)
    rows = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for row in pool.map(_solve, jobs):
            rows.append(row)
            print(
                f"  {row['label']:<34} lcoc={row['lcoc']:.4f} "
                f"infra=${row['infra_per_year'] / 1e6:6.1f}M "
                f"pv={row['pv_mw']:6.1f} gen={row['gen_mw']:6.1f} "
                f"({row['solve_seconds']:.0f}s)",
                flush=True,
            )
    print(f"total {time.perf_counter() - t0:.0f}s")

    RESULTS.write_text(json.dumps({
        "year": YEAR,
        "settlement_point": SETTLEMENT_POINT,
        "grid_ceiling_mw": GRID_CEILING,
        "compute_target": COMPUTE_TARGET,
        "inference_peak_hour_local": workload.PEAK_HOUR_LOCAL,
        "inference_peak_to_trough": workload.PEAK_TO_TROUGH,
        "runs": rows,
    }, indent=1) + "\n")
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
