"""V6: is the answer a finding, or a fact about 2019?

Every rung so far ran on one weather year at one site. V3 showed that is not a
detail: the relationship between solar output and price *inverted* between 2020
and 2023, so a single year is a sample from a non-stationary process and the
2019 the study happens to use sits on the far side of the inversion.

This sweeps what varies:

* **fourteen years**, 2011-2024 -- the overlap of project 1's weather record and
  ERCOT's nodal price record, which begins on 1 December 2010 (landmine 13).
* **two sites**, each with the settlement point a load there would actually
  settle at. Dallas/``LZ_NORTH`` is project 1's site. Midland-Odessa/``LZ_WEST``
  is where ERCOT's solar actually went, so it has both the better resource and
  the worse capture price.
* **two interconnections**, on either side of V2's crossover: 125 MW, which is
  full facility load, and 60 MW, which is scarce.
* **two compute regimes**, rigid and the measured power cap at 98%.

The output is not a number. It is a distribution, and the question asked of it
is whether the *sign* of the flexibility trade is stable -- because a conclusion
that flips with the weather year is not a conclusion, it is a coin.
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
from tecopt.inputs import Limits
from tecopt.site import (
    SITES, coincident_peak_window, gpu_curve, pv_capacity_factor, site_coords, weather_frame,
)

YEARS = list(range(2011, 2025))
SITE_NAMES = ["dallas", "west_texas"]
GRID_CEILINGS = [125.0, 60.0]
RUNS = [("rigid", 1.00), ("powercap", 0.98)]
WORKERS = 5

RESULTS = Path(__file__).resolve().parents[1] / "results" / "v6_sweep.json"


def _solve(job):
    site_name, year, ceiling, mode, target = job
    lat, lon = site_coords(site_name)
    point = SITES[site_name]["settlement_point"]

    base = Scenario()
    scenario = replace(base, limits=replace(base.limits, max_grid_mw=ceiling))
    curve = gpu_curve(base.gpus.curve_name)
    cf = pv_capacity_factor(lat, lon, year)
    index = weather_frame(lat, lon, year).index

    t0 = time.perf_counter()
    try:
        r = optimise(
            scenario, cf, curve,
            flexibility=mode,
            compute_target_fraction=target,
            coincident_peak_mask=coincident_peak_window(index),
            energy_price_per_mwh=prices.energy_price_series(year, point),
        )
    except Exception as exc:  # keep one bad cell from losing the sweep
        return {
            "site": site_name, "year": year, "grid_ceiling_mw": ceiling,
            "mode": mode, "compute_target": target,
            "error": f"{type(exc).__name__}: {exc}",
            "solve_seconds": time.perf_counter() - t0,
        }

    return {
        "site": site_name,
        "settlement_point": point,
        "year": year,
        "grid_ceiling_mw": ceiling,
        "mode": mode,
        "compute_target": target,
        "lcoc": r.lcoc_per_gpu_hour,
        "infra_per_year": r.annual_cost - r.cost_breakdown["gpu_capital"],
        "pv_mw": r.design.pv_mw,
        "bess_mw": r.design.bess_mw,
        "bess_mwh": r.design.bess_mwh,
        "gen_mw": r.design.gen_mw,
        "grid_mw": r.design.grid_mw,
        "energy_cost": r.cost_breakdown["grid_energy"],
        "fuel_cost": r.cost_breakdown["fuel"],
        "coincident_peak_mw": r.coincident_peak_mw,
        "pv_curtailed_fraction": r.pv_curtailed_fraction,
        "mean_it_power_fraction": r.mean_it_power_fraction,
        "mean_price_per_mwh": r.price_basis["mean_per_mwh"],
        "solve_seconds": time.perf_counter() - t0,
    }


def main() -> None:
    jobs = [
        (site, year, ceiling, mode, target)
        for site in SITE_NAMES
        for year in YEARS
        for ceiling in GRID_CEILINGS
        for mode, target in RUNS
    ]
    print(f"{len(jobs)} solves on {WORKERS} workers", flush=True)

    rows, done = [], 0
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for row in pool.map(_solve, jobs):
            rows.append(row)
            done += 1
            tag = row.get("error", f"lcoc={row.get('lcoc', float('nan')):.4f}")
            print(
                f"  [{done:>3}/{len(jobs)}] {row['site']:<11} {row['year']} "
                f"{row['grid_ceiling_mw']:>5.0f}MW {row['mode']:<9} {tag} "
                f"({row['solve_seconds']:.0f}s)",
                flush=True,
            )
    print(f"total {time.perf_counter() - t0:.0f}s")

    RESULTS.write_text(json.dumps({
        "years": YEARS,
        "sites": {name: SITES[name] for name in SITE_NAMES},
        "grid_ceilings_mw": GRID_CEILINGS,
        "runs": rows,
    }, indent=1) + "\n")
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
