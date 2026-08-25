import type { Cube } from '@/lib/types';
import { Estimated } from './Figure';

/**
 * The electricity prices are real. Almost nothing else is.
 *
 * An interactive page is a screenshot machine, so this belongs on the page and
 * not in a footnote. The difference between a study and a source of confident
 * nonsense is whether a number can travel without the note saying where it came
 * from.
 */
export function Provenance({ cube }: { cube: Cube }) {
  const p = cube.provenance;
  const v = p.versions;
  return (
    <section className="border-t border-rule py-10">
      <h2 className="text-2xl font-semibold tracking-tight text-ink">
        How much of this should you believe?
      </h2>
      <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-ink-secondary">
        Short version: trust the shape of the answers, not the exact dollar figures. Here is
        exactly which is which.
      </p>

      <div className="mt-6 grid gap-5 md:grid-cols-2">
        <div className="rounded-lg border border-rule bg-surface-raised p-5">
          <h3 className="text-sm font-semibold text-ink">Real, and checked</h3>
          <ul className="mt-2 space-y-2 text-[13px] leading-relaxed text-ink-secondary">
            <li>
              <strong className="text-ink">Electricity prices.</strong> Actual hourly prices from
              the Texas grid operator, for the same place and the same year as the weather. Lining
              the clocks up sounds trivial and is not — Texas publishes them on daylight-saving
              time, and getting that wrong would have shifted summer afternoons by an hour and
              quietly ruined the solar comparison.
            </li>
            <li>
              <strong className="text-ink">Weather and solar output.</strong> Real years of
              recorded weather, run through a solar model, on a scale that is consistent between
              years — so &ldquo;200 MW of solar&rdquo; means the same array in every year.
            </li>
            <li>
              <strong className="text-ink">How chips trade speed for power.</strong> Measured on
              real hardware, not assumed. Its shape is what lets the whole thing be worked out
              exactly rather than searched for by trial and error.
            </li>
          </ul>
        </div>

        <div className="rounded-lg border border-warn-rule bg-warn-wash p-5">
          <h3 className="text-sm font-semibold text-warn-ink">Educated guesses</h3>
          <p className="mt-2 text-[13px] leading-relaxed text-warn-ink">
            Every equipment price, the cost of borrowing, how much of the cooling load is fixed,
            the grid demand charge, and the daily shape of chatbot traffic are{' '}
            <Estimated>estimates</Estimated> — sensible round numbers chosen so the model could
            run, not quotes from a supplier.
          </p>
          <p className="mt-2 text-[13px] leading-relaxed text-warn-ink">
            So the <em>thresholds</em> on this page — 108 MW, 2% — would move if you put real
            prices in. The <em>directions</em> would not: which way each effect pushes, and why,
            does not depend on the guesses.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <div className="rounded-lg border border-rule p-5">
          <h3 className="text-sm font-semibold text-ink">Things left out on purpose</h3>
          <ul className="mt-2 space-y-1.5 text-[13px] leading-relaxed text-ink-secondary">
            <li>
              <strong className="text-ink">Selling power back to the grid.</strong>{' '}
              {p.allow_export
                ? 'Allowed here.'
                : 'Not allowed. Everything is sized to serve the site itself, which is what the earlier comparisons assumed.'}
            </li>
            <li>
              <strong className="text-ink">Unlimited generator running.</strong> Air permits cap
              how long backup generators may run, so the model caps them too. The cap is on fuel
              burned rather than hours run, which is close but not the same thing — read the
              generator hours as a hint, never as proof of compliance.
            </li>
            <li>
              <strong className="text-ink">Knowing the future.</strong> These plants were sized by
              a model that could see the whole year in advance. A real operator cannot. Tested
              separately, every design falls short of its promise — and it flatters the
              never-slow-down design most, because never missing an hour is exactly what perfect
              foresight buys you.
            </li>
            <li>
              <strong className="text-ink">Clean energy tax credits.</strong> Not modelled. At 30%
              or more off solar and batteries, they would move the numbers by more than the effect
              being measured here.
            </li>
          </ul>
        </div>

        <div className="rounded-lg border border-rule p-5">
          <h3 className="text-sm font-semibold text-ink">Where these answers came from</h3>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px] text-ink-secondary">
            <dt className="text-ink-muted">Answers</dt>
            <dd className="tnum">
              {p.cells.toLocaleString('en-US')} of {p.expected_cells.toLocaleString('en-US')}{' '}
              worked out{p.complete ? '' : ' so far'}
              {p.failed_cells > 0 && `, ${p.failed_cells} failed`}
            </dd>
            <dt className="text-ink-muted">Computed</dt>
            <dd className="tnum">{p.built_utc}</dd>
            <dt className="text-ink-muted">Code version</dt>
            <dd className="tnum">{p.git_sha ? p.git_sha.slice(0, 12) : 'unknown'}</dd>
            <dt className="text-ink-muted">Solved with</dt>
            <dd className="tnum">{v.solver}, Python {v.python}</dd>
          </dl>
          <p className="mt-3 text-[12px] leading-relaxed text-ink-muted">
            Each answer took between ten seconds and three minutes to work out, so they were all
            computed ahead of time and saved. Nothing is being solved while you read this — the
            page is looking up answers and doing arithmetic, which is why the sliders are instant.
          </p>
        </div>
      </div>
    </section>
  );
}
