"""Read results/v3_prices.json and say what the price series changed.

Three questions, in the order they matter:

1. Did the *crossover* move? That is V2's headline and the study's main claim.
2. Did the *design* change? A price level and a price shape can leave a summary
   statistic alone while rebuilding the plant underneath it.
3. Why? The mechanism is one number -- what a megawatt of solar is worth per
   year -- and it is computable without the optimiser, which makes it checkable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, prices
from tecopt.inputs import crf
from tecopt.site import DALLAS, pv_capacity_factor

ROOT = Path(__file__).resolve().parents[1]
BASES = ("flat_placeholder", "flat_actual_mean", "hourly")
FULL_FACILITY_MW = 125.0


def crossover(points: list[tuple[float, float]]) -> float | None:
    """Linear interpolation of the interconnection size where the LCOC delta is 0."""
    ordered = sorted(points, reverse=True)
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if y0 > 0 >= y1:
            return x0 + (x1 - x0) * (0 - y0) / (y1 - y0)
    return None


def main() -> None:
    payload = json.loads((ROOT / "results" / "v3_prices.json").read_text())
    runs = {(r["price_basis"], r["grid_ceiling_mw"], r["mode"]): r for r in payload["runs"]}
    ceilings = sorted({r["grid_ceiling_mw"] for r in payload["runs"]}, reverse=True)

    print(f"V3 -- {payload['settlement_point']} {payload['year']}, ERCOT day-ahead")
    stats = payload["price_stats"]
    print(
        f"  mean ${stats['mean_per_mwh']:.2f}/MWh   median ${stats['median_per_mwh']:.2f}   "
        f"max ${stats['max_per_mwh']:,.0f}   {stats['hours_over_100']} hours over $100   "
        f"{stats['negative_hours']} negative"
    )
    print("  The median is well under the mean: the level is set by a few hundred hours.\n")

    print("1. Does the crossover move?\n")
    print(f"   {'basis':<18} {'crossover':>10} {'% of facility load':>20}")
    for basis in BASES:
        pts = []
        for ceiling in ceilings:
            rigid = runs[(basis, ceiling, "rigid")]
            flex = runs[(basis, ceiling, "powercap")]
            pts.append((ceiling, (flex["lcoc"] - rigid["lcoc"]) / rigid["lcoc"] * 100))
        x = crossover(pts)
        print(f"   {basis:<18} {x:9.1f} MW {x / FULL_FACILITY_MW * 100:19.0f}%")
    print("\n   Barely. Flexibility is a capacity product; the energy price is not")
    print("   what decides it. The flat-price shortcut survived the question V2 asked.\n")

    print("2. Does the design move?\n")
    for ceiling in (max(ceilings), 60.0):
        print(f"   at a {ceiling:.0f} MW interconnection, rigid compute:")
        print(f"     {'basis':<18} {'PV':>8} {'BESS':>10} {'gen':>8} {'imports':>10} "
              f"{'energy $':>10} {'4CP':>8}")
        for basis in BASES:
            r = runs[(basis, ceiling, "rigid")]
            print(
                f"     {basis:<18} {r['pv_mw']:6.1f}MW {r['bess_mwh']:8.0f}MWh "
                f"{r['gen_mw']:6.1f}MW {r['imports_mwh'] / 1e3:8.0f}GWh "
                f"${r['energy_cost'] / 1e6:8.1f}M {r['coincident_peak_mw']:6.1f}MW"
            )
        print()

    print("3. The mechanism, computed without the optimiser:\n")
    scenario = Scenario()
    costs, financing = scenario.costs, scenario.financing
    annual_cost = 1000.0 * (
        costs.pv_capex_per_kw_dc * crf(financing.discount_rate, financing.pv_life_years)
        + costs.pv_fom_per_kw_yr
    )
    cf = pv_capacity_factor(*DALLAS, payload["year"])
    hourly = prices.energy_price_series(payload["year"], payload["settlement_point"])

    flat_value = float(cf.sum()) * float(hourly.mean())
    shaped_value = float((cf * hourly).sum())

    print(f"   One MW of PV costs                       ${annual_cost:>10,.0f}/MW-yr")
    print(f"   ...is worth, priced at the annual mean    ${flat_value:>10,.0f}/MW-yr  "
          f"({'pays' if flat_value > annual_cost else 'does not pay'})")
    print(f"   ...is worth, priced hour by hour          ${shaped_value:>10,.0f}/MW-yr  "
          f"({'pays' if shaped_value > annual_cost else 'does not pay'})")
    print(f"\n   A flat price undervalues solar by {(1 - flat_value / shaped_value) * 100:.0f}% "
          f"at this node and year, because solar produces\n   disproportionately in hours that "
          f"are priced above the mean. That is the whole\n   of landmine 6, and it is the "
          f"difference between building no solar and building\n   "
          f"{runs[('hourly', max(ceilings), 'rigid')]['pv_mw']:.0f} MW of it.\n")

    print("   The sign of that correction is not a constant of nature:\n")
    print(f"   {'year':>6} {'PV $/MW-yr':>12} {'vs cost':>10}")
    for year in (2019, 2021, 2023, 2024):
        try:
            p = prices.energy_price_series(year, payload["settlement_point"])
        except Exception:
            continue
        c = pv_capacity_factor(*DALLAS, year)
        value = float((c * p).sum())
        print(f"   {year:>6} {value:>11,.0f} {value / annual_cost:>9.2f}x")


if __name__ == "__main__":
    main()
