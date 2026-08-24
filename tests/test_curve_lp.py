"""The concave-hull encoding is the load-bearing claim. Pin it.

Everything in this project is an LP only because the GPU power-performance
curve is concave, which lets ``compute <= m_k * power + c_k`` over hull
segments stand in for the curve itself. If that encoding is ever wrong — or if
project 1's curve is replaced by one that is not concave — every result becomes
a statement about a curve nobody measured. These tests fail loudly instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt.inputs import Scenario
from tecopt.model import concave_hull_segments
from tecopt.site import gpu_curve


@pytest.fixture(scope="module")
def curve():
    return gpu_curve(Scenario().gpus.curve_name)


def test_hull_envelope_reproduces_the_curve(curve):
    """min over hull lines == the hull curve, at every power fraction."""
    segments = concave_hull_segments(curve)
    hull = curve.concave_hull()
    x = np.linspace(hull.min_operating_power_fraction, 1.0, 501)

    envelope = np.min([slope * x + intercept for slope, intercept in segments], axis=0)
    expected = hull.compute_fraction_at(x)

    np.testing.assert_allclose(envelope, expected, atol=1e-12)


def test_segment_slopes_are_strictly_decreasing(curve):
    """Concavity, stated as the property the LP actually relies on.

    If slopes ever stop decreasing the lower envelope is no longer the curve,
    the LP silently optimises against a different function, and nothing else in
    this repository would notice.
    """
    slopes = [slope for slope, _ in concave_hull_segments(curve)]
    assert len(slopes) >= 2
    assert all(a > b for a, b in zip(slopes, slopes[1:])), slopes


def test_hull_is_an_upper_bound_on_the_measured_curve(curve):
    """Fleet aggregation may only ever add reachable points, never remove them.

    The hull represents a fleet running a *mix* of per-device power states, so
    it must dominate the per-device curve everywhere the latter is defined.
    """
    x = np.linspace(curve.min_operating_power_fraction, 1.0, 501)
    assert np.all(curve.concave_hull().compute_fraction_at(x) >= curve.compute_fraction_at(x) - 1e-12)


def test_curve_is_still_the_measured_one(curve):
    """Guard against silently inheriting a synthetic curve from project 1."""
    assert curve.is_measured, curve.provenance.kind
    assert curve.provenance.power_basis == "power_cap"
