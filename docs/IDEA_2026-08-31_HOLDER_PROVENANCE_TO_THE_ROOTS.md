# IDEA 2026-08-31 — HOLDER PROVENANCE, TO THE ROOTS (Murat, saved for next sessions)

**Status: IDEA CAPTURE — not a trial, nothing pre-registered yet.** Next
session that picks this up starts at §4 (data inventory), then writes a
pre-registration per the standing skill before any evaluation.

## 1. Murat's words (2026-08-31, verbatim intent)

> "which firm, hedge fund bought it, what was their percentage, when bought,
> how long they normally hold and expect growth from a company, their public
> papers bc they also have to explain their reasonings. like for example I look
> at a company and if BlackRock and Vanguard hold at the same time and more
> than 15% I assume it's safe. this is so simple stupid I want you to go to
> the roots with this idea. … let's identify these big shareholders and
> influencers. how long they normally hold into a company, what's their
> expectation, do they also give credit / lend money to that company. like
> anything they do rn and what they did in the past is a good comparison. I
> bet there will be outliers and these are good instances to learn too."

Per the invariants: **intuition GENERATES, data ADJUDICATES.** Each clause
above is a typed hypothesis with an observable that would separate it from
factor beta.

## 2. What we already measured — and the scope caution

The 13F work (S28/S30b, receipts in `tracker_backtest/`) **inverted the naive
prior at the RETURN level**: institutions *selling*, not buying, predicted
stronger subsequent returns, surviving controls for popularity, momentum,
liquidity bands, and quoted-spread costs; strongest in the $10m–$50m/day band.

**Scope-aware verdict discipline applies hard here.** Murat's
BlackRock+Vanguard≥15% heuristic is a **SAFETY** claim (survival, drawdown,
"I assume it's safe"), and the 13F test answered a **RETURN** question. A
global negative on returns does not answer the safety question that was never
asked. The heuristic may be right about ruin/drawdown and wrong about alpha —
test BOTH objectives, name the objective on every ranked comparison. Also
note: BlackRock/Vanguard positions are overwhelmingly INDEX holdings — a 15%
passive stake is a statement about index membership, not about anyone's
opinion. Separating passive (13G, index funds) from active conviction (13D,
concentrated managers) is the first typed distinction.

## 3. The typed hypotheses (each owes one separating observation)

| # | Hypothesis (Murat's clause) | Separating observable | Objective |
|---|---|---|---|
| H1 | Big passive co-ownership (BLK+VG ≥15%) ⇒ "safe" | drawdown/ruin frequency & tail vs matched non-held names, NOT mean return | preservation |
| H2 | WHO bought matters (manager identity carries skill) | per-manager forward return of NEW positions vs that manager's own base rate; stable manager IDs across filings | balanced |
| H3 | Holding-period fingerprint: a long-holder ENTERING is a different event than a fast trader entering | per-manager historical holding-duration distribution; condition entry events on it | balanced |
| H4 | Their public papers explain reasoning ⇒ expectation is extractable | 13D letters, fund shareholder letters, prospectuses — does stated thesis horizon predict realized holding period? | research |
| H5 | Lending relationships (they also give credit) change the meaning of equity stakes | DealScan/loan data joined to 13F: does lender+holder dual exposure predict different outcomes than holder-only? | balanced |
| H6 | Outliers are the learning instances | winner-vs-matched-loser on extreme cells (e.g. concentrated activist ≥10% in thin names) — never a gallery of survivors | research |
| H7 | Complete exits / new funds / crowding shifts (the S30b follow-up list) | top-1/5/10 holder %, holder concentration, # of new funds, complete-exit events | balanced |

## 4. The roots — where each datum actually lives (next session starts HERE)

- **13F (quarterly, ≤45-day lag):** WRDS Thomson Reuters s34 — entitlement to
  VERIFY (the RavenPack lesson: check before planning). Gives holdings by
  manager, so per-manager duration, entries, exits, concentration all derive
  from the panel. Already partially used (S28 liquidity-band result).
- **13D/13G (>5% stakes, days-level lag):** EDGAR full-text, free. 13D =
  active intent WITH A WRITTEN REASON (Item 4 "Purpose of Transaction" — the
  "public papers" Murat wants). 13G = passive. The copy_lab already has an
  ACTIVIST_13D lane (`backend/data/optimus/copy_lab/ACTIVIST_13D/`) — extend,
  don't duplicate.
- **N-PORT (monthly fund holdings, ~60-day lag):** EDGAR, free — faster than
  13F for mutual funds specifically.
- **Form 4 (insiders, 2-day lag):** already in the roadmap; different actor
  class, same provenance frame. CORPORATE_INSIDER_CLUSTER copy_lab lane exists.
- **Fund letters / prospectuses:** EDGAR (485BPOS, N-CSR shareholder letters)
  + manager websites. This is the LLM-extraction surface (thesis, horizon,
  expected growth) — extraction is upstream of verification, never a picker.
- **Lending:** WRDS DealScan (syndicated loans; lender identities) —
  entitlement to VERIFY. Join lender ↔ 13F holder by institution.
- **PIT discipline:** every filing joins on FILING/PUBLICATION timestamp,
  never period-end or transaction date (the STOCK-Act rule generalises).

## 5. Guardrails inherited on day one

- 13F is stale ≤45 days: it is OWNERSHIP STRUCTURE (crowding, who has exited,
  under-ownership), not a live catalyst. No "fund bought → buy" edges.
- The S30b twin-failure pattern ([[feedback-run-the-control-you-would-not-have-chosen]]):
  run the control cell you wouldn't have chosen — for H1 that includes names
  BLK+VG hold that CRASHED (the AAPL+85% lesson in reverse).
- Every cell reports n_effective by DATE BLOCKS (§58) and the liquidity band
  it lives in — the $10m–$50m band result says microstructure decides whether
  an ownership signal is buyable at all.
- This grows CompanyState's holder layer (checkpoint queue item 7); it does
  not spawn a parallel store.

## 6. Licence

Exploration under `PRODUCT_EXPERIMENT` (post-hoc allowed, twenty variants
allowed, costs never omitted, PIT never relaxed). Any claim ("manager skill
exists") graduates only through `RESEARCH_CLAIM` gates.
