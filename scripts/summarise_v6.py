"""Read results/v6_sweep.json and ask whether the conclusion is a conclusion.

One question, asked of a distribution rather than a number: across fourteen
years and two sites, does compute flexibility *reliably* lower levelised compute
cost at a scarce interconnection, and does it *reliably* fail to at a generous
one? A result that holds in twelve years out of fourteen is a finding with a
stated failure rate. A result that holds in eight is a coin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    payload = json.loads((ROOT / "results" / "v6_sweep.json").read_text())
    runs = [r for r in payload["runs"] if "error" not in r]
    failed = [r for r in payload["runs"] if "error" in r]
    if failed:
        print(f"!! {len(failed)} cells failed:")
        for r in failed[:8]:
            print(f"   {r['site']} {r['year']} {r['grid_ceiling_mw']}MW {r['mode']}: {r['error']}")
        print()

    index = {(r["site"], r["year"], r["grid_ceiling_mw"], r["mode"]): r for r in runs}
    sites = list(payload["sites"])
    years = payload["years"]
    ceilings = payload["grid_ceilings_mw"]

    for ceiling in ceilings:
        print(f"=== {ceiling:.0f} MW interconnection "
              f"({ceiling / 125 * 100:.0f}% of full facility load) ===\n")
        print(f"   {'site':<11} {'year':>5} {'rigid':>8} {'flex':>8} {'LCOC d%':>9} "
              f"{'infra d%':>9} {'$/MWh':>7} {'PV':>8} {'gen d':>8}")
        summary = {}
        for site in sites:
            deltas = []
            for year in years:
                rigid = index.get((site, year, ceiling, "rigid"))
                flex = index.get((site, year, ceiling, "powercap"))
                if not rigid or not flex:
                    continue
                dl = (flex["lcoc"] - rigid["lcoc"]) / rigid["lcoc"] * 100
                di = ((flex["infra_per_year"] - rigid["infra_per_year"])
                      / rigid["infra_per_year"] * 100)
                deltas.append(dl)
                print(f"   {site:<11} {year:>5} {rigid['lcoc']:8.4f} {flex['lcoc']:8.4f} "
                      f"{dl:+9.3f} {di:+9.2f} {rigid['mean_price_per_mwh']:7.2f} "
                      f"{rigid['pv_mw']:7.1f} {flex['gen_mw'] - rigid['gen_mw']:+8.1f}")
            summary[site] = np.array(deltas)
            print()

        print(f"   {'site':<11} {'n':>3} {'median':>9} {'min':>9} {'max':>9} "
              f"{'favourable':>12}")
        for site, deltas in summary.items():
            if not len(deltas):
                continue
            wins = int((deltas < 0).sum())
            print(f"   {site:<11} {len(deltas):>3} {np.median(deltas):+9.3f} "
                  f"{deltas.min():+9.3f} {deltas.max():+9.3f} "
                  f"{wins:>7}/{len(deltas):<4}")
        print()

    print("=== the question ===\n")
    for ceiling in ceilings:
        allv = []
        for site in sites:
            for year in years:
                rigid = index.get((site, year, ceiling, "rigid"))
                flex = index.get((site, year, ceiling, "powercap"))
                if rigid and flex:
                    allv.append((flex["lcoc"] - rigid["lcoc"]) / rigid["lcoc"] * 100)
        allv = np.array(allv)
        if not len(allv):
            continue
        wins = int((allv < 0).sum())
        verdict = ("flexibility pays" if wins == len(allv)
                   else "flexibility does not pay" if wins == 0
                   else f"MIXED -- {wins}/{len(allv)}")
        print(f"   {ceiling:>5.0f} MW: median {np.median(allv):+.3f}%  "
              f"range [{allv.min():+.3f}, {allv.max():+.3f}]  "
              f"favourable in {wins}/{len(allv)}  -> {verdict}")


if __name__ == "__main__":
    main()
