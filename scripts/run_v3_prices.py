"""V3: what a real price series does to the flexibility crossover.

V1 and V2 priced grid energy at a flat $45/MWh. That is not a rounding error in
an input, it is a deleted correlation: a flat price cannot say that abundant
solar and cheap energy are the same hours, nor that the hours a data center most
wants to import are the hours the grid charges most for them (README landmine 6).

The experiment separates *level* from *shape*, because swapping a placeholder
for a real series changes both at once and the two have nothing to do with each
other:

* ``flat_placeholder`` -- $45/MWh, exactly what V2 ran on.
* ``flat_actual_mean`` -- the real annual mean of the chosen year, flat. Level
  corrected, shape still absent.
* ``hourly`` -- the real series.

The difference between the first two is a mistake about the price of energy.
The difference between the last two is the whole content of landmine 6, and it
is the only one of the three that tells us whether the correlation matters.
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

from tecopt import Scenario, optimise, prices
from tecopt.site import DALLAS, coincident_peak_window, gpu_curve, pv_capacity_factor, weather_frame

YEAR = 2019
SETTLEMENT_POINT = "LZ_NORTH"          # Dallas load zone; the weather is Dallas
GRID_CEILINGS = [125.0, 110.0, 95.0, 80.0, 60.0, 30.0]
RUNS = [("rigid", 1.00), ("powercap", 0.98)]
WORKERS = 6

RESULTS = Path(__file__).resolve().parents[1] / "results" / "v3_prices.json"


def _solve(job):
    ceiling, mode, target, basis, price = job
    base = Scenario()
    lat, lon = DALLAS
    curve = gpu_curve(base.gpus.curve_name)
    cf = pv_capacity_factor(lat, lon, YEAR)
    cp_mask = coincident_peak_window(weather_frame(lat, lon, YEAR).index)
    scenario = replace(base, limits=replace(base.limits, max_grid_mw=ceiling))

    t0 = time.perf_counter()
    r = optimise(
        scenario, cf, curve,
        flexibility=mode,
        compute_target_fraction=target,
        coincident_peak_mask=cp_mask,
        energy_price_per_mwh=price,
    )
    infra = r.annual_cost - r.cost_breakdown["gpu_capital"]
    return {
        "grid_ceiling_mw": ceiling,
        "price_basis": basis,
        "mode": mode,
        "compute_target": target,
        "lcoc": r.lcoc_per_gpu_hour,
        "infra_per_year": infra,
        "pv_mw": r.design.pv_mw,
        "bess_mw": r.design.bess_mw,
        "bess_mwh": r.design.bess_mwh,
        "gen_mw": r.design.gen_mw,
        "grid_mw": r.design.grid_mw,
        "energy_cost": r.cost_breakdown["grid_energy"],
        "fuel_cost": r.cost_breakdown["fuel"],
        "coincident_peak_mw": r.coincident_peak_mw,
        "imports_mwh": float(r.dispatch["import_mw"].sum()),
        "mean_it_power_fraction": r.mean_it_power_fraction,
        "pv_curtailed_fraction": r.pv_curtailed_fraction,
        "solve_seconds": time.perf_counter() - t0,
    }


def main() -> None:
    hourly = prices.energy_price_series(YEAR, SETTLEMENT_POINT)
    bases = {
        "flat_placeholder": float(Scenario().costs.energy_price_per_mwh),
        "flat_actual_mean": float(hourly.mean()),
        "hourly": hourly,
    }

    jobs = [
        (ceiling, mode, target, basis, price)
        for basis, price in bases.items()
        for ceiling in GRID_CEILINGS
        for mode, target in RUNS
    ]
    print(f"{len(jobs)} solves on {WORKERS} workers", flush=True)

    rows = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for row in pool.map(_solve, jobs):
            rows.append(row)
            print(
                f"  {row['price_basis']:<17} {row['grid_ceiling_mw']:>6.0f} MW "
                f"{row['mode']:<9} lcoc={row['lcoc']:.4f} infra=${row['infra_per_year']/1e6:6.1f}M "
                f"({row['solve_seconds']:.0f}s)",
                flush=True,
            )
    print(f"total {time.perf_counter() - t0:.0f}s")

    payload = {
        "year": YEAR,
        "settlement_point": SETTLEMENT_POINT,
        "price_provenance": prices.fetch_year(YEAR).provenance,
        "price_stats": {
            "mean_per_mwh": float(hourly.mean()),
            "median_per_mwh": float(np.median(hourly)),
            "max_per_mwh": float(hourly.max()),
            "min_per_mwh": float(hourly.min()),
            "negative_hours": int((hourly < 0).sum()),
            "hours_over_100": int((hourly > 100).sum()),
        },
        "runs": rows,
    }
    RESULTS.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
