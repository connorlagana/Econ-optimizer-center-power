/**
 * The arithmetic that makes this a tool instead of a report.
 *
 * `ann_gpu = gpu_count * capex_per_gpu * crf(rate, life)` is added to the
 * planner's objective but is not a function of any decision variable, so it
 * cannot change the argmin. For a fixed (site, year, interconnection, compute
 * target, mode) the optimal *design* is therefore invariant to every GPU
 * parameter, and only the reported levelised cost moves. Which means the
 * browser can recompute the headline for any GPU basis with no solver in the
 * loop:
 *
 *     lcoc = infra/(compute_hours * gpu_count) + capex*crf/compute_hours
 *
 * The second term is where the fleet size cancels: more GPUs cost more and
 * produce proportionally more, so only the per-GPU capex survives.
 *
 * `itNameplateMw` is deliberately NOT exposed as a slider. Scaling the fleet
 * without scaling the interconnection ceiling changes the physics — the plant
 * has to serve a different load against the same wire — so it needs a solve.
 * It is a parameter here only so the identity above is written honestly.
 */

import type { Cell, GpuKnobs, StripRow } from './types';

/** Capital recovery factor: the annuity that repays $1 over `life` years. */
export function crf(discountRate: number, lifeYears: number): number {
  if (discountRate === 0) return 1 / lifeYears;
  const growth = Math.pow(1 + discountRate, lifeYears);
  return (discountRate * growth) / (growth - 1);
}

export function gpuCount(knobs: GpuKnobs): number {
  return (knobs.itNameplateMw * 1000) / knobs.kwPerGpu;
}

/** Annualised GPU capital for the whole fleet, in dollars per year. */
export function gpuCapitalPerYear(knobs: GpuKnobs): number {
  return gpuCount(knobs) * knobs.capexPerGpu * crf(knobs.discountRate, knobs.lifeYears);
}

type Priceable = Pick<Cell, 'infra_per_year' | 'compute_unit_hours'>;

/** Levelised cost of compute, $/GPU-hour, at an arbitrary GPU basis. */
export function lcoc(cell: Priceable, knobs: GpuKnobs): number {
  const n = gpuCount(knobs);
  const perGpuHour = cell.compute_unit_hours * n;
  if (perGpuHour <= 0) return Number.POSITIVE_INFINITY;
  return (cell.infra_per_year + gpuCapitalPerYear(knobs)) / perGpuHour;
}

/**
 * The number the whole study is about: how much cheaper (negative) or dearer
 * (positive) flexible compute is than rigid compute, in percent.
 */
export function lcocDeltaPct(
  flex: Priceable | undefined,
  rigid: Priceable | undefined,
  knobs: GpuKnobs,
): number | null {
  if (!flex || !rigid) return null;
  const a = lcoc(flex, knobs);
  const b = lcoc(rigid, knobs);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
  return ((a - b) / b) * 100;
}

/** Infrastructure delta in percent — the other true number, for the other audience. */
export function infraDeltaPct(
  flex: Priceable | undefined,
  rigid: Priceable | undefined,
): number | null {
  if (!flex || !rigid || rigid.infra_per_year === 0) return null;
  return ((flex.infra_per_year - rigid.infra_per_year) / rigid.infra_per_year) * 100;
}

/**
 * Linear interpolation of the interconnection at which the LCOC delta crosses
 * zero. Returns null when the sign never changes across the sampled ceilings,
 * which is a real answer — at a high enough GPU capex it never pays.
 */
export function crossoverMw(
  points: { ceiling: number; delta: number | null }[],
): number | null {
  const pts = points
    .filter((p): p is { ceiling: number; delta: number } => p.delta !== null)
    .sort((a, b) => a.ceiling - b.ceiling);
  for (let i = 0; i < pts.length - 1; i += 1) {
    const lo = pts[i];
    const hi = pts[i + 1];
    if ((lo.delta <= 0 && hi.delta >= 0) || (lo.delta >= 0 && hi.delta <= 0)) {
      if (lo.delta === hi.delta) return lo.ceiling;
      const t = -lo.delta / (hi.delta - lo.delta);
      return lo.ceiling + t * (hi.ceiling - lo.ceiling);
    }
  }
  return null;
}

/**
 * The GPU price at which the trade-off exactly breaks even at one grid size.
 *
 * The slider shows the threshold moving, which is a picture. This is the
 * sentence: "below about $12,000 a chip, slowing down pays even on a full-size
 * grid connection." Found by bisection on the fact that the gap widens
 * monotonically as chips get more expensive — a costlier chip makes an idle
 * hour costlier, and nothing else in the comparison moves.
 */
export function capexAtBreakEven(
  deltaAtCapex: (capex: number) => number | null,
  bounds: [number, number] = [500, 250_000],
): number | null {
  const [lowCapex, highCapex] = bounds;
  const atLow = deltaAtCapex(lowCapex);
  const atHigh = deltaAtCapex(highCapex);
  if (atLow === null || atHigh === null) return null;
  // Cheap chips should favour slowing down and dear ones should not. If the
  // sign does not turn over inside the bracket there is no break-even to report.
  if (atLow > 0 || atHigh < 0) return null;

  let lo = lowCapex;
  let hi = highCapex;
  for (let i = 0; i < 60; i += 1) {
    const mid = (lo + hi) / 2;
    const d = deltaAtCapex(mid);
    if (d === null) return null;
    if (d < 0) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

export type { StripRow };
