'use client';

import type { GpuKnobs } from '@/lib/types';
import { crf, gpuCapitalPerYear, gpuCount } from '@/lib/lcoc';
import { Estimated } from './Figure';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wider text-ink-muted">{label}</span>
      {children}
    </label>
  );
}

const selectClass =
  'rounded-md border border-rule bg-surface-raised px-2.5 py-1.5 text-sm text-ink '
  + 'focus:border-rule-strong focus:outline-none';

export function SceneControls({
  sites, years, site, year, onSite, onYear, siteNote,
}: {
  sites: string[];
  years: number[];
  site: string;
  year: number;
  onSite: (s: string) => void;
  onYear: (y: number) => void;
  siteNote: string;
}) {
  const label: Record<string, string> = {
    dallas: 'Dallas, Texas',
    west_texas: 'Midland-Odessa, West Texas',
  };
  return (
    <div className="flex flex-wrap items-end gap-x-5 gap-y-4">
      <Field label="Where">
        <select className={selectClass} value={site} onChange={(e) => onSite(e.target.value)}>
          {sites.map((s) => <option key={s} value={s}>{label[s] ?? s}</option>)}
        </select>
      </Field>
      <Field label="Which year's weather and prices">
        <select className={selectClass} value={year} onChange={(e) => onYear(Number(e.target.value))}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </Field>
      <p className="max-w-sm text-[13px] leading-snug text-ink-muted">{siteNote}</p>
    </div>
  );
}

/**
 * The chip panel.
 *
 * Nothing in here can change what the best power plant is. Chip cost enters the
 * sum as a fixed amount that is the same whichever plant you build, so moving
 * these changes what the answer costs and never which answer wins. That is why
 * there is no spinner: no solving happens when a slider moves.
 */
export function GpuControls({
  knobs, setKnobs, defaults,
}: {
  knobs: GpuKnobs;
  setKnobs: (k: GpuKnobs) => void;
  defaults: GpuKnobs;
}) {
  const perChipHour = (knobs.capexPerGpu * crf(knobs.discountRate, knobs.lifeYears)) / 8760;
  const changed = JSON.stringify(knobs) !== JSON.stringify(defaults);

  return (
    <div className="rounded-lg border border-rule bg-surface-raised p-5">
      <div className="mb-1 flex items-baseline justify-between gap-4">
        <h3 className="text-sm font-semibold tracking-tight text-ink">
          What the chips cost — try changing these
        </h3>
        {changed && (
          <button
            type="button"
            onClick={() => setKnobs(defaults)}
            className="text-xs text-ink-muted underline underline-offset-2 hover:text-ink"
          >
            put them back
          </button>
        )}
      </div>
      <p className="mb-5 text-[13px] leading-relaxed text-ink-secondary">
        The chips are by far the most expensive thing here — far more than everything that makes
        the electricity. That is why an idle hour hurts so much, and it is what decides the whole
        question. Move a slider and every chart below updates instantly.
      </p>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label={`Price of one chip — $${knobs.capexPerGpu.toLocaleString('en-US')}`}>
          <input
            type="range" min={5000} max={60000} step={1000}
            value={knobs.capexPerGpu}
            onChange={(e) => setKnobs({ ...knobs, capexPerGpu: Number(e.target.value) })}
          />
        </Field>
        <Field label={`Years before it is written off — ${knobs.lifeYears}`}>
          <input
            type="range" min={2} max={10} step={1}
            value={knobs.lifeYears}
            onChange={(e) => setKnobs({ ...knobs, lifeYears: Number(e.target.value) })}
          />
        </Field>
        <Field label={`Cost of borrowing — ${(knobs.discountRate * 100).toFixed(1)}% a year`}>
          <input
            type="range" min={0} max={0.2} step={0.005}
            value={knobs.discountRate}
            onChange={(e) => setKnobs({ ...knobs, discountRate: Number(e.target.value) })}
          />
        </Field>
        <Field label={`Power one chip draws — ${knobs.kwPerGpu.toFixed(2)} kW`}>
          <input
            type="range" min={0.5} max={3} step={0.05}
            value={knobs.kwPerGpu}
            onChange={(e) => setKnobs({ ...knobs, kwPerGpu: Number(e.target.value) })}
          />
        </Field>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-rule pt-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-wider text-ink-muted">Chips on site</dt>
          <dd className="tnum text-ink">{Math.round(gpuCount(knobs)).toLocaleString('en-US')}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-ink-muted">They cost</dt>
          <dd className="tnum text-ink">${(gpuCapitalPerYear(knobs) / 1e6).toFixed(0)}M a year</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-ink-muted">An idle hour wastes</dt>
          <dd className="tnum text-ink">${perChipHour.toFixed(2)} per chip</dd>
        </div>
      </dl>
      <p className="mt-3 text-[12px] leading-relaxed text-ink-muted">
        That last number is the one to hold on to. An hour where a chip sits idle throws away
        about ${perChipHour.toFixed(2)} of what you paid for it — while the electricity that hour
        would have used costs around six cents. Roughly fifteen to one. Any argument for slowing
        down to save on power has to clear that gap first. All four sliders start from{' '}
        <Estimated>estimated figures</Estimated>, not quotes.
      </p>
    </div>
  );
}

/**
 * A compact chip-price slider that sits next to a chart.
 *
 * The full panel above is fine for setting up a scenario, but it scrolls out of
 * view exactly when you want it: the whole point of this control is to drag it
 * and watch a line move, and you cannot do that if the line is off-screen. So
 * the one slider worth dragging live is repeated beside each chart it affects.
 * The other three are set-and-forget and stay in the panel.
 */
export function ChipPriceSlider({
  knobs, setKnobs, defaults,
}: {
  knobs: GpuKnobs;
  setKnobs: (k: GpuKnobs) => void;
  defaults: GpuKnobs;
}) {
  const changed = knobs.capexPerGpu !== defaults.capexPerGpu;
  return (
    <div className="rounded-lg border border-rule bg-surface-raised p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-wider text-ink-muted">
          Price of one chip
        </span>
        {changed && (
          <button
            type="button"
            onClick={() => setKnobs({ ...knobs, capexPerGpu: defaults.capexPerGpu })}
            className="text-[11px] text-ink-muted underline underline-offset-2 hover:text-ink"
          >
            back to ${(defaults.capexPerGpu / 1000).toFixed(0)}k
          </button>
        )}
      </div>
      <div className="tnum mt-0.5 text-2xl font-semibold text-ink">
        ${knobs.capexPerGpu.toLocaleString('en-US')}
      </div>
      <input
        className="mt-2"
        type="range" min={5000} max={60000} step={1000}
        value={knobs.capexPerGpu}
        aria-label="Price of one chip, in dollars"
        onChange={(e) => setKnobs({ ...knobs, capexPerGpu: Number(e.target.value) })}
      />
      <div className="flex justify-between text-[11px] text-ink-muted">
        <span>$5k</span>
        <span>$60k</span>
      </div>
      <p className="mt-1.5 text-[12px] leading-snug text-ink-muted">
        Drag it and watch the chart move. Nothing is being re-solved — the answers are
        already worked out.
      </p>
    </div>
  );
}
