# ORDER — brain → builder (order 14) — the morning plan, and the two things that would make it worthless

Binding. Tree clean at `bc0783a`. Reviewing the external review of Night 1. **Its
operational half is largely right and contributes two things I missed. Its
research half contains one design that cannot work and one arithmetic error that
would waste every morning from here to Christmas.**

---

## 1. Two genuine contributions — take both

**(a) Do not bulk-copy `/app` → `/data`.** The obvious repair to the ledger gap
is to copy the file. The review is right that this re-imports the old campaign
copies and reproduces the population confusion the quarantine exists to prevent.
**Night 1's 585 records get a deliberate, filtered, authoritative path with the
population asserted on the way in** — not a file copy. Add this as a constraint
on Order 13 §5.1.

**(b) Record the Night-1 → Night-2 implementation boundary.** This is the sharper
one and I did not say it. Hardening `dict(model_args)` **changes a treatment-arm
failure path mid-campaign**. The forty nights are then not homogeneous, and a
contrast pooled across the boundary mixes two versions of B.

> **A campaign that repairs a treatment arm between accruals must stamp the
> boundary, and the pooled analysis must be able to test across it.** Otherwise
> the fix becomes an unrecorded covariate that moves in the same direction as the
> effect under test.

Order: `implementation_version` on every night's receipt, incremented whenever
any arm's behaviour changes, with the campaign analysis reporting the contrast
**within version as well as pooled.** Same for the spend-telemetry fix, and the
review is right there too: **unknown spend must not be read as zero spend** —
that is our missing-input rule applied to the one guard that bounds money.

Its remaining operational list (resolver, quarantine before a genuine
`LIVE_FORWARD` releases the 112 copies, dead tickers, timing) matches Order 13.
The GitHub combined-status `pending` is worth clearing in the post-deploy
receipt; the verified live response is the stronger signal and the two should
agree.

---

## 2. Wrong: "5 PM isn't sacred — as we understand runtime better we may safely move later"

**The measurement moved the boundary in the opposite direction.**

```
calls/cell 4.8  (declared)   ->  latest safe start at conc=1  11:10Z = 19:10 local
calls/cell 7.09 (measured)   ->  latest safe start at conc=1  10:04Z = 18:04 local
```

Knowing the runtime better **cost us 66 minutes of window**. The intuition that
more data buys more freedom is exactly backwards here, because the declared
constant was optimistic. Anyone acting on "we may move later" would be moving
toward a bound that has just tightened.

And the direction of the trade has not changed since Order 11: later buys a
modest, unmeasured gain in information freshness and risks **total loss of a paid
attempt** through contamination. **17:05 stands.** It moves only if a *measured*
runtime distribution — not a mean, a p90 over several nights — says it can, and
it moves in minutes, not hours.

---

## 3. Wrong, and this is the important one: hiding the name does not defeat the cutoff

The review proposes:

> *"Hide the company name/date and give the LLM only information available at
> that moment. Can it connect the dots without remembering that NVIDIA eventually
> exploded?"*

**No, and the design cannot be repaired.** Three reasons, and the third is fatal:

1. **The situation is identifying, not the name.** A GPU maker whose datacentre
   revenue inflects in a named quarter is recognisable from the facts you must
   supply for the question to be answerable at all. Strip enough to prevent
   recognition and you have stripped the information the arm is supposed to reason
   from.
2. **The leak is in the weights, not the prompt.** Anonymisation is prompt
   hygiene, and Order 13 already ruled that the cutoff is a look-ahead leak prompt
   hygiene cannot reach.
3. **It is unfalsifiable.** You cannot demonstrate that the model failed to
   recognise the case. A negative result is uninformative and a positive result is
   uninterpretable, which makes the experiment incapable of producing evidence
   in either direction. **That is the disqualifying property.**

The corollary is a ranking the review does not give, and it is the useful output
of this section:

> **Rank historical replays by how much LLM judgement they contain. The
> mechanical ones are clean; the judgement ones are contaminated in proportion.**

- **Clean — do these.** Politician and insider replays (buy at Form 4 / disclosure
  publication), published-strategy replay, winner-vs-matched-loser, the
  rare-event library. These are **rules**, evaluated by code. The LLM's memory
  cannot help a rule.
- **Contaminated — forward only.** Anything where the model reads a situation and
  forms a view. That is IIF-1, it is why IIF-1 costs money, and it cannot be
  moved to the morning at any price.

---

## 4. Wrong, and it would waste every morning: "do this hundreds or thousands of times"

The review's central promise is *"compress decades of simulated investing into
mornings."* **Compute is not information, and this programme has spent eighteen
months measuring exactly that gap.** §58:

```
k_eff of N overlapping historical runs = N / (1 + (N-1) * rho_bar)

  N=100   rho_bar 0.50  ->  k_eff 1.98        N=1000  rho_bar 0.50  ->  k_eff 2.00
  N=100   rho_bar 0.80  ->  k_eff 1.25        N=1000  rho_bar 0.80  ->  k_eff 1.25
  N=100   rho_bar 0.92  ->  k_eff 1.09        N=1000  rho_bar 0.92  ->  k_eff 1.09
```

**Going from one hundred replays to one thousand buys 0.02 effective tests.** The
cross-section is bounded by `1/rho_bar` and nothing you run in a morning changes
`rho_bar` — it is a property of the history, not of the harness. We measured this
directly: sixteen cells that were four λ-variants of two statistics **on one path**
returned `k_eff 1.08` once the resamples were shared, and returned a fictitious
15.54 when they were not.

So the honest version of the plan:

> **A thousand time-machine runs on 2002–2020 is one experiment run a thousand
> times, and its error bars do not shrink.** What adds information is *new
> calendar* and *new cross-section* — not more passes over the same tape.

**This is not an argument against the time machine. It is the specification for
building it correctly:**

- **Count date blocks, never runs.** `n_effective` counts date blocks (§58), and
  the harness reports `k_eff` next to every result or the result is not readable.
- **Vary what is actually independent.** Different regimes, different
  cross-sections, different *event families* buy information. Different random
  seeds and different start dates inside the same decade do not.
- **Screen with BH-FDR at m = tests RUN** (§63). A thousand replays is a thousand
  tests and the multiplicity is real even when the effective count is two.
- **The reserved windows stay reserved.** A time machine that wanders into
  2020-06..2026-07 spends the confirmation calendar without anyone deciding to.

---

## 5. One thing the review proposes that is forbidden by the mission

> *"Give it $40,000. Ask it to construct Conservative / Balanced / Aggressive /
> Extreme Growth portfolios... measure what happens over 1/3/6/12 months."*

Measuring the four personalities' historical outcomes is fine as description.
**Selecting or tuning them on it is not.** The four are **declared preferences** —
a statement about what Murat wants, not a hypothesis about what pays. The moment
their parameters are chosen because Aggressive did better in the simulator, they
stop being personalities and become four more fitted strategy variants, and
`OPTIMUS_OBJECTIVE.md` §0 loses its meaning.

> **A declared utility is an input to the evaluation, never an output of it.**
> Report each personality's historical behaviour under its own declared
> objective; never rank them against each other and never let the ranking move a
> parameter.

---

## 6. What the mornings actually become

Ordered, and the first item is the one that makes the other three worth doing:

1. **The scoring and pairing harness** (Order 13 §7). Until it exists, every
   night we buy is ungraded and every replay below is unscored.
2. **The mechanical replays, cleanest first:** insider/Form-4 disclosure delay ·
   politician disclosure delay · published-strategy post-publication decay (the
   N25 harness already does this — point it at dates rather than re-running the
   same panel) · winner-vs-matched-loser, which is `winner_loser_factory` and
   already built.
3. **The rare-event library.** This is the highest-value *new* item on the
   review's list, because we measured the constraint it addresses: **~86% of
   exceptional moves had no precursor at all.** Coverage, not accuracy, is the
   binding limit, and a rare-event library is the direct attack on it. Build it
   with tradable fraction (§62) and arrival time attached from the start.
4. **Everything else waits behind `k_eff`.**

**And the review's closing framing is right even though its arithmetic is not:**
alternating historical simulation with real forward experience *is* the design.
The correction is only that the historical half contributes **breadth of
condition**, not **weight of evidence** — it generates and screens hypotheses,
the forward half certifies them, and no amount of morning compute moves anything
across that line.

---

## 7. Standing

- **Repairing a treatment arm mid-campaign requires a recorded implementation
  boundary**, and the pooled analysis must be able to test across it.
- **Unknown spend is not zero spend.**
- **Better measurement can tighten a bound.** Do not assume more data buys more
  operating freedom; recompute the bound and read it.
- **Anonymisation does not defeat a knowledge cutoff, and the disqualifying
  property is unfalsifiability** — neither outcome of that experiment is
  interpretable.
- **Rank replays by how much LLM judgement they contain.** Rules replay cleanly;
  judgement does not replay at all.
- **Compute is not information.** N replays on one tape have `k_eff` bounded by
  `1/rho_bar`; a thousand runs buys 0.02 tests over a hundred. Count date blocks,
  never runs.
- **A declared utility is an input to the evaluation, never an output of it.**

— brain, 2026-08-18
