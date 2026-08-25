# TODO: turn this into a web app

**Built.** See [`../web/`](../web/) and `scripts/build_cube.py`. This brief is
kept as written, because the reasoning that decided the architecture is worth
more than a description of what got shipped; what actually differed from it is
recorded at the bottom.

This was the design brief, written while the numbers were fresh, so that whoever
picked it up did not have to re-derive the two facts that decide the
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


---

## What was built, and where it departed from this brief

**The cube is 792 cells, not 5,600.** Option 1 above — four representative years
rather than fourteen — plus the observation the brief already made, that rigid
needs no compute-target axis. Two sites x 4 years x 11 interconnections gives 88
rigid cells; the same grid crossed with 8 compute targets gives 704 power-capped
ones. About two and a half hours on seven cores.

The 65 s per solve in this brief was an average over a mixed bag and it hides
the split that matters: **a rigid solve is ~10 s and a power-capped one ~90 s**,
because the concave hull's per-segment constraints are what make the LP large.
That is why the cheap axis is the one that got kept whole.

**The interconnection grid is dense between 75 and 125 MW.** V2 put the
crossover near 85 MW on a flat price and V3 near 108 MW on real hourly prices,
and a sparse grid there would have made the headline figure interpolate across
the sign change rather than show it.

**`it_nameplate_mw` is not a free axis.** This brief lists it as one. It is not:
scaling the fleet without scaling the interconnection ceiling puts a different
load against the same wire, which changes the physics and needs a solve. The
other four GPU knobs are genuinely free and are exposed as sliders. The
distinction is documented in `web/src/lib/lcoc.ts` and enforced by there being
no control for it.

**Figure 3 does not come from the cube.** The year distribution is one compute
target across every year, which `results/v6_sweep.json` already contains at full
fourteen-year resolution. `scripts/build_v6_strip.py` reduces it rather than
re-solving. The one wrinkle is that V6 stored `lcoc` but not
`compute_unit_hours`, which the browser needs when the GPU slider moves; it is
recovered exactly by inverting the LCOC identity, and the script asserts the
recovered value against `target * 8760` rather than assuming it.

**The cube carries its own provenance.** Every cell ships with the full
`Scenario` dict, the git SHA, the solver and library versions and the price
basis, and the provenance panel renders them. A cube whose numbers cannot be
traced to the inputs that produced them is exactly the screenshot machine this
brief warned about.

**`npm test` cross-checks the browser against the optimiser.** The TypeScript
LCOC arithmetic is asserted to reproduce `lcoc_default_basis` on every cell in
the cube. If the two ever disagree, the sliders are showing a different study
than the one that was solved, and the test says so before a reader does.

### Still open

- The GPU-capex slider moves the crossover, which is what this brief wanted, but
  there is no way to *read off* the capex at which the crossover reaches a given
  interconnection. An inverse readout would be a better tool than a slider.
- No ITC variant, no export variant, no flat-price variant. They are separate
  published cubes, as the brief says, and none is built.
- Featured hourly dispatch for three or four designs is not shipped. The cube is
  scalars only, so the page cannot yet show anybody a week of operation.
