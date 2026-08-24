"""Levelised compute cost on compute actually delivered, not compute promised.

Every LCOC quoted so far divides by the annual LP's compute, which assumes a
controller that can see the whole year. This re-does the division using what
each design produced under a 48-hour horizon and a realistic forecast, with the
variable costs the controller actually incurred. Capital comes from the design
itself, so no re-solve is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario, crf

HOURS = 8760


def annual_capital(scenario: Scenario, d: dict, coincident_peak_mw: float) -> dict:
    c, fin, g = scenario.costs, scenario.financing, scenario.gpus
    return {
        "pv": 1000 * d["pv_mw"] * (c.pv_capex_per_kw_dc * crf(fin.discount_rate, fin.pv_life_years)
                                   + c.pv_fom_per_kw_yr),
        "bess": 1000 * (d["bess_mw"] * (c.bess_capex_per_kw * crf(fin.discount_rate, fin.bess_life_years)
                                        + c.bess_fom_per_kw_yr)
                        + d["bess_mwh"] * c.bess_capex_per_kwh * crf(fin.discount_rate, fin.bess_life_years)),
        "gen": 1000 * d["gen_mw"] * (c.gen_capex_per_kw * crf(fin.discount_rate, fin.gen_life_years)
                                     + c.gen_fom_per_kw_yr),
        "grid": 1000 * (d["grid_mw"] * (c.interconnect_capex_per_kw * crf(fin.discount_rate, fin.grid_life_years)
                                        + c.transmission_fom_per_kw_yr)
                        + coincident_peak_mw * c.coincident_peak_per_kw_yr),
        "gpu": g.total_capex * crf(fin.discount_rate, fin.gpu_life_years),
    }


def main() -> None:
    scenario = Scenario()
    gpu_count = scenario.gpus.gpu_count
    rows = json.loads((Path(__file__).resolve().parents[1] / "results" / "foresight.json").read_text())

    print(f"{'design':28s} {'basis':10s} {'compute':>8s} {'infra $/yr':>11s} "
          f"{'LCOC':>9s} {'vs rigid':>9s}")
    print("-" * 84)

    baselines: dict[str, float] = {}
    for row in rows:
        cap = annual_capital(scenario, row["design"], row["annual"]["coincident_peak_mw"])
        capital = sum(cap.values())
        infra_capital = capital - cap["gpu"]

        bases = [("planned", row["annual"]["compute_fraction"], row["annual"]["variable_cost"])]
        bases += [(r["forecast"], r["compute_fraction"], r["variable_cost"]) for r in row["runs"]]

        for name, frac, varcost in bases:
            total = capital + varcost
            lcoc = total / (frac * HOURS * gpu_count)
            key = name
            if row["mode"] == "rigid":
                baselines[key] = lcoc
            ref = baselines.get(key)
            delta = f"{(lcoc/ref - 1)*100:+8.2f}%" if ref and row["mode"] != "rigid" else "  baseline"
            print(f"{row['label']:28s} {name:10s} {frac:7.2%} "
                  f"{(infra_capital + varcost)/1e6:10.1f}M {lcoc:9.4f} {delta}")
        print()


if __name__ == "__main__":
    main()
