'use client';

import { useMemo } from 'react';
import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip,
  XAxis, YAxis, ZAxis,
} from 'recharts';
import { siteLabel, stripLookup } from '@/lib/cube';
import { lcocDeltaPct } from '@/lib/lcoc';
import type { GpuKnobs, Strip } from '@/lib/types';
import { EstimatedCostBasis, Figure, NumbersTable, Verdict } from './Figure';

const AXIS = { fontSize: 12, fill: 'var(--ink-muted)' };
const TARGET = 0.98;

interface Point {
  x: number; y: number; year: number; site: string; ceiling: number;
}

export function YearStrip({
  strip, knobs, facilityLoadMw,
}: {
  strip: Strip;
  knobs: GpuKnobs;
  facilityLoadMw: number;
}) {
  const look = useMemo(() => stripLookup(strip.rows), [strip.rows]);
  const ceilings = useMemo(
    () => strip.grid_ceilings_mw.slice().sort((a, b) => b - a),
    [strip.grid_ceilings_mw],
  );
  const sites = Object.keys(strip.sites);

  const { points, stats } = useMemo(() => {
    const pts: Point[] = [];
    const st = ceilings.map((ceiling) => {
      const deltas: number[] = [];
      sites.forEach((site, si) => {
        strip.years.forEach((year) => {
          const d = lcocDeltaPct(
            look.flex(site, year, ceiling, TARGET),
            look.rigid(site, year, ceiling),
            knobs,
          );
          if (d === null) return;
          deltas.push(d);
          pts.push({
            x: d,
            // Two sub-rows per ceiling so the sites separate without a legend.
            y: ceilings.indexOf(ceiling) + (si === 0 ? -0.13 : 0.13),
            year, site, ceiling,
          });
        });
      });
      const sorted = deltas.slice().sort((a, b) => a - b);
      const median = sorted.length
        ? sorted.length % 2
          ? sorted[(sorted.length - 1) / 2]
          : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
        : null;
      return {
        ceiling,
        n: deltas.length,
        favourable: deltas.filter((d) => d < 0).length,
        median,
        lo: sorted[0] ?? null,
        hi: sorted[sorted.length - 1] ?? null,
      };
    });
    return { points: pts, stats: st };
  }, [ceilings, sites, strip.years, look, knobs]);

  const bySite = sites.map((site) => ({
    site,
    data: points.filter((p) => p.site === site),
    color: site === sites[0] ? 'var(--rigid)' : 'var(--flex)',
  }));

  return (
    <Figure
      index={3}
      title="Or did we just get lucky with the weather?"
      claim={
        <>
          <p>
            Any answer above came from one year of weather and one year of electricity prices.
            Pick a different year and you might get a different answer — so here is the same
            question asked again for every year we have data for, at both sites. Each dot is one
            year at one place.
          </p>
          <p className="mt-2">
            What matters is not where the dots sit but whether they all sit on the{' '}
            <em>same side of zero</em>. An answer that flips depending on which year you happened
            to pick is not an answer.
          </p>
        </>
      }
      caveat={
        <>
          Fourteen years, not fifteen. Texas&rsquo;s wholesale electricity market only started
          publishing these prices in December 2010, so there is one more year of weather data
          than there is of price data. Saying &ldquo;fifteen years&rdquo; without saying which
          record runs out first is how an off-by-one gets into a headline.
        </>
      }
    >
      <div className="mb-4"><EstimatedCostBasis /></div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="h-[240px] sm:h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 12, right: 24, bottom: 20, left: 8 }}>
              <CartesianGrid stroke="var(--rule)" horizontal={false} />
              <XAxis
                type="number" dataKey="x" tick={AXIS} stroke="var(--rule-strong)"
                domain={['auto', 'auto']}
                tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
                label={{
                  value: 'change in the cost of an hour of computing',
                  position: 'insideBottom', offset: -12,
                  style: { ...AXIS, textAnchor: 'middle' },
                }}
              />
              <YAxis
                type="number" dataKey="y" tick={AXIS} stroke="var(--rule-strong)"
                domain={[-0.6, ceilings.length - 0.4]} width={92}
                ticks={ceilings.map((_, i) => i)}
                tickFormatter={(v: number) => {
                  const c = ceilings[Math.round(v)];
                  return c === undefined ? '' : `${c} MW`;
                }}
              />
              <ZAxis range={[54, 54]} />
              <ReferenceLine x={0} stroke="var(--ink)" strokeWidth={1.25} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3', stroke: 'var(--rule-strong)' }}
                contentStyle={{
                  background: 'var(--surface-raised)', border: '1px solid var(--rule)',
                  borderRadius: 8, fontSize: 12, color: 'var(--ink)',
                }}
                formatter={(_v, _n, item) => {
                  const p = item.payload as Point;
                  return [`${p.x > 0 ? '+' : ''}${p.x.toFixed(3)}%`, `${siteLabel(p.site)} ${p.year}`];
                }}
                labelFormatter={() => ''}
              />
              {bySite.map((s) => (
                <Scatter
                  key={s.site} data={s.data} fill={s.color}
                  fillOpacity={0.8} isAnimationActive={false}
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
          <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 pl-4 text-[12px] text-ink-muted sm:pl-24">
            {bySite.map((s) => (
              <span key={s.site} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
                {siteLabel(s.site)}
              </span>
            ))}
            <span>· giving up {((1 - TARGET) * 100).toFixed(0)}% of the year&rsquo;s work</span>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          {stats.map((s) => {
            const good = s.favourable === s.n;
            return (
              <div key={s.ceiling} className="rounded-lg border border-rule bg-surface-sunken p-4">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-semibold text-ink">{s.ceiling} MW</span>
                  <span className="text-[12px] text-ink-muted">
                    {((s.ceiling / facilityLoadMw) * 100).toFixed(0)}% of what it needs
                  </span>
                </div>
                <div className="tnum mt-1 text-xl font-semibold">
                  <Verdict value={s.median}>
                    {s.median === null ? '—' : `${s.median > 0 ? '+' : '−'}${Math.abs(s.median).toFixed(3)}%`}
                  </Verdict>
                </div>
                <div className="text-[12px] text-ink-muted">
                  typical year · worst to best {s.lo?.toFixed(2)}% to{' '}
                  {s.hi !== null && s.hi > 0 ? '+' : ''}{s.hi?.toFixed(2)}%
                </div>
                <div className="mt-2 text-[13px] text-ink-secondary">
                  <strong className={good ? 'text-favourable' : ''}>
                    {s.favourable} of {s.n}
                  </strong>{' '}
                  year-and-place combinations came out cheaper
                </div>
                <div className="mt-1 text-[12px] leading-snug text-ink-muted">
                  {good
                    ? 'Every single one, and never close to the line. This answer does not depend on which year you picked.'
                    : s.favourable === 0
                      ? 'Not one. Slowing down loses in every year we have data for.'
                      : 'It depends on the year — so no single year is worth quoting here.'}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <NumbersTable
        columns={['site', 'year', 'grid connection', 'change in the cost of an hour of computing']}
        rows={points
          .slice()
          .sort((a, b) => b.ceiling - a.ceiling || a.site.localeCompare(b.site) || a.year - b.year)
          .map((p) => [
            siteLabel(p.site),
            p.year,
            `${p.ceiling} MW`,
            `${p.x > 0 ? '+' : ''}${p.x.toFixed(3)}%`,
          ])}
      />
    </Figure>
  );
}
