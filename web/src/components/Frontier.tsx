'use client';

import { useMemo } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceDot, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { CubeIndex } from '@/lib/cube';
import { lcoc } from '@/lib/lcoc';
import { procurable } from '@/lib/format';
import type { GpuKnobs } from '@/lib/types';
import { ChipPriceSlider } from './Controls';
import {
  EstimatedCostBasis, Figure, IncompleteNotice, NumbersTable, Verdict,
} from './Figure';

const AXIS = { fontSize: 12, fill: 'var(--ink-muted)' };
const TIP = {
  background: 'var(--surface-raised)', border: '1px solid var(--rule)',
  borderRadius: 8, fontSize: 12, color: 'var(--ink)',
};

export function Frontier({
  index, site, year, ceiling, onCeiling, target, onTarget, knobs, setKnobs, defaults,
  solved, expected,
}: {
  index: CubeIndex;
  site: string;
  year: number;
  ceiling: number;
  onCeiling: (c: number) => void;
  target: number;
  onTarget: (t: number) => void;
  knobs: GpuKnobs;
  setKnobs: (k: GpuKnobs) => void;
  defaults: GpuKnobs;
  solved: number;
  expected: number;
}) {
  const rigid = index.rigid(site, year, ceiling);
  const cells = useMemo(() => index.frontier(site, year, ceiling), [index, site, year, ceiling]);

  const data = useMemo(() => cells.map((c) => ({
    target: c.compute_target * 100,
    cost: lcoc(c, knobs),
    solar: c.cost_pv / 1e6,
    batteries: c.cost_bess / 1e6,
    generators: c.cost_gen / 1e6,
    grid: (c.cost_grid_capacity + c.cost_grid_energy + c.cost_fuel) / 1e6,
    genMw: c.gen_mw,
    bessMwh: c.bess_mwh,
    pvMw: c.pv_mw,
    plant: c.infra_per_year / 1e6,
  })), [cells, knobs]);

  const rigidCost = rigid ? lcoc(rigid, knobs) : null;
  const best = data.length ? data.reduce((a, b) => (b.cost < a.cost ? b : a)) : null;
  const bestCell = best ? cells.find((c) => c.compute_target * 100 === best.target) : undefined;
  const bestGap = best && rigidCost ? ((best.cost - rigidCost) / rigidCost) * 100 : null;
  const genRange = data.length
    ? { max: Math.max(...data.map((d) => d.genMw)), min: Math.min(...data.map((d) => d.genMw)) }
    : null;

  return (
    <Figure
      index={2}
      title="How much slower should it be allowed to run?"
      notice={<IncompleteNotice solved={solved} expected={expected} />}
      claim={
        <>
          <p>
            More slack is not better. Reading right to left, the site is allowed to give up more
            and more work over the year. The power plant keeps getting cheaper the whole way —
            but the cost of an hour of computing bottoms out and then climbs, because past a
            point you are throwing away more work than you are saving in equipment.
          </p>
          <p className="mt-2">
            The dip is shallow and it is not where you might guess. The right answer is a couple
            of percent, not eight.
          </p>
        </>
      }
      caveat={
        <>
          <strong>Trust the totals, not the mix.</strong> Near the bottom of a shallow dip,
          several different combinations of generators and batteries cost almost exactly the
          same, and the model just picks one — which is why the generator column jumps around
          instead of falling smoothly. The cost curve and the totals are solid. Before quoting a
          specific mix, pin the total and re-solve.
        </>
      }
    >
      <div className="mb-4"><EstimatedCostBasis /></div>

      <div className="mb-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wider text-ink-muted">
            Grid connection
          </span>
          <select
            className="rounded-md border border-rule bg-surface-raised px-2.5 py-1.5 text-sm text-ink focus:outline-none"
            value={ceiling}
            onChange={(e) => onCeiling(Number(e.target.value))}
          >
            {index.ceilings.slice().sort((a, b) => b - a).map((c) => (
              <option key={c} value={c}>{c} MW{c === 0 ? ' — none at all' : ''}</option>
            ))}
          </select>
        </label>

        {best && bestCell && (
          <>
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-muted">Best answer here</div>
              <div className="tnum text-xl font-semibold text-ink">
                give up {(100 - best.target).toFixed(0)}% of the work
              </div>
              <button
                type="button"
                onClick={() => onTarget(best.target / 100)}
                className="text-[12px] text-ink-secondary underline underline-offset-2 hover:text-ink"
              >
                use this in figure 1
              </button>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-muted">
                vs never slowing down
              </div>
              <div className="tnum text-xl font-semibold">
                <Verdict value={bestGap}>
                  {bestGap === null ? '—' : `${bestGap < 0 ? '−' : '+'}${Math.abs(bestGap).toFixed(2)}%`}
                </Verdict>
              </div>
              <div className="text-[12px] text-ink-muted">cost of an hour of computing</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-muted">Backup generators</div>
              <div className="tnum text-xl font-semibold text-ink">
                {rigid ? `${rigid.gen_mw.toFixed(0)} → ${bestCell.gen_mw.toFixed(1)} MW` : '—'}
              </div>
              <div className="text-[12px] text-ink-muted">
                you would actually buy {procurable(bestCell.gen_mw, 2).toFixed(0)} MW — they come
                in 2 MW units
              </div>
            </div>
          </>
        )}
        </div>
        <ChipPriceSlider knobs={knobs} setKnobs={setKnobs} defaults={defaults} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="min-w-0">
          <div className="mb-1 text-xs uppercase tracking-wider text-ink-muted">
            Cost of an hour of computing, all in
          </div>
          <div className="h-[240px] sm:h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data}
                margin={{ top: 8, right: 12, bottom: 22, left: 4 }}
                onClick={(e) => {
                  const picked = Number(e?.activeLabel);
                  if (Number.isFinite(picked)) onTarget(picked / 100);
                }}
              >
                <CartesianGrid stroke="var(--rule)" vertical={false} />
                <XAxis
                  dataKey="target" type="number" reversed
                  domain={['dataMin', 'dataMax']} tick={AXIS} stroke="var(--rule-strong)"
                  tickFormatter={(v: number) => `${(100 - v).toFixed(0)}%`}
                  label={{
                    value: 'share of the year’s work given up', position: 'insideBottom', offset: -12,
                    style: { ...AXIS, textAnchor: 'middle' },
                  }}
                />
                <YAxis
                  tick={AXIS} stroke="var(--rule-strong)" width={52}
                  domain={['auto', 'auto']} tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                />
                {rigidCost && (
                  <ReferenceLine
                    y={rigidCost} stroke="var(--rigid)" strokeDasharray="5 4" strokeWidth={1.5}
                    label={{
                      value: 'never slowing down', position: 'insideTopRight',
                      style: { ...AXIS, fill: 'var(--rigid)' },
                    }}
                  />
                )}
                {best && (
                  <ReferenceDot
                    x={best.target} y={best.cost} r={5}
                    fill="var(--flex)" stroke="var(--surface-raised)" strokeWidth={2}
                  />
                )}
                <ReferenceLine x={target * 100} stroke="var(--rule-strong)" strokeDasharray="2 3" />
                <Tooltip
                  contentStyle={TIP}
                  formatter={(v) => [typeof v === 'number' ? `$${v.toFixed(4)} per chip-hour` : '—', 'cost']}
                  labelFormatter={(v) => `giving up ${(100 - Number(v)).toFixed(0)}% of the work`}
                />
                <Line
                  type="monotone" dataKey="cost" stroke="var(--flex)" strokeWidth={2.25}
                  dot={{ r: 3, fill: 'var(--flex)', strokeWidth: 0 }}
                  connectNulls={false} isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="min-w-0">
          <div className="mb-1 text-xs uppercase tracking-wider text-ink-muted">
            What the money buys, $M a year — the generators go first
          </div>
          <div className="h-[240px] sm:h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 8, right: 12, bottom: 22, left: 4 }}>
                <CartesianGrid stroke="var(--rule)" vertical={false} />
                <XAxis
                  dataKey="target" reversed tick={AXIS} stroke="var(--rule-strong)"
                  tickFormatter={(v: number) => `${(100 - v).toFixed(0)}%`}
                  label={{
                    value: 'share of the year’s work given up', position: 'insideBottom', offset: -12,
                    style: { ...AXIS, textAnchor: 'middle' },
                  }}
                />
                <YAxis tick={AXIS} stroke="var(--rule-strong)" width={44}
                  tickFormatter={(v: number) => `$${v}M`} />
                <Tooltip
                  contentStyle={TIP}
                  formatter={(v, n) => [typeof v === 'number' ? `$${v.toFixed(1)}M` : '—', String(n)]}
                  labelFormatter={(v) => `giving up ${(100 - Number(v)).toFixed(0)}% of the work`}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: 'var(--ink-muted)' }} />
                <Bar dataKey="solar" stackId="a" name="solar" fill="var(--flex)" isAnimationActive={false} />
                <Bar dataKey="batteries" stackId="a" name="batteries" fill="var(--rigid)" isAnimationActive={false} />
                <Bar dataKey="generators" stackId="a" name="generators" fill="var(--unfavourable)" isAnimationActive={false} />
                <Bar dataKey="grid" stackId="a" name="grid + fuel" fill="var(--rule-strong)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {genRange && (
            <p className="mt-2 text-[12px] leading-snug text-ink-muted">
              Backup generators across this chart: {genRange.max.toFixed(0)} MW down to{' '}
              {genRange.min.toFixed(1)} MW. Batteries barely move by comparison. What a little
              slack buys you is not having to build the machinery that exists purely to survive
              the worst few hours of the year.
            </p>
          )}
        </div>
      </div>

      <NumbersTable
        columns={[
          'work given up', 'cost per chip-hour', 'power plant $M/yr',
          'solar MW', 'batteries MWh', 'generators MW',
        ]}
        rows={data.map((d) => [
          `${(100 - d.target).toFixed(0)}%`,
          `$${d.cost.toFixed(4)}`,
          `$${d.plant.toFixed(1)}M`,
          d.pvMw.toFixed(1),
          Math.round(d.bessMwh).toLocaleString('en-US'),
          d.genMw.toFixed(1),
        ])}
      />
    </Figure>
  );
}
