'use client';

import { useState, type ReactNode } from 'react';

/**
 * A figure here is a claim, a picture, and the condition that keeps the claim
 * honest. The condition is not decoration. Every headline on this page is true
 * only in a particular situation, and a web page makes it far easier to
 * screenshot a number away from its situation than a document does.
 */
export function Figure({
  index, title, claim, children, caveat, notice,
}: {
  index: number;
  title: string;
  claim: ReactNode;
  children: ReactNode;
  caveat?: ReactNode;
  notice?: ReactNode;
}) {
  return (
    <section className="border-t border-rule py-10">
      <div className="mb-6 max-w-3xl">
        <div className="text-xs font-medium uppercase tracking-widest text-ink-muted">
          Figure {index}
        </div>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-ink">{title}</h2>
        <div className="mt-2 text-[15px] leading-relaxed text-ink-secondary">{claim}</div>
      </div>
      {notice}
      {children}
      {caveat && (
        <div className="mt-5 max-w-3xl border-l-2 border-warn-rule bg-warn-wash px-4 py-3 text-[13px] leading-relaxed text-warn-ink">
          {caveat}
        </div>
      )}
    </section>
  );
}

/**
 * Says out loud that a chart is drawn from answers that have not all been
 * worked out yet.
 *
 * Without this the page cannot be trusted while the answers are still being
 * computed: a grid size nobody has solved for looks exactly like a grid size
 * where nothing happens, and "we have not worked this out" reads as "we
 * checked, and there is nothing there".
 */
export function IncompleteNotice({
  solved, expected,
}: {
  solved: number;
  expected: number;
}) {
  if (expected === 0 || solved >= expected) return null;
  const pct = Math.round((solved / expected) * 100);
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-warn-rule bg-warn-wash px-4 py-3 text-[13px] text-warn-ink">
      <strong>Still being worked out — {pct}% done.</strong>
      <span>
        {solved} of {expected} answers for this site and year have been computed. Gaps in the
        chart below are questions nobody has answered yet, not answers of &ldquo;nothing
        happens here&rdquo;.
      </span>
    </div>
  );
}

/**
 * The verdict, said three ways at once — in words, with a symbol, and in
 * colour. Colour alone would hide the only judgement this page actually makes
 * from anyone who cannot separate red from green.
 */
export function Verdict({ value, children }: { value: number | null; children?: ReactNode }) {
  if (value === null) {
    return <span className="text-ink-muted">not worked out yet</span>;
  }
  const good = value < 0;
  return (
    <span className={good ? 'text-favourable' : 'text-unfavourable'}>
      <span aria-hidden="true">{good ? '▼ ' : '▲ '}</span>
      {children}
    </span>
  );
}

/**
 * Building the power plant gets 20-30% cheaper. The cost of an hour of computing
 * moves by about 1%. Both come from the same result, and quoting one without the
 * other is how you mislead somebody, so this will not render one alone.
 */
export function BothNumbers({
  infraPct, lcocPct, label,
}: {
  infraPct: number | null;
  lcocPct: number | null;
  label: string;
}) {
  const fmt = (x: number | null) =>
    x === null ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(2)}%`;

  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-ink-muted">{label}</div>
      <div className="mt-2 flex flex-wrap gap-x-8 gap-y-3">
        <div>
          <div className="tnum text-2xl font-semibold">
            <Verdict value={infraPct}>{fmt(infraPct)}</Verdict>
          </div>
          <div className="text-xs text-ink-muted">cost of the power plant</div>
          <div className="text-[11px] text-ink-muted">what the site developer sees</div>
        </div>
        <div>
          <div className="tnum text-2xl font-semibold">
            <Verdict value={lcocPct}>{fmt(lcocPct)}</Verdict>
          </div>
          <div className="text-xs text-ink-muted">cost of an hour of computing</div>
          <div className="text-[11px] text-ink-muted">what the chip buyer sees</div>
        </div>
      </div>
    </div>
  );
}

/**
 * A made-up number, marked so it cannot travel without its warning.
 *
 * This used to be a hover tooltip, which is invisible on a phone and
 * undiscoverable everywhere else — the weakest possible version of a warning
 * that the brief called load-bearing. It is now visible text.
 */
export function Estimated({ children }: { children: ReactNode }) {
  return (
    <span className="whitespace-nowrap rounded bg-warn-wash px-1.5 py-0.5 text-warn-ink ring-1 ring-warn-rule">
      {children}
    </span>
  );
}

/** A standing marker for a figure whose money figures are guesses. */
export function EstimatedCostBasis() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-warn-rule bg-warn-wash px-2.5 py-1 text-[11px] font-medium text-warn-ink">
      <span aria-hidden="true">◆</span>
      Prices of equipment are estimates, not quotes
    </span>
  );
}

/**
 * Charts are for seeing the shape; a table is for checking the number. Hover
 * tooltips serve neither anyone on a touch screen nor anyone who wants to copy
 * a column out, so every figure can show its own numbers.
 */
export function NumbersTable({
  columns, rows,
}: {
  columns: string[];
  rows: (string | number)[][];
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-[13px] text-ink-secondary underline underline-offset-2 hover:text-ink"
        aria-expanded={open}
      >
        {open ? 'Hide the numbers' : 'Show the numbers behind this chart'}
      </button>
      {open && (
        <div className="mt-3 overflow-x-auto rounded-lg border border-rule">
          <table className="w-full min-w-[520px] border-collapse text-[13px]">
            <thead>
              <tr className="bg-surface-sunken text-left">
                {columns.map((c) => (
                  <th key={c} className="whitespace-nowrap px-3 py-2 font-medium text-ink-secondary">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tnum">
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-rule">
                  {r.map((cell, j) => (
                    <td key={j} className="whitespace-nowrap px-3 py-1.5 text-ink">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
