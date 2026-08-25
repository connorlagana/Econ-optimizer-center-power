"""Site inputs, borrowed from project 1 rather than rebuilt.

Project 1 (``../solar-project-1``) already owns the parts of this problem that
are about the physical world and were expensive to get right:

* fifteen actual Dallas weather years, ERA5, cross-checked against NSRDB, all
  on one canonical non-leap local-standard-time index;
* a PV model whose output is per unit of nameplate DC on a scale **common to
  every year** — the correction in ``pv_model.py``, without which "200 MW of
  solar" describes a different array in each year and the years reorder;
* a measured H100 power-performance curve with declared provenance.

Rebuilding any of that here would fork three sourced artefacts into two
divergent copies. So this module imports them. The coupling is a deliberate
prototype shortcut and it is the first thing to fix if project 2 outlives the
prototype: publish project 1 as a package, or vendor the three files with a
pinned commit hash, rather than reaching across the filesystem.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_1 = Path(__file__).resolve().parents[3] / "solar-project-1"

if not PROJECT_1.exists():          # pragma: no cover - environment guard
    raise RuntimeError(
        f"Expected project 1 at {PROJECT_1}. It supplies weather, the PV model "
        "and the GPU curve; see this module's docstring."
    )
sys.path.insert(0, str(PROJECT_1 / "src"))

DALLAS = (32.78, -96.80)

#: Sites this study can be run at, each paired with the ERCOT settlement point a
#: load there would actually settle at. The pairing is the point: landmine 6 is
#: about prices and weather coming from the same place as well as the same year,
#: and a Dallas irradiance series priced at ``LZ_WEST`` is a different and
#: entirely fictional site.
#:
#: West Texas is Midland-Odessa, which is where ERCOT's solar build actually
#: went and therefore where the capture-price collapse V3 found is sharpest. It
#: is a genuinely different site, not a sensitivity: more irradiance, a weaker
#: load zone, and a price series that has inverted its diurnal shape since 2020.
SITES = {
    "dallas": {
        "latitude": 32.78, "longitude": -96.80,
        "settlement_point": "LZ_NORTH",
        "note": "A big-city site in north Texas: less sun than the west of the state, but a stronger local grid.",
    },
    "west_texas": {
        "latitude": 31.95, "longitude": -102.35,
        "settlement_point": "LZ_WEST",
        "note": "Oil country in west Texas: much more sun, but so many solar farms have been built there that midday power is now nearly worthless.",
    },
}


def site_coords(name: str) -> tuple[float, float]:
    if name not in SITES:
        raise KeyError(f"unknown site {name!r}; known: {sorted(SITES)}")
    return SITES[name]["latitude"], SITES[name]["longitude"]


def pv_capacity_factor(latitude: float, longitude: float, year: int) -> np.ndarray:
    """AC output per unit installed DC nameplate, on the common annual scale."""
    from flexcompute import pv_model, weather

    record = weather.get_weather_year(latitude, longitude, year)
    return pv_model.unnormalised_dc_profile(record.data, latitude, longitude)


def weather_frame(latitude: float, longitude: float, year: int):
    from flexcompute import weather

    return weather.get_weather_year(latitude, longitude, year).data


def gpu_curve(name: str):
    from flexcompute import gpu

    return gpu.get_curve(name)


def coincident_peak_window(index, *, months=(6, 7, 8, 9), hours=range(15, 20)) -> np.ndarray:
    """Hours in which a coincident-peak transmission charge could be set.

    ERCOT's 4CP charge is set by a load's demand during the four 15-minute
    intervals of system peak, one per summer month. Which four is not known
    until after the fact, so a load defends against the whole risk window
    rather than four known hours.

    Modelling it as four *known* hours would let the optimiser dodge the charge
    with four hours of curtailment a year — a clairvoyance bound, useful only
    as the optimistic end of a pair. This window is the conservative end. The
    honest result is reported as the interval between them, not as one number.
    """
    months_arr = np.asarray(index.month)
    hours_arr = np.asarray(index.hour)
    return np.isin(months_arr, months) & np.isin(hours_arr, list(hours))
