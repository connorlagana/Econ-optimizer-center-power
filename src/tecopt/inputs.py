"""Every number the optimiser is allowed to know, in one place.

Two rules for this module:

1. **No number without a comment saying where it came from.** A techno-economic
   result is a claim about the world only to the extent its inputs are. Values
   marked ``PLACEHOLDER`` are order-of-magnitude figures chosen to make the
   model run; they are not sourced and must be replaced before any number
   leaves this repository.
2. **Nothing here is a decision variable.** If the optimiser gets to choose it,
   it belongs in ``model.py``.

Unit convention, enforced by naming: ``_mw`` / ``_mwh`` for quantities,
``_per_kw`` / ``_per_kwh`` for costs (industry quotes them per kW), ``_per_mwh``
for energy prices. The model converts once, at the objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


def crf(discount_rate: float, life_years: int) -> float:
    """Capital recovery factor: the annuity that repays $1 over ``life_years``.

    Real (not nominal) rate against real (not escalated) costs. Mixing the two
    conventions is the single most common error in levelised-cost arithmetic
    and it biases long-lived assets — solar — against short-lived ones — GPUs.
    """
    if discount_rate == 0:
        return 1.0 / life_years
    growth = (1.0 + discount_rate) ** life_years
    return discount_rate * growth / (growth - 1.0)


@dataclass(frozen=True)
class Financing:
    discount_rate: float = 0.08          # PLACEHOLDER: real WACC, merchant-ish project
    pv_life_years: int = 30              # NREL ATB convention for utility PV
    bess_life_years: int = 20            # before augmentation; see degradation note
    gen_life_years: int = 25
    grid_life_years: int = 40            # substation/interconnect assets are long-lived
    gpu_life_years: int = 5              # hyperscaler depreciation schedule, 5-6y typical


@dataclass(frozen=True)
class TechCosts:
    """2026-ish real USD. Every one of these is a PLACEHOLDER pending sourcing."""

    # --- solar -----------------------------------------------------------
    pv_capex_per_kw_dc: float = 1050.0   # PLACEHOLDER utility-scale single-axis, pre-ITC
    pv_fom_per_kw_yr: float = 18.0       # PLACEHOLDER

    # --- storage ---------------------------------------------------------
    # Priced on two axes because the optimiser chooses duration. A $/kW-only
    # model (which is what most published DC studies use) hands the optimiser
    # unlimited MWh for free and its duration answer is meaningless.
    bess_capex_per_kw: float = 250.0     # PLACEHOLDER power conversion + BOS
    bess_capex_per_kwh: float = 150.0    # PLACEHOLDER cells + enclosure
    bess_fom_per_kw_yr: float = 10.0     # PLACEHOLDER

    # --- backup generation ----------------------------------------------
    # Reciprocating engines, not turbines: 2026 turbine lead times put frames
    # beyond the plausible in-service date of a project being sized today.
    gen_capex_per_kw: float = 1400.0     # PLACEHOLDER installed recip genset
    gen_fom_per_kw_yr: float = 25.0      # PLACEHOLDER
    gen_heat_rate_mmbtu_per_mwh: float = 8.5   # ~40% LHV efficiency
    gen_vom_per_mwh: float = 12.0        # PLACEHOLDER
    gas_price_per_mmbtu: float = 3.50    # PLACEHOLDER Waha-ish delivered

    # --- grid ------------------------------------------------------------
    interconnect_capex_per_kw: float = 300.0   # PLACEHOLDER substation + line
    transmission_fom_per_kw_yr: float = 12.0   # PLACEHOLDER non-coincident charges
    energy_price_per_mwh: float = 45.0         # PLACEHOLDER flat. See README landmine 6.
    # Coincident-peak transmission charge. In ERCOT this is the 4CP mechanism and
    # for a 100 MW load it is the largest single lever compute flexibility has.
    # Rate is per kW of the load's peak demand during the charging window.
    coincident_peak_per_kw_yr: float = 75.0    # PLACEHOLDER


@dataclass(frozen=True)
class GpuFleetSpec:
    """The compute side. Its capital cost is why this study has a real answer."""

    it_nameplate_mw: float = 100.0
    kw_per_gpu: float = 1.4              # PLACEHOLDER rack-level: GPU + host + net + storage
    capex_per_gpu: float = 35_000.0      # PLACEHOLDER all-in system cost per GPU
    curve_name: str = "h100_llama3_8b_pretrain_mayr2026"

    @property
    def gpu_count(self) -> float:
        return self.it_nameplate_mw * 1000.0 / self.kw_per_gpu

    @property
    def total_capex(self) -> float:
        return self.gpu_count * self.capex_per_gpu


@dataclass(frozen=True)
class Facility:
    """Non-IT load. The part every naive model gets wrong.

    Cooling and electrical losses do **not** scale linearly to zero with IT
    load: chillers, pumps, CRAHs and UPS conversion losses have a large fixed
    component. Modelling PUE as a single multiplier means a 40% GPU throttle
    appears to shed 40% of facility load, which overstates the power a throttle
    actually releases and therefore overstates the value of flexibility.
    """

    pue_at_full_load: float = 1.25       # PLACEHOLDER West Texas, evaporative-assisted
    overhead_fixed_share: float = 0.5    # PLACEHOLDER of the overhead, half is fixed

    def fixed_overhead_mw(self, it_nameplate_mw: float) -> float:
        overhead = (self.pue_at_full_load - 1.0) * it_nameplate_mw
        return overhead * self.overhead_fixed_share

    def variable_multiplier(self) -> float:
        overhead = self.pue_at_full_load - 1.0
        return 1.0 + overhead * (1.0 - self.overhead_fixed_share)


@dataclass(frozen=True)
class StoragePhysics:
    charge_efficiency: float = 0.95      # one-way; 0.90 round-trip
    discharge_efficiency: float = 0.95
    soc_min_fraction: float = 0.10       # usable-window floor
    soc_max_fraction: float = 1.00


@dataclass(frozen=True)
class Limits:
    """Physical and regulatory ceilings the optimiser may not exceed."""

    max_grid_mw: float | None = None     # None = unconstrained interconnection (fiction)
    max_pv_mw: float | None = None       # land-limited in practice: ~5 acres/MW-DC
    # Air permits are the binding constraint on backup generation, not fuel cost.
    # Texas emergency-engine permits typically cap non-emergency operation at
    # order-100 hours/year. Leaving this unbounded is how a model concludes
    # "cheap gas dominates" when what it has actually built is an unpermittable
    # merchant power plant.
    #
    # NAME IT HONESTLY: this caps annual generator *energy*, expressed as
    # equivalent full-load hours, because an energy cap is linear and an
    # operating-hour cap is not -- counting hours needs a binary per hour. A
    # permit caps hours. So a plant that runs 1,500 hours at a third of load
    # satisfies this constraint and would violate the real one. The gap is a
    # declared V5 item; until then, read generator run-hours in the results as
    # a diagnostic, never as a compliance claim.
    gen_annual_full_load_hours: float = 500.0  # PLACEHOLDER; sweep it, do not trust it


@dataclass(frozen=True)
class Scenario:
    name: str = "west_texas_v1"
    financing: Financing = field(default_factory=Financing)
    costs: TechCosts = field(default_factory=TechCosts)
    gpus: GpuFleetSpec = field(default_factory=GpuFleetSpec)
    facility: Facility = field(default_factory=Facility)
    storage: StoragePhysics = field(default_factory=StoragePhysics)
    limits: Limits = field(default_factory=Limits)

    def as_dict(self) -> dict:
        return asdict(self)
