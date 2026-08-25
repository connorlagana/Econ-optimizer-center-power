# Is it cheaper to build a power plant, or to let the computers run slower?

A large AI data center uses about as much electricity as a small city. The
waiting list for a grid connection that size now runs to years, so operators
build their own supply instead — solar panels, batteries, backup generators —
and that gets expensive very fast.

There is another option, which until recently nobody took seriously: **let the
computers run slightly slower on the handful of days when power is tightest, and
build a smaller power plant.** This project works out when that trade is worth
making, and when it is not.

The short answer is that it depends almost entirely on **how big a grid
connection you managed to get**. Not on solar, not on batteries, and not on
anything about the computers themselves.

There is an interactive version of the main results at
[`web/`](web/) — see [Running it](#running-it).

---

## What the words mean

This is a technical study, but the ideas in it are not complicated. A few terms
turn up constantly:

| term | what it means here |
|---|---|
| **grid connection** | How much power the site is allowed to draw from the public grid. Measured in megawatts (MW). Getting a big one takes years. |
| **never slowing down** | The site always runs its computers flat out, whatever the power costs. The conventional design. |
| **running slower** | The site is allowed to give up a small share of the year's computing work, spread out however is cheapest. |
| **cost of an hour of computing** | Everything — chips, solar, batteries, generators, grid bills, fuel — divided by the computing actually done. The number that decides whether a design is good. |
| **cost of the power plant** | The same total, but leaving the chips out. What a site developer's budget looks like. |
| **the model** | A piece of maths that picks the cheapest possible combination of solar, batteries, generators and grid connection, *and* schedules every hour of the year, at the same time. It finds the genuine best answer rather than the best of a few guesses. |

One number is worth holding on to before anything else. In these scenarios the
chips cost roughly **$626 million a year** and everything that makes electricity
costs roughly **$63 million a year**. So an hour where a chip sits idle throws
away about **$1.00** of what you paid for it, while the electricity that hour
would have used costs about **six cents**.

Fifteen to one. Every argument for slowing down to save power has to clear that
gap first, and most of them do not.

---

## How this is worked out, and why it matters

There are two ways to answer a question like this.

The obvious one is to sketch five plausible designs, simulate each hour by hour,
and pick the winner. That is what most studies do. It has a fatal weakness: you
only ever learn which of your five guesses was best, and with five things to
choose at once — how much solar, how many batteries, how big a battery, how big
a generator, how big a grid connection — you would need an impossible number of
guesses to be confident about any of them.

The approach here instead asks the maths to find the cheapest design directly.
Everything in the problem happens to be *linear* — doubling the solar farm
doubles its cost and doubles its output — which means a well-understood technique
can find the exact best answer rather than search for it. The one part that could
have broken this is the relationship between a chip's power and its speed, which
is a curve rather than a straight line. It turns out to be a curve of exactly the
right shape to be handled without any tricks.

The practical result: **the design is an answer this study produces, not an
assumption it starts with.** Every table below is the best possible plant for
that situation, not the best of a shortlist.

A second choice worth flagging. The natural thing to minimise is cost *per unit
of computing*, which is a ratio and is awkward to handle directly. Rather than
reach for a clever technique, the study fixes how much computing must be done and
minimises cost, then repeats that for every level of computing. Sweeping it out
that way produces the entire trade-off curve — which was the thing worth having
anyway — and the cost per unit of computing is simply a column in it.

---

## Round 1: the surprising thing about idle chips

The first run: Dallas, 2019 weather, 100 MW of computers (71,429
high-end chips), an unlimited grid connection at a flat electricity price, and Texas's summer peak-charge risk window of 610
hours. All equipment prices here are **estimates**, not quotes — read the shapes, not the
digits.

| | batteries | power plant $/yr | computing done | cost per chip-hour |
|---|---:|---:|---:|---:|
| never slows down | none | $63.3M | 100.0% | $1.1018 |
| switches machines off, 99% | none | $60.3M | 99.0% | $1.1081 |
| runs slower, 99% | none | $58.5M | 99.0% | $1.1052 |
| runs slower, 96% | none | $52.2M | 96.0% | $1.1293 |

Three things come out of this, and the third is the point of the whole project.

**The chips dominate everything.** $626M a year of chips against $63M a year of
everything that makes electricity. Any study that measures "useful computing"
without counting what the chips cost will happily throttle them, and will be
wrong by a factor of fifteen about what that costs.

**So flexibility makes the power plant cheaper and still loses.** Running slower
to a 96% target cuts the power plant's cost by 17% — and *raises* the cost of an
hour of computing by 2.5%, because 4% of the computing is worth more than 17% of
a relatively small number. With an unlimited grid connection, slowing down is
simply a bad idea. That is the opposite of what the project set out expecting,
and it is correct.

**Running slower beats switching machines off.** At the same 99% target, turning
the chips' speed down costs $58.5M against $60.3M for parking some of the
machines idle — and needs 58 MW of solar instead of 115 MW. Chips are
disproportionately efficient when running gently, and that efficiency is worth
real money on its own, separately from the value of just doing less work.

**And there is one place flexibility is enormously valuable even here.** Texas
charges large power users based on their demand during the four moments of peak
grid stress each summer. Giving up **one percent** of the year's computing takes
the site's exposure to that charge from 125 MW to 62 MW — worth about $4.7M a
year for roughly 88 chip-hours of lost work. The useful question is never "what
share of the year can you go dark" but **how few hours, and how deep**.

---

## Round 2: what happens when you cannot get the grid connection

An unlimited 125 MW grid connection is not something a project starting today can
buy. It is a place in a queue with a date on it. So: constrain it, and size the
whole plant twice at each size — once never slowing down, once allowed to run
slower.

| grid connection | plant, rigid | plant, flexible | change | cost/hr rigid | cost/hr flexible | change |
|---:|---:|---:|---:|---:|---:|---:|
| 125 MW | $63.3M | $52.2M | −17.5% | $1.1018 | $1.1293 | **+2.50%** |
| 60 MW | $107.8M | $71.4M | −33.7% | $1.1729 | $1.1613 | **−0.99%** |
| 30 MW | $136.5M | $97.4M | −28.7% | $1.2189 | $1.2045 | −1.18% |
| 10 MW | $157.6M | $116.5M | −26.1% | $1.2526 | $1.2364 | −1.29% |
| 0 MW | $168.6M | $126.9M | −24.8% | $1.2702 | $1.2536 | −1.31% |

**Somewhere between 125 MW and 60 MW, the answer flips.** That is the finding.
And notice what it is a statement about: the scarcity of grid capacity. Not
solar, not batteries, not whether chips can be throttled. As the grid connection
is taken away, the power plant's cost grows from $63M to $169M a year — and once
it is a big enough slice of the chip bill, saving a quarter of it is worth losing
4% of the computing.

**What flexibility replaces is the generator, not the battery.** At a 60 MW
connection the never-slow-down design builds 140.1 MW of backup generation. The
flexible one builds **1.4 MW** — a hundredfold difference, against only −25% on
batteries and −21% on solar. The project expected batteries to be displaced. The
model says the first thing to go is the machinery you bought purely to survive
the worst few hours of the year, because surviving them by computing slightly
less is nearly free.

### Two numbers, both true, for two different people

The power plant gets 25–34% cheaper. The cost of an hour of computing falls about
1%. **Both come from the same run.** The first is what matters to whoever builds
the plant; the second is what matters to whoever signs for the chips, and it is
small because the chips are most of its denominator. Quoting either alone is a
way of misleading somebody, so this study always quotes both.

### Where exactly it flips

| grid connection | cost/hr rigid | cost/hr flexible | change |
|---:|---:|---:|---:|
| 125 MW | $1.1018 | $1.1293 | +2.50% |
| 110 MW | $1.1125 | $1.1293 | +1.51% |
| 95 MW | $1.1262 | $1.1329 | +0.59% |
| **~85 MW** | | | **break-even** |
| 80 MW | $1.1446 | $1.1410 | −0.32% |
| 60 MW | $1.1729 | $1.1613 | −0.99% |

Running flat out this site draws 125 MW, so the break-even sits at roughly **68%
of what the site needs**. Put that way the finding travels to other sites: below
about two-thirds coverage, letting the computers slow down pays for itself; above
it, the computing you give up is worth more than the plant you save.

### How much slack to buy: 2%, not 8%

The trade-off curve at a 60 MW connection:

| computing target | solar | batteries | generators | plant $/yr | cost/hr |
|---:|---:|---:|---:|---:|---:|
| 100% (rigid) | 369.3 MW | 1,234 MWh | 140.1 MW | $107.8M | $1.1729 |
| 99% | 364.7 MW | 1,199 MWh | 62.9 MW | $93.2M | $1.1613 |
| **98%** | **344.7 MW** | **1,130 MWh** | **22.7 MW** | **$83.3M** | **$1.1569** |
| 97% | 303.4 MW | 979 MWh | 19.6 MW | $76.6M | $1.1578 |
| 96% | 293.0 MW | 928 MWh | 1.4 MW | $71.4M | $1.1613 |
| 94% | 252.4 MW | 724 MWh | 2.4 MW | $63.6M | $1.1727 |
| 92% | 220.2 MW | 543 MWh | 8.2 MW | $58.0M | $1.1885 |
| 90% | 209.6 MW | 492 MWh | 0.0 MW | $53.8M | $1.2075 |

**More slack is not better.** The power plant keeps getting cheaper all the way
down — that part is straightforward. But the cost of an hour of computing bottoms
out at 98% and by 92% is worse than never slowing down at all. Buying too much
flexibility is worse than buying none, and the "8% of annual computing" figure
this project started from sits well past the point where the trade has already
reversed.

So the honest headline for this scenario:

> At a 60 MW grid connection serving a site that needs 125 MW, allowing **2%** of
> the year's computing to be given up removes **84% of the backup generators** and
> **23% of the power plant's cost**, and lowers the cost of an hour of computing
> by **1.4%**. Past about 4%, the trade reverses.

**One caveat, about the mix rather than the totals.** Generators are what gets
traded away across the whole curve — 140 → 63 → 23 → 1.4 MW — while batteries
fall far more slowly. But the generator column is not smooth (1.4 MW at 96%, 8.2
at 92%, zero at 90%), and that is the signature of a shallow optimum: near the
bottom, several different mixes cost almost the same and the model just picks
one. The totals and the cost curve are solid. The exact mix at any single point
is not. Before quoting a mix, pin the total and re-solve.

---

## Round 3: real electricity prices, and a shortcut that survived

Rounds 1 and 2 priced grid electricity at a flat $45 per megawatt-hour, which
was always the study's biggest hole. Real prices swing hour by hour, and the
whole question is about *when* power is expensive. So this round brings in the
actual hourly prices the Texas grid operator published, for the same place and
the same year as the weather, 2011 to 2024.

Swapping a made-up flat price for a real one changes two separate things at once
— the average level, and the hour-by-hour shape — so the experiment runs three
versions to keep them apart: flat at $45, flat at the year's true average, and
the real hourly series. The middle rung corrects a wrong number. The gap between
it and the third is the thing actually worth measuring.

### The break-even barely moves

| priced at | break-even | as % of what the site needs |
|---|---:|---:|
| the flat $45 guess | 106.6 MW | 85% |
| flat, at the true average ($38.12) | 109.6 MW | 88% |
| real hourly prices | 108.4 MW | 87% |

Three percent, on a number the previous round would only ever state as "roughly
two-thirds to five-sixths". **The flat-price shortcut survived.** And the reason
is round 1's own finding: what flexibility sells is avoided *capacity* —
generators you did not build, peak charges you did not incur — both billed per
kilowatt. The hour-by-hour shape of an electricity price moves the *energy* bill,
which is the part flexibility was never competing against.

Worth saying plainly, because it is the opposite of what the worry predicted. The
worry was not wrong about the mechanism. It was wrong about which conclusion the
mechanism threatened.

### But the plant you should build changes completely

At a 125 MW grid connection, sizing for a site that never slows down:

| priced at | solar | batteries | power bought | energy bill | peak-charge exposure |
|---|---:|---:|---:|---:|---:|
| flat $45 | **none** | none | 1,095 GWh | $49.3M | 125.0 MW |
| flat, true average | **none** | none | 1,095 GWh | $41.7M | 125.0 MW |
| real hourly | **113.6 MW** | 216 MWh | 865 GWh | $19.0M | 76.5 MW |

A flat price says *build no solar at all*. The real price says *build 114 MW of
it and a two-hour battery*, cuts the power bought by 21%, cuts the energy bill by
61%, and takes peak-charge exposure from 125 MW to 76.5 MW. Same model, same
weather, same site.

### Why, in one number

What a megawatt of solar is worth in a year is just its output multiplied by the
price in each hour, added up. Against an annual cost of $111,269 per MW:

| valued at | worth | verdict |
|---|---:|---|
| the year's average price | $79,158/MW-yr | does not pay for itself |
| the actual hourly price | $151,370/MW-yr | pays for itself |

**A flat price undervalues solar by 48%** here, because solar produces
disproportionately in hours that are priced above average — 2019's average of
$38.12 sits against a *typical* hour of $20.86, so the average is dragged up by a
few hundred hot afternoons that are also sunny ones. That single ratio is the
difference between building no solar farm and building a 114 MW one.

### And this is not a permanent fact about solar

| year | what a MW of solar earns | vs its cost |
|---:|---:|---:|
| 2019 | $151,370 | 1.36× |
| 2021 | $285,961 | 2.57× |
| 2023 | $207,983 | 1.87× |
| 2024 | $63,451 | **0.57×** |

The same array, the same costs, four different price years. It pays for itself in
2019, pays 2.6 times over in 2021 — the year of the Texas winter storm — and
misses by 43% in 2024.

The cause is visible in the price record with no model at all. Here is the midday
price in west Texas, as a ratio to that year's average:

| 2011–2019 | 2020 | 2023 | 2024 |
|---:|---:|---:|---:|
| 1.15–1.54 | 0.99 | 0.78 | **0.51** |

Midday was Texas's *expensive* time for the first decade of this market and is
now its cheapest, with 254 hours of *negative* prices in 2024 against zero in
2019. So much solar was built that it destroyed its own value at exactly the
hours it generates — and the 2019 weather year this study inherited sits on the
far side of that flip.

This is what makes round 6 mandatory rather than decorative. It is not that one
year is noisy. It is that the underlying relationship **reversed direction
mid-record**, so no single year represents any other, and a study quoting one
year is describing a moment rather than a climate.

### Two smaller things this round settled

**Selling power back to the grid is now a switch**, restricted to solar. Selling
generator output is a merchant power station with a different permit; selling
stored energy is a trading business that deserves its own study. It defaults off,
because rounds 1 and 2 assumed the site serves only itself and the comparison has
to hold. Turning it on without also limiting the grid connection does not answer
the question — it raises a different one, because with unlimited land and an
unlimited wire, building solar to sell has no upper bound. At 2019 prices that
business clears its own costs by about $3k per MW a year, so the model genuinely
has no answer; at 2024 prices it misses by $53k and the same model is fine. The
code says so explicitly rather than letting the solver return a confusing error.

**The price record is shorter than the weather record.** The Texas wholesale
market opened on 1 December 2010, so 2010 is a one-month file. Fourteen years
overlap, not fifteen, and the code refuses a partial year rather than padding it.

### What is still open here

These are day-ahead prices, not real-time ones. Real-time carries the dramatic
scarcity spikes that make flexibility look valuable — but handing a year of them
to a model that can see the whole year in advance measures clairvoyance, not
flexibility. Day-ahead is also the price a site can actually contract against.
The right home for real-time prices is round 4's more realistic operator, and
that pairing is not yet built.

---

## Round 4: what survives when the operator cannot see the future

Every design so far was sized by a model that sees all 8,760 hours of the year at
once. No real operator can. This round takes three of those designs and re-runs
them under a controller that can only see 48 hours ahead — once with a perfect
two-day forecast, once with a realistically wrong one — and divides by the
computing *actually delivered* rather than the computing promised.

| design | promised | perfect 2-day forecast | realistic forecast | cost of the short horizon | cost of forecast error |
|---|---:|---:|---:|---:|---:|
| 60 MW, never slows | 100.00% | 97.52% | 97.51% | 2.372% | 0.045% |
| 60 MW, runs slower to 98% | 98.00% | 97.48% | 97.38% | 0.503% | 0.121% |
| no grid at all, 96% | 96.00% | 93.45% | 93.01% | 2.673% | 0.461% |

### The prediction was wrong, in an interesting direction

The expectation was that perfect foresight makes every design look better than it
really is. It does — every design under-delivers. But it does *not* do so evenly.
It flatters the **never-slow-down** design most, because that design's entire
selling point is "never misses an hour", and never missing an hour is precisely
what knowing the future buys you. Run realistically, it cannot keep its promise
either: it delivers **97.51%**, not 100%.

Which collapses the comparison the whole planning study rested on:

| | plant $/yr | computing delivered | cost/hr | vs rigid |
|---|---:|---:|---:|---:|
| never slows, as promised | $107.8M | 100.00% | $1.1729 | — |
| runs slower to 98%, as promised | $83.3M | 98.00% | $1.1569 | −1.37% |
| never slows, as actually operated | $106.9M | 97.51% | $1.2014 | — |
| runs slower to 98%, as actually operated | $83.1M | 97.38% | $1.1640 | **−3.11%** |

On paper the trade looks like *2 percentage points of computing for 23% of the
plant*. Operated realistically, the two designs deliver computing within **0.13
percentage points of each other** — and one of them costs 23% less to build.

Checking the realistic case did not weaken the argument for flexibility. It
roughly **doubled** it.

The general lesson is worth more than the number: a planner that assumes perfect
foresight does not flatter every design equally. It systematically favours
whichever design most depends on knowing the future. Skip this check and you do
not merely get optimistic numbers — you rank the designs in the wrong order.

### Seeing further beats forecasting better, by four to six times

At every design, the cost of only seeing 48 hours ahead is several times the cost
of a realistically wrong forecast: 2.372% against 0.045%, 0.503% against 0.121%,
2.673% against 0.461%. That is actionable, because seeing further is a bigger
computer and forecasting better is a procurement contract. Before it gets quoted,
the horizon needs sweeping — 24, 48, 96, 168 hours — since one point cannot show
where the curve flattens out.

### Cutting the grid off entirely is expensive, and foresight is why

The fully islanded design loses 3.13% of its value against 0.63% for the one with
a 60 MW connection — five times worse — and it is the only case that ever fails
to power its own load — 139.5 MWh of it, over 17 hours, and only under the
realistic forecast. A grid connection absorbs forecast mistakes. Without one,
every mistake is paid for out of a battery or a fuel tank.

### Two bugs this experiment found, both of which produced believable numbers

Recorded because both were silent, and silence is the failure mode that matters.

**The penalty for failing to power the site was scaled by the value of
computing** — which is legitimately zero for the never-slow-down design, because
computing is not a choice there. That scaled the penalty to zero too, so the
controller cheerfully shed the entire year's load for free and reported 100%
computing. Any penalty that a legitimate input can scale to zero is not a
penalty. It is now a fixed number.

**The never-slow-down design was written as "always draw full power, always
deliver 100%".** That is how the *planner* states it, and there it is exactly
right, because the plant is sized so the case never comes up. Carried into an
operator that can fail, it credited full computing for hours the plant could not
power — 100% computing across 834 hours of blackout. Both are now pinned by
tests.

---

## Round 5: deadlines, and why they mostly do not matter

Every number so far quietly assumed that computing is one big interchangeable
pool — that work given up in August can be made good in November. That is the
most flexible a workload could possibly be, which makes every earlier result an
upper bound. This round puts real deadlines on the work and measures how much of
that bound is real.

Three kinds of work, differing only in how tightly they are tied to the clock:

- **Chatbot-style serving.** Must happen the moment it is asked for. Cannot move
  at all, and its busy hours are the evening — which is when power is scarcest.
- **Training with a deadline.** A quantity of work that must finish inside a
  window: so much per day, per week, per month. Free to move inside the window,
  unable to cross it.
- **Background batch.** An annual total, placeable anywhere. This is exactly what
  rounds 1 through 4 assumed.

### It did not need heavier machinery, and that is a result

The roadmap assumed deadlines would force a much harder and slower class of
problem. They do not. A deadline is just "this much must be finished by then",
which is the kind of constraint the existing approach handles natively. Writing
the chip speed curve in absolute terms rather than as percentages keeps the whole
thing tractable. Heavier machinery is only needed for genuinely all-or-nothing
choices — a job that must run for a minimum unbroken stretch, or be admitted
whole or not at all — and none of those are modelled here. That matters
practically: it is what keeps a fourteen-year sweep affordable.

### How much of the bound is real

All work deadline-bound, at a 60 MW connection, 2019 prices, 98% target:

| deadline window | cost/hr | vs never slowing | generators | value kept |
|---|---:|---:|---:|---:|
| never slows | $1.1594 | — | 152.0 MW | — |
| annual (the old assumption) | $1.1425 | −1.461% | 27.8 MW | 100% |
| monthly | $1.1506 | −0.764% | 78.9 MW | 52% |
| weekly | $1.1530 | −0.553% | 93.9 MW | 38% |
| daily | $1.1569 | −0.219% | 111.2 MW | 15% |
| six hours | $1.1611 | **+0.142%** | 128.3 MW | **−10%** |

A monthly deadline halves the value of flexibility; a weekly one removes 62% of
it; at a six-hour window the trade reverses entirely. The generators climb back
towards the never-slow-down design's 152 MW as the window shrinks — the same
story as round 2, told backwards. What flexibility buys is not having to build
for the worst hours, and it can only do that if it is allowed to move work far
enough to reach them.

### But almost no realistic mix is affected at all

Every mixed workload tested returns **exactly** the simple pool's answer — same
cost to six decimal places, same 335.3 MW of solar, same 27.8 MW of generators:

| mix | cost/hr | value kept |
|---|---:|---:|
| half weekly deadline, half batch | $1.1425 | 100% |
| 75% weekly deadline, 25% batch | $1.1425 | 100% |
| 90% weekly deadline, 10% batch | $1.1425 | 100% |
| 30% chatbot serving, 70% batch | $1.1425 | 100% |
| 60% chatbot serving, 40% batch | $1.1425 | 100% |
| 30% serving, 50% weekly, 20% batch | $1.1425 | 100% |

Non-deferrable serving work at 60% of the fleet costs nothing. A weekly deadline
on 90% of the fleet costs nothing.

### Why — and a rule that predicts it

**Because the model does not want to interrupt anything in the first place.** Its
preferred schedule never drops below **91.5%** in any hour of the year. It takes
its 2% by shaving a little power off **3,079 separate hours** rather than by
cutting deeply in a few. The shape of the chip efficiency curve is what makes
that the cheap way to do it: throttling gently gives up very little work for the
power it frees.

So a deadline only bites if it demands more than the model was going to deliver
anyway. That gives an exact, checkable rule:

| window | lowest the model ever goes | deadlines bite above |
|---|---:|---:|
| annual | 98.00% | 100.0% of the fleet |
| monthly | 94.85% | 96.8% |
| weekly | 93.45% | **95.4%** |
| daily | 91.52% | 93.4% |

Tested against the weekly threshold of 95.4%: shares of 92% and 95% come back
bit-for-bit identical to the simple pool, and 98% binds (cost $1.142994,
generators 27.8 → 44.8 MW). The rule predicts the
transition rather than describing it afterwards.

**Five percent of genuinely flexible work buys back all of it.** Anything short
of a fleet that is essentially entirely deadline-bound pays nothing for its
deadlines.

### What this changes about what you would actually sell

The worry was right that lumping all computing together hides deadlines. It was
wrong about the consequence. The hidden deadline costs nothing across the whole
realistic range, because the flexibility being used is **shallow and continuous**
rather than deep and occasional.

That reframes the product entirely. What the model wants is **"run 2% slower for
three thousand hours"**, not **"go dark 8% of the time"** — and those are
completely different things to sell, to contract for, and to operate.

It also resolves a separate worry from the other side. A large training run is
synchronised: slowing down some of the machines achieves nothing, because the job
runs at the pace of its slowest worker. But a *uniform* mild speed limit applied
across the whole job is precisely the one form of throttling such a job can
accept, since there is no straggler if everyone is slowed equally. The control
this study says is valuable is the control the hardware can actually offer.

The caveat is that none of this survives if the flexibility gets deep. At the
"8% of annual computing" figure the project started from, the cuts would have to
be far deeper than 91.5%, and deadlines would bite hard.

### What it costs, and why round 6 leaves it out

A three-class solve takes **1,126 seconds** against 40 for the simple pool,
because splitting the fleet hour by hour creates a large family of nearly-equal
answers the solver has to walk through — to arrive, in every mixed case tested,
at the pool's answer anyway. Until that is fixed, a fourteen-year workload sweep
is a different order of expense, which is why round 6 runs the simple model and
says so.

---

## Round 6: is this a finding, or a fact about 2019?

Every round so far ran on one weather year at one site. Round 3 showed that is
not a detail but a hazard: the relationship between solar output and price
*reversed* between 2020 and 2023, and the 2019 this study inherited sits on the
far side of that reversal.

So sweep it. Fourteen years, two sites each paired with the price point a site
there would actually be billed at, two grid connection sizes either side of the
break-even, never-slowing against running-slower at 98%. 112 separate solves.

The output is a distribution, and the only question worth asking of it is whether
the **sign** is stable — because an answer that flips with the weather year is
not an answer.

| grid connection | typical result | worst to best | favourable | verdict |
|---|---:|---:|---:|---|
| 125 MW (all it needs) | +0.542% | −0.170% to +1.151% | **2 of 28** | slowing down does not pay |
| 60 MW (48% of what it needs) | −1.141% | −1.539% to −0.426% | **28 of 28** | slowing down pays |

**With a squeezed grid connection the trade is favourable in every year at every
site, and it is never close to the line.** The worst case across fourteen years —
including the 2021 winter storm, including the collapse in solar's value — is
−0.426%, and the best is −1.539%. With a full-size connection it is unfavourable
in 26 of 28, and both exceptions are 2021, the year a winter storm made firm
capacity worth more than anything else in the record.

So round 2's headline survives contact with the entire price record. That is
worth more than the number it survived with.

### The site changes the size of the effect, not its direction

| site | typical at 60 MW | typical at 125 MW | rigid cost/hr at 60 MW |
|---|---:|---:|---:|
| Dallas | −1.399% | +0.738% | ~$1.16 |
| Midland-Odessa | −0.798% | +0.483% | ~$1.13 |

West Texas gets roughly **half** the benefit Dallas does — and the reason is not
that flexibility works worse there. It is that the never-slow-down plant is
already cheaper, because a 23% better solar resource — 2,550 against 2,076
full-output hours per MW per year — means the plant that never throttles costs
less to build in the first place. **Flexibility is worth most
where the alternative is worst.**

### The result nobody would have predicted from a single year

At a full-size 125 MW connection, **whether the model builds any solar at all
flips between years.** At Dallas:

| solar built | years |
|---|---|
| none at all | 2012, 2013, 2014, 2015, 2016, 2017, 2020, 2024 |
| 91–184 MW | 2011, 2018, 2019, 2021, 2022, 2023 |

Eight of fourteen years build **zero** solar; six build up to 184 MW. This is
round 3's mechanism — solar's worth is its output times the price, hour by hour —
now showing up as a yes/no outcome rather than a percentage. A study that picked
2016 and a study that picked 2019 would disagree about whether to build a solar
farm, using the same model, the same site, and the same costs.

**Report the distribution or report nothing.** A single-year answer here is not
merely imprecise; on the question it is most often asked, it is a coin flip
dressed up as an optimisation.

### What this round does not cover

One computing target and one set of equipment prices. The full trade-off curve
and the tax-credit cases are the obvious next steps, and both are affordable —
the constraint is that they multiply against fourteen years rather than one. The
workload structure from round 5 is deliberately *not* included, for the timing
reason given above.

---

## Ways to get this badly wrong

Ordered by how much damage each does if missed. The first four change the
answer's direction, not just its precision.

**1. Forgetting what the chips cost.** Covered at the top. An hour of computing
given up strands about $1.00 of chip; the electricity it would have used costs
about six cents. Any model that leaves the chips out of the sum will throttle
enthusiastically and be wrong by fifteen times about what that costs.
Non-negotiable.

**2. Assuming the operator can see the future.** The planning model sees all
8,760 hours; a real controller does not. **Measured in round 4, and the effect
was not what this entry originally predicted.** It is not an even haircut: the
planner systematically favours whichever design most depends on knowing the
future, which is the never-slow-down one. Skipping this check does not make a
study merely optimistic — it makes it rank designs in the wrong order. Check
every headline comparison, never just the winner.

**3. Unlimited gas.** Give the model unlimited generator hours and it will build
an unpermittable merchant power station, then report that cheap gas wins. Texas
emergency-engine permits cap non-emergency running at something like a hundred
hours a year. There is a setting for this — sweep it, because the conclusion
depends on it. **And it is an approximation:** it caps the generator's *fuel*
rather than its *hours*, because fuel is easy to constrain and hours are not. A
design that runs 1,500 hours at a third of load satisfies this model and violates
the real permit, which is exactly what the never-slow-down cases in round 2 do.
Read generator hours as a diagnostic, never as a compliance claim. Also: turbine
lead times in 2026 push them past any plausible in-service date, so reciprocating
engines are the realistic technology and the costs should be theirs.

**4. Treating cooling as a simple multiplier.** Chillers, pumps and electrical
conversion losses do **not** scale down to zero when the computers slow down —
a large part of them is fixed. Using a single efficiency multiplier makes a 40%
throttle look like it sheds 40% of the site's load, which overstates how much
power a throttle actually frees and therefore overstates the whole case for
flexibility. Modelled here as a fixed part plus a variable part. In west Texas
the fixed part is worst exactly when it hurts most: hot afternoons are peak
cooling, peak price, peak grid-charge risk *and* peak solar-panel heat losses,
all at once.

**5. Synchronised training jobs cannot be partly throttled.** Slowing some of the
chips in a synchronised training run buys nothing — the job runs at the pace of
its slowest worker. The control has to be a speed limit applied to the *whole
job* uniformly, not to a subset of chips. So a "throttle 30% of the fleet" policy
only works if 30% of the fleet is a separable job. Note also that the chip
efficiency curve here was measured on four chips in one machine; at cluster scale
the stragglers would flatten it, and that flattening is a direct haircut on
everything in this study.

**6. Mismatched prices and weather.** ~~Rounds 1 and 2 use a flat placeholder
price.~~ **Closed in round 3, and the entry was right about the mechanism and
wrong about the casualty.** A flat price undervalues solar by 48% at Dallas in
2019 — the difference between building no solar and building 114 MW — so the
*design* was badly wrong. But the break-even moved 3%, because flexibility sells
avoided capacity and the price shape moves the energy bill. Fix the prices to get
the plant right; round 2's headline did not depend on it.

The pattern this entry describes is also **not a fact about Texas, it is a fact
about Texas after roughly 2021.** Midday prices in west Texas ran 1.15–1.54 times
the annual average from 2011 through 2019, and reached 0.51 in 2024; hours of
negative prices went from zero to 254. Solar destroyed its own value mid-record,
and this study's inherited 2019 weather year is on the far side of it. Never
quote a single price year as though the world were standing still.

**7. Peak grid charges are a forecasting problem, not a scheduling one.** Which
moments set the charge is unknown until after the fact. Scheduling against four
*known* peak hours is a fantasy that lets the model dodge the charge with four
hours of downtime a year; defending the whole summer risk window is the
conservative version, and it is what is implemented. Report the pair, not a
point. And check the tariff — the rules for large flexible loads in Texas have
been changing, and a 2026 study cannot cite 2019 rules.

**8. Selling power back changes the solar answer completely.** Cut off from the
grid, a site throws away 73.5% of everything it generates. Connected, with the right to
sell, solar is nearly free to oversize. That switch moves the right amount of
solar by a factor, not a margin.

**9. Clean energy tax credits swamp the effect being measured.** Thirty percent
base plus adders moves solar and battery costs by 30–40%, which is larger than
any flexibility effect in this study. Model before and after, and say which you
are quoting. The rules are live policy in 2026 — make them a setting, never a
hardcoded number.

**10. The model's answer is not buildable.** Grid connections come in transformer
sizes and queue positions, not smooth megawatts. Generators come in unit sizes.
Report the exact optimum, then round to something procurable and re-simulate —
never present `147.3 MW / 26.4 MW` as a specification.

**11. Batteries wear out, and it cuts both ways.** Roughly 2% capacity loss a
year means either building extra on day one or budgeting to top it up. But
flexibility that reduces cycling also reduces wear, which is a second-order
benefit worth capturing.

**12. "Chip-hours" hides deadlines.** A throttled chip-hour and a full one are
not interchangeable for a deadline-bound training run. **Measured in round 5, and
the consequence is the opposite of the worry.** Across every realistic mix the
deadline costs *nothing*, because the model's preferred flexibility is shallow
and continuous rather than deep and occasional. Deadlines bite only above roughly
a 95% deadline-bound share, or when the window falls to hours. Do not assume the
simple pool is conservative; check it against the rule in round 5, which predicts
the transition exactly.

**13. The price record is shorter than the weather record.** The Texas market
opened on 1 December 2010. Weather goes back to 2010 and prices do not, so a
"fifteen-year" sweep is fourteen years the moment prices are real. Stating a year
count without saying which record runs out first is how an off-by-one gets into a
headline.

---

## Where this is up to

| | | |
|---|---|---|
| **Round 1** ✅ | Solar, batteries, grid, gas and the chip curve, all sized at once | done |
| **Round 2** ✅ | Sweep the grid connection; find where the answer flips | `run_grid_sweep.py`, `run_crossover.py` |
| **Round 3** ✅ | Real hourly Texas electricity prices, same year and place as the weather | `prices.py`, `run_v3_prices.py` |
| **Round 4** ✅ | Re-run it with an operator who cannot see the future | `run_v4_foresight.py`, `summarise_v4.py` |
| **Round 5** ✅ | Deadlines and service levels on the work itself | `workload.py`, `run_v5_workload.py` |
| **Round 6** ✅ | All fourteen years and both sites — does the answer hold? | `run_v6_sweep.py`, `summarise_v6.py` |
| **Round 7** ✅ | Interactive web version over pre-computed answers | `build_cube.py`, [`web/`](web/) |

The one genuinely surprising thing about the sequence: deadlines were expected to
force a much harder class of problem at round 5, and they did not. The whole
ladder stayed tractable, which is what kept the fourteen-year two-site sweep
affordable. Heavier machinery is still needed for all-or-nothing choices —
minimum run durations, whole-job admission, the cost of restarting from a
checkpoint — and that is now a future round rather than this one.

---

## Running it

This borrows weather data, the solar model and the chip curve from a sibling
project at `../solar-project-1`, and runs on its Python environment. Those three
things were expensive to get right and copying them would create two versions
that drift apart. Fixing that properly — packaging the sibling project, or
copying the files against a pinned version — is the first thing to do if this
outlives the prototype.

```sh
../solar-project-1/.venv/bin/python scripts/run_v1.py
../solar-project-1/.venv/bin/python scripts/run_grid_sweep.py
../solar-project-1/.venv/bin/python scripts/run_crossover.py
../solar-project-1/.venv/bin/python scripts/fetch_prices.py       # once; downloads the price archives
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

Each full-year solve takes roughly 60–75 seconds — but that average hides a split
the web build depends on: a never-slow-down solve is about 10 seconds and a
run-slower one about 90, because the chip efficiency curve is what makes the
problem large.

### The web version

```sh
../solar-project-1/.venv/bin/python scripts/build_cube.py --workers 7
../solar-project-1/.venv/bin/python scripts/build_v6_strip.py
cd web && npm install && npm run dev
```

The first command works out every combination the web page needs and saves the
answers to a file it can look them up in — 792 separate solves, about two and a
half hours on seven cores. A solve is far too slow to run while somebody waits,
so nothing is solved live; the page looks answers up and does arithmetic, which
is why its sliders are instant.

It is safe to interrupt. Each answer is written out the moment it lands, and
re-running picks up where it stopped. `--assemble-only` rebuilds the web page's
data file from whatever has been solved so far. See [`web/README.md`](web/README.md).
