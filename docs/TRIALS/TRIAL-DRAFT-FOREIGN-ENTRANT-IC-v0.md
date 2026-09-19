# TRIAL-DRAFT-FOREIGN-ENTRANT-IC — foreign-competitor entry as an incumbent event class (v0)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-19 by Fable from
`docs/research_notes/2026-09-19/research_murat_ideas_adjudicated.md` §1, **before any read and
before the event id exists**. Not in `rule_experiments`; `cumulative_trials` not incremented.
Registration is the attended step. This draft licenses a `PRODUCT_EXPERIMENT` READ only once its
prerequisite (§2) is built; a `RESEARCH_CLAIM` stays attended.

**Origin (Murat, 2026-09-19):** *"China has a new RAM manufacturer whose RAMs are now compatible
with AMD and Nvidia systems. These RAMs can enter the market and make Micron's shares fall. Can we
short Micron? Or invest in the Chinese stock? These are the decisions the engine needs to make."*

**Family:** NEW, `FOREIGN_ENTRANT_2026_09`, declared at size **1** (one primary). It does not
extend any night-job family.

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

- **Resurrects nothing refuted.** `NEGATIVE_RESULTS.md` §12 (supplier thesis) is a customer-link
  cross-section at annual cadence; this is an incumbent-side EVENT at daily cadence. §19 (LLM
  trading alpha) binds only if the LLM allocates — here it TYPES an event and a deterministic
  forward-IC estimator reads it (the `TRIAL-CONGRESS-IC` / `TRIAL-ARK-IC` pattern). §26/§27 stand
  as the prior that a long-only top-decile book fails to harvest rank information; this trial
  measures IC first and registers no book.
- **The literal trade is NOT this trial.** MU −5.2% on 2026-09-14 sat inside a SOXX-wide day and
  is not attributable; MU −5% on 2026-07-27 (CXMT IPO day) is the cleaner instance and is one
  observation. A single-name short is not a hypothesis (CLAUDE.md: what observation would separate
  it from factor beta?). The generalisation below is.
- **New instrument:** a vocabulary id that does not exist in v2 (43 ids; the nearest are
  `tariff_or_trade_policy` and `product_launch_or_innovation`, which fire on the entrant's own
  announcement, not on the incumbent-relevant reading of it).

## 1. Hypothesis

> When a credible foreign entrant achieves qualified compatibility or capacity parity in an
> incumbent's product category (typed as `foreign_entrant_capacity`, direction −1 for the named
> incumbent), the incumbent's return over the following 1, 5 and 21 sessions, **net of its
> beta-matched sector control**, is negative with rank-IC ≥ the MDE in §4 across the typed
> events; the entrant leg, where a tradeable listing exists, is a SECONDARY read.

**What separates it from beta:** the incumbent's abnormal return is measured against a
same-sector, beta-matched control on the event sessions; a sector-wide day contributes zero by
construction. The shuffled-incumbent null (the same events assigned to random same-sector names)
and the date-shift placebo (same names, event dates shifted −20 sessions) must both be flat.

**Honest prior:** low-to-moderate. Entrant news is incremental and public for months
(BIOS qualifications, IPO roadshows, capacity reports), so most of the information is priced
before a headline; the mechanism the literature supports is the *qualification* step (a
discrete, dated fact), not the narrative. Expected IC at 21 sessions: 0.01-0.03 if real.

## 2. Prerequisite (a build, not a read)

Vocabulary **v3** = v2 + `foreign_entrant_capacity` (direction prior −1 for the incumbent named
in `entities.incumbent`, +1 for `entities.entrant`; magnitude buckets unchanged; the id must be
ON THE WIRE in the system prompt — `event_extraction.system_with_schema`). Hash pins updated;
kappa protocol re-run on the 500-row control sample. Then the typed corpus is re-read for this
id only over the existing text-return panel (local model; $0), and the event count is printed
BEFORE §4 is filled in.

## 3. Construction

- Universe: the tradable band (median $ volume ≥ $10M, price ≥ $5, ETFs excluded), US listings;
  incumbents identified by the typed row's `entities.incumbent`.
- Event date: `first_seen_utc` of the earliest typed row per (incumbent, entrant, category)
  within a 60-day window (dedup rule declared here, not after looking).
- Outcome: close-to-close log return of the incumbent minus the beta-matched sector control
  (beta over the trailing 250 sessions; control = the SIC-3 peer basket, equal-weight), at
  horizons 1, 5, 21 sessions from the next open after `first_seen_utc`.
- Metric: rank-IC of the typed direction × confidence against the abnormal return, per date
  block (§58: n_effective counts date blocks), with the two nulls in §1.
- Costs: not applicable to an IC read; any book built later pays the TAQ curve.

## 4. Power (deferred, by rule)

Filled in ONLY after §2 prints the event count. If the count over the panel's history is below
the number that gives 80% decision power at IC 0.02 with Holm over one test, the trial is
registered `NOT_ANSWERABLE_AT_N` and accrues FORWARD (the `CONGRESS-IC` pattern), with the
earliest read date computed from the observed event rate.

## 5. Decision rule

PASS: IC at 21 sessions ≥ MDE with both nulls flat (|t| < 1) → a screen-only follow-up
(short-leg information is used as an EXCLUSION on long-only books per the failure thesis's
first re-test; no long-short book is registered here). FAIL: `FAILED_VARIANT` for this
construction; the id stays in the vocabulary (it costs nothing and feeds the panel).

## 6. What Murat signs

The family name, the size (1), the id's direction prior, and the read date once §4 is filled.
