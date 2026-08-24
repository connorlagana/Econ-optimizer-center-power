# TODO: turn this into a web app

Not started. This is the design brief, written while the numbers were fresh, so
that whoever picks it up does not have to re-derive the two facts that decide the
architecture.

## The two facts that decide it

**1. A solve is 65 seconds, and it is the solver, not the setup.**

Measured on the V3 model, Dallas 2019, hourly prices, 60 MW ceiling:

```
vars=78,847  eq=26,281  leq=132,015
compile=0.1s   solver=65.3s
```

Canonicalisation is 0.15% of it. So the obvious optimisation — compile the
problem once with CVXPY parameters and re-solve with new coefficients — buys
nothing. There is no way to make this interactive by making the solve faster.
**Do not build a live-solve backend.** A queue, a worker with HiGHS, and a
60-90 second spinner is a worse product than an instant one and costs money to
run.

**2. GPU capital is a constant in the objective, so the most interesting knob is
free.**

In `model.py`, `ann_gpu = g.total_capex * crf(...)` is added to the objective but
is not a function of any decision variable. It cannot change the argmin. So for a
fixed (site, year, interconnection, compute target, mode), **GPU capex, GPU
count, kW per GPU, GPU life and the GPU discount rate change the reported LCOC
and change nothing else.**

That is the whole product. Landmine 1 says GPU capital dominates by an order of
magnitude and decides the sign of the flexibility trade. A slider for it
recomputes the entire headline in the browser with no solver in the loop — drag
GPU capex from $35k to $15k and watch the crossover walk across the chart.

## Architecture

Precompute a result cube offline, ship it as JSON, do lookups plus closed-form
arithmetic in the browser. Static Next.js on Vercel, no API, no queue, no
database, no cold start, $0. Same stack as `housing-compare`, so no new
framework.

### Axes that need a solve — these go in the cube

| axis | values | why it is here |
|---|---|---|
| site | dallas, west_texas | `SITES` in `site.py` |
| year | 2011–2024 | 14, not 15 — landmine 13 |
| interconnection | ~10 ceilings | the V2/V3 crossover axis |
| compute target | ~10 from 1.00 to 0.90 | the V2 frontier axis |
| mode | rigid, powercap | curtail only if someone asks |

Do **not** put these in the cube as extra dimensions; they multiply it and are
better as separate published cube variants: energy price basis, ITC on/off, PUE,
gas hour cap, export on/off.

### Axes that are free in the browser

GPU capex, GPU life, GPU discount rate, kW per GPU, IT nameplate. All of them
only touch the LCOC numerator and denominator after the fact.

### Cost of building the cube

2 sites × 14 years × 10 ceilings × 10 targets × 2 modes = 5,600 solves.
At 65 s on 5 workers that is **about 20 hours**. Options, in order of preference:

1. Cut years to a representative subset for the interactive cube (say 2016 low,
   2019 high-scarcity, 2021 Uri, 2024 post-inversion) and keep all 14 for the
   static V6 figures. 1,600 solves, ~6 hours.
2. Coarsen the ceiling × target grid to 6 × 6 and interpolate. 2,016 solves.
3. Run the full thing once overnight and never again.

Rigid runs do not need the compute-target axis (target is always 1.0), which
removes 90% of the rigid cells. Check `tests/test_workload.py` — rigid is also
invariant to workload structure, so it is one solve per (site, year, ceiling).

### Payload size

Dispatch is 9 arrays × 8,760 floats per solve. Do **not** ship it for every cell
or the page is 40 MB. Ship summary scalars per cell (LCOC, infra, PV, BESS, gen,
grid, 4CP, curtailment), and full hourly dispatch for three or four featured
designs only, downsampled to daily or to one representative week.

## What the app should be

Not a parameter dashboard. This project has an argument and the app should be the
argument, in three interactive figures:

1. **The sign change.** LCOC delta (flex − rigid) against interconnection size,
   zero line marked, GPU-capex slider moving the crossover live. Headline: below
   roughly two-thirds interconnection coverage, flexibility pays for itself.
2. **How much to buy.** The U-shaped frontier at a chosen ceiling, with the
   shallow optimum at ~98% marked, and a stacked bar showing that what
   flexibility displaces is the generator (140 → 1.4 MW) and not the battery.
   Carry V2's caveat into the UI: the *composition* at any single target is not
   robust, only the totals and the cost curve are.
3. **Is it a finding or a year?** The V6 distribution — the same trade computed
   across 14 years and 2 sites — as a strip or box plot. This is the honest
   answer to "should I believe this", and it is the figure most studies omit.

A fourth, if there is appetite: the V3 capture-price inversion, which needs no
optimiser at all and is the most immediately legible thing in the repository.

### Rules the UI has to follow

- **Always show infra % and LCOC % together.** They are 25% and 1% of the same
  run. Quoting either alone misleads, and a web app makes single-number quoting
  much easier than a README does.
- **Label every placeholder.** V3 made the *prices* real. Every capex, the
  financing rate, the PUE split, the 4CP rate and the inference profile are still
  `PLACEHOLDER`. An interactive tool is a screenshot machine; a provenance badge
  per input is cheap and it is the difference between a study and a
  misinformation vector.
- **Never present the continuous optimum as a spec** (landmine 10). If the app
  shows `147.3 MW`, it should show the procurable rounding next to it.

## Sequencing

1. `scripts/build_cube.py` — parallel over cores, writes `web/public/cube.json`.
   This is the long pole and its schema is what everything else is built on.
2. The three figures, static, against a checked-in cube.
3. The GPU-capex slider, which is where it stops being a report and starts being
   a tool.
4. Only then, if anyone asks for scenarios the cube does not cover, consider a
   queued "run my own" escape hatch. Probably nobody will ask.

## Before it goes public

The prices are real and sourced. Nothing else is. Either replace the capex basis
with sourced figures (NREL ATB is the obvious start) or make the provenance
badges load-bearing enough that no one can screenshot a number without also
screenshotting that it is made up.
