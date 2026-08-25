import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { capexAtBreakEven, crf, crossoverMw, gpuCount, lcoc, lcocDeltaPct } from './lcoc';
import type { Cube, GpuKnobs } from './types';

const CUBE_PATH = join(process.cwd(), 'public', 'cube.json');

function defaults(cube: Cube): GpuKnobs {
  return {
    capexPerGpu: cube.free_axes.capex_per_gpu,
    kwPerGpu: cube.free_axes.kw_per_gpu,
    lifeYears: cube.free_axes.gpu_life_years,
    discountRate: cube.free_axes.discount_rate,
    itNameplateMw: cube.free_axes.it_nameplate_mw,
  };
}

describe('crf', () => {
  it('is 1/n at a zero discount rate', () => {
    expect(crf(0, 20)).toBeCloseTo(0.05, 12);
  });

  it('matches the textbook annuity factor', () => {
    // 8% over 5 years: 0.08 * 1.08^5 / (1.08^5 - 1)
    expect(crf(0.08, 5)).toBeCloseTo(0.2504564546, 9);
  });
});

describe('gpuCount', () => {
  it('divides nameplate by rack-level draw', () => {
    const knobs: GpuKnobs = {
      capexPerGpu: 35000, kwPerGpu: 1.4, lifeYears: 5,
      discountRate: 0.08, itNameplateMw: 100,
    };
    expect(gpuCount(knobs)).toBeCloseTo(71428.5714, 4);
  });
});

describe('crossoverMw', () => {
  it('interpolates the zero crossing', () => {
    const at = crossoverMw([
      { ceiling: 60, delta: -1 },
      { ceiling: 80, delta: 1 },
    ]);
    expect(at).toBeCloseTo(70, 9);
  });

  it('returns null when the sign never changes', () => {
    expect(crossoverMw([
      { ceiling: 60, delta: -1 },
      { ceiling: 80, delta: -2 },
    ])).toBeNull();
  });

  it('ignores cells that failed to solve', () => {
    const at = crossoverMw([
      { ceiling: 60, delta: -1 },
      { ceiling: 70, delta: null },
      { ceiling: 80, delta: 1 },
    ]);
    expect(at).toBeCloseTo(70, 9);
  });
});

// The load-bearing test: the browser's arithmetic has to reproduce the
// optimiser's own reported LCOC on every cell, or the sliders are quietly
// showing a different study than the one that was solved.
describe('against the solved cube', () => {
  it.skipIf(!existsSync(CUBE_PATH))('reproduces every cell at the default basis', () => {
    const cube = JSON.parse(readFileSync(CUBE_PATH, 'utf8')) as Cube;
    const knobs = defaults(cube);
    expect(cube.cells.length).toBeGreaterThan(0);
    for (const cell of cube.cells) {
      expect(lcoc(cell, knobs)).toBeCloseTo(cell.lcoc_default_basis, 9);
    }
  });

  it.skipIf(!existsSync(CUBE_PATH))('moves the flexibility verdict when GPU capital falls', () => {
    const cube = JSON.parse(readFileSync(CUBE_PATH, 'utf8')) as Cube;
    const knobs = defaults(cube);
    const at = (mode: string, ceiling: number, target: number) =>
      cube.cells.find(
        (c) => c.site === 'dallas' && c.year === 2019 && c.mode === mode
          && c.grid_ceiling_mw === ceiling && Math.abs(c.compute_target - target) < 1e-9,
      );

    const rigid = at('rigid', 125, 1.0);
    const flex = at('powercap', 125, 0.98);
    if (!rigid || !flex) return;                 // ceiling not in this cube variant

    const dear = lcocDeltaPct(flex, rigid, knobs);
    const cheap = lcocDeltaPct(flex, rigid, { ...knobs, capexPerGpu: 5000 });
    expect(dear).not.toBeNull();
    expect(cheap).not.toBeNull();
    // Cheaper GPUs shrink the stranded-capital penalty on giving up compute, so
    // the trade always moves in the favourable direction. This is landmine 1
    // stated as a monotonicity, and it is what the slider is for.
    expect(cheap as number).toBeLessThan(dear as number);
  });
});

describe('capexAtBreakEven', () => {
  it('finds the price where the gap turns over', () => {
    // A gap that is negative below $20k and positive above it.
    const at = capexAtBreakEven((capex) => (capex - 20000) / 10000);
    expect(at).toBeCloseTo(20000, 3);
  });

  it('reports nothing when the sign never turns over in range', () => {
    expect(capexAtBreakEven(() => -1)).toBeNull();
    expect(capexAtBreakEven(() => 1)).toBeNull();
  });

  it('reports nothing when a cell is missing', () => {
    expect(capexAtBreakEven(() => null)).toBeNull();
  });
});
