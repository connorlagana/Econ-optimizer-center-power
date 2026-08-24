"""V1: does the co-optimisation actually solve, and what does it say?

Runs three flexibility rungs against one Dallas weather year and prints the
architecture each one chooses. The rungs differ only in what the compute load
is allowed to do:

  rigid     GPUs draw nameplate every hour. The reference architecture.
  curtail   GPUs may be parked; work falls off proportionally. The value of
            simply doing less.
  powercap  GPUs may be power-capped along the measured concave curve. The
            value of the curve, over and above doing less.

Separating the last two matters: a study that reports only "flexible vs rigid"
cannot say whether the benefit came from the hardware's efficiency curve or
from the fact that it was permitted to skip work, and those have completely
different implications for whoever has to operate the site.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, optimise
from tecopt.site import DALLAS, coincident_peak_window, gpu_curve, pv_capacity_factor, weather_frame

YEAR = 2019


def money(x: float) -> str:
    return f"${x/1e6:,.1f}M"


def main() -> None:
    lat, lon = DALLAS
    scenario = Scenario()
    curve = gpu_curve(scenario.gpus.curve_name)
    cf = pv_capacity_factor(lat, lon, YEAR)
    index = weather_frame(lat, lon, YEAR).index
    cp_mask = coincident_peak_window(index)

    print(f"Site: Dallas {lat},{lon}   weather year {YEAR}   {cf.size} hours")
    print(f"PV capacity factor: {cf.mean():.3f}")
    print(f"GPU curve: {curve.provenance.name}  ({curve.provenance.kind})")
    print(f"Fleet: {scenario.gpus.gpu_count:,.0f} GPUs, {scenario.gpus.it_nameplate_mw:.0f} MW IT nameplate")
    print(f"GPU capital: {money(scenario.gpus.total_capex)}  -> {money(scenario.gpus.total_capex * __import__('tecopt').crf(0.08, 5))}/yr")
    print(f"Coincident-peak risk window: {cp_mask.sum()} hours\n")

    runs = [
        ("rigid", 1.00),
        ("curtail", 0.99),
        ("powercap", 0.99),
        ("powercap", 0.96),
    ]

    results = []
    for mode, target in runs:
        t0 = time.perf_counter()
        r = optimise(
            scenario, cf, curve,
            flexibility=mode,
            compute_target_fraction=target,
            coincident_peak_mask=cp_mask,
        )
        elapsed = time.perf_counter() - t0
        results.append(r)
        d = r.design
        print(f"--- {mode:9s} compute >= {target:.0%}   [{r.status}, {elapsed:.1f}s]")
        print(f"    PV {d.pv_mw:7.1f} MW | BESS {d.bess_mw:6.1f} MW / {d.bess_mwh:7.1f} MWh ({d.bess_duration_h:.1f}h)"
              f" | grid {d.grid_mw:6.1f} MW | gen {d.gen_mw:5.1f} MW")
        print(f"    annual cost {money(r.annual_cost)}   of which infrastructure "
              f"{money(r.annual_cost - r.cost_breakdown['gpu_capital'])}")
        print(f"    compute {r.compute_unit_hours:,.0f} unit-h ({r.compute_unit_hours/cf.size:.1%})"
              f"   LCOC ${r.lcoc_per_gpu_hour:.4f}/GPU-h")
        print(f"    mean IT power {r.mean_it_power_fraction:.1%} | peak import {r.peak_import_mw:.1f} MW"
              f" | 4CP demand {r.coincident_peak_mw:.1f} MW | gen {r.gen_run_hours:.0f} h"
              f" | PV curtailed {r.pv_curtailed_fraction:.1%}")
        print()

    base = results[0]
    print("=" * 78)
    print(f"{'':22s} {'BESS MWh':>10s} {'infra $/yr':>12s} {'compute':>9s} {'LCOC':>10s}")
    for r in results:
        infra = r.annual_cost - r.cost_breakdown["gpu_capital"]
        base_infra = base.annual_cost - base.cost_breakdown["gpu_capital"]
        label = f"{r.flexibility} @ {r.compute_target_fraction:.0%}"
        d_bess = (r.design.bess_mwh / base.design.bess_mwh - 1) * 100 if base.design.bess_mwh > 1e-6 else float("nan")
        d_infra = (infra / base_infra - 1) * 100
        d_lcoc = (r.lcoc_per_gpu_hour / base.lcoc_per_gpu_hour - 1) * 100
        print(f"{label:22s} {r.design.bess_mwh:10.0f} {infra/1e6:11.1f}M "
              f"{r.compute_unit_hours/cf.size:8.1%} {r.lcoc_per_gpu_hour:9.4f}"
              f"   ({d_bess:+.0f}% BESS, {d_infra:+.0f}% infra, {d_lcoc:+.2f}% LCOC)")
    print("=" * 78)


if __name__ == "__main__":
    main()
