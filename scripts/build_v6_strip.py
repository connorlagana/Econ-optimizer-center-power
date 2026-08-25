"""Reduce the fourteen-year V6 sweep to what figure 3 needs.

The cube in ``build_cube.py`` carries four representative years, because a full
year axis crossed with the target axis is hours of solving for a figure that
only ever shows one target. The year *distribution* is the other way round: one
target, every year, and it already exists in ``results/v6_sweep.json``.

The one wrinkle is that V6 stored ``lcoc`` at the default GPU basis but not
``compute_unit_hours``, and the browser needs the latter to re-derive LCOC when
the GPU slider moves. It is recoverable exactly rather than assumed, because

    lcoc = (infra + gpu_capital) / (compute_unit_hours * gpu_count)

is an identity in quantities V6 did record. Inverting it is not an
approximation; asserting it against ``target * 8760`` proves that.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import Scenario
from tecopt.inputs import crf

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "v6_sweep.json"
OUT = ROOT / "web" / "src" / "data" / "v6_strip.json"

HOURS = 8760


def main() -> None:
    payload = json.loads(SOURCE.read_text())
    base = Scenario()
    gpu_count = base.gpus.gpu_count
    gpu_capital = base.gpus.total_capex * crf(base.financing.discount_rate,
                                              base.financing.gpu_life_years)

    rows = []
    for r in payload["runs"]:
        if "error" in r:
            continue
        compute_hours = (r["infra_per_year"] + gpu_capital) / (r["lcoc"] * gpu_count)
        expected = r["compute_target"] * HOURS
        # The compute floor binds in every solved cell, so the inverted value
        # must be the target. If it ever is not, the identity above is being
        # applied to a cell it does not describe and the figure would be wrong.
        assert abs(compute_hours - expected) < 1e-3 * HOURS, (
            f"{r['site']} {r['year']} {r['mode']}: recovered {compute_hours:.1f} "
            f"compute-unit-hours against a target of {expected:.1f}"
        )
        rows.append({
            "site": r["site"],
            "year": r["year"],
            "grid_ceiling_mw": r["grid_ceiling_mw"],
            "mode": r["mode"],
            "compute_target": r["compute_target"],
            "infra_per_year": r["infra_per_year"],
            "compute_unit_hours": compute_hours,
            "pv_mw": r["pv_mw"],
            "gen_mw": r["gen_mw"],
            "bess_mwh": r["bess_mwh"],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "results/v6_sweep.json",
        "years": payload["years"],
        "sites": payload["sites"],
        "grid_ceilings_mw": payload["grid_ceilings_mw"],
        "rows": rows,
    }, separators=(",", ":")) + "\n")
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
