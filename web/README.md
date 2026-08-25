# The web version

An interactive version of the study's three main results. It is a plain static
site: no server, no database, no queue, and nothing solved while you read it.

## Why nothing is solved live

Working out the best plant for one situation takes between ten seconds and three
minutes. You cannot make somebody wait that long for a chart to move, and making
the solver faster is not on the table — almost all of that time is the solver
itself, not setup.

So every combination is worked out ahead of time and saved to a single file the
page looks answers up in. The page does lookups and arithmetic, which is why it
feels instant.

## Running it

```sh
npm install
npm run dev          # http://localhost:3000
npm run typecheck
npm test
npm run build
```

The page needs `public/cube.json`, which is built from the repo root:

```sh
../solar-project-1/.venv/bin/python scripts/build_cube.py --workers 7
```

That is 792 solves and about two and a half hours on seven cores. It is safe to
interrupt — every answer is written out the moment it lands and re-running picks
up where it stopped. `--assemble-only` rebuilds `cube.json` from what has been
solved so far, so you can look at a partial version while the rest runs; the page
will say plainly how much of it is missing. `--fresh` starts over.

Figure 3 uses a separate, smaller file built from the existing fourteen-year
results rather than new solving:

```sh
../solar-project-1/.venv/bin/python scripts/build_v6_strip.py
```

## Why the sliders are free

The chips cost the same whichever power plant you build. That means chip prices
change what an answer *costs* but never *which answer wins* — so the page can
recompute the entire headline in the browser from two numbers per saved answer:

```
cost per chip-hour
  = power plant cost / (computing done × number of chips)
  + price of one chip × annual cost factor / computing done
```

`npm test` checks that this reproduces the solver's own reported figure for every
saved answer. If the two ever disagree, the sliders are showing a different study
than the one that was actually solved, and the test says so before a reader does.

**The number of chips on site is not a free slider**, although an early draft of
the brief assumed it was. Changing the size of the fleet without changing the
grid connection puts a different load on the same wire, which changes the
physics rather than just the arithmetic. It needs a solve, so it is not offered.

## Four rules the page keeps

1. **The power plant's cost and the cost per chip-hour always appear together.**
   They are about 25% and about 1% of the same result, and quoting either alone
   misleads. The component that renders them will not render one without the
   other.
2. **A partial set of answers never poses as a complete one.** Gaps are labelled
   as unanswered questions, lines are not drawn across them, and "no break-even
   here" is never shown when the truth is "not worked out yet".
3. **Every estimated price is visibly marked**, on the page rather than in a
   tooltip nobody will hover.
4. **The exact optimum is never shown as a specification.** Where a design figure
   appears, the number you could actually buy appears next to it.
