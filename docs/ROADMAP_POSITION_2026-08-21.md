# ROADMAP POSITION — 2026-08-21 (Fable, on Murat's direct handoff)

Murat's instruction this morning, compressed: *the night didn't run and I'm
tired of waiting; nights must run even if the PC is closed (without blowing up
the Railway bill); there is still no live continuously-learning LLM+brain
system; some rules are 6 months old and may be outdated; log every day what
happened vs what we thought; build the NN when the substrate is ready; you're
the expert — update the roadmap and move.*

This document is the answer. Everything in §1–§3 was verified against disk or
the live machine today, not carried forward from a handoff.

---

## 0. The one-paragraph answer

**The continuously-learning system Murat is asking for is ~90% built and 0%
deployed.** The arena (self-grading LLM forecasts, reliability ledger, regret
reader, discovery outside the watchlist, event intake) exists, is tested, and
runs daily — *once pushed and seeded*. The reason "there is not a live working
LLM+brain system" is that ~25 commits sat local on `main`. The critical path
today is: **push → verify prod → seed → let the clocks run**, plus the one new
piece that was genuinely missing: a daily digest corpus (built today,
`pi_daily_digest`, 18:15 ET) that records every day's decisions, grades, and
outcomes as training substrate. The night that "didn't run" on 08-20 was a
**correct refusal** (asked to launch at 17:18 against a 17:02 latest-safe
boundary) — the launcher is armed and Ready for its first self-launch **today
17:00**.

## 1. State, verified today

| Surface | State |
|---|---|
| IIF-1 nights | 3 clean nights; schtask `AegisIIF1NightLauncher` **Ready, next run 2026-08-21 17:00**, armed at User scope. 08-20 was a refusal (`PAST_LATEST_SAFE_LAUNCH`), not a failure. First 396 forward resolutions land today. |
| WRDS substrate | 738+ parquet on disk, 26+ GB. Catch-up pid running with `--max-seconds 14400`, self-terminates ~14:46 (clear of 17:00). ~230 retryable remain; **one-shot task `AegisWRDSPullNight` registered: tonight 22:00, wake-from-sleep, 12 h budget ending ~10:00.** Verifier baseline: 317 COMPLETE / 16 SHORT_MINOR / 0 BROKEN; 23 truncated files quarantined. |
| Arena | Built + tested end-to-end on live data; **unseeded, undeployed** until the push + `AEGIS_SEED_ARENA=1`. Coverage measured `{"1":206,"6":1}` — quality factor fill shipped, four families still narrow. |
| Daily digest | **Built today.** `backend/services/daily_digest.py`, job `pi_daily_digest` 18:15 ET all 7 days, corpus at `optimus/digests/digest_corpus.jsonl`, endpoint `/api/optimus/digest`. Documentation only, never a signal. |
| Evidence | Demonstrated edge still **0%** and honestly so: two Holm-surviving results are a RISK result and an ANTI-signal (streak/factor winner-chasing). Lanes at 74 days of a 24-month floor. |

## 2. Rules audit — what Murat asked to re-examine

Verdicts on the "rules written 6 months ago":

1. **Paper lanes are NOT outdated.** They are the only thing that can ever
   license a skill claim (24-month floor, inception 2026-06-08). What changed
   is their *job*: lanes are the slow **evidence clock**; the arena books are
   the fast **learning loop** (PRODUCT_EXPERIMENT, never `paper_nav`). Both
   run; they answer different questions. Killing lanes to "move faster" would
   reset the only clock that matters.
2. **"The LLM narrates; the engine computes" — AMENDED in practice, honestly.**
   The arena now treats LLM beliefs as a *measured forecasting layer*: prior
   from disk, graded every pass, reliability cells that refuse thin data. The
   line that stands: **no LLM allocation** — the LLM cannot size or trade.
3. **"No database" — STANDS for the API, does not apply to research.** The
   prod API stays stateless + cache. The WRDS parquet substrate is a research
   corpus, not a served database. No conflict.
4. **PIT hierarchy — STANDS, sharpened.** CRSP > SEC-EDGAR > ... > yfinance
   (forbidden for PIT). The one standing exception: *live forward* collectors
   may use hang-safe yfinance because forward accrual is PIT by construction.
5. **13F / "watch how hedge funds move" — half-open.** Backtesting manager
   skill is BLOCKED (13F `fdate` is a vintage stamp, not a knowledge date —
   MANAGER-\* corpses). But the *forward* trackers Murat wants are already
   accruing daily: ARK holdings deltas, congress trades, insider clusters,
   13F snapshots on their legal lag. The digest now records them every day —
   this is exactly the "how they buy and sell" log he asked for, accruing at
   the only speed that is honest (forward).
6. **"Research/heavy work on Opus" — UPDATE.** Fable now exists and this
   session runs on it; the budget rule's intent (don't burn top-model tokens
   on mechanical work) stands, the model name doesn't.
7. **Methodology rules (preregistration, MDE, matched losers, §58–§64) — ALL
   STAND.** Nothing in six months of negatives came from the rules being too
   strict; the two real positives *survived* them. The rules are why we can
   trust our own no's.

## 3. Nights that run with the PC closed — the design

Three tiers, by cost and by what prereg discipline allows:

**Tier 1 — local, hardened (live today, $0).** Launcher armed, task Ready for
17:00; the WRDS night task shows the pattern (one-shot, `WakeToRun`, budget
ends clear of the next launch). Residual risk: laptop unplugged/asleep at
16:55–17:05. This tier can never fully satisfy "PC closed".

**Tier 2 — everything daily moves to Railway (this push, ~$0 marginal).**
The arena pass, ledger resolver, all collectors, and now the digest are
scheduler jobs inside the existing Railway service — they already run with
the laptop closed the moment the push lands. No new service, no new cost
beyond the existing plan.

**Tier 3 — IIF-1 nights in the cloud (next week, disclosed amendment).**
Moving a registered trial's runner mid-clock is an amendment, not a tweak.
Plan: build a shadow runner (Railway one-off job or GitHub Actions cron —
compute is trivial; the $0.92/night is API spend either way), run it in
parallel with local nights for 3 nights, compare receipts field-by-field
(`arm_implementation_fingerprint`, `prereg_hash`, record counts), then switch
with the comparison attached as the amendment's evidence. **Do not switch on
the same night as the first self-launch.** Until then the laptop stays the
host and the margin stays ~2 minutes.

## 4. Continuous learning — what runs every day after the push + seed

17:45 arena pass (decide/grade/discover) → 16:30 resolver → 18:15 **digest**
(one corpus row: what we thought, what happened, what matured, what was
right). Nightly IIF adds graded forecasts. This is the "every day so much data
is passing, we should document it all" machine — it now exists end-to-end.

**Deliberately NOT built** (and why): continuous *LLM* self-play (token cost
with no registered question — the arena's daily cadence is the registered
version of this); the complex allocator (must first lose to the simple rule
on a real reliability ledger — Q2 in the 08-21 handoff); NN training before
the substrate verifier gates it (a 4%-of-table parquet joins cleanly and
poisons everything — the pull + `wrds_verify_substrate` are the critical
path, and it closes this week).

## 5. Murat's direct questions, answered

- **"Why is WRDS 26 GB, isn't it just binary?"** It *is* binary (compressed
  columnar parquet). The size is the panel: `crsp.daily_nav_ret` alone is
  186M rows; Compustat footnote tables run 500–886 columns × decades ×
  every filer. Text would be ~5–10× larger.
- **"Will the documents/footnotes be useful, how to digest them?"** The wide
  footnote/descriptor tables are structured accounting detail — useful for
  supervised features (restatements, segment changes), not for reading. The
  honest open question from the handoff stands: whether they are worth their
  egress — decide explicitly per family, don't let a timeout decide.
- **"Should Claudes talk in binary / shorter prompts?"** No — models read
  subword tokens; binary encodings cost *more* tokens and destroy auditability.
  The right compression is what the project already converged on: structured
  JSON receipts + dated handoffs + the memory index. The digest corpus now
  gives future sessions one canonical place to read a day from.
- **"$26/month paper accounts"** — that is the Railway plan, and every Tier-2
  item rides inside it. Nothing in this roadmap adds a paid service.

## 6. The queue (supersedes the 08-21 handoff's §5 where they differ)

**Murat (attended):**
1. `AEGIS_SEED_ARENA=1` for one boot — after today's push, LAST.
2. Laptop plugged in 16:55–17:05 today (first self-launch; margin ~2 min).
3. The MAX_ROWS cap decision (raise to ~20M or cell-budget; partition or
   declare out-of-scope the 47M/76M/186M-row four). Numbers in
   `docs/HANDOFF_2026-08-21_ARENA_LEARNS.md` §2.
4. NAV stamp fix P-day-2026-08-19a go; G2 prereg signatures before 09-08;
   positions read; LOSS amendment; Track E prereg.

**Next sessions (unattended):**
1. Verify substrate after tonight's pull; re-run verifier; then Q1 (WRDS →
   universe-wide diverse features, PIT-clean, new `COMPOSITE_VERSION`).
2. Q3 known-answer battery (flips G1 → PASSED).
3. Tier-3 shadow night runner + 3-night receipt comparison.
4. Q4 supervised learning on the verified substrate (risk heads first — §59;
   LGBM beat ridge at scale, 0.747 vs 0.680, on the 1990–2012 era).
5. Free-API inventory (public-apis repo) + MCP wiring for live sources —
   *after* the arena is live; new feeds enter as registered trials, never
   straight into the composite.
