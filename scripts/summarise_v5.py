"""Read results/v5_workload.json and say how much of the bound was real.

V2 and V3 measure the value of flexibility against a workload that is maximally
flexible by construction -- one annual pool, no deadlines. That is an upper
bound. This reports what fraction of it survives once the work has to be
delivered on time, which is the only version of the number anyone can act on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    payload = json.loads((ROOT / "results" / "v5_workload.json").read_text())
    runs = {r["label"]: r for r in payload["runs"]}

    rigid = runs["rigid (no workload structure)"]
    rigid_mixed = runs.get("rigid (3-class mix)")

    print(f"V5 -- {payload['settlement_point']} {payload['year']}, "
          f"{payload['grid_ceiling_mw']:.0f} MW interconnection, "
          f"compute target {payload['compute_target']:.0%}")
    print(f"     inference arrivals peak at {payload['inference_peak_hour_local']:.0f}:00 "
          f"local, {payload['inference_peak_to_trough']:.1f}:1 peak to trough\n")

    if rigid_mixed:
        gap = abs(rigid_mixed["lcoc"] - rigid["lcoc"]) / rigid["lcoc"]
        print(f"Rigid is invariant to workload structure: "
              f"{rigid['lcoc']:.6f} vs {rigid_mixed['lcoc']:.6f} "
              f"({gap:.2e} relative). A plant that never throttles has no")
        print("scheduling problem, so all of V5's effect is on the flexible side.\n")

    pool = runs["pool -- V1 through V4"]
    pool_gain = (pool["lcoc"] - rigid["lcoc"]) / rigid["lcoc"] * 100

    print(f"{'workload':<36} {'LCOC':>9} {'vs rigid':>10} {'infra $M':>9} "
          f"{'gen MW':>8} {'retained':>10}")
    print(f"{'rigid (any workload)':<36} {rigid['lcoc']:9.4f} {'--':>10} "
          f"{rigid['infra_per_year'] / 1e6:9.1f} {rigid['gen_mw']:8.1f} {'--':>10}")

    order = ["pool -- V1 through V4"]
    order += [k for k in runs if k.startswith("deadline ")]
    order += [k for k in runs if k.startswith("inference ")]

    for label in order:
        r = runs.get(label)
        if r is None:
            continue
        gain = (r["lcoc"] - rigid["lcoc"]) / rigid["lcoc"] * 100
        retained = gain / pool_gain * 100 if pool_gain else float("nan")
        print(f"{label:<36} {r['lcoc']:9.4f} {gain:+10.3f} "
              f"{r['infra_per_year'] / 1e6:9.1f} {r['gen_mw']:8.1f} {retained:9.0f}%")

    print("\n('retained' is this mix's LCOC saving as a percentage of the "
          "fungible pool's.\n A value under 100% is the part of V2 and V3's "
          "headline that assumed away a deadline.)\n")

    for label in order:
        r = runs.get(label)
        if r is None or not r.get("workload"):
            continue
        alloc = r["workload"].get("mean_allocation_mw", {})
        powers = r["workload"].get("mean_power_fraction", {})
        if len(alloc) < 2:
            continue
        parts = ", ".join(
            f"{name} {alloc[name]:.1f}MW @ {powers.get(name, 0):.0%}"
            for name in alloc
        )
        print(f"  {label}: {parts}")


if __name__ == "__main__":
    main()
