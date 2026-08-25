"""V7: precompute the result cube the web app reads.

The architecture argument is in ``docs/web-app-todo.md`` and it rests on two
measurements. A solve is tens of seconds and it is the *solver*, not the
canonicalisation, so there is no live-solve backend that is not a spinner. And
GPU capital enters the objective as a constant, so every GPU knob is free in
the browser. Together those say: solve the expensive axes offline, ship scalars,
do arithmetic in the client.

What is in the cube, and what is not
------------------------------------
**Solved axes.** site x year x interconnection x compute target x mode. These
change the argmin, so each combination is a solve.

**Free axes.** GPU capex, GPU life, GPU discount rate, kW per GPU. These touch
only the LCOC numerator and denominator after the fact:

    lcoc = infra/(compute_hours * gpu_count) + capex_per_gpu*crf/compute_hours

so the browser recomputes them from ``infra_per_year`` and
``compute_unit_hours`` with no solver in the loop. ``it_nameplate_mw`` is
**not** free, despite the todo listing it: scaling the fleet without scaling the
interconnection ceiling changes the physics, not just the arithmetic.

**Not axes at all.** Energy price basis, ITC, PUE, gas hour cap, export. They
multiply the cube and belong in separate published variants. This one is built
on real hourly ERCOT prices at each site's own settlement point, which is the
basis V3 and V6 established; the stamp in the output says so.

Resumability
------------
The full cube is hours of solving, so every cell is appended to a JSONL
checkpoint as it lands and a restart skips what is already there. Kill it and
re-run it; it picks up. ``--fresh`` starts over.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, optimise, prices
from tecopt.inputs import crf
from tecopt.site import (
    SITES, coincident_peak_window, gpu_curve, pv_capacity_factor, site_coords, weather_frame,
)

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "results" / "cube_cells.jsonl"
CUBE = ROOT / "web" / "public" / "cube.json"

SITE_NAMES = ["dallas", "west_texas"]

#: Four years rather than fourteen, which is option 1 in the todo's cost list.
#: They are not a random subset: 2016 is a low-price year, 2019 is the year
#: every earlier rung ran on, 2021 is Uri, and 2024 is after the capture-price
#: inversion V3 found. The full fourteen stay in ``results/v6_sweep.json`` for
#: the static distribution figure, which is where the year axis actually earns
#: its keep.
YEARS = [2016, 2019, 2021, 2024]

#: Dense either side of the crossover, which V2 put near 85 MW on a flat price
#: and V3 near 108 MW on real hourly prices. A sparse grid there would make the
#: headline figure interpolate across the sign change.
CEILINGS = [125.0, 115.0, 105.0, 95.0, 85.0, 75.0, 60.0, 45.0, 30.0, 15.0, 0.0]

#: Dense near 1.0, because the frontier's optimum is shallow and sits at ~98%.
#: Past ~0.90 the trade has long since reversed and the curve is only there to
#: show that it does.
TARGETS = [1.00, 0.99, 0.98, 0.97, 0.96, 0.94, 0.92, 0.90]

WORKERS = 7


# --------------------------------------------------------------------------
# per-worker caching: 88 cells share each (site, year), so weather, prices and
# the coincident-peak mask are built once per worker rather than once per solve.
# --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _context(site_name: str, year: int):
    lat, lon = site_coords(site_name)
    point = SITES[site_name]["settlement_point"]
    cf = pv_capacity_factor(lat, lon, year)
    mask = coincident_peak_window(weather_frame(lat, lon, year).index)
    price = prices.energy_price_series(year, point)
    return cf, mask, price, point


@lru_cache(maxsize=None)
def _curve(name: str):
    return gpu_curve(name)


def cell_key(job) -> str:
    site, year, ceiling, mode, target = job
    return f"{site}|{year}|{ceiling:.1f}|{mode}|{target:.4f}"


def _solve(job) -> dict:
    site_name, year, ceiling, mode, target = job
    base = Scenario()
    scenario = replace(base, limits=replace(base.limits, max_grid_mw=ceiling))
    cf, mask, price, point = _context(site_name, year)
    curve = _curve(base.gpus.curve_name)

    row = {
        "key": cell_key(job),
        "site": site_name,
        "settlement_point": point,
        "year": year,
        "grid_ceiling_mw": ceiling,
        "mode": mode,
        "compute_target": target,
    }

    t0 = time.perf_counter()
    try:
        r = optimise(
            scenario, cf, curve,
            flexibility=mode,
            compute_target_fraction=target,
            coincident_peak_mask=mask,
            energy_price_per_mwh=price,
        )
    except Exception as exc:      # one bad cell must not lose the sweep
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["solve_seconds"] = time.perf_counter() - t0
        return row

    row.update({
        "status": r.status,
        # Everything except GPU capital. The browser adds the GPU term back at
        # whatever capex the slider is on, which is the whole trick.
        "infra_per_year": r.annual_cost - r.cost_breakdown["gpu_capital"],
        "compute_unit_hours": r.compute_unit_hours,
        "lcoc_default_basis": r.lcoc_per_gpu_hour,
        "pv_mw": r.design.pv_mw,
        "bess_mw": r.design.bess_mw,
        "bess_mwh": r.design.bess_mwh,
        "gen_mw": r.design.gen_mw,
        "grid_mw": r.design.grid_mw,
        "cost_pv": r.cost_breakdown["pv"],
        "cost_bess": r.cost_breakdown["bess"],
        "cost_gen": r.cost_breakdown["generator"],
        "cost_grid_capacity": r.cost_breakdown["grid_capacity"],
        "cost_grid_energy": r.cost_breakdown["grid_energy"],
        "cost_fuel": r.cost_breakdown["fuel"],
        "coincident_peak_mw": r.coincident_peak_mw,
        "peak_import_mw": r.peak_import_mw,
        "gen_run_hours": r.gen_run_hours,
        "pv_curtailed_fraction": r.pv_curtailed_fraction,
        "mean_it_power_fraction": r.mean_it_power_fraction,
        "mean_price_per_mwh": r.price_basis["mean_per_mwh"],
        "negative_price_hours": r.price_basis["negative_hours"],
        "solve_seconds": time.perf_counter() - t0,
    })
    return row


def jobs_for_cube() -> list:
    jobs = []
    for site in SITE_NAMES:
        for year in YEARS:
            for ceiling in CEILINGS:
                # Rigid is compute-target-invariant by construction: the mode
                # pins compute at 100%, so a target axis would be 8 identical
                # solves. One cell per (site, year, ceiling).
                jobs.append((site, year, ceiling, "rigid", 1.00))
                for target in TARGETS:
                    jobs.append((site, year, ceiling, "powercap", target))
    return jobs


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return None


def _versions() -> dict:
    import cvxpy, numpy, pandas, scipy
    return {
        "python": platform.python_version(),
        "cvxpy": cvxpy.__version__,
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "solver": "HIGHS",
    }


def load_checkpoint() -> dict:
    if not CHECKPOINT.exists():
        return {}
    done = {}
    for line in CHECKPOINT.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:      # a torn final line from a hard kill
            continue
        done[row["key"]] = row
    return done


def write_cube(cells: dict) -> None:
    """Assemble the checkpoint into the single JSON the web app ships.

    The output declares how complete it is, and that is not bookkeeping. A
    half-built cube looks exactly like a finished one to a chart: missing cells
    read as absent data points, a line drawn through them invents a trend, and a
    sign change that has not been solved for yet is indistinguishable from one
    that does not exist. The page has to be able to tell those apart, so the
    cube tells it -- overall, and per (site, year), because that is the slice a
    reader is actually looking at.
    """
    base = Scenario()
    rows = [cells[k] for k in sorted(cells)]
    ok = [r for r in rows if "error" not in r]
    failed = [r for r in rows if "error" in r]

    expected = jobs_for_cube()
    expected_keys = {cell_key(j) for j in expected}
    solved_keys = {r["key"] for r in ok}

    # Per-slice completeness: the page renders one (site, year) at a time.
    slices: dict[str, dict] = {}
    for job in expected:
        site, year = job[0], job[1]
        name = f"{site}|{year}"
        entry = slices.setdefault(name, {"site": site, "year": year, "expected": 0, "solved": 0})
        entry["expected"] += 1
        if cell_key(job) in solved_keys:
            entry["solved"] += 1
    for entry in slices.values():
        entry["complete"] = entry["solved"] == entry["expected"]

    CUBE.parent.mkdir(parents=True, exist_ok=True)
    CUBE.write_text(json.dumps({
        "schema": 1,
        "provenance": {
            "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_sha": _git_sha(),
            "host": platform.node(),
            "versions": _versions(),
            "price_basis": "ERCOT DAM settlement-point prices, hourly, each site "
                           "at its own load zone (README V3). Not flat.",
            "allow_export": False,
            "cells": len(ok),
            "failed_cells": len(failed),
            "expected_cells": len(expected_keys),
            "complete": solved_keys >= expected_keys and not failed,
            "slices": slices,
        },
        # The whole cost basis, verbatim. A cube whose numbers cannot be traced
        # to the inputs that produced them is a screenshot machine.
        "scenario": base.as_dict(),
        # What the browser needs to redo the LCOC arithmetic itself.
        "free_axes": {
            "capex_per_gpu": base.gpus.capex_per_gpu,
            "kw_per_gpu": base.gpus.kw_per_gpu,
            "gpu_life_years": base.financing.gpu_life_years,
            "discount_rate": base.financing.discount_rate,
            "it_nameplate_mw": base.gpus.it_nameplate_mw,
            "gpu_crf_default": crf(base.financing.discount_rate, base.financing.gpu_life_years),
            "note": "lcoc = infra_per_year/(compute_unit_hours*gpu_count) "
                    "+ capex_per_gpu*crf(rate, life)/compute_unit_hours, where "
                    "gpu_count = it_nameplate_mw*1000/kw_per_gpu. it_nameplate_mw "
                    "is NOT free -- it changes the physics, not just the arithmetic.",
        },
        "axes": {
            "sites": {name: SITES[name] for name in SITE_NAMES},
            "years": YEARS,
            "grid_ceilings_mw": CEILINGS,
            "compute_targets": TARGETS,
            "modes": ["rigid", "powercap"],
        },
        "facility_load_mw": base.gpus.it_nameplate_mw * base.facility.variable_multiplier()
                            + base.facility.fixed_overhead_mw(base.gpus.it_nameplate_mw),
        "cells": ok,
        "errors": failed,
    }, separators=(",", ":")) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Solve every combination the web page needs, once, and save the answers "
            "to a file it can look them up in.\n\n"
            "A solve takes between ten seconds and three minutes, so the page cannot "
            "run one while somebody waits. Instead this solves them all ahead of time: "
            "two sites, four price years, eleven grid connection sizes and eight "
            "compute targets, which is 792 separate optimisations and about two and a "
            "half hours on seven cores.\n\n"
            "It is safe to interrupt. Each answer is written to "
            "results/cube_cells.jsonl the moment it lands, and re-running picks up "
            "where it stopped."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--fresh", action="store_true", help="ignore the checkpoint")
    ap.add_argument("--assemble-only", action="store_true",
                    help="write cube.json from the checkpoint without solving")
    args = ap.parse_args()

    if args.fresh and CHECKPOINT.exists():
        CHECKPOINT.unlink()

    done = load_checkpoint()
    if args.assemble_only:
        write_cube(done)
        print(f"assembled {len(done)} cells -> {CUBE}")
        return

    jobs = jobs_for_cube()
    todo = [j for j in jobs if cell_key(j) not in done]
    print(f"cube: {len(jobs)} cells, {len(done)} already done, {len(todo)} to solve "
          f"on {args.workers} workers", flush=True)
    if not todo:
        write_cube(done)
        print(f"nothing to solve; wrote {CUBE}")
        return

    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    completed = 0
    with CHECKPOINT.open("a") as sink, ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(_solve, todo):
            sink.write(json.dumps(row) + "\n")
            sink.flush()
            os.fsync(sink.fileno())
            done[row["key"]] = row
            completed += 1
            elapsed = time.perf_counter() - t0
            eta = elapsed / completed * (len(todo) - completed)
            tag = row.get("error", f"lcoc={row.get('lcoc_default_basis', float('nan')):.4f}")
            print(
                f"  [{completed:>4}/{len(todo)}] {row['site']:<11} {row['year']} "
                f"{row['grid_ceiling_mw']:>5.0f}MW {row['mode']:<9} "
                f"t={row['compute_target']:.2f} {tag} "
                f"({row['solve_seconds']:.0f}s)  "
                f"{100*(len(done))/len(jobs):.0f}% of cube  eta {eta/60:.0f}m",
                flush=True,
            )

    write_cube(done)
    print(f"total {(time.perf_counter() - t0)/60:.1f}m; wrote {CUBE}")


if __name__ == "__main__":
    main()
