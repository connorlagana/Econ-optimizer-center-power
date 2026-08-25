/** Shapes of the precomputed cube. Mirrors scripts/build_cube.py. */

export type Mode = 'rigid' | 'powercap';

/** One solved cell. Everything here is a scalar; dispatch arrays are not shipped. */
export interface Cell {
  key: string;
  site: string;
  settlement_point: string;
  year: number;
  grid_ceiling_mw: number;
  mode: Mode;
  compute_target: number;
  status: string;
  /** Annualised cost of everything that makes electricity — GPU capital excluded. */
  infra_per_year: number;
  /** Annual compute, in fleet-equivalent hours. The LCOC denominator, pre-fleet-size. */
  compute_unit_hours: number;
  lcoc_default_basis: number;
  pv_mw: number;
  bess_mw: number;
  bess_mwh: number;
  gen_mw: number;
  grid_mw: number;
  cost_pv: number;
  cost_bess: number;
  cost_gen: number;
  cost_grid_capacity: number;
  cost_grid_energy: number;
  cost_fuel: number;
  coincident_peak_mw: number;
  peak_import_mw: number;
  gen_run_hours: number;
  pv_curtailed_fraction: number;
  mean_it_power_fraction: number;
  mean_price_per_mwh: number;
  negative_price_hours: number;
  solve_seconds: number;
}

export interface SiteMeta {
  latitude: number;
  longitude: number;
  settlement_point: string;
  note: string;
}

export interface Cube {
  schema: number;
  provenance: {
    built_utc: string;
    git_sha: string | null;
    host: string;
    versions: Record<string, string>;
    price_basis: string;
    allow_export: boolean;
    cells: number;
    failed_cells: number;
    /** How many cells a finished cube has. A partial cube must not be read as a finished one. */
    expected_cells: number;
    complete: boolean;
    /** Completeness of each (site, year) slice — the slice a reader actually looks at. */
    slices: Record<string, { site: string; year: number; expected: number; solved: number; complete: boolean }>;
  };
  scenario: Record<string, unknown>;
  free_axes: {
    capex_per_gpu: number;
    kw_per_gpu: number;
    gpu_life_years: number;
    discount_rate: number;
    it_nameplate_mw: number;
    gpu_crf_default: number;
    note: string;
  };
  axes: {
    sites: Record<string, SiteMeta>;
    years: number[];
    grid_ceilings_mw: number[];
    compute_targets: number[];
    modes: Mode[];
  };
  facility_load_mw: number;
  cells: Cell[];
  errors: unknown[];
}

/** The subset of a cell figure 3 needs, recovered from the fourteen-year sweep. */
export interface StripRow {
  site: string;
  year: number;
  grid_ceiling_mw: number;
  mode: Mode;
  compute_target: number;
  infra_per_year: number;
  compute_unit_hours: number;
  pv_mw: number;
  gen_mw: number;
  bess_mwh: number;
}

export interface Strip {
  source: string;
  years: number[];
  sites: Record<string, SiteMeta>;
  grid_ceilings_mw: number[];
  rows: StripRow[];
}

/** The axes that cost nothing to move, because they are not in the argmin. */
export interface GpuKnobs {
  capexPerGpu: number;
  kwPerGpu: number;
  lifeYears: number;
  discountRate: number;
  itNameplateMw: number;
}
