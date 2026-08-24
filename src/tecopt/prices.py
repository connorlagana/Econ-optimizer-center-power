"""ERCOT settlement-point prices on project 1's canonical hour index.

Closes README landmine 6: *prices and weather must come from the same year and
node*. V1 and V2 priced grid energy at a flat $45/MWh, which is not merely
imprecise -- it deletes the correlation structure that the entire study is
about. A flat price cannot express that the hours when solar is abundant are
the hours when energy is cheap, nor that the hours when a data center most
wants to import are the hours when the grid charges the most for it.

**Source.** ERCOT MIS report 13060, *DAM Settlement Point Prices for Load Zones
and Hubs*, annual archives, 2010 to present. Day-ahead rather than real-time,
deliberately: the LP resolves hourly and DAM is the hourly product, whereas
real-time settles at 15 minutes and would have to be averaged up. More
importantly DAM is the *hedgeable* price -- it is what a load can actually
contract against a day ahead -- while a perfect-foresight LP handed a year of
real-time scarcity spikes would report the value of clairvoyance, not the value
of flexibility. See :func:`fetch_year` for the real-time caveat.

**The alignment landmine.** ERCOT stamps prices in Central Prevailing Time --
local clock time, *with* daylight saving. Project 1's canonical index is local
*standard* time, fixed UTC-6, 8760 hours, non-leap. Reading the ERCOT timestamps
as if they were standard time shifts roughly two-thirds of the year by one hour,
in the same direction for every summer hour, which is precisely the season and
precisely the offset that would corrupt the solar/price relationship this module
exists to introduce. The conversion here goes CPT -> UTC -> fixed UTC-6, using
``fold`` to disambiguate the repeated hour at the autumn transition, and asserts
a bijection onto 8760 slots.

Verification that the alignment is right, rather than merely plausible, is in
``tests/test_prices.py``: ERCOT's summer scarcity peaks land in the afternoon
hours where they are historically documented, and shifting the series by one
hour in either direction moves them off it.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "prices"
RAW_DIR = CACHE_DIR / "raw"

#: Label year of the canonical index. Must match project 1's ``weather``
#: module; imported rather than redefined would create an import cycle through
#: ``site``, so it is asserted against in :func:`canonical_index`.
REFERENCE_YEAR = 2023
HOURS_PER_YEAR = 8760

#: ERCOT MIS report: DAM Settlement Point Prices for Load Zones and Hubs.
DAM_LZ_HB_REPORT_ID = 13060

MIS_LISTING = "https://www.ercot.com/misapp/GetReports.do?reportTypeId={report_id}"
MIS_DOWNLOAD = "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={doc_id}"

#: ERCOT publishes in Central Prevailing Time; the canonical index is Central
#: *Standard* Time year-round.
ERCOT_CLOCK = ZoneInfo("America/Chicago")
LOCAL_STANDARD = timezone(timedelta(hours=-6))

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: Settlement points a data-center load might plausibly settle at, paired with
#: the site whose weather belongs with them. A load settles at its *load zone*;
#: hubs are the liquid trading points a PPA would reference.
SITE_SETTLEMENT_POINTS = {
    "dallas": {"load_zone": "LZ_NORTH", "hub": "HB_NORTH"},
    "west_texas": {"load_zone": "LZ_WEST", "hub": "HB_WEST"},
    "houston": {"load_zone": "LZ_HOUSTON", "hub": "HB_HOUSTON"},
    "south": {"load_zone": "LZ_SOUTH", "hub": "HB_SOUTH"},
}


class IncompletePriceYear(RuntimeError):
    """Raised when an archive does not cover a whole calendar year."""


@dataclass(frozen=True)
class PriceYear:
    """One year of hourly prices for every settlement point, canonically indexed."""

    year: int
    frame: pd.DataFrame          # 8760 x n_points, index = canonical LST hours
    provenance: dict

    def series(self, settlement_point: str) -> np.ndarray:
        if settlement_point not in self.frame.columns:
            raise KeyError(
                f"{settlement_point!r} not published in {self.year}; available: "
                f"{sorted(self.frame.columns)}"
            )
        values = self.frame[settlement_point].to_numpy(dtype=float)
        if np.isnan(values).any():
            raise ValueError(
                f"{settlement_point} has {int(np.isnan(values).sum())} missing hours "
                f"in {self.year}; it is probably not published for the whole year."
            )
        return values


def canonical_index() -> pd.DatetimeIndex:
    """The 8760-hour local-standard-time index every array in this study shares."""
    return pd.date_range(
        start=f"{REFERENCE_YEAR}-01-01 00:00",
        periods=HOURS_PER_YEAR,
        freq="h",
        tz=LOCAL_STANDARD,
        name="local_standard_time",
    )


# --------------------------------------------------------------------------
# xlsx reading, without an xlsx library
# --------------------------------------------------------------------------
# ERCOT ships these archives as a single-sheet-per-month xlsx inside a zip.
# Reading them with openpyxl would mean adding a dependency to an environment
# that is pinned specifically so that results do not move underneath the study.
# The files use one narrow corner of the format -- inline numbers and shared
# strings, no formulas, no styles that affect values -- so the standard library
# is enough, and the ingestion stays reproducible for anyone with a bare Python.

def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in si.iter(f"{_XLSX_NS}t"))
        for si in root.iter(f"{_XLSX_NS}si")
    ]


def _sheet_rows(archive: zipfile.ZipFile, sheet: str, strings: list[str]):
    root = ET.fromstring(archive.read(sheet))
    for row in root.iter(f"{_XLSX_NS}row"):
        values = []
        for cell in row.iter(f"{_XLSX_NS}c"):
            node = cell.find(f"{_XLSX_NS}v")
            raw = None if node is None else node.text
            if cell.get("t") == "s" and raw is not None:
                raw = strings[int(raw)]
            values.append(raw)
        yield values


_RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _worksheets(archive: zipfile.ZipFile) -> list[str]:
    """Worksheet parts in workbook order, resolved through the relationships.

    Not by globbing ``Sheet\d+.xml``: ERCOT's older archives name the part
    ``sheet1.xml`` (lower case) with a sheet named ``Dec_1``, and a glob that
    misses them reports "no rows parsed" rather than the truth, which is that
    the file is a partial year. Relationship order is also workbook order,
    which a lexical sort of part names is not once there are ten or more.
    """
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.get("Id"): rel.get("Target")
        for rel in rels.iter(f"{_RELS_NS}Relationship")
    }
    parts = []
    for sheet in workbook.iter(f"{_XLSX_NS}sheet"):
        target = targets.get(sheet.get(f"{_DOC_NS}id"))
        if target is None:
            continue
        target = target.lstrip("/")
        parts.append(target if target.startswith("xl/") else f"xl/{target}")
    return parts


# --------------------------------------------------------------------------
# time alignment
# --------------------------------------------------------------------------

def _hour_of_year(delivery_date: str, hour_ending: str, repeated_flag: str) -> int | None:
    """Map one ERCOT (date, hour-ending, DST flag) row to a canonical hour index.

    ``Hour Ending`` runs ``01:00``..``24:00`` and labels the *end* of the
    interval, so ``01:00`` is the hour beginning at midnight. ``Repeated Hour
    Flag`` is ``Y`` on the second pass through the hour that occurs twice when
    daylight saving ends, which is exactly what ``fold=1`` selects.

    Returns ``None`` for 29 February, which the canonical non-leap index drops.
    """
    month, day, year = (int(part) for part in delivery_date.split("/"))
    hour = int(hour_ending.split(":")[0]) - 1
    fold = 1 if repeated_flag.strip().upper() == "Y" else 0

    start_of_hour = datetime(year, month, day) + timedelta(hours=hour)
    in_clock_time = start_of_hour.replace(tzinfo=ERCOT_CLOCK, fold=fold)
    local = in_clock_time.astimezone(LOCAL_STANDARD)

    if (local.month, local.day) == (2, 29):
        return None
    reference = datetime(REFERENCE_YEAR, local.month, local.day, local.hour)
    return int((reference - datetime(REFERENCE_YEAR, 1, 1)).total_seconds() // 3600)


# --------------------------------------------------------------------------
# acquisition
# --------------------------------------------------------------------------

def discover_archives(report_id: int = DAM_LZ_HB_REPORT_ID) -> dict[int, str]:
    """Map year -> MIS document id for the annual price archives.

    Scraped rather than hardcoded because ERCOT reissues archives (a document
    id changes when a year is corrected and republished), and a stale hardcoded
    id fails by silently serving the wrong vintage.
    """
    import requests

    response = requests.get(
        MIS_LISTING.format(report_id=report_id),
        timeout=120,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    pairs = re.findall(
        r"DAMLZHBSPP_(\d{4})\.zip[\s\S]{0,600}?doclookupId=(\d+)", response.text
    )
    if not pairs:
        raise RuntimeError(
            f"No annual archives found in MIS report {report_id}. The listing "
            "layout may have changed; inspect the page before trusting a fix."
        )
    return {int(year): doc_id for year, doc_id in pairs}


def _download_archive(year: int, doc_id: str, *, refresh: bool = False) -> bytes:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached = RAW_DIR / f"ercot_dam_lz_hb_{year}.zip"
    if cached.exists() and not refresh:
        return cached.read_bytes()

    import requests

    response = requests.get(
        MIS_DOWNLOAD.format(doc_id=doc_id),
        timeout=600,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    cached.write_bytes(response.content)
    return response.content


def _parse_archive(payload: bytes, year: int) -> pd.DataFrame:
    outer = zipfile.ZipFile(io.BytesIO(payload))
    members = outer.namelist()
    if len(members) != 1:
        raise RuntimeError(f"Expected one member in the {year} archive, got {members}")
    workbook = zipfile.ZipFile(io.BytesIO(outer.read(members[0])))

    strings = _shared_strings(workbook)
    columns: dict[str, np.ndarray] = {}
    seen: dict[str, np.ndarray] = {}

    for sheet in _worksheets(workbook):
        rows = _sheet_rows(workbook, sheet, strings)
        header = next(rows, None)
        if header is None:
            continue
        expected = ("Delivery Date", "Hour Ending", "Repeated Hour Flag",
                    "Settlement Point", "Settlement Point Price")
        if tuple(header) != expected:
            raise RuntimeError(f"Unexpected header in {year} {sheet}: {header}")

        for delivery_date, hour_ending, flag, point, price in rows:
            hoy = _hour_of_year(delivery_date, hour_ending, flag)
            if hoy is None:
                continue
            if point not in columns:
                columns[point] = np.full(HOURS_PER_YEAR, np.nan)
                seen[point] = np.zeros(HOURS_PER_YEAR, dtype=bool)
            if seen[point][hoy]:
                raise ValueError(
                    f"Two {point} prices landed on hour {hoy} of {year}. The "
                    "daylight-saving mapping is wrong; do not paper over this."
                )
            columns[point][hoy] = float(price)
            seen[point][hoy] = True

    if not columns:
        raise RuntimeError(f"No price rows parsed from the {year} archive")

    frame = pd.DataFrame(columns, index=canonical_index()).sort_index(axis=1)
    if frame.notna().any(axis=1).sum() < HOURS_PER_YEAR:
        covered = int(frame.notna().any(axis=1).sum())
        raise IncompletePriceYear(
            f"ERCOT's {year} archive covers {covered} of {HOURS_PER_YEAR} hours. "
            "The nodal market opened on 1 December 2010, so 2010 is a one-month "
            "file and no settlement-point series exists before 2011."
        )
    return frame


def _cache_paths(year: int) -> tuple[Path, Path]:
    stem = f"ercot_dam_lz_hb_{year}"
    return CACHE_DIR / f"{stem}.parquet", CACHE_DIR / f"{stem}.json"


def fetch_year(year: int, *, use_cache: bool = True, refresh: bool = False) -> PriceYear:
    """Load one year of ERCOT DAM settlement-point prices, canonically indexed.

    **Day-ahead, not real-time.** Real-time prices carry the scarcity spikes --
    the $5,000/MWh hours that make flexibility look valuable -- but handing them
    to a perfect-foresight LP measures clairvoyance rather than flexibility,
    because the planner would schedule around spikes no operator can see coming.
    Day-ahead is the price a load can actually hedge to. Real-time belongs in
    the V4 operational validation, where the controller cannot see ahead, and
    that pairing is not yet built.
    """
    data_path, meta_path = _cache_paths(year)
    if use_cache and not refresh and data_path.exists() and meta_path.exists():
        frame = pd.read_parquet(data_path)
        frame.index = canonical_index()
        return PriceYear(year, frame, json.loads(meta_path.read_text()))

    archives = discover_archives()
    if year not in archives:
        raise ValueError(
            f"ERCOT does not publish a {year} annual archive; available: "
            f"{sorted(archives)}"
        )
    payload = _download_archive(year, archives[year], refresh=refresh)
    frame = _parse_archive(payload, year)

    complete = [c for c in frame.columns if not frame[c].isna().any()]
    provenance = {
        "source": "ERCOT MIS report 13060, DAM Settlement Point Prices for Load Zones and Hubs",
        "listing": MIS_LISTING.format(report_id=DAM_LZ_HB_REPORT_ID),
        "doclookup_id": archives[year],
        "year": year,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": "day-ahead",
        "currency_units": "USD per MWh",
        "timezone_source": "Central Prevailing Time (hour-ending)",
        "timezone_canonical": "fixed UTC-06:00, local standard time, hour-beginning",
        "leap_day_policy": "29 February dropped, matching project 1's canonical index",
        "settlement_points": sorted(frame.columns),
        "complete_settlement_points": sorted(complete),
        "hours": int(len(frame)),
    }

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(data_path)
        meta_path.write_text(json.dumps(provenance, indent=2) + "\n")
    return PriceYear(year, frame, provenance)


def energy_price_series(
    year: int,
    settlement_point: str = "LZ_NORTH",
    *,
    adder_per_mwh: float = 0.0,
) -> np.ndarray:
    """Hourly $/MWh for one settlement point, ready to hand to the optimiser.

    ``adder_per_mwh`` covers the non-energy components of a delivered price that
    the settlement point does not include -- ancillary service allocation, ERCOT
    administrative fees, retail adder. It is a scalar because those components
    are roughly flat per MWh; transmission is *not* in it, because transmission
    is charged on demand rather than energy and the model already carries it as
    ``coincident_peak_per_kw_yr`` and ``transmission_fom_per_kw_yr``.
    """
    return fetch_year(year).series(settlement_point) + adder_per_mwh
