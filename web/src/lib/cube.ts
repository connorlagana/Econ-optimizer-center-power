/** Indexing and selection over the precomputed cube. No arithmetic lives here. */

import type { Cell, Cube, Mode, StripRow } from './types';

export const HOURS_PER_YEAR = 8760;

function key(site: string, year: number, ceiling: number, mode: Mode, target: number): string {
  return `${site}|${year}|${ceiling.toFixed(1)}|${mode}|${target.toFixed(4)}`;
}

export class CubeIndex {
  private readonly byKey: Map<string, Cell>;

  constructor(readonly cube: Cube) {
    this.byKey = new Map(cube.cells.map((c) => [key(
      c.site, c.year, c.grid_ceiling_mw, c.mode, c.compute_target,
    ), c]));
  }

  /** Rigid is solved once per (site, year, ceiling) — its target is always 1.0. */
  rigid(site: string, year: number, ceiling: number): Cell | undefined {
    return this.byKey.get(key(site, year, ceiling, 'rigid', 1.0));
  }

  flex(site: string, year: number, ceiling: number, target: number): Cell | undefined {
    return this.byKey.get(key(site, year, ceiling, 'powercap', target));
  }

  /** The frontier at one interconnection: every compute target, ascending. */
  frontier(site: string, year: number, ceiling: number): Cell[] {
    return this.cube.axes.compute_targets
      .map((t) => this.flex(site, year, ceiling, t))
      .filter((c): c is Cell => c !== undefined)
      .sort((a, b) => a.compute_target - b.compute_target);
  }

  get sites(): string[] { return Object.keys(this.cube.axes.sites); }
  get years(): number[] { return this.cube.axes.years; }
  get ceilings(): number[] { return this.cube.axes.grid_ceilings_mw; }
  get targets(): number[] { return this.cube.axes.compute_targets; }
}

/** Figure 3's rows, keyed the same way but from the fourteen-year sweep. */
export function stripLookup(rows: StripRow[]) {
  const map = new Map<string, StripRow>();
  for (const r of rows) {
    map.set(key(r.site, r.year, r.grid_ceiling_mw, r.mode, r.compute_target), r);
  }
  return {
    rigid: (site: string, year: number, ceiling: number) =>
      map.get(key(site, year, ceiling, 'rigid', 1.0)),
    flex: (site: string, year: number, ceiling: number, target: number) =>
      map.get(key(site, year, ceiling, 'powercap', target)),
  };
}

export const SITE_LABEL: Record<string, string> = {
  dallas: 'Dallas',
  west_texas: 'Midland-Odessa',
};

export function siteLabel(name: string): string {
  return SITE_LABEL[name] ?? name;
}

/**
 * How much of one (site, year) slice has actually been solved.
 *
 * A chart cannot tell a missing answer from an absent effect: an unsolved grid
 * size looks like a gap, a line drawn through it invents a trend, and "no sign
 * change here" and "not worked out yet" render identically. So the page asks
 * this before it makes any claim about a slice.
 */
export function sliceProgress(cube: Cube, site: string, year: number) {
  const s = cube.provenance.slices?.[`${site}|${year}`];
  if (!s) return { solved: 0, expected: 0, complete: false, fraction: 0 };
  return {
    solved: s.solved,
    expected: s.expected,
    complete: s.complete,
    fraction: s.expected > 0 ? s.solved / s.expected : 0,
  };
}
