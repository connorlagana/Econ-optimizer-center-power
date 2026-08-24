"""Guards on the workload-class formulation (V5).

The tests that matter here are the *equivalences*. A multi-class model that does
not reduce to the single-pool model when given a single pool is not a
generalisation of V1 through V4, it is a different study, and every comparison
drawn against the earlier rungs would be meaningless.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tecopt import site, workload
from tecopt.inputs import Limits, Scenario
from tecopt.model import optimise


@pytest.fixture(scope="module")
def context():
    from dataclasses import replace

    scenario = replace(Scenario(), limits=Limits(max_grid_mw=60.0))
    index = site.weather_frame(*site.DALLAS, 2019).index
    return {
        "scenario": scenario,
        "cf": site.pv_capacity_factor(*site.DALLAS, 2019),
        "curve": site.gpu_curve(scenario.gpus.curve_name),
        "coincident_peak_mask": site.coincident_peak_window(index),
        "local_hour": np.asarray(index.hour),
    }


def _solve(context, **kwargs):
    ctx = dict(context)
    scenario, cf, curve = ctx.pop("scenario"), ctx.pop("cf"), ctx.pop("curve")
    return optimise(scenario, cf, curve, **ctx, **kwargs)


def test_shares_must_sum_to_one():
    """A mix asked for less work than the pool would look flexible for free."""
    with pytest.raises(ValueError, match="sum to"):
        workload.WorkloadMix((workload.WorkloadClass("a", "batch", 0.5),))


def test_deadline_class_needs_a_window():
    with pytest.raises(ValueError, match="window_hours"):
        workload.WorkloadClass("t", "deadline", 1.0)


def test_annual_window_equals_batch(context):
    """A deadline of one year is not a deadline. Both must price identically."""
    batch = _solve(context, flexibility="powercap", compute_target_fraction=0.98,
                   workload=workload.single_pool())
    annual = _solve(context, flexibility="powercap", compute_target_fraction=0.98,
                    workload=workload.WorkloadMix((
                        workload.WorkloadClass("t", "deadline", 1.0, window_hours=8760),
                    )))
    assert annual.lcoc_per_gpu_hour == pytest.approx(batch.lcoc_per_gpu_hour, rel=1e-6)


def test_single_pool_reproduces_the_unstructured_model(context):
    """The V5 formulation must collapse exactly onto V1 through V4."""
    unstructured = _solve(context, flexibility="powercap", compute_target_fraction=0.98)
    pooled = _solve(context, flexibility="powercap", compute_target_fraction=0.98,
                    workload=workload.single_pool())
    assert pooled.lcoc_per_gpu_hour == pytest.approx(
        unstructured.lcoc_per_gpu_hour, rel=1e-6
    )
    assert pooled.design.pv_mw == pytest.approx(unstructured.design.pv_mw, rel=1e-4)


def test_rigid_is_invariant_to_workload_structure(context):
    """A plant that never throttles has no scheduling problem.

    Rigid compute pins power to nameplate every hour, so the plant sees the same
    load whatever the work is. If this ever fails, workload structure has leaked
    into the power model and the V5 comparison is measuring two things at once.
    """
    plain = _solve(context, flexibility="rigid", compute_target_fraction=1.0)
    mixed = _solve(context, flexibility="rigid", compute_target_fraction=1.0,
                   workload=workload.default_mix(0.30, 0.50, 168))
    assert mixed.lcoc_per_gpu_hour == pytest.approx(plain.lcoc_per_gpu_hour, rel=1e-6)


def test_tighter_deadlines_cannot_be_cheaper(context):
    """Shrinking a window only removes schedules. Cost must be monotone."""
    loose = _solve(context, flexibility="powercap", compute_target_fraction=0.98,
                   workload=workload.default_mix(0.0, 1.0, 730))
    tight = _solve(context, flexibility="powercap", compute_target_fraction=0.98,
                   workload=workload.default_mix(0.0, 1.0, 24))
    assert tight.annual_cost >= loose.annual_cost - 1.0


def test_allocation_is_conserved(context):
    """Classes share one fleet; the shares must add up to it every hour."""
    r = _solve(context, flexibility="powercap", compute_target_fraction=0.98,
               workload=workload.default_mix(0.30, 0.50, 168))
    peak = sum(r.workload["peak_allocation_mw"].values())
    assert peak <= Scenario().gpus.it_nameplate_mw * 1.001


def test_inference_profile_matches_its_documentation():
    """The docstring claims a 19:00 peak and a 2.2:1 ratio. Hold it to that."""
    profile = workload.diurnal_inference_profile(np.arange(24))
    assert int(np.argmax(profile)) == int(workload.PEAK_HOUR_LOCAL)
    assert profile.max() / profile.min() == pytest.approx(workload.PEAK_TO_TROUGH, rel=1e-6)
