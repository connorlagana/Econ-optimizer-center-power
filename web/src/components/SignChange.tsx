'use client';

import { useMemo } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell as RCell, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { CubeIndex } from '@/lib/cube';
import { capexAtBreakEven, crossoverMw, infraDeltaPct, lcocDeltaPct } from '@/lib/lcoc';
import type { GpuKnobs } from '@/lib/types';
import { ChipPriceSlider } from './Controls';
import {
  BothNumbers, EstimatedCostBasis, Figure, IncompleteNotice, NumbersTable, Verdict,
} from './Figure';

const AXIS = { fontSize: 12, fill: 'var(--ink-muted)' };
const TIP = {
  background: 'var(--surface-raised)', border: '1px solid var(--rule)',
  borderRadius: 8, fontSize: 12, color: 'var(--ink)',
};

export function SignChange({
  index, site, year, target, ceiling, onCeiling, knobs, setKnobs, defaults, facilityLoadMw,
  solved, expected,
}: {
  index: CubeIndex;
  site: string;
  year: number;
  target: number;
  ceiling: number;
  onCeiling: (c: number) => void;
  knobs: GpuKnobs;
  setKnobs: (k: GpuKnobs) => void;
  defaults: GpuKnobs;
  facilityLoadMw: number;
  solved: number;
  expected: number;
}) {
  const data = useMemo(() => index.ceilings
    .map((c) => {
      const rigid = index.rigid(site, year, c);
      const flex = index.flex(site, year, c, target);
      return {
        ceiling: c,
        gap: lcocDeltaPct(flex, rigid, knobs),
        // The same curve at the study's own chip price, so dragging the slider
        // does not destroy the thing you are comparing against.
        gapAtDefault: lcocDeltaPct(flex, rigid, defaults),
        plant: infraDeltaPct(flex, rigid),
      };
    })
    .sort((a, b) => a.ceiling - b.ceiling), [index, site, year, target, knobs, defaults]);

  const crossing = crossoverMw(data.map((d) => ({ ceiling: d.ceiling, delta: d.gap })));
  const coverage = crossing === null ? null : (crossing / facilityLoadMw) * 100;
  const knobsChanged = knobs.capexPerGpu !== defaults.capexPerGpu;

  // The sentence the slider cannot say on its own: the chip price at which the
  // trade breaks even on a full-size grid connection.
  const fullSize = Math.max(...index.ceilings);
  const breakEven = useMemo(() => capexAtBreakEven((capex) => lcocDeltaPct(
    index.flex(site, year, fullSize, target),
    index.rigid(site, year, fullSize),
    { ...knobs, capexPerGpu: capex },
  )), [index, site, year, fullSize, target, knobs]);

  const readout = (c: number) => {
    const rigid = index.rigid(site, year, c);
    const flex = index.flex(site, year, c, target);
    return { infraPct: infraDeltaPct(flex, rigid), lcocPct: lcocDeltaPct(flex, rigid, knobs) };
  };
  const scarce = index.ceilings.includes(60) ? 60 : index.ceilings[Math.floor(index.ceilings.length / 2)];

  return (
    <Figure
      index={1}
      title="How small does the grid connection have to be before slowing down is worth it?"
      notice={<IncompleteNotice solved={solved} expected={expected} />}
      claim={
        <>
          <p>
            Every dot is one size of grid connection. The line shows what happens to the cost of
            an hour of computing if the site is allowed to run{' '}
            <strong>{((1 - target) * 100).toFixed(0)}% slower over the year</strong> instead of
            never slowing down.
          </p>
          <p className="mt-2">
            Below the line, slowing down is cheaper. Above it, it costs more than it saves. The
            place where the line crosses zero is the whole answer — and it moves when chips get
            cheaper, because a cheaper chip sitting idle wastes less money. Drag the slider
            beside the chart.
          </p>
        </>
      }
      caveat={
        <>
          <strong>Read both numbers, never one.</strong> Slowing down makes the power plant
          20–30% cheaper to build, but the cost of an hour of computing barely moves — because
          the chips themselves are most of that cost, and you still bought all of them. The
          first number is what a site developer cares about. The second is what the person
          paying for the chips cares about. They are the same result.
        </>
      }
    >
      <div className="mb-4"><EstimatedCostBasis /></div>

      <div className="mb-5 lg:hidden">
        <ChipPriceSlider knobs={knobs} setKnobs={setKnobs} defaults={defaults} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0">
          <div className="mb-1 text-xs uppercase tracking-wider text-ink-muted">
            Change in the cost of an hour of computing
          </div>
          <div className="h-[260px] sm:h-[290px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={data}
                margin={{ top: 8, right: 12, bottom: 24, left: 0 }}
                onClick={(e) => {
                  // activeLabel is the x value under the cursor — the grid size.
                  const picked = Number(e?.activeLabel);
                  if (Number.isFinite(picked)) onCeiling(picked);
                }}
              >
                <CartesianGrid stroke="var(--rule)" vertical={false} />
                <XAxis
                  dataKey="ceiling" type="number" domain={['dataMin', 'dataMax']}
                  tick={AXIS} stroke="var(--rule-strong)"
                  label={{
                    value: 'size of the grid connection (MW)', position: 'insideBottom', offset: -14,
                    style: { ...AXIS, textAnchor: 'middle' },
                  }}
                />
                <YAxis
                  tick={AXIS} stroke="var(--rule-strong)" width={58}
                  tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
                />
                <ReferenceLine y={0} stroke="var(--ink)" strokeWidth={1.25} />
                <ReferenceLine
                  x={facilityLoadMw} stroke="var(--rule-strong)" strokeDasharray="4 4"
                  label={{ value: 'everything it needs', position: 'insideTopLeft', style: AXIS }}
                />
                <ReferenceLine
                  x={ceiling} stroke="var(--rigid)" strokeWidth={1.25} strokeOpacity={0.5}
                  label={{ value: 'figure 2', position: 'insideBottomLeft', style: { ...AXIS, fill: 'var(--rigid)' } }}
                />
                {crossing !== null && (
                  <ReferenceLine
                    x={crossing} stroke="var(--flex)" strokeWidth={1.5}
                    label={{
                      value: `breaks even at ${crossing.toFixed(0)} MW`,
                      position: 'insideBottomRight', style: { ...AXIS, fill: 'var(--flex)' },
                    }}
                  />
                )}
                <Tooltip
                  contentStyle={TIP}
                  formatter={(v, n) => [
                    typeof v === 'number' ? `${v > 0 ? '+' : ''}${v.toFixed(3)}%` : 'not worked out yet',
                    n === 'gapAtDefault' ? "at the study's chip price" : 'at your chip price',
                  ]}
                  labelFormatter={(v) => `${v} MW grid connection`}
                />
                {knobsChanged && (
                  <Line
                    type="monotone" dataKey="gapAtDefault" stroke="var(--rule-strong)"
                    strokeWidth={1.5} strokeDasharray="4 3" dot={false}
                    connectNulls={false} isAnimationActive={false}
                  />
                )}
                {/* connectNulls is deliberately off: a straight line drawn across
                    a grid size nobody has solved for is an invented result. */}
                <Line
                  type="monotone" dataKey="gap" stroke="var(--flex)" strokeWidth={2.25}
                  dot={{ r: 3, fill: 'var(--flex)', strokeWidth: 0 }}
                  connectNulls={false} isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 mb-1 text-xs uppercase tracking-wider text-ink-muted">
            Change in the cost of the power plant — same result, the other audience
          </div>
          <div className="h-[120px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="var(--rule)" vertical={false} />
                <XAxis dataKey="ceiling" type="number" domain={['dataMin', 'dataMax']} hide />
                <YAxis
                  tick={AXIS} stroke="var(--rule-strong)" width={58}
                  tickFormatter={(v: number) => `${v.toFixed(0)}%`}
                />
                <ReferenceLine y={0} stroke="var(--ink)" />
                <Tooltip
                  contentStyle={TIP}
                  formatter={(v) => [
                    typeof v === 'number' ? `${v.toFixed(1)}%` : 'not worked out yet',
                    'power plant cost',
                  ]}
                  labelFormatter={(v) => `${v} MW grid connection`}
                />
                <Bar dataKey="plant" isAnimationActive={false} maxBarSize={22}>
                  {data.map((d) => (
                    <RCell
                      key={d.ceiling}
                      fill={d.plant === null ? 'var(--rule)'
                        : d.plant < 0 ? 'var(--favourable)' : 'var(--unfavourable)'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <NumbersTable
            columns={[
              'grid connection', 'cost of an hour of computing', 'cost of the power plant',
            ]}
            rows={data.map((d) => [
              `${d.ceiling} MW`,
              d.gap === null ? 'not worked out yet' : `${d.gap > 0 ? '+' : ''}${d.gap.toFixed(3)}%`,
              d.plant === null ? 'not worked out yet' : `${d.plant.toFixed(1)}%`,
            ])}
          />
        </div>

        <div className="flex flex-col gap-4">
          <div className="hidden lg:sticky lg:top-6 lg:z-10 lg:block">
            <ChipPriceSlider knobs={knobs} setKnobs={setKnobs} defaults={defaults} />
          </div>
          <div className="rounded-lg border border-rule bg-surface-sunken p-4">
            <div className="text-xs uppercase tracking-wider text-ink-muted">Breaks even at</div>
            {crossing === null ? (
              <>
                <div className="mt-1 text-lg font-semibold text-ink">
                  {solved < expected ? 'not enough answers yet' : 'never, at any size'}
                </div>
                <p className="mt-1 text-[13px] leading-snug text-ink-secondary">
                  {solved < expected
                    ? 'Some grid sizes for this site and year are still being computed. Come back when the chart has filled in.'
                    : 'At this chip price, slowing down never pays for itself — at any size of grid connection shown.'}
                </p>
              </>
            ) : (
              <>
                <div className="tnum mt-1 text-2xl font-semibold text-ink">
                  {crossing.toFixed(0)} MW
                </div>
                <p className="mt-1 text-[13px] leading-snug text-ink-secondary">
                  That is {coverage!.toFixed(0)}% of what the site would draw flat out. With a
                  smaller connection than this, letting the computers run{' '}
                  {((1 - target) * 100).toFixed(0)}% slower saves money. With a bigger one, it
                  costs money.
                </p>
              </>
            )}
          </div>

          <div className="rounded-lg border border-rule bg-surface-sunken p-4">
            <div className="text-xs uppercase tracking-wider text-ink-muted">
              The chip price that decides it
            </div>
            {breakEven === null ? (
              <p className="mt-1 text-[13px] leading-snug text-ink-secondary">
                No chip price in a sensible range flips the answer at a full-size{' '}
                {fullSize} MW connection.
              </p>
            ) : (
              <>
                <div className="tnum mt-1 text-2xl font-semibold text-ink">
                  ${Math.round(breakEven / 100) * 100 >= 1000
                    ? `${(breakEven / 1000).toFixed(1)}k`
                    : Math.round(breakEven)}
                </div>
                <p className="mt-1 text-[13px] leading-snug text-ink-secondary">
                  per chip. Below that, slowing down pays even on a full-size {fullSize} MW
                  connection — the case where it normally loses. Today&rsquo;s assumption is $
                  {knobs.capexPerGpu.toLocaleString('en-US')}.
                </p>
              </>
            )}
          </div>

          <div className="rounded-lg border border-rule p-4">
            <BothNumbers label={`Full-size connection — ${fullSize} MW`} {...readout(fullSize)} />
          </div>
          <div className="rounded-lg border border-rule p-4">
            <BothNumbers label={`Squeezed connection — ${scarce} MW`} {...readout(scarce)} />
          </div>
          <p className="text-[12px] leading-snug text-ink-muted">
            <Verdict value={-1}>down</Verdict> means cheaper. <Verdict value={1}>up</Verdict>{' '}
            means dearer. Click any point on the chart to send that grid size to figure 2.
          </p>
        </div>
      </div>
    </Figure>
  );
}
