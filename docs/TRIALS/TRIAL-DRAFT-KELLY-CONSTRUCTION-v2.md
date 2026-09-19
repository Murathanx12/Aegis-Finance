# TRIAL-DRAFT-KELLY-CONSTRUCTION — does conviction sizing beat 1/N at the same alpha? (v2)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-19 (chunk 19) by the Opus builder from
`docs/research_notes/2026-09-19/research_murat_ideas_adjudicated.md` §9, **before the book has a
single NAV row**. Not in `rule_experiments`; `cumulative_trials` not incremented. Registration and
seeding are both attended steps and both are Murat's.

**Book:** `PROFIT_ALLOCATOR_v2` in `backend/data/arena/arena_books_v1.yaml`.
**Twin:** `ENGINE_BASELINE_v1` — the arena's equal-weight control, already live with a NAV history.
**Family:** `KELLY_CONSTRUCTION_2026_09`, declared at size **1** (one primary). It extends no
existing family. Export-time multiplicity rule: **Holm** over the declared family; at size 1 Holm
is the identity, and it is named here so that a second primary added later cannot enter without
re-declaring the size.
**Licence:** `PRODUCT_EXPERIMENT`. Simulation in the arena namespace: no `paper_nav`, no lane YAML,
no order path, no real capital, no skill claim.

---

## 0. Why this trial exists at all, and what it is NOT

`PROFIT_ALLOCATOR_v1` was seeded 2026-08-21 and retired 2026-08-23 (`arena/spec.py::RETIRED`). The
reason was not a result: the trust router's cluster adjustment had been ON-by-mistake-OFF, the
correction made it ON, and because the router's verdict feeds `ce_kelly` sizing directly it is part
of a ce_kelly book's **policy identity** — so the book correctly refused to continue under its own
seed rather than leaving one NAV series describing two policies. **It has one NAV row. Its
construction was never measured.**

So this is a re-registration of a question that never got asked, not a resurrection of a refuted
one. The corpse check:

- **`NEGATIVE_RESULTS.md` has no entry closing conviction sizing.** §26/§27/§28 close long-only
  top-decile books on *particular signals*; they say nothing about how capital is split across a
  selected list. S38g's finding (the NN sizer lost to trailing vol, and both lost to flat 1×) is the
  nearest thing and it is a verdict on a **learned** sizer, not on a declared-prior Kelly rule.
- **THE BOTTLENECK's rule is respected literally.** A new mechanism arrives as its own book, never
  as a weight inside `arena_composite`. This book's *selection* is byte-identical to
  ENGINE_BASELINE_v1's, so it adds nothing to the one-selector problem and cannot manufacture alpha:
  it is a construction test by construction.
- **This is not a second selector** and must never be counted as one on the scoreboard's
  "independent selectors with evidence" line, which stays at **one**.

## 1. Hypothesis

> At a FIXED alpha source — the same composite, the same top-k selection, the same universe, the
> same costs and the same information gates — sizing positions by fractional-Kelly conviction
> (`ce_kelly` with a DECLARED `ic_prior`) produces higher net terminal wealth than equal weighting
> over the same decision dates.

**Primary metric:** net excess of `PROFIT_ALLOCATOR_v2` over `ENGINE_BASELINE_v1`, per **date
block** (CANON §58: one observation per block, never per name-day), with a Newey-West t.
**Direction:** one-sided positive is the hypothesis; the test is two-sided and the sign is reported.

**What separates this from noise:** the two books hold the **same names on the same dates**. Every
difference is a weight. There is no universe difference, no turnover-source difference and no cost
difference to hide behind — which is why this trial needs no random twin: *the twin is the identical
book with one rule changed*, which is the strongest control the arena's factorial can produce.

## 2. The prior, stated before the read

**DeMiguel, Garlappi & Uppal (2009, *Review of Financial Studies* 22(5)):** across seven empirical
datasets and fourteen optimisation models, **naive 1/N was not reliably beaten out of sample**,
because estimation error in the mean-return vector swamps the theoretical gain of optimising. That
is the honest reason equal weight is a defensible default and not merely a lazy one, and it is the
prior this trial runs against.

**The one version of the question DGU does not already answer.** DGU's models *estimate* expected
returns. `size_ce_kelly` does not: it implements Grinold's `mu = IC * z * sigma` with **`ic_prior`
declared in advance and never fit** to this book, the arena, or any backtest. So the estimation
error DGU identifies as the killer is, for the mean, **assumed away by declaration** rather than
estimated — and what remains under test is whether the cross-sectional *ordering* the composite
already produces carries enough information to be worth weighting by.

**Honest prior: low.** The composite is 12-1 momentum for 99.5% of names (`CLAUDE.md`, THE
BOTTLENECK). If that ordering were informative enough to size on, the selection books would not all
sit at a demonstrated edge of 0%. The most likely outcome is a difference indistinguishable from
zero, and that result is worth having: it would close the construction question the same way §26
closed a selection question, with a receipt.

## 3. The construction, frozen

| | |
|---|---|
| selection | `composite_top_k` over `arena_composite` — **identical to the twin** |
| sizing | `ce_kelly` (`backend/services/arena/policies.py::size_ce_kelly`) |
| `ic_prior` | **0.05** — DECLARED. Upper range of published momentum ICs. Never fit. |
| `kelly_fraction` | **0.5** — half-Kelly at full trust. Never fit. |
| `abstain_kelly_factor` | **0.5** — quarter-Kelly effective while the trust router cannot vouch |
| `max_gross` | **1.0** — long-only, no leverage; cash is the residual |
| `select_top_k` | 12 (file default, same as the twin) |
| `max_single_name` | 0.15 (file default, same as the twin) |
| costs | 5 bps one-way + 1 bp slippage (file default, same as the twin) |
| router | the **CORRECTED** setting (`cluster_adjust=1`) from birth, in the book's fingerprint |

Both allocator numbers are copied verbatim from v1 and are **declared priors, never fit to the
book's own history**. Fitting either would make the book's result a statement about the fit. The
receipt prints both on every decision.

## 4. Worst case in dollars, for the largest admissible book (protocol §4)

Printed before anything runs, because the 2026-08-28 lesson is that a sizing change is not
reviewable without it.

```
n names x cap x stop  =  12 x 15%  x 3%   =  0.45% of equity per name at the cap
                                              5.40% if EVERY name is at the cap and every stop hits
gross                 =  Σ|notional| / equity  ≤  max_gross = 1.00x
worst case on notional_usd = $100,000        =  $5,400 at a 3% stop, all twelve at the cap
```

Three things this arithmetic says, and one it does not:

1. **`ce_kelly` cannot exceed the twin's gross.** `size_ce_kelly` scales gross **down** to
   `max_gross`, never up (`scale = max_gross / gross` when `gross > max_gross`), and capped
   conviction becomes **cash**, not a forced bet. A fully-invested equal-weight k=12 book at the
   same stop shows the same $5,400.
2. **Where Kelly moves the worst case is CONCENTRATION, not gross.** Equal weight always spreads to
   1/12 ≈ 8.3% regardless of conviction; Kelly can put several names near the 15% cap at once when
   conviction is broadly high. The *pathological all-capped* case above is the number that matters
   and it is bounded by `max_gross`.
3. **No stop is declared in the arena's YAML.** The 3% above is the figure used for comparability
   with the decision contract's own worst case; with no stop the true bound on a single name is its
   whole 15%, i.e. **$15,000 of $100,000** on a total loss. That is stated rather than hidden.

What it does not say: nothing here is real money. The arena is simulation in its own namespace and
promotion to a real lane is a separate, attended, pre-registered step.

## 5. Decision rule (what closes this trial, declared before any number)

Read on the primary metric, on date blocks, at the earliest decision date in §6:

- **FAILED_VARIANT** — the block mean is at or below zero. A point estimate on the wrong side of
  zero is not rescued by under-power (Book B's clause, same words).
- **CONDITIONAL** — positive but |t| < 2.0, or positive with n_effective below the MDE in §6.
- **PRODUCT_PROMISING** — positive, |t| ≥ 2.0 on date blocks, **and** the turnover and realised
  concentration are inside the declared caps on every decision (a book that paid for its edge by
  breaching its own cap has not won the test it was registered for).
- **CANNOT DETERMINE** — fewer than 24 date blocks, or any decision date on which either book was in
  `degraded_information_state`. A check that did not run is not a check that passed.

**The falsifier:** if the difference is explained by the **cash position** rather than the weights —
i.e. if a leg that forces `ce_kelly`'s gross to 1.0 (spending the residual cash into the same names
pro-rata) reproduces the whole difference — then what was measured is market timing through the back
door, not conviction sizing, and the trial closes as `FAILED_VARIANT` whatever the primary said.

## 6. Power, and the earliest decision date

Forward evidence cannot be parallelised (invariants §9). At the arena's monthly selection cadence
with daily marking, and with the two books holding the same names, the difference series is a
low-variance paired series — but nothing about its variance is known before it exists, so **the MDE
is computed from the book's OWN realised difference series and printed on the first receipt**, not
asserted here.

**Earliest decision date: the 24th monthly block after seeding.** Before that, the standing verdict
is `CANNOT DETERMINE` by name. No interim read may promote; an interim read may only *kill* (the
FAILED_VARIANT clause is readable at any point, because a negative point estimate needs no power to
be a negative point estimate).

## 7. What is NOT authorised by this draft

- **Seeding.** `PROFIT_ALLOCATOR_v2` is deliberately **absent from
  `backend/services/arena/spec.AUTHORISED_ACTIVE`**, so `active_specs()` will not return it and
  `engine.seed_all()` cannot write an inception for it. `seeding.profit_allocator_v2.authorised` in
  the YAML is the empty string. Three attended steps, in order: add the id to `AUTHORISED_ACTIVE`,
  sign this draft, then `python -m scripts.arena_run --seed`.
- **Any capital.** The arena never writes `paper_nav`, never touches a lane YAML, never enters the
  order path.
- **Any claim.** This is `PRODUCT_EXPERIMENT`. A `RESEARCH_CLAIM` about conviction sizing needs the
  full preregistration ladder and is a different document.
- **Editing this book in place.** A changed rule is a new book id in a new file version. The
  per-book fingerprint (`book-v1`) is what enforces it.

## 8. Receipts this trial will produce

| when | what | where |
|---|---|---|
| at seeding | inception with `book_fingerprint`, `policy_fingerprint`, the declared allocator block | `<OPTIMUS_LEDGER_DIR>/arena/` |
| every decision | the realised weights beside the twin's, `ic_prior` and `kelly_fraction` printed, the router verdict in force, the cash residual | the arena's own ledger |
| every block | the paired difference and its running NW t, with `n_effective` | the leaderboard row |
| at the decision date | §5's ladder applied, the falsifier in §5 run, the MDE from the realised series | a night-factory receipt |

---

*Nothing in this file has been measured. It is a commitment made before the first number, which is
the only kind of commitment CANON §6 counts.*
