"""Warm the ERCOT price cache. Run once; everything downstream reads parquet.

The nodal market opened on 1 December 2010, so the price record starts in 2011
while project 1's weather record starts in 2010. Fourteen years overlap, not
fifteen, and V6 is bounded by the shorter of the two.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import prices

FIRST_FULL_YEAR = 2011
LAST_YEAR = 2024


def main() -> None:
    for year in range(FIRST_FULL_YEAR, LAST_YEAR + 1):
        try:
            record = prices.fetch_year(year)
        except prices.IncompletePriceYear as exc:
            print(f"{year}: skipped -- {exc}")
            continue
        complete = record.provenance["complete_settlement_points"]
        print(f"{year}: {len(complete)} settlement points, {record.provenance['hours']} hours")


if __name__ == "__main__":
    main()
