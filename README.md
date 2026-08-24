# Techno-economic co-optimisation of AI data-center power architecture

**Question.** For a given AI workload and site, what combination of solar,
storage, grid capacity, backup generation and compute flexibility produces the
cheapest useful compute?

Project 1 asks *given this plant, which controller wins*. This asks *what plant
should have been built*. The difference is that capacity is a decision variable
here, not a setting.

Status: **V1 runs.** Capacity and 8760-hour dispatch co-optimise in one LP, on
project 1's Dallas weather years and measured H100 curve.

---

## The two structural calls, and why

### 1. One LP, not a search over candidate designs

The brief describes comparing designs A–E and simulating each. That is what
project 1 does — upstream's Latin-hypercube screen into differential evolution
over (solar MW, battery MW), with a simulator in the loop — and it does not
extend to five dimensions. A derivative-free search over a simulator needs
samples exponential in dimension, and it can only ever report the best design it
happened to sample.

Every term here is linear in the decision variables. Capital cost is `$/MW × MW`.
A capacity limit is `flow[t] ≤ capacity`, and `capacity` being a variable does
not change that. Storage state is an equality. And the GPU power-performance
curve is **concave**, which project 1 already established and relies on
(`gpu.PowerPerformanceCurve.concave_hull`) — so `compute ≤ mₖ·power + cₖ` over the
hull segments, maximised, traces the curve exactly with no binaries.

So sizing and dispatch solve simultaneously and exactly, in about a minute, and
the result is *the* optimum. The design table in the brief becomes an output
rather than an input.

### 2. The ratio objective does not need special handling

`min cost / compute` is a linear-fractional program, not an LP. Three ways out:
Charnes–Cooper, Dinkelbach bisection, or fix the denominator. Take the third —
`min cost s.t. compute ≥ α` — and sweep α. The sweep *is* the Pareto frontier,
which was the headline deliverable anyway, and levelised cost is then a column
in it rather than an objective. The minimum of that column is the
LCOC-optimal design.

---

## What V1 already says

Dallas 2019, 100 MW IT nameplate, 71,429 H100-class GPUs, unconstrained grid at
a flat $45/MWh, ERCOT-style coincident-peak charge on a 610-hour summer risk
window. All costs are placeholders (see `inputs.py`) — read the structure, not
the digits.

| | BESS | infrastructure $/yr | compute | LCOC $/GPU-h |
|---|---:|---:|---:|---:|
| rigid @ 100% | 0 MWh | $63.3M | 100.0% | 1.1018 |
| curtail @ 99% | 0 MWh | $60.3M | 99.0% | 1.1081 |
| powercap @ 99% | 0 MWh | $58.5M | 99.0% | 1.1052 |
| powercap @ 96% | 0 MWh | $52.2M | 96.0% | 1.1293 |

Three things fall out, and the third is the point of the project.

**GPU capital dominates by an order of magnitude.** $626M/yr of GPU capital
against $63M/yr of everything that makes electricity. An hour of compute forgone
strands about **$1.00** of GPU capital; the energy it would have consumed costs
about **$0.06**. Any model that puts "useful compute" in a denominator without
putting GPU capital in the numerator will happily throttle, and will be wrong by
a factor of fifteen about what a throttle costs.

**So flexibility cuts infrastructure and still loses.** Power-capping to a 96%
compute target removes 17% of infrastructure cost — and raises levelised compute
cost 2.5%, because 4% of compute is worth more than 17% of a small number. This
is the brief's "opposite" conclusion, and it is the correct one *under an
unconstrained grid*.

**The curve is worth something on its own.** At the same 99% compute target,
power-capping beats parking racks: $58.5M vs $60.3M of infrastructure, on 58 MW
of PV instead of 115 MW. That gap is the specific value of the measured
efficiency curve, separated from the value of merely doing less work — which is
why the two are separate rungs and not one "flexible" case.

**And the coincident peak is where flexibility actually lives.** One percent of
annual compute takes the 4CP-exposed demand from 125 MW to 62 MW. At a
placeholder $75/kW-yr that is ~$4.7M/yr for ~88 compute-unit-hours. The right
axis for the headline is not "8% of annual compute" — it is *how few hours, how
deep*. Flexibility is a capacity product, not an energy product.

---

## V2: the interconnection sweep, and the sign change

An unconstrained 125 MW interconnection is not something a 2026 project can
buy; it is a queue position with a date on it. So constrain it, and size the
system twice at each ceiling — rigid compute against the measured power cap.

| grid ceiling | rigid infra | flex infra | infra Δ | rigid LCOC | flex LCOC | LCOC Δ |
|---:|---:|---:|---:|---:|---:|---:|
| 125 MW | $63.3M | $52.2M | −17.5% | 1.1018 | 1.1293 | **+2.50%** |
| 60 MW | $107.8M | $71.4M | −33.7% | 1.1729 | 1.1613 | **−0.99%** |
| 30 MW | $136.5M | $97.4M | −28.7% | 1.2189 | 1.2045 | −1.18% |
| 10 MW | $157.6M | $116.5M | −26.1% | 1.2526 | 1.2364 | −1.29% |
| 0 MW | $168.6M | $126.9M | −24.8% | 1.2702 | 1.2536 | −1.31% |

**Flexibility changes sign between 125 MW and 60 MW of interconnection.** That
is the project's actual finding, and it is a statement about scarcity of grid
capacity — not about energy, not about solar, and not about whether GPUs can be
throttled. Infrastructure grows from $63M to $169M/yr as the grid is withdrawn;
once it is a large enough fraction of GPU capital, saving a quarter of it beats
losing 4% of compute.

**What flexibility actually displaces is the generator, not the battery.** At a
60 MW interconnection the rigid design builds 140.1 MW of backup generation and
the flexible one builds **1.4 MW** — a hundredfold reduction, against −25% on
storage (1,234 → 928 MWh) and −21% on PV (369 → 293 MW). The brief predicted
battery displacement; the model says the first thing to go is the plant you
built to survive the worst hours, because surviving them by computing slightly
less is nearly free. That is a more interesting claim and a more useful one, and
it is worth stress-testing hard before it leaves this repository.

### Two numbers, both true, aimed at different people

Infrastructure falls 25–34%. Levelised compute cost falls ~1%. Both are the
same run. The first is what matters to whoever builds the plant; the second is
what matters to whoever signs for the GPUs, and it is small because GPU capital
is most of the denominator. Quoting either one alone is a way of misleading
somebody, so the study should always quote both.

### Where the crossover is

| grid ceiling | rigid LCOC | flex LCOC | LCOC Δ |
|---:|---:|---:|---:|
| 125 MW | 1.1018 | 1.1293 | +2.50% |
| 110 MW | 1.1125 | 1.1293 | +1.51% |
| 95 MW | 1.1262 | 1.1329 | +0.59% |
| **~85 MW** | | | **0** |
| 80 MW | 1.1446 | 1.1410 | −0.32% |
| 60 MW | 1.1729 | 1.1613 | −0.99% |

Full facility load here is 125 MW (100 MW IT plus overhead), so the crossover
sits at roughly **68% of full facility load**. Stated that way it travels: below
about two-thirds interconnection coverage, compute flexibility pays for itself;
above it, the compute it costs is worth more than the plant it saves.

### How much flexibility to buy: 2%, not 8%

Frontier at a 60 MW interconnection, sweeping the compute target:

| compute target | PV | BESS | gen | infra $/yr | LCOC |
|---:|---:|---:|---:|---:|---:|
| 100% (rigid) | 369.3 MW | 1,234 MWh | 140.1 MW | $107.8M | 1.1729 |
| 99% | 364.7 MW | 1,199 MWh | 62.9 MW | $93.2M | 1.1613 |
| **98%** | **344.7 MW** | **1,130 MWh** | **22.7 MW** | **$83.3M** | **1.1569** |
| 97% | 303.4 MW | 979 MWh | 19.6 MW | $76.6M | 1.1578 |
| 96% | 293.0 MW | 928 MWh | 1.4 MW | $71.4M | 1.1613 |
| 94% | 252.4 MW | 724 MWh | 2.4 MW | $63.6M | 1.1727 |
| 92% | 220.2 MW | 543 MWh | 8.2 MW | $58.0M | 1.1885 |
| 90% | 209.6 MW | 492 MWh | 0.0 MW | $53.8M | 1.2075 |

The frontier is **U-shaped and the optimum is shallow**: 98%, not the 96% the
V2 sweep assumed by assertion. Infrastructure keeps falling all the way down —
it is monotone — but levelised compute cost turns around at 98% and by 92% is
worse than building rigid. Buying too much flexibility is worse than buying
none, and the brief's "8% annual compute flexibility" headline sits well past
the point where the trade has already reversed.

So the honest headline for this scenario is:

> At a 60 MW interconnection serving a 125 MW facility, allowing **2%** annual
> compute flexibility removes **84% of backup generation** and **23% of
> infrastructure cost**, and lowers levelised compute cost **1.4%**. Past ~4%,
> the trade reverses.

**A caveat on the composition, not the totals.** Generation is the marginal
asset across the whole frontier — 140 → 63 → 23 → 1.4 MW — while storage falls
far more slowly, which is what "flexibility displaces the generator" means. But
the generator column is not monotone (1.4 MW at 96%, 8.2 MW at 92%, 0 at 90%),
which is the signature of a flat optimum with alternate optima: near the
minimum, several gen/storage splits cost nearly the same and the solver picks
among them arbitrarily. Totals and the cost curve are robust; the exact split at
any single target is not. Before quoting a composition, re-solve with the total
fixed and a secondary objective, or perturb costs and check the answer holds.


---

## V3: real prices, and the shortcut that survived

V1 and V2 priced grid energy at a flat $45/MWh. Landmine 6 says that is the
study's largest open hole, so this closes it: ERCOT day-ahead settlement-point
prices, `LZ_NORTH`, same year and node as the weather, 2011–2024 ingested and
cached (`prices.py`, `scripts/fetch_prices.py`).

Swapping a placeholder for a real series changes two independent things at once —
the *level* of the price and its *shape* — so the experiment runs three bases and
separates them: flat $45, flat at the year's actual mean, and the real hourly
series. The middle rung is a correction to a wrong number. The gap between it and
the third is the whole content of landmine 6.

### The crossover does not move

| basis | crossover | % of facility load |
|---|---:|---:|
| flat $45 placeholder | 106.6 MW | 85% |
| flat at actual mean ($38.12) | 109.6 MW | 88% |
| real hourly series | 108.4 MW | 87% |

Three percent, on a quantity V2 was only ever willing to state as "roughly
two-thirds to five-sixths of facility load". **The flat-price shortcut survived
the question V2 asked**, and the reason is V1's own conclusion: flexibility is a
capacity product. What it sells is avoided backup generation and avoided
coincident-peak demand, both charged per kW. The hourly shape of an energy price
moves energy cost, which is the part of the bill flexibility was never selling
against.

That is worth stating plainly because it is the opposite of what landmine 6
predicts, and the landmine is not wrong — it is wrong about *which* result it
threatens.

### The design moves completely

At a 125 MW interconnection, sizing for rigid compute:

| basis | PV | BESS | imports | energy $/yr | 4CP demand |
|---|---:|---:|---:|---:|---:|
| flat $45 | **0 MW** | 0 MWh | 1,095 GWh | $49.3M | 125.0 MW |
| flat at actual mean | **0 MW** | 0 MWh | 1,095 GWh | $41.7M | 125.0 MW |
| real hourly | **113.6 MW** | 216 MWh | 865 GWh | $19.0M | 76.5 MW |

A flat price says *build no solar at a grid-connected site*. The real price says
*build 114 MW of it and a two-hour battery*, cuts imports by 21%, cuts the energy
bill by 61%, and takes coincident-peak demand from 125 MW to 76.5 MW. Both
answers came from the same optimiser on the same weather. So V1's headline
LCOC was roughly right for a reason that had nothing to do with its being
correctly modelled.

### The mechanism is one number, and the optimiser is not needed to check it

What a megawatt of PV is worth in a year is `Σ cf(t)·price(t)`. Against an
annualised cost of $111,269/MW-yr at placeholder capex:

| priced at | value | verdict |
|---|---:|---|
| the annual mean | $79,158/MW-yr | does not pay |
| hour by hour | $151,370/MW-yr | pays |

**A flat price undervalues solar by 48%** at this node and year, because solar
produces disproportionately in hours priced above the mean — 2019's mean of
$38.12 sits against a median of $20.86, so the level is set by a few hundred
afternoon hours that are also sunny ones. That single ratio is the difference
between building no solar and building 114 MW.

### And its sign is not a constant of nature

| year | PV value $/MW-yr | vs cost |
|---:|---:|---:|
| 2019 | 151,370 | 1.36× |
| 2021 | 285,961 | 2.57× |
| 2023 | 207,983 | 1.87× |
| 2024 | 63,451 | **0.57×** |

Solar pays for itself on energy value alone in 2019, pays 2.6× in the year of
Uri, and **misses by 43% in 2024**. The same array, the same cost basis, four
price years.

The cause is visible in the price record without any model at all. Midday price
at `LZ_WEST`, as a ratio to that year's annual mean:

| 2011–2019 | 2020 | 2023 | 2024 |
|---:|---:|---:|---:|
| 1.15–1.54 | 0.99 | 0.78 | **0.51** |

Midday was ERCOT's *expensive* time for the first decade of the nodal market and
is now its cheapest, with 254 negative-price hours in 2024 against zero in 2019.
Solar cannibalised its own capture price somewhere between 2020 and 2023, and
**project 1's weather year sits on the far side of that inversion.**

This is the finding that makes V6 mandatory rather than ornamental. It is not
that a single year is noisy. It is that the structural relationship between
solar output and price *changed sign mid-record*, so no single year is
representative of any other, and a study quoting one year is quoting a regime
rather than a climate.

### Two smaller things this rung settled

**Export is now a modelled switch** (landmine 8), restricted to PV — exporting
generator output is a merchant plant with a different permit, and exporting
stored energy is arbitrage that deserves its own study. It defaults off, because
V1 and V2 assumed behind-the-meter and the comparison has to hold. Turning it on
without an interconnection limit raises rather than solves: with export rights,
unlimited land and an unlimited wire, merchant solar has no upper bound, and at
2019 prices it clears its own cost by about $3k/MW-yr so the LP is genuinely
unbounded. At 2024 prices it misses by $53k and the same model is bounded. The
error message says so rather than letting the solver report `unbounded`.

**The price record is shorter than the weather record.** ERCOT's nodal market
opened on 1 December 2010, so 2010 is a one-month file. Fourteen years overlap,
not fifteen, and `IncompletePriceYear` refuses the partial year rather than
padding it.

### What is still open here

Day-ahead, not real-time. Real-time carries the scarcity spikes that make
flexibility look valuable, but handing a year of them to a perfect-foresight LP
measures clairvoyance rather than flexibility. Day-ahead is also the price a
load can actually hedge to. The right home for real-time is V4's receding-horizon
operator, where the controller cannot see ahead — that pairing is not yet built,
and it is the most valuable single thing left undone in this repository.

---

## V4: what survives when the controller stops being clairvoyant

Every sizing above came from an LP that sees all 8,760 hours. This re-runs three
designs under a receding 48-hour horizon — once with an exact forecast, once
with one calibrated to 10% realised day-ahead nRMSE (project 1's error model) —
and divides by the compute actually delivered rather than the compute promised.

| design | planned | perfect MPC | noisy MPC | horizon cost | forecast cost |
|---|---:|---:|---:|---:|---:|
| 60 MW grid, rigid @100% | 100.00% | 97.52% | 97.51% | 2.372% | 0.045% |
| 60 MW grid, powercap @98% | 98.00% | 97.48% | 97.38% | 0.503% | 0.121% |
| islanded, powercap @96% | 96.00% | 93.45% | 93.01% | 2.673% | 0.461% |

Cost columns are net value forgone against the annual LP — compute priced at
stranded GPU capital, less variable cost. Capacity is sunk and identical across
rungs, so it cancels and only operation is compared.

### The prediction was wrong, in the interesting direction

The landmine list said perfect foresight makes LP sizings optimistic, and it
does: every design under-delivers. But it is *differentially* optimistic, and
it flatters the **rigid** design most — because rigid's entire value proposition
is "never miss an hour", and never missing an hour is precisely what
clairvoyance buys. Operated realistically, the rigid design cannot keep its
promise either: it delivers **97.51%**, not 100%.

Which collapses the comparison that the planning study was built on:

| | infrastructure $/yr | compute delivered | LCOC | vs rigid |
|---|---:|---:|---:|---:|
| rigid @100%, as planned | $107.8M | 100.00% | 1.1729 | — |
| powercap @98%, as planned | $83.3M | 98.00% | 1.1569 | −1.37% |
| rigid @100%, as operated | $106.9M | 97.51% | 1.2014 | — |
| powercap @98%, as operated | $83.1M | 97.38% | 1.1640 | **−3.11%** |

Under perfect foresight the trade looks like *2 percentage points of compute for
23% of the plant*. Under realistic operation the two designs deliver compute
within **0.13 percentage points of each other** — and one of them costs 23% less
to build. The foresight validation did not weaken the case for flexibility. It
roughly **doubled** it, from −1.37% to −3.11% on levelised compute cost.

The general lesson is worth more than the number: a perfect-foresight planner
does not bias all architectures equally. It systematically favours whichever
design depends most on knowing the future, and a study that skips the
validation step will rank architectures wrongly rather than merely optimistically.

### Horizon length beats forecast quality, 4–6×

At every design the cost of a 48-hour horizon exceeds the cost of 10% forecast
error several times over: 2.372% vs 0.045% rigid, 0.503% vs 0.121% at the
optimum, 2.673% vs 0.461% islanded. That is an actionable ranking, because a
longer horizon is a bigger LP and a better forecast is a procurement contract.
Before it is quoted, it needs the horizon swept — 24 / 48 / 96 / 168 hours —
since a single 48-hour point cannot show where the curve flattens.

### Islanding remains expensive, and foresight is why

The islanded design loses 3.13% of net value against 0.63% at a 60 MW
interconnection — five times worse — and it is the only case that sheds load at
all (139.5 MWh over 17 hours, under the noisy forecast only). A grid connection
absorbs forecast error; without one, every mistake is paid for out of storage or
fuel. Project 1's islanded framing was the hard case, and this quantifies how
much harder.

### Two bugs this experiment surfaced, both of which produced plausible numbers

Recorded because both were silent, and silence is the failure mode that matters.

**The unserved-load penalty was scaled by the compute price.** The rigid
design's compute price is legitimately zero — compute is not a decision there,
so the planner's dual on the compute floor is degenerate — which scaled the
penalty to zero with it. The controller shed all 8,760 hours of load for free
and reported 100% compute. Any penalty that a legitimate input can scale to
zero is not a penalty; it is now absolute.

**Rigid compute was encoded as `p_it == it_max, compute == 1`.** That is how the
*planner* states it, and there it is exact, because the plant is sized so the
case never arises. Carried into an operator that has an unserved-load slack, it
credited full compute for hours the plant could not power: 100% compute across
834 hours of blackout, and a net value *higher* than the annual LP that bounds
it. Rigid and curtail share their operational physics — work falls off in
proportion to power — and what separates them is a planning permission, not
anything the hardware does at run time.

Both are pinned by regression tests in `tests/test_operate.py`, including the
`compute_price=0.0` parameterisation that would have caught the first.

---

## V6: is it a finding, or a fact about 2019?

Every rung above ran on one weather year at one site. V3 showed that is not a
detail but a hazard: the relationship between solar output and price *inverted*
between 2020 and 2023, so a single year is a draw from a non-stationary process,
and the 2019 the study inherited sits on the far side of the inversion.

So sweep it. Fourteen years (2011–2024, the overlap of project 1's weather
record with ERCOT's nodal price record), two sites each paired with the
settlement point a load there would actually settle at, two interconnections
either side of the crossover, rigid against the measured power cap at 98%.
112 solves.

The output is a distribution, and the only question worth asking of it is
whether the **sign** is stable — because a conclusion that flips with the
weather year is not a conclusion.

| interconnection | median LCOC Δ | range | favourable | verdict |
|---|---:|---:|---:|---|
| 125 MW (100% of facility load) | +0.542% | [−0.170, +1.151] | **2 / 28** | flexibility does not pay |
| 60 MW (48% of facility load) | −1.141% | [−1.539, −0.426] | **28 / 28** | flexibility pays |

**At a scarce interconnection the trade is favourable in every year at every
site, and it is never close to the line.** The worst case across fourteen years
of ERCOT prices — including Uri, including the capture-price inversion — is
−0.426%, and the best is −1.539%. At full facility load the trade is unfavourable
in 26 of 28, and the two exceptions are both 2021, the year a winter storm made
firm capacity worth more than anything else in the record.

So V2's headline survives contact with the whole price record. That is worth
more than the number it survived with.

### The site changes the size, not the sign

| site | median at 60 MW | median at 125 MW | rigid LCOC at 60 MW |
|---|---:|---:|---:|
| Dallas / `LZ_NORTH` | −1.399% | +0.738% | ~1.16 |
| Midland-Odessa / `LZ_WEST` | −0.798% | +0.483% | ~1.13 |

West Texas gets roughly **half** the benefit Dallas does, and the reason is not
that flexibility works worse there — it is that the rigid design is already
cheaper. A 23% better solar resource (2,550 vs 2,076 full-load hours per MW)
means the plant that never throttles is less expensive to build in the first
place, so there is less left for flexibility to save. Flexibility is worth most
where the alternative is worst.

### The result nobody would have predicted from a single year

At a 125 MW interconnection, **whether the optimiser builds any solar at all
flips between years.** Dallas:

| built PV | years |
|---|---|
| none at all | 2012, 2013, 2014, 2015, 2016, 2017, 2020, 2024 |
| 91–184 MW | 2011, 2018, 2019, 2021, 2022, 2023 |

Eight of fourteen years build **zero** behind-the-meter solar; six build up to
184 MW. This is the V3 mechanism — solar's energy value is `Σ cf(t)·price(t)`,
which crosses its annualised cost somewhere in the middle of this record — now
visible as a binary outcome rather than a percentage. A study that picked 2016
and a study that picked 2019 would disagree about whether to build a solar farm,
using the same model, the same site and the same cost basis.

**Report the distribution or report nothing.** A single-year techno-economic
result here is not merely imprecise; on the question it is most often asked to
answer, it is a coin flip dressed as an optimisation.

### What this rung does not cover

One compute target (98%) and one cost basis. The frontier sweep and the ITC
cases are the obvious next multiplications, and both are affordable — the
constraint is that they multiply against fourteen years rather than one. The
workload structure of V5 is *not* included here: a three-class solve is 1,126
seconds against 40 for the pool, so a fourteen-year workload sweep is a
different order of expense and belongs behind the LP speedups, not in front of
them.

---

## Landmines

Ordered by how much damage each does if missed. The first four change the
answer's sign, not its precision.

**1. GPU capital in the objective.** Above. Non-negotiable.

**2. Perfect foresight.** The LP sees all 8760 hours; a real controller does
not, so every LP sizing here is a lower bound. **Measured in V4, and the effect
is not what this entry originally predicted.** It is not a uniform haircut: the
planner systematically favours whichever architecture depends most on knowing
the future, which is the rigid one. Skipping the validation step does not make a
study merely optimistic — it makes it rank architectures wrongly. Validate every
headline design comparison, never just the winner.

**3. Unbounded gas.** Give the optimiser unlimited generator hours and it
builds an unpermittable merchant power plant, then reports that cheap gas
dominates. Texas emergency-engine air permits cap non-emergency operation at
order-100 hours/year. `Limits.gen_annual_full_load_hours` exists for this —
sweep it, because the conclusion is a function of it. **And it is a proxy:** it
caps generator *energy* as equivalent full-load hours, because that is linear,
whereas a permit caps *operating* hours and counting those needs a binary per
hour. A design that runs 1,500 hours at a third of load satisfies this model and
violates the real permit — which is exactly what the rigid cases in V2 do. Read
generator run-hours in the results as a diagnostic, never as compliance. Also: turbine lead times in 2026
push frames past a plausible in-service date, so reciprocating engines are the
realistic technology and the cost basis should be theirs.

**4. PUE is not a multiplier.** Chillers, pumps and UPS conversion losses have a
large fixed component. A single PUE number makes a 40% throttle look like it
sheds 40% of facility load, overstating the power a throttle releases and hence
the value of flexibility. Modelled here as `fixed + variable×P_IT`
(`Facility.overhead_fixed_share`), and in West Texas the fixed part is worst
exactly when it hurts: hot afternoons are peak cooling, peak scarcity price,
peak 4CP risk *and* peak PV temperature derate.

**5. Synchronous training has no partial throttle.** Power-capping a subset of
GPUs in a synchronous data-parallel job buys nothing — the job runs at the
slowest worker. The control variable is a per-*job* cap applied uniformly, not a
per-GPU one, so a "throttle 30% of the fleet" policy only works if 30% of the
fleet is a separable job. Project 1's curve provenance already flags that the
measurement is 4-GPU single-node and that cluster-scale straggler effects would
flatten the curve. That flattening is a direct haircut on everything here.

**6. Prices and weather must come from the same year and node.** ~~V1 uses a
flat placeholder price and is honest that this is its largest open hole.~~
**Closed in V3, and the entry was right about the mechanism and wrong about the
casualty.** A flat price undervalues solar by 48% at Dallas/`LZ_NORTH` in 2019,
which is the difference between the optimiser building no solar and building
114 MW of it — so the *design* was badly wrong. But the flexibility crossover
moved by 3%, because flexibility sells avoided capacity and the energy price
shape moves energy cost. Fix the prices to get the plant right; V2's headline
did not depend on it.

The anti-correlation this entry describes is also **not a fact about ERCOT, it
is a fact about ERCOT after about 2021.** Midday price at `LZ_WEST` relative to
the annual mean ran 1.15–1.54 from 2011 through 2019 and reached 0.51 in 2024;
negative-price hours went from 0 to 254. Solar cannibalised its own capture price
mid-record, and project 1's 2019 weather year is on the far side of the
inversion. Never quote a single price year as though the regime were stationary.

**7. 4CP is a forecasting problem, not a scheduling one.** Which four intervals
set the charge is unknown until after the fact. Charging against four *known*
hours is a clairvoyance bound; charging against the whole summer risk window is
the conservative bound. `coincident_peak_window` implements the conservative
one. Report the pair, not a point. And check the tariff — ERCOT/PUCT treatment
of large flexible loads has been actively changing and a 2026 study cannot cite
2019 rules.

**8. Export changes the PV answer completely.** Islanded, project 1 curtails
73.5% of everything it generates. Grid-connected with export rights, PV is
nearly free to oversize. Behind-the-meter vs front-of-meter is a switch that
moves the optimal PV size by a factor, and V1 currently assumes no export.

**9. The ITC swamps the effect being measured.** 30% base plus domestic-content
and energy-community adders moves PV and storage capex by 30–40%, which is
larger than any flexibility effect in the table above. Model pre- and
post-credit and state which is quoted. Deadlines and FEOC restrictions are
live policy in 2026 — parameterise, do not hardcode.

**10. The LP's answer is not buildable.** Interconnection comes in transformer
sizes and queue positions, not continuous MW. Generators come in unit sizes.
Report the continuous optimum, then round to a procurable configuration and
re-simulate — never present `147.3 MW / 26.4 MW` as a spec.

**11. Battery degradation cuts both ways.** ~2%/yr fade means either day-one
oversizing or an augmentation budget. But flexibility that reduces cycling also
reduces fade, a second-order benefit worth capturing — project 1 already has
rainflow counting and a fade surrogate.

**12. "GPU-equivalent hours" hides deadlines.** A throttled GPU-hour and a full
one are not fungible for a deadline-bound training run. Acceptable in V1; it is
exactly what workload classes in V5 exist to fix.

**13. The price record is shorter than the weather record.** ERCOT's nodal
market opened 1 December 2010. Weather goes back to 2010 and prices do not, so a
"fifteen-year" sweep is fourteen years the moment prices are real. Stating the
year count without stating which series binds it is how an off-by-one enters a
headline.

---

## Roadmap

The brief's V1–V6 ladder is right in shape but front-loads the wrong things.
Grid and gas are not late additions — they are what makes the unconstrained
answer interesting, and V1 here already carries them because they cost about
twenty lines each in an LP. What is genuinely hard comes later.

| | | |
|---|---|---|
| **V1** ✅ | PV + BESS + grid + gas + concave curve, one LP, one year | done |
| **V2** ✅ | Interconnection-constrained sweep; the crossover where flexibility starts paying | `run_grid_sweep.py`, `run_crossover.py` |
| **V3** ✅ | Real ERCOT day-ahead prices, same year and node as the weather | `prices.py`, `run_v3_prices.py` |
| **V4** ✅ | Foresight validation: size by LP, operate under a receding horizon, report the gap | `run_v4_foresight.py`, `summarise_v4.py` |
| **V5** | Workload classes, deadlines, inference SLAs | needs MILP or a rolling relaxation |
| **V6** | All fourteen overlapping years × sites; is the sign stable? | the publishable artefact |
| **V7** | Interactive web app over a precomputed result cube | [`docs/web-app-todo.md`](docs/web-app-todo.md) |

MILP arrives only at V5, and only for deadline coupling. Everything before it
stays an LP, which is what keeps a fifteen-year × multi-site sweep affordable.

---

## Running it

Prototype coupling: this imports project 1 from `../solar-project-1` for
weather, the PV model and the GPU curve, and runs on its virtualenv. Those three
artefacts were expensive to get right and forking them would create two
divergent copies. Fixing the coupling properly — package project 1, or vendor
the files against a pinned commit — is the first thing to do if this outlives
the prototype.

```sh
../solar-project-1/.venv/bin/python scripts/run_v1.py
../solar-project-1/.venv/bin/python scripts/run_grid_sweep.py
../solar-project-1/.venv/bin/python scripts/run_crossover.py
../solar-project-1/.venv/bin/python scripts/fetch_prices.py       # once; warms data/prices
../solar-project-1/.venv/bin/python scripts/run_v3_prices.py
../solar-project-1/.venv/bin/python scripts/summarise_v3.py
../solar-project-1/.venv/bin/python scripts/run_v4_foresight.py
../solar-project-1/.venv/bin/python scripts/summarise_v4.py
../solar-project-1/.venv/bin/python scripts/run_v5_workload.py
../solar-project-1/.venv/bin/python scripts/summarise_v5.py
../solar-project-1/.venv/bin/python scripts/run_v6_sweep.py    # ~30 min on 5 cores
../solar-project-1/.venv/bin/python scripts/summarise_v6.py
../solar-project-1/.venv/bin/python -m pytest
```

Roughly 60–75 s per 8760-hour solve via HiGHS.
