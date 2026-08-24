"""Workload classes: what "compute" means once it has deadlines.

V1 through V4 treat compute as one fungible pool with an annual target. That is
the assumption landmine 12 flags -- a throttled GPU-hour and a full one are not
interchangeable for a deadline-bound training run, and "8% annual compute
flexibility" says nothing about *when* the 8% may be given up. A pool with an
annual target is maximally flexible by construction, so every number V2 and V3
report about the value of flexibility is an upper bound.

This module gives compute temporal structure, in three kinds that differ only in
the shape of the constraint that ties delivery to time:

``inference``
    Must be served in the hour it arrives. An exogenous arrival profile, an
    hourly floor, no deferral at all. This is the class that cannot move, and
    its arrival peak is in the evening -- which is when power is expensive.

``deadline``
    A quantity of work that must be finished inside a window: so many
    nameplate-hours per day, per week, per month. Free to move *within* the
    window and unable to cross it. The window length is the dial that turns
    V1's fungible pool into a real training schedule, and sweeping it is the
    experiment.

``batch``
    An annual total, placeable anywhere. This is exactly what V1 through V4
    modelled, and it survives as the most flexible rung so the comparison has a
    floor.

**This is still a linear program, and that is the finding, not an accident.**
The roadmap assumed V5 needed a MILP. It does not. A deadline is a cumulative
delivery constraint over a window -- linear. A class's share of the fleet is a
capacity variable, and the concave power-performance hull stays linear in it as
long as the curve is written in absolute rather than fractional terms:

    compute_k(t) <= m_j · p_k(t) + c_j · N_k

for each hull segment j, where ``N_k`` is the class's nameplate in MW. Both
terms are products of a constant and a variable. Writing the same curve as
``compute_frac <= m·p_k/N_k + c`` would divide by a variable and force either a
fixed split or integers; the absolute form does not, so the fleet split is a
free decision and the whole thing stays an LP.

What genuinely needs binaries is discrete *commitment* -- a job that must run
for a minimum unbroken duration, or be admitted whole or not at all, or pay a
checkpoint cost to restart. Those are real and they are not modelled here.
Everything in this file is a continuously divisible quantity of work with a
temporal boundary, which is the right first cut and keeps a fourteen-year
multi-site sweep affordable.

**Landmine 5 is fixed properly here, not worked around.** Power-capping a subset
of GPUs inside a synchronous data-parallel job buys nothing, because the job
runs at the pace of its slowest worker. The control variable has to be a
per-*job* cap applied uniformly. A class is that unit: each class has one power
level per hour applied across its whole allocation, so a "throttle 30% of the
fleet" policy is only expressible when 30% of the fleet is a separable class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

Kind = Literal["inference", "deadline", "batch"]

#: Local-standard-time hour at which inference arrivals peak. PLACEHOLDER, but
#: the *coincidence* it encodes is the point: this is inside ERCOT's 4CP risk
#: window, so the class that cannot move is the one that peaks when power is
#: scarcest.
PEAK_HOUR_LOCAL = 19.0

#: Ratio of the busiest hour to the quietest. PLACEHOLDER; sweep before quoting.
PEAK_TO_TROUGH = 2.2


@dataclass(frozen=True)
class WorkloadClass:
    """One class of work competing for the same fleet.

    ``share_of_compute`` is this class's fraction of the fleet's annual
    unconstrained compute -- what it would deliver running flat out for 8,760
    hours. The shares across a mix must sum to 1, so that a mix and V1's single
    pool are asked for exactly the same total work and the comparison is fair.
    """

    name: str
    kind: Kind
    share_of_compute: float

    #: ``deadline`` only: length of the delivery window in hours. 24 is a daily
    #: quota, 168 a weekly one, 8760 an annual one (identical to ``batch``).
    window_hours: int | None = None

    #: ``inference`` only: the fraction of arriving demand that must be served
    #: in the arriving hour. Below 1.0 this is a load-shedding allowance, not a
    #: deferral -- unserved inference is lost, not postponed.
    sla_fraction: float = 1.0

    #: ``inference`` only: hourly arrival shape, normalised inside the mix.
    #: ``None`` uses :func:`diurnal_inference_profile`.
    arrival_profile: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.kind == "deadline" and not self.window_hours:
            raise ValueError(f"{self.name}: a deadline class needs window_hours")
        if self.kind != "deadline" and self.window_hours:
            raise ValueError(f"{self.name}: window_hours is meaningless for {self.kind}")
        if not 0.0 <= self.sla_fraction <= 1.0:
            raise ValueError(f"{self.name}: sla_fraction must be in [0, 1]")
        if self.share_of_compute < 0:
            raise ValueError(f"{self.name}: share_of_compute must be non-negative")


@dataclass(frozen=True)
class WorkloadMix:
    """A set of classes that together account for the fleet's annual compute."""

    classes: tuple[WorkloadClass, ...]

    def __post_init__(self) -> None:
        if not self.classes:
            raise ValueError("a mix needs at least one class")
        total = sum(c.share_of_compute for c in self.classes)
        if not np.isclose(total, 1.0, atol=1e-9):
            raise ValueError(
                f"class shares sum to {total:.6f}, not 1. A mix and V1's single "
                "pool must be asked for the same total work or the comparison "
                "measures the difference in the ask, not in the structure."
            )
        names = [c.name for c in self.classes]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate class names: {names}")

    def describe(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "kind": c.kind,
                "share_of_compute": c.share_of_compute,
                "window_hours": c.window_hours,
                "sla_fraction": c.sla_fraction,
            }
            for c in self.classes
        ]


def diurnal_inference_profile(hours: np.ndarray) -> np.ndarray:
    """A plausible inference arrival shape. PLACEHOLDER -- shape, not digits.

    Two things about it matter and one does not. What matters: inference demand
    is diurnal, and it peaks in the late afternoon and evening, which in ERCOT
    is when power is scarcest and the coincident-peak window is open. That
    coincidence is the whole reason inference is a different problem from
    training, and any profile with those two properties will reproduce the
    qualitative result.

    What does not matter, and is not claimed: the exact peak-to-trough ratio.
    It is set to 2.2:1 here, which is in the range published operators describe
    for consumer-facing traffic, but it is not sourced and a real study would
    take it from the operator's own telemetry. Sweep it before quoting anything
    that depends on it.
    """
    hours = np.asarray(hours)
    amplitude = (PEAK_TO_TROUGH - 1.0) / (PEAK_TO_TROUGH + 1.0)
    return 1.0 + amplitude * np.cos(2 * np.pi * (hours - PEAK_HOUR_LOCAL) / 24.0)


def _windows(total_hours: int, window_hours: int) -> list[slice]:
    """Contiguous delivery windows, with a short final one where it does not divide.

    168 hours does not divide 8,760. Forcing the window length to a divisor
    would silently change the experiment's independent variable, so the
    remainder becomes a shorter final window and its quota is prorated.
    """
    if window_hours <= 0:
        raise ValueError("window_hours must be positive")
    return [
        slice(start, min(start + window_hours, total_hours))
        for start in range(0, total_hours, window_hours)
    ]


def default_mix(
    inference_share: float = 0.30,
    deadline_share: float = 0.50,
    window_hours: int = 168,
    sla_fraction: float = 1.0,
) -> WorkloadMix:
    """The reference three-class mix. Batch takes whatever is left over."""
    batch_share = 1.0 - inference_share - deadline_share
    if batch_share < -1e-9:
        raise ValueError(
            f"inference {inference_share} + deadline {deadline_share} exceeds 1"
        )
    classes = []
    if inference_share > 0:
        classes.append(
            WorkloadClass("inference", "inference", inference_share,
                          sla_fraction=sla_fraction)
        )
    if deadline_share > 0:
        classes.append(
            WorkloadClass("training_deadline", "deadline", deadline_share,
                          window_hours=window_hours)
        )
    if batch_share > 1e-9:
        classes.append(WorkloadClass("batch", "batch", batch_share))
    return WorkloadMix(tuple(classes))


def single_pool() -> WorkloadMix:
    """V1 through V4's assumption, stated as a mix so it can be compared."""
    return WorkloadMix((WorkloadClass("pool", "batch", 1.0),))
