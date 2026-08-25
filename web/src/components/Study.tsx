'use client';

import { useMemo, useState } from 'react';
import { CubeIndex, sliceProgress } from '@/lib/cube';
import type { Cube, GpuKnobs, Strip } from '@/lib/types';
import { SceneControls, GpuControls } from './Controls';
import { SignChange } from './SignChange';
import { Frontier } from './Frontier';
import { YearStrip } from './YearStrip';
import { Provenance } from './Provenance';

/** Where the story starts: give up 2% of the year's work. Figure 2 can change it. */
const OPENING_TARGET = 0.98;

export function Study({ cube, strip }: { cube: Cube; strip: Strip }) {
  const index = useMemo(() => new CubeIndex(cube), [cube]);
  const defaults: GpuKnobs = useMemo(() => ({
    capexPerGpu: cube.free_axes.capex_per_gpu,
    kwPerGpu: cube.free_axes.kw_per_gpu,
    lifeYears: cube.free_axes.gpu_life_years,
    discountRate: cube.free_axes.discount_rate,
    itNameplateMw: cube.free_axes.it_nameplate_mw,
  }), [cube.free_axes]);

  const [knobs, setKnobs] = useState<GpuKnobs>(defaults);
  const [site, setSite] = useState<string>(index.sites[0] ?? 'dallas');
  const [year, setYear] = useState<number>(index.years.includes(2019) ? 2019 : index.years[0]);
  const [ceiling, setCeiling] = useState<number>(
    index.ceilings.includes(60) ? 60 : index.ceilings[0],
  );

  // One shared choice across both figures. Figure 1 asks "at this much slack,
  // how small must the grid connection be?"; figure 2 asks "at this grid
  // connection, how much slack?". If they disagreed, the page would be arguing
  // with itself in front of the reader.
  const nearest = (want: number) => index.targets.reduce(
    (a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a),
  );
  const [target, setTarget] = useState<number>(nearest(OPENING_TARGET));

  const progress = sliceProgress(cube, site, year);

  return (
    <div className="mx-auto max-w-6xl px-5 pb-24 sm:px-8">
      <header className="py-12">
        <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
          Is it cheaper to build a power plant, or to let the computers run slower?
        </h1>
        <div className="mt-5 max-w-3xl space-y-4 text-[17px] leading-relaxed text-ink-secondary">
          <p>
            A large AI data center needs about as much electricity as a small city, and the
            waiting list for a grid connection that size is now measured in years. So operators
            build their own supply instead — solar panels, batteries, backup generators — and
            that gets expensive fast.
          </p>
          <p>
            There is another option nobody used to take seriously: let the computers run a little
            slower on the handful of days when power is tightest, and build a smaller power plant.
            This page works out when that trade is worth making.
          </p>
          <p className="text-ink">
            The short answer is that it depends almost entirely on <strong>how big a grid
            connection you managed to get</strong> — and not on solar, or batteries, or anything
            about the computers themselves.
          </p>
        </div>

        <div className="mt-7 max-w-3xl rounded-lg border border-rule bg-surface-sunken px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">Start here</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-[14px] leading-relaxed text-ink-secondary">
            <li>Look at figure 1 and find where the line crosses zero.</li>
            <li>
              Drag the <strong>price of one chip</strong> slider — the one sitting next to the
              chart — down to $10,000, and watch that crossing point slide to the right. That
              movement is the entire argument.
            </li>
            <li>Figure 3 is the honesty check: does the answer survive a different year?</li>
          </ol>
        </div>
      </header>

      <div className="grid gap-6 border-t border-rule py-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <div className="flex flex-col justify-between gap-6">
          <SceneControls
            sites={index.sites}
            years={index.years}
            site={site}
            year={year}
            onSite={setSite}
            onYear={setYear}
            siteNote={cube.axes.sites[site]?.note ?? ''}
          />
          <p className="max-w-md text-[13px] leading-relaxed text-ink-muted">
            Running flat out, this site would draw{' '}
            <strong className="text-ink-secondary">{cube.facility_load_mw.toFixed(0)} MW</strong> —
            the computers themselves plus the cooling and electrical losses that come with them,
            which do not disappear just because the computers slow down. Every grid connection
            size below is worth reading against that number.
          </p>
        </div>
        <GpuControls knobs={knobs} setKnobs={setKnobs} defaults={defaults} />
      </div>

      <SignChange
        index={index}
        site={site}
        year={year}
        target={target}
        ceiling={ceiling}
        onCeiling={setCeiling}
        knobs={knobs}
        setKnobs={setKnobs}
        defaults={defaults}
        facilityLoadMw={cube.facility_load_mw}
        solved={progress.solved}
        expected={progress.expected}
      />

      <Frontier
        index={index}
        site={site}
        year={year}
        ceiling={ceiling}
        onCeiling={setCeiling}
        target={target}
        onTarget={(t) => setTarget(nearest(t))}
        knobs={knobs}
        setKnobs={setKnobs}
        defaults={defaults}
        solved={progress.solved}
        expected={progress.expected}
      />

      <YearStrip strip={strip} knobs={knobs} facilityLoadMw={cube.facility_load_mw} />

      <Provenance cube={cube} />
    </div>
  );
}
