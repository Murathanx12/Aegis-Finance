# DECISIONS — 2026-09-05 — the open questions in plain language, with Fable's recommendation

For Murat. Each item: what it is, what is being asked, what I recommend and why.
Nothing here is applied until you say so; Opus reads this file at its next
session start and applies what you approved.

---

## A. Fable's verdict on Opus's B1 session (short)

**Good session. Gate B1 = PASS. I agree with its decisions, with two changes below.**

What it got right:
- It re-derived every number I gave it instead of trusting me, and corrected
  five: overlapping-window inflation +949% (I said +932%), same-session round
  trips **60%** (I said 84% — my number came from a 29-row hand table that
  mixed two exit paths; 60% still refutes a 21-session thesis), "3 of 64 nulls"
  is 2, the delisting-code range, and the dsf universe is 99.8% complete so no
  re-pull was needed. Those corrections are right and they are the review
  interface working.
- It withdrew the "corrected toxic band is a long" reading. Correct: 84% of
  that cell trades under $5, a $5 floor flips the sign, 2022-24 is t 0.03. The
  band is noise, not a long and not a short.
- Every re-issued receipt got worse, and the market leg did not move. That is
  what a defect inside an admission threshold looks like when fixed honestly.
- It stopped the fleet's same-day churn at the variable layer (manage-only on
  all six, entry style deleted on hack4/6) without a deploy. Right call.
- The PANW finding is real and important: five shorts on the two SAFE books
  were 1:8 risk/reward before any signal question, the stop sat 0.5σ inside
  the noise, and `Mandate.tier` is a label nothing reads.

Two things I change:
1. **The daily 10:45 curfew must be keyed to the deadline DATE before entries
   are re-armed.** `alpha/exits.py:114` returns True every day at 10:45 ET once
   the deadline date has passed. With `AAT_LOOP_EXPIRY=2026-09-04` and entries
   on, the books would be liquidated every single day. Opus kept it "sharp
   edge included" for agility; agility is fine, but the predicate must be
   `date == deadline`, or the expiry must be moved out, before Monday.
2. **The revision "ranking skill" (claim 3) is not a censored floor to carry
   forward; it is the first candidate for B4's proper inference.** Keep it
   labelled CANNOT DETERMINE until DSR/SPA exist.

---

## B. The decisions, one by one

### 1. Band prior → "guide, not rule" (your own words)
**What it is.** The analyst-target/price ratio bands (below 1.5, 1.5-3, 3-5,
above 5) were used as an *admission rule*: names above 5 excluded, 3-5
favoured. The constants came from the corrupted tape.
**Asked.** (a) On the research side, retire the four return constants and keep
only hygiene (price ≥ $2, ≥ 2 analysts, unreadable-across-split)? (b) On the
live fleet, hygiene-only now (A) or re-derive thresholds from the live Finnhub
object first (B)? (c) If A, re-seal on the next pass or hold?
**Recommend.** (a) **Yes.** (b) **A — hygiene only, and keep the ratio as a
displayed indicator and a model feature, never a gate.** That is exactly
"guides and indicators, not rules". Re-deriving thresholds from the live
object is a research task (it goes into the night lab), not a precondition
for trading. (c) The books are flat anyway; the first re-seal after B2 ships
is the first seal under hygiene-only.

### 2. "Contract-aware exits" — what I meant
Today every position is sold at −3% or +2.5% with no minimum holding time,
and the horizon used for exits was "sessions until the contest ends". A
**strategy contract** is just the small set of numbers a book must state
before it trades: *how long is this thesis supposed to take* (e.g. 21
sessions), *the earliest normal exit* (e.g. 10 sessions), *what would prove
it wrong* (the falsifiers), and *the risk budget in dollars*. "Contract-aware"
means the exit code reads those numbers: before the minimum hold it may only
sell for a typed reason (thesis broken, data error, hard risk limit,
execution correction, deadline). Not "sell because the price wiggled 3%".
**This is the fix that gives the paper accounts holdings again.** It is B2
§1-3 and it is the first thing Opus builds tonight.

### 3. Why the paper accounts are empty, and the plan to fill them
The expiry guard liquidated everything at 10:45 ET on judging day, and Opus
then deliberately disarmed entries so the −3%/+2.5% churn could not restart.
Empty is intentional for ~2 sessions, not a bug. Order of operations:
1. Tonight: B2 §1-3 (contract fields, contract-aware exits, re-entry guard
   that sees every exit), curfew keyed to date, `AAT_LOOP_EXPIRY` moved far
   out, tier binding on side (no shorts on SAFE books), the 1:8 refusal
   (`expected_edge_usd < k × stop_loss_usd` ⇒ refuse).
2. You push and deploy Monday before the open (`fleet --deploy <role> --up`).
3. Re-arm entries (remove `--manage-only`) on the tracker books only; hack1
   stays manage-only by design.
4. The first seal under hygiene-only admits names; holdings appear Monday
   10:01 ET and must survive at least the minimum hold.

### 4. "Mirror" and "conviction" — NOT your six hack accounts
These are two of the ten **website paper lanes** (seeded 2026-06-08 from
your then-real holdings = *mirror*, and your picks = *conviction*). Their
NAV is computed by our own code on Railway; the Alpaca "mirror" was only an
external copy, and those two Alpaca keys were revoked at Alpaca. **You do not
need more Alpaca accounts.** Recommend: leave those lanes as internal
simulation only (no new keys); the six hack accounts are the real paper fleet.
**About the −16%:** on 2026-08-19 a reconciliation found the mirror's ~−17%
is the *real* performance of the June book, and separately found a NAV-lag
bug (rows stamped one day late), which was fixed. So the number is most
likely true, not a setup error. If you still suspect missing items, the
one-command check is `python -m scripts.lane_positions_reconcile` — Opus can
run it in the night lab and print exactly what the lane holds vs what you
think it should hold.

### 5. What the "corpus" is, and whether it goes to Railway
The corpus is the news/filings store the terminal collects: 230,661 rows
(EDGAR filings, Benzinga/Finnhub headlines, earnings calendar, macro
releases, clinical-trial dates), each stamped with *when it became true* and
*when we could have known it*. It feeds features like `days_to_catalyst`.
It lives only on your laptop, so the Railway authority seals books without
it — that is why hack4 sealed empty. **Recommend: yes, move collection to
Railway** as a scheduled job on the seal-authority service writing to its
volume, so the fleet never depends on the laptop again. Cost: one cron
service, a few dollars a month. Opus designs it tonight; you approve the
Railway change.

### 6. Push both repos — **yes, do it now** (judging is over).
Finance: my commit `4ae55a9` + Opus's B1 commit. Terminal: `fd0c75b` (+7).

### 7. Duplicate WRDS parquet (14.25 GiB) — **delete after the alias fix**,
keep the quarantine folder. Nothing reads the duplicates; the manifest test
proves what remains.

### 8. `aat-loop-staging` failed service — **delete it.**

### 9. Entry-timing tournament — restart only after B2 §1-3 are live.

### 10. Event-driven timing proposal — adopted in principle, sequenced after B2.

---

## C. Your questions from tonight, answered with what we know

**"Biggest gainer / biggest loser usually reverses next day — LULU should
bounce."** Measured on 2013-2024: a daily reversal lane loses after costs;
most of its gross was bid-ask bounce on small names. On *large* names after
an *earnings* gap the evidence is continuation, not reversal, and the
"DOWN big" cell was +0.21% (t 0.24) — nothing. So "LULU bounces" is a
hypothesis, not a rule. It is logged tonight as a typed human thesis with a
falsifier, and the night lab re-measures reversal by size bucket, by
event/no-event, using next-open-to-close returns so bid-ask bounce cannot
flatter it.

**GPRO / ADSK / the target-raise list / the "most potential" list.** Saved
in `MURAT_2026-09-05_INPUTS.md` with today's date as observed-at; the night
lab treats them as a human generator and grades them like any other.

**Polymarket.** We already pull Polymarket and Kalshi daily
(`alpha/sources/belief.py`, TRIAL-PREDMARKET-1), stored as a belief series,
explicitly "never a signal" until measured. History is short; the lab
inventories it and designs the test.

**Psychology / neuroscience of investors.** Concrete first step: the
52-week-high anchor (George-Hwang), distance-from-purchase-price
(disposition effect) and attention spikes are measurable behavioural
features; the lab tests the first on the clean panel tonight. The LLM's own
disposition effect is testable in the diary arm of era replay (B7).

**Options / calls open interest → the stock and its peers.** OptionMetrics
1996-2024 is on disk. The lab tests implied-vol change and skew as
cross-sectional predictors of next-month returns (known literature),
joined to the clean panel. Live open-interest needs a feed we do not have
yet; that is a data decision after the historical test.
