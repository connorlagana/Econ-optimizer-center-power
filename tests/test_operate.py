"""Guards on the operational controller.

The first test exists because this bug shipped: the unserved-load penalty was
expressed as a multiple of the compute price, the rigid design's compute price
is legitimately zero (compute is not a decision there, so the planner's dual on
the compute floor is degenerate), and the penalty went to zero with it. The
controller then shed all 8,760 hours of load at no cost and reported 100%
compute. Every downstream number was garbage and nothing failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import operate
from tecopt.inputs import Scenario
from tecopt.model import Design
from tecopt.site import gpu_curve


class _FlatForecast:
    """Exact knowledge of a constant PV series. No weather, no error."""

    name = "flat"

    def __init__(self, series: np.ndarray) -> None:
        self.series = series

    def horizon(self, t: int, hours: int) -> np.ndarray:
        return self.series[t : t + hours]


@pytest.fixture(scope="module")
def curve():
    return gpu_curve(Scenario().gpus.curve_name)


@pytest.mark.parametrize("compute_price", [0.0, 1e5])
def test_load_is_served_even_when_compute_is_priced_at_zero(curve, compute_price):
    """A grid big enough to serve the load must result in no shedding.

    Parameterised on a zero compute price specifically: that is the rigid
    design's real input, and the penalty must not be scalable to zero by it.
    """
    scenario = Scenario()
    hours = 72
    design = Design(pv_mw=0.0, bess_mw=0.0, bess_mwh=0.0, grid_mw=200.0, gen_mw=0.0)

    result = operate.simulate(
        scenario, design, curve, np.zeros(hours), _FlatForecast(np.zeros(hours)),
        flexibility="rigid",
        compute_price=compute_price,
        planned_compute_fraction=1.0,
        planned_coincident_peak_mw=200.0,
        coincident_peak_mask=np.zeros(hours, dtype=bool),
        horizon_hours=24,
    )

    assert result.unserved_mwh == pytest.approx(0.0, abs=1e-6)
    assert result.unserved_hours == 0
    if compute_price > 0:
        # Worth producing, and the grid can cover it: run flat out.
        assert result.compute_fraction == pytest.approx(1.0)
    else:
        # Compute priced at zero is worth nothing, so an operator maximising
        # value idles the fleet rather than paying for imports. Correct, and
        # the reason this parameterisation only asserts on shedding.
        assert result.compute_fraction < 1.0


def test_shedding_happens_only_below_the_idle_floor(curve):
    """Throttle first, shed only what the hardware floor cannot give up.

    A 10 MW grid cannot run a 100 MW fleet. The controller must throttle to the
    fleet's idle floor before shedding anything, and then shed only the
    remainder — the fixed facility overhead plus idle IT draw, which no amount
    of throttling removes. Shedding more than that would mean the controller
    preferred a blackout to a throttle; shedding less would mean the LP had
    found free energy.
    """
    scenario = Scenario()
    hours = 24
    design = Design(pv_mw=0.0, bess_mw=0.0, bess_mwh=0.0, grid_mw=10.0, gen_mw=0.0)

    result = operate.simulate(
        scenario, design, curve, np.zeros(hours), _FlatForecast(np.zeros(hours)),
        flexibility="rigid",
        compute_price=0.0,
        planned_compute_fraction=1.0,
        planned_coincident_peak_mw=10.0,
        coincident_peak_mask=np.zeros(hours, dtype=bool),
        horizon_hours=12,
    )

    # Facility draw with the fleet at its idle floor: fixed overhead plus the
    # idle IT load, grossed up for the variable share of cooling.
    idle_it = curve.idle_power_fraction * 100.0
    floor = (scenario.facility.fixed_overhead_mw(100.0)
             + scenario.facility.variable_multiplier() * idle_it)
    assert result.unserved_mwh == pytest.approx((floor - 10.0) * hours, rel=1e-6)
    assert result.unserved_hours == hours


def test_storage_terminal_value_is_positive_and_finite(curve):
    value = operate.storage_terminal_value(Scenario(), curve, compute_price=1e5)
    assert 0.0 < value < 1e5


def test_rigid_does_not_credit_compute_for_hours_it_cannot_power(curve):
    """Rigid must lose compute when supply is short, not bank it as unserved.

    This shipped too. The planner states rigid as ``p_it == it_max,
    compute == 1``, which is exact there because the plant is sized so the case
    never arises. Carried into the operator, where an unserved-load slack
    exists, it credited full compute for hours the plant could not power: the
    rigid design reported 100% compute across 834 hours of blackout, and scored
    a *higher* net value than the annual LP that is supposed to bound it.
    """
    scenario = Scenario()
    hours = 24
    # Enough for the fixed overhead and an idling fleet, nowhere near full load.
    design = Design(pv_mw=0.0, bess_mw=0.0, bess_mwh=0.0, grid_mw=30.0, gen_mw=0.0)

    result = operate.simulate(
        scenario, design, curve, np.zeros(hours), _FlatForecast(np.zeros(hours)),
        flexibility="rigid",
        compute_price=71_477.0,
        planned_compute_fraction=1.0,
        planned_coincident_peak_mw=30.0,
        coincident_peak_mask=np.zeros(hours, dtype=bool),
        horizon_hours=12,
    )

    assert result.compute_fraction < 0.5, result.compute_fraction
    assert result.unserved_mwh == pytest.approx(0.0, abs=1e-6)
