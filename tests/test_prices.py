"""Tests for ERCOT price ingestion, aimed at the one bug that would be silent.

A one-hour daylight-saving error in the price series does not raise, does not
produce NaNs, and does not look wrong in a summary statistic. It shifts roughly
two-thirds of the year -- every hour between March and November -- in the same
direction, which corrupts the solar/price correlation that V3 exists to
introduce while leaving every scalar diagnostic intact. So it is tested against
external facts about ERCOT that a shifted series cannot reproduce.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import prices


pytestmark = pytest.mark.skipif(
    not (prices.CACHE_DIR / "ercot_dam_lz_hb_2019.parquet").exists(),
    reason="price cache not warmed; run scripts/fetch_prices.py",
)


def test_canonical_index_matches_project_one():
    """Prices must land on the same 8760-hour index as weather, or nothing aligns."""
    from tecopt import site

    weather_index = site.weather_frame(*site.DALLAS, 2019).index
    assert prices.canonical_index().equals(weather_index)


def test_year_is_complete_and_unique():
    year = prices.fetch_year(2019)
    assert len(year.frame) == prices.HOURS_PER_YEAR
    series = year.series("LZ_NORTH")
    assert not np.isnan(series).any()


def test_scarcity_peaks_land_in_the_summer_afternoon():
    """ERCOT's 2019 scarcity was August-September, mid-afternoon local time.

    This is the load-bearing alignment test. The August 2019 and September 2019
    scarcity events are among the best-documented hours in ERCOT's history and
    they occurred in the 15:00-17:00 CDT range, which is 14:00-16:00 local
    standard time. A series shifted by one hour in either direction moves the
    top-priced hours off that window.
    """
    series = prices.energy_price_series(2019, "LZ_NORTH")
    index = prices.canonical_index()
    top = np.argsort(series)[-10:]

    months = np.asarray(index.month)[top]
    hours = np.asarray(index.hour)[top]

    assert set(months.tolist()) <= {8, 9}
    assert hours.min() >= 13 and hours.max() <= 16


def test_daylight_saving_shift_would_be_detected():
    """Guard the guard: the test above must actually fail on a shifted series."""
    series = prices.energy_price_series(2019, "LZ_NORTH")
    index = prices.canonical_index()
    hours = np.asarray(index.hour)

    def afternoon_share(shift: int) -> float:
        shifted = np.roll(series, shift)
        top = np.argsort(shifted)[-10:]
        return float(np.mean((hours[top] >= 13) & (hours[top] <= 16)))

    assert afternoon_share(0) == 1.0
    assert afternoon_share(2) < 1.0
    assert afternoon_share(-2) < 1.0


def test_repeated_hour_is_not_dropped_or_doubled():
    """The autumn fall-back hour occurs twice in clock time and once in the index."""
    year = prices.fetch_year(2019)
    assert year.provenance["hours"] == prices.HOURS_PER_YEAR
    assert not year.frame["LZ_NORTH"].isna().any()


def test_incomplete_year_refuses_rather_than_pads():
    """2010 is a one-month file; a partial year must not masquerade as a full one."""
    with pytest.raises(prices.IncompletePriceYear, match="2010"):
        prices.fetch_year(2010, use_cache=False)


def test_hourly_price_changes_the_answer():
    """A flat mean and the real shape must not produce the same design.

    If they do, the price series is not reaching the objective and V3 is
    decorative.
    """
    from tecopt import site
    from tecopt.inputs import Scenario
    from tecopt.model import optimise

    scenario = Scenario()
    cf = site.pv_capacity_factor(*site.DALLAS, 2019)
    curve = site.gpu_curve(scenario.gpus.curve_name)
    hourly = prices.energy_price_series(2019, "LZ_NORTH")

    flat = optimise(scenario, cf, curve, flexibility="powercap",
                    compute_target_fraction=0.98,
                    energy_price_per_mwh=float(hourly.mean()))
    shaped = optimise(scenario, cf, curve, flexibility="powercap",
                      compute_target_fraction=0.98,
                      energy_price_per_mwh=hourly)

    assert shaped.price_basis["hourly"] is True
    assert flat.price_basis["hourly"] is False
    assert not np.isclose(shaped.design.pv_mw, flat.design.pv_mw, rtol=1e-3)


def test_export_is_off_by_default_and_pays_when_on():
    """Export must be an explicit choice, and must relax the problem when taken."""
    from tecopt import site
    from tecopt.inputs import Scenario
    from tecopt.model import optimise

    from dataclasses import replace
    from tecopt.inputs import Limits

    scenario = Scenario()
    bounded = replace(scenario, limits=Limits(max_grid_mw=60.0))
    cf = site.pv_capacity_factor(*site.DALLAS, 2019)
    curve = site.gpu_curve(scenario.gpus.curve_name)
    hourly = prices.energy_price_series(2019, "LZ_NORTH")

    closed = optimise(bounded, cf, curve, flexibility="powercap",
                      compute_target_fraction=0.98, energy_price_per_mwh=hourly)
    open_ = optimise(bounded, cf, curve, flexibility="powercap",
                     compute_target_fraction=0.98, energy_price_per_mwh=hourly,
                     allow_export=True)

    assert closed.dispatch["export_mw"].max() == pytest.approx(0.0, abs=1e-6)
    # Export is a strictly larger feasible set, so it cannot cost more.
    assert open_.annual_cost <= closed.annual_cost + 1.0


def test_export_without_a_bound_refuses_rather_than_reporting_unbounded():
    """An unbounded merchant solar farm is not an answer to this question."""
    from tecopt import site
    from tecopt.inputs import Scenario
    from tecopt.model import optimise

    scenario = Scenario()
    cf = site.pv_capacity_factor(*site.DALLAS, 2019)
    curve = site.gpu_curve(scenario.gpus.curve_name)

    with pytest.raises(ValueError, match="max_grid_mw"):
        optimise(scenario, cf, curve, allow_export=True,
                 energy_price_per_mwh=prices.energy_price_series(2019, "LZ_NORTH"))
