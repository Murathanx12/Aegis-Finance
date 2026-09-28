# Signal alerts to Telegram: what exists, what the evidence supports, and a buildable spec (2026-09-28)

**Licence: this note is research/design only. Nothing here is a claim, an order, or a code change.**
Scope: turn "OpenClaw discovers -> AEGIS evaluates -> Telegram alert" from a reviewer's proposal into
something a builder can implement by reusing what already runs in this repo. Read after
`docs/AEGIS_STRATEGIC_INVARIANTS.md`, `docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md` and
`docs/HANDOFF_2026-09-28_THE_READER_NIGHT.md`.

---

## PART 1 — INVENTORY: what already exists

### 1.0 The single biggest finding: the delivery mechanism already exists and is running, unused

`backend/services/telegram_bridge.py` (own-identity Telegram BOT, not a linked device — built
2026-09-22 specifically because the WhatsApp "linked device" incident let OpenClaw answer a stranger's
message) + `scripts/telegram_agent.py` (`--serve`, `--brief`, `--daily`, `--claim`). It enforces
`OWNER_CHAT_ID` or refuses to send, never derives the recipient from an inbound message, has a fixed
command dict (no shell escape hatch), and already ships an **approval-tap** pattern (`/pending`,
`/approve <id>`, `/deny <id>`) and an **alarm class** (drawdown breach, CI red, ownership conflict, a
night that died with no receipt).

Checked live, 2026-09-28 ~13:40 HKT:
- Scheduled task `AegisTelegramAgent` is **Running** (`schtasks /Query`).
- `backend/data/optimus/telegram/heartbeat.json` is moving in real time (loop count climbing,
  `pid 138516`) — the long-poll loop is alive.
- `backend/data/optimus/telegram/supervisor.jsonl` shows it restarts itself on a stale heartbeat
  (one restart at 2026-09-28 03:05 UTC, "heartbeat stale (5356s > 600s)") and on network timeouts
  (`agent.log.err` shows repeated `WinError 10060` from Telegram's `getUpdates` long-poll, handled).
- **`backend/data/optimus/telegram/outbox.jsonl` has sent nothing since 2026-09-23.** Every row before
  that is a reply to a manual `/brief` or `/sim` command. The `daily_jobs()` function that calls
  `TG.send(line, tag="daily")` exists and is wired to `--daily`, but nothing in `scripts/daily_pass.py`,
  the scheduled-task list, or `always_on_lab` invokes `--daily` or `--brief` on a cadence.

So: the owner's literal request ("send me a message whenever we find something good") already has a
safe, tested, allowlisted transport sitting idle. This is a **caller problem, not a build-a-bot problem**
— exactly the CLAUDE.md rule "give every new module a caller, or classify it" pointed at a case it
hadn't yet found. Building a new Telegram integration would duplicate a bridge that already has the
hard safety property (bot identity, allowlist, no-order guarantee) solved.

### 1.1 Typed-event extraction (the "43-id enum")

`backend/services/event_vocabulary.py` is the frozen typed-event table: **39 substantive event ids +
`no_event`**, each with a definition, 8-K item mapping, a direction *prior* (not a label), a magnitude
bucket, an example and a counter-example, all covered by a `VOCABULARY_HASH`. The module's own docstring
flags that the spec's prose miscounts itself (heading says 39, closing sentence says 38+1) — and
elsewhere in the repo (`backend/services/lab_themes.py`) the same vocabulary is called "the 43-id event
vocabulary." **I could not resolve this discrepancy by import** (the venv/module path did not load
cleanly from this shell), so the true current count should be read from `event_vocabulary.N_SUBSTANTIVE`
at runtime, not assumed from any of the three numbers (38/39/43) written in comments — a fourth grep
would just find a fourth quoted number. Whoever builds this next should print `N_SUBSTANTIVE` in the
first receipt.

`backend/services/event_extraction.py` is the extraction contract itself: JSON-schema-shaped, one
document -> one typed row or a named refusal, `PROMPT_HASH` over the wire prompt, and a hand-written
validator because `jsonschema` isn't installed (a guard on a dormant validator would be the
`ANTHROPIC_API_KEY` lesson again — the module already says so). `backend/services/event_intel.py` is the
descriptive layer on top: LLM classifies into **enums only** (never prose), direction is always relative
to the named entity, context cards default to `{"status": "none_measured"}`, and "no events found" is
distinguished from "extraction unavailable." `backend/services/event_store.py` is the append-only history
with **three separate clocks** (`source_at`, `ingested_at`, `accepted_at`) built specifically so novelty
("same headline re-syndicated by four outlets") and PIT availability can be computed at all — before it
existed, events were fetched fresh and discarded daily.

**Status: built, tested, and the closest thing to computed "novelty" in the repo.** Not verified live
against fresh data in this session.

### 1.2 Collectors

| Collector | What | Scheduled? | Last output seen | Known defects |
|---|---|---|---|---|
| `scripts/news_pull.py` | GDELT, Google News RSS (multi-locale incl. `google_news_rss_en_hk`), Nikkei Asia RSS(1.0/RDF), Reddit `.rss`(Atom), SEC EDGAR current-filings Atom, Alpaca/Benzinga (refused: no credential), yfinance ticker news — one JSONL/source/day, resumable cursor, dedup by guid, `first_seen_utc` written at write time, two-zero-rows-in-a-row = RED | Yes, per its own docstring, via `daily_pass`/`always_on_lab` cadence; `system_health.p_news_collectors` probes it every 15 min | `backend/data/optimus/news_corpus/yfinance_ticker_news/` mtime 2026-09-27 08:04; several WSJ subfolders mtime 2026-09-26 22:30 — **a day-plus stale relative to "today," worth a fresh probe read before trusting it's current** | Alpaca leg dead (no APCA credential in this env); parser-vs-feed mismatches were a known failure class the registry now encodes explicitly |
| `scripts/gdelt_pull.py` | Raw GDELT export/mentions/GKG zips, 15-min granularity, robots.txt-checked, resumable | Yes (own cursor + receipt-every-N) | not timestamp-checked this session | Explicitly does **not** touch Alpaca/Finnhub news ("another lane owns that leg") — two collectors, two stores, **not obviously joined** |
| `backend/services/dowjones_feeds.py` | The ten free WSJ/Barron's/MarketWatch **RSS** feeds (headline + one-line summary only) over plain HTTP, no browser, no LLM; refuses on a non-XML bot-check page (`REFUSED_NON_XML`) rather than reading it as zero items; receipt prints feed-item **age** | Yes, via `news_registry` + `news_pull.pull_all` | part of `bridge_2026-09-28.json` / `freeze_gate_2026-09-28.json` | Headline-only by design (ToU §9.1: personal, non-commercial) |
| `backend/services/digest_inbox.py` | Murat's **paste inbox** — the PRIMARY full-text Dow Jones path, because ToU §9.4.1 explicitly bars "browser automation tool" and "AI agent or assistant." Parses `=== url\|date\|source` blocks, forgiving format, feeds the same claim extractor as the reader | Human-triggered only, by design | `backend/data/optimus/digest_inbox/READING_LIST_2026-09-28.md` generated 2026-09-28 11:09 | Depends entirely on Murat pasting; nothing automatic |
| SEC EDGAR 8-K / XBRL | `backend/services/edgar_events.py`; `derive_q4` in `backend/services/inflection.py` recovers 59,296 fundamental rows XBRL never explicitly tags (median gap 182 days per memory S55) | edgar_events likely on the same news_pull cadence (current-filings Atom is in the collector list above) | `news_corpus/sec_edgar_8k_current_atom/` mtime 2026-09-25 18:02, `sec_edgar_8k_ex99_body/` 2026-09-25 18:03 — **3 days stale** | fair-access rate limit applies (below) |
| Analyst revisions | `backend/services/analyst_intelligence.py`, `analyst_ledger.py`, `estimate_revisions.py`, `revision_flow.py`; 393k dated yfinance revisions, `target_revisions.parquet` (7.1 MB, last pulled 2026-09-27 01:14) | `revision_flow_sweep.py` run 2026-09-25 | fresh (within 24-36h as of this session) | **MEASURED, not assumed:** the *level* (target/price) is CLOSED/PERVERSE; the *flow* signal cleared `t 5.24` raw but the 2026-09-28 handoff reclassifies it **`BETA_EXPLAINS`** once the shared −1.10% drift every revised name carries is netted out, and it is **2025-only** (+2.67% vs −0.02% in 2026). Any alert component built on "analysts revising in the same direction" must inherit this control or it will re-discover a already-closed false positive. |
| StockTwits | `docs/research_notes/2026-09-27/research_v3_crowd_reads_stocktwits_http.md` + `stocktwits_http.json`: public JSON endpoint `api.stocktwits.com/api/2/streams/symbol/<T>.json`, **plain HTTP, no browser**, 68/68 names OK on 2026-09-27 | One-off research snapshot, **not a running collector loop** | 2026-09-27 23:35 HKT | Watchers/msgs/bull-bear/authors only; per the owner's constraint this is discovery-lane only and must never generate an order |
| X (Twitter) handles | `d75a3c79`: 15/20 X handles confirmed from company homepages, no browser | Not a running collector | 2026-09-27 | Timelines themselves still unread (X blocks plain HTTP; would need paid API or browser, both out of scope per constraints) |
| Reddit | `.rss` parsed by `news_pull`, but `.rss` beyond first 15 names returns 403 | Attempted, mostly blocked | 2026-09-27 | Same-shape as X: discovery-lane, low reliability |

### 1.3 Evaluation / synthesis layer

- **`backend/services/investigator_agent.py`** + `investigator_night.py` / `_tools.py` / `_triggers.py`
  — INTERNET-INVESTIGATOR-FWD-1, pre-registered (`Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md`),
  five separately-gradeable microtasks (gather -> event -> expectations -> forecast -> critic), replacing
  an earlier 14-persona "mega-schema" design that measured 0.49 effective distinct ideas per call against
  0.85 for one generic agent at a fifth of the cost. **This is the one component in the whole inventory
  with a documented positive forward-OOS result**: per memory (§64, 2026-09-24), held-out grading found the
  investigator **as a PROCESS +8.97%** against nine thematic personas at **−27.98% at their own optimal
  weight (zero)** — i.e., negative discrimination. Any "AEGIS evaluates" step in the requested pipeline
  should route through this process, not a fresh directional LLM call, given the project's own separately
  measured finding that raw LLM directional calls carry **~−8.7% skill** on direction.
- **`backend/services/thesis_card.py`** — engine-side computed features + one OpenClaw web quest (Murat's
  twelve fixed questions, flat JSON) + one DeepSeek synthesis call, producing bull/bear/falsifier/verdict/
  confidence. Explicitly "evidence and a falsifier, not an order." Measured cost per card from the
  2026-09-27 calibration run: ~$0.04–0.09 for the OpenClaw quest + ~$0.0008 for the synthesis call.
- **`backend/services/decision_contract.py`** — the existing "one row: what would be bought, at what size,
  why, what would make it wrong" pattern, with named absences (`"NOT CALIBRATED"`, `"CANNOT DETERMINE: ..."`)
  instead of fabricated defaults. This is the template Part 3's "what the system does NOT know" field
  should reuse rather than reinvent.
- **`backend/services/lane_autopsy.py`**, `backend/services/research_gym/autopsy.py` /
  `autopsy_llm.py` — the after-close autopsy machinery the VISION file calls for.
- **`backend/services/revision_flow.py`** + sweep — see 1.2 above; closed/BETA_EXPLAINS as of 2026-09-28.

### 1.4 Grading / calibration / adaptation

- **`backend/services/forecast_grader.py`** — the daily caller `belief_state`/`ledger_resolver` never
  had; built 2026-09-20 after finding 17,614 of 24,839 ledger rows sat `resolved_at: null` past their due
  date. It builds its own local price panel so grading does not depend on a live vendor call.
- **`backend/services/source_scorecard.py`** — grades what WSJ/Barron's/MarketWatch **said** against what
  **happened**, at **1, 5, 21 and 63 sessions**, vs SPY **and** a matched control, clustered by publication
  date (the §58 "n_effective counts DATE BLOCKS" rule applied directly). As of the newest receipt
  (`source_scorecard_2026-09-28_000228.json`), **0 of 60 cells are `ALPHA_DETECTED`; every Dow Jones cell
  is `TOO_FEW`** — the WSJ leg has 16 claims on only **9 publication dates**, and the receipt itself states
  **~110 dates are needed**. This is a real, already-measured answer to Part 3(f) below, not a guess.
- **`backend/services/three_source_compare.py`** — cross-checks WSJ/Barron's/MarketWatch/analyst-consensus
  agreement. The 2026-09-28 handoff's own review (R5) flags that MarketWatch's consensus rating is "up" for
  80%+ of covered names, so raw agreement-count is mostly base rate — **any alert component using
  "N sources agree" must be defined against a rating's CHANGE, not its level, with the base rate printed
  beside it**, or it silently re-imports the flaw the review just found in the parent session.
- **`backend/services/policy_state.py`** — the **only** thing an unattended night may change about itself:
  a fixed, typed, range-bounded schema (risk limits explicitly excluded), every write journaled with old
  value / new value / reason / evidence / timestamp, refusing on any undeclared key. This is the exact
  mechanism a learned alert threshold should live in — never a code edit.
- **`backend/services/system_health.py`** — probe registry that derives ALIVE/STALE/DEAD/UNKNOWN only from
  evidence a producer itself wrote (never a bare filesystem mtime), already carries a `telegram_agent`
  probe (`p_telegram_agent`, cadence 60s via heartbeat) and says explicitly its output feeds "the morning
  report and the Telegram brief" — i.e., the health surface was already designed with a Telegram brief in
  mind; it's the caller (1.0) that's missing.

### 1.5 What's connected today, and what sits unread

**Connected, live-ish:** `news_pull`/`dowjones_feeds`/`gdelt_pull` (collectors, cadence via `daily_pass`/
`always_on_lab`) -> `event_intel`/`event_extraction`/`event_store` (typed classification + 3-clock history)
-> `thesis_card` (on a selected universe) -> `predictions.jsonl` (frozen forecast rows — schema below) ->
`forecast_grader` (resolves at horizon) -> `source_scorecard` / `revision_flow` / `three_source_compare`
(diagnostics) -> `policy_state` (bounded nightly adaptation) -> `system_health` (probes). `telegram_bridge`
is alive and polling but is a **dead end for outbound alerts** — nothing calls `TG.send()` on a schedule.

**Unread / disconnected:** the investigator's positive-skill process output is not wired into `thesis_card`
or into any alert path; StockTwits/X are one-off research snapshots, not running loops; `attention_z`
(`backend/services/pit_features.py`, `trends_sentiment.py`) is computed and consumed by
`strategy_library_ext`/`predictability_router_r1/r2`, but I did not verify it is read by any *decision*
path in this session — treat as unconfirmed rather than either connected or dead; ANALYST-SKILL-1
(33,043-analyst IBES skill model) was registered 2026-08-31 and, per the 2026-09-25 roadmap notes, had
still never been run as of that date; GDELT's raw store and the Alpaca/Finnhub news leg are explicitly
two separate, unjoined pipelines by the collector's own docstring.

---

## PART 2 — what the evidence says a "good alert" is

Full literature pass (author/year, effect size, horizon, retail-cost verdict) is in the appendix at the
end of this file. Summary, ranked by retail tradability *today*, being strict about sample-period decay
and about the difference between an academic effect size and a cost-surviving one:

1. **Analyst revision-cluster momentum** (Gleason & Lee 2003; Womack 1996; confirmed in recent samples,
   e.g. Chen/Nie/Shi/Zhang 2024/25) is the most durable of the eight surveyed mechanisms — multi-month
   horizon, underreaction persists, concentrated in less-covered names. **But this project's own
   measurement of the closely-related signal (revision *flow*) just reclassified it `BETA_EXPLAINS` and
   2025-only** (F2, §HANDOFF 2026-09-28). Evidence quality: real in the literature, **not yet cleared** in
   this codebase's own data after its own drift control.
2. **News novelty vs. repetition / stale-news filtering** (Tetlock 2011: 413bps equal-weight /
   75bps value-weight difference between stale and fresh news deciles) is the most **directly actionable**
   finding — not as a standalone signal but as a **pre-processing gate**: deduplicate before scoring
   anything, because a fifth rewrite of a fact should never generate a fifth alert.
3. **8-K item-type reactions** (Lerman & Livnat 2010) are real and item-specific (bankruptcy/going-concern
   largest, several items show *no* reaction at all) but "Who Pays Attention to SEC Form 8-K?" (Accounting
   Review 2022) shows the informative items move on the **press-release** event date, before the filing —
   an 8-K-filing-triggered alert is structurally late for liquid names. Useful mainly for illiquid names
   where the filing itself is closer to first disclosure.
4. **Insider cluster buying** (Cohen/Malloy/Pomorski 2012, "opportunistic" clusters 82–180 bps/month) is
   real academically but the retail-tradable residual shrinks a lot once the mandatory **T+2 Form 4 filing
   lag** and look-ahead-free cluster assignment are applied (headline cluster numbers in non-peer-reviewed
   sources roughly halve under an honest construction).
5. **PEAD** is the largest documented historical anomaly (Bernard & Thomas 1989) but is **documented as
   structurally decaying** (Chordia et al. 2014; Zhao; Martineau 2021 finds post-2010 returns barely
   related to SUE rank) — treat as weak/dated evidence today, not a design pillar.
6. **Price discovery speed** is the binding constraint on the whole pipeline: for liquid large caps, most
   of a news-driven move completes within minutes (Jiang/Lo/Valente; von Beschwitz/Keim/Massa) — a Telegram
   alert arrives too late to capture the jump. For illiquid/small-caps, minutes-to-days of genuine lag
   exist, which is also exactly where realistic retail costs (30bps+ spread/slippage) bite hardest.
7. **Attention/crowding** (Da, Engelberg & Gao 2011) is small, mean-reverting, and a *warning* as much as a
   signal: a stock getting noticed by many alert services simultaneously is the crowding effect eating its
   own edge.

**Cross-cutting design implication:** every mechanism surveyed is strongest precisely where this
codebase's costs and data quality are weakest (illiquid, thinly-covered names), and weakest precisely
where the data is best (liquid mega-caps, already priced in minutes). This matches the VISION file's own
framing (§1: "NVDA has every firm's price analysis; a small stock has three or five analysts") — the
alert pipeline's coverage-normalization instinct is directionally right, but it means **every alert on a
liquid name should default to a lower confidence tier than an identical alert on a small name**, not the
reverse of what a naive "biggest mover" screen would emphasize.

---

## PART 3 — design spec

### (a) Every alert is a frozen, timestamped forecast row, written before it is sent

Reuse the existing `predictions.jsonl` schema (verified live from the tail of the ledger, 2026-09-28) —
it already carries `made_at`, `resolves_after`, `horizon_days`, `probability`, `thesis`,
`counter_thesis`, `next_observable`, `model`/`model_version`, `prompt_hash`, `input_snapshot_hash`,
`schema_version`, `evidence_population`, `licence`, `benchmark`, and null `resolved_at`/`outcome`/`brier`
at write time. An alert row is this schema **plus**:

```
alert_id, alert_level, sent_utc, telegram_chat_id, telegram_message_id,
price_at_alert, sigma_move_1d, sigma_move_5d,
source_lane ("truth" | "discovery"), primary_source_url,
dedup_cluster_id, component_scores{ ... },
what_is_new, what_contradicts, what_is_unknown
```

The row is written to the ledger **before** `telegram_bridge.send()` is called, in the same function
call, so a crash between write and send is visible (a row with no `sent_utc`) rather than invisible (a
send with no record) — the same discipline `event_store` already applies to `accepted_at`.

### (b) Required content per alert

- **What is new**: computed from `event_store`'s three-clock history — this scope + event_type pair's
  count of prior *independent* (deduplicated) mentions in the last 30/90 days. A first-mention alert says
  so explicitly ("first coverage in 90 days"); a fourth says so too ("4th mention in 6 days — see cluster
  <id>") and is demoted to INFO by construction (2c below).
- **Primary source link**: the URL of the highest-priority source in the cluster (truth lane beats
  discovery lane; SEC/company-IR beats a wire beats a blog).
- **Price already moved**: `sigma_move_1d`/`sigma_move_5d` = realized return since the event's
  `source_at` (or since market open if `source_at` predates it) divided by the name's trailing
  realized daily vol — the same normalization CLAUDE.md's own insider-lesson insists on ("quote stops in
  sigma, not percent"). An alert whose `sigma_move_1d` already exceeds ~1.5–2σ should say **"likely
  already priced"** in the message itself, per the Part 2 finding that liquid-name reactions complete in
  minutes.
- **What contradicts it**: a same-ticker opposite-direction row from `three_source_compare` or
  `source_scorecard`'s stored claims, or an opposite-signed analyst-revision-flow reading — reported with
  the base rate attached (R5's lesson), never as a bare "2 sources disagree."
- **What the system does not know**: reuse `decision_contract`'s named-absence convention
  (`"NOT CALIBRATED"`, `"CANNOT DETERMINE: ..."`) rather than omitting the field. At minimum: whether the
  extractor's read of this specific document type has ever been hand-labeled (R6's open debt — it hasn't,
  for Dow Jones claims), and whether the mechanism has cleared the grading bar in (f) below.

### (c) Deduplication

Cluster key = `(scope, event_type, direction)` from the typed-event row. A new candidate joins an
existing open cluster (window: 72h, matching `event_store.ingested_at`) if its title's cosine similarity
to the cluster's seed exceeds a threshold (reuse whatever the corpus dedup in `news_pull` already computes
for guid-level dedup; extend to near-duplicate text, which guid-dedup does not catch). **Only the cluster's
first qualifying member sends a live alert.** Subsequent members increment a `corroboration_count` on the
same `alert_id` (via a low-key follow-up, not a new push) and feed the "what is new" novelty count above.
This operationalizes the Part 2 Tetlock-2011 finding directly.

### (d) Daily cap and quiet hours

Owner is in Hong Kong (UTC+8); US cash session is 21:30–04:00 HKT. Quiet-hours window: **04:00–07:30
HKT** (US just closed, before the Asia news day meaningfully updates and before `dowjones_feeds`'
next scheduled pull) — nothing pushes live in this window; anything that would have qualified queues into
the 07:30 HKT digest instead. Outside quiet hours: a **hard cap of 6 non-INFO pushes per rolling 24h**
(THESIS_CHANGE + SIGNAL_CANDIDATE + PAPER_ACTION combined), enforced by `telegram_bridge` refusing to send
past the cap and instead appending to the next digest — mirroring the existing `--daily` job. INFO-level
items are never pushed live; they fold into at most two digests/day (07:30 HKT pre-open, and an
after-close autopsy digest per the VISION file's §4.1 cycle).

### (e) Alert levels and their rules

| Level | Fires when | Requires grading history? |
|---|---|---|
| **INFO** | Any accepted typed event clears a low novelty/impact floor. Pure template rendering from `event_intel` fields (enum -> deterministic sentence), no LLM call, no thesis, no probability. | No — it makes no forecast, so there is nothing to grade. Allowed from day one. |
| **THESIS_CHANGE** | A typed event with confidence >= HIGH, not a duplicate (2c), maps to one of the event types with a *documented* effect size in Part 2 (guidance change, a specific 8-K item, an insider cluster, a bankruptcy/going-concern flag), and `sigma_move_1d` < ~2σ (not already fully priced). | Allowed from day one **only** for event types on the Part-2-documented list; anything else is demoted to SIGNAL_CANDIDATE-ungraded. |
| **SIGNAL_CANDIDATE** | Routes through the investigator process (1.3) for a forecast row with an explicit probability; matches a mechanism the codebase itself has *not yet* closed as BETA_EXPLAINS/CLOSED (revision-flow currently fails this test and must be excluded until re-cleared). | Emittable immediately but **must carry a visible "UNGRADED MECHANISM" tag** until `n_effective` (below) is reached — the `PRODUCT_EXPERIMENT` licence needs no significance gate to be *tested*, but the alert copy must say so, or Murat cannot tell an established finding from a fresh guess. |
| **PAPER_ACTION** | Only emitted by `decision_contract`/`pc_broker` reporting that a frozen paper-book position was actually entered. Never a suggestion — a report of something that already happened in paper. | N/A — it's a fact, not a forecast, though the position itself carries its own forecast row already. |

No level ever has authority to place a real-money order, per the binding constraint; PAPER_ACTION only
ever describes the existing paper books.

### (f) Grading plan

Measure at **1, 5 and 21 sessions** (matching `forecast_grader`/`source_scorecard`'s existing convention)
against **(i)** SPY/relevant sector ETF and **(ii)** a matched control (same liquidity/cap bucket, drawn
the way `source_scorecard` already draws its control), clustered by **alert date**, not by alert count
(§58: n_effective counts date blocks).

**How many alerts are needed, computed, not guessed:**

- *This codebase's own calibration point*: `source_scorecard`'s live WSJ leg has 16 claims on 9
  publication dates and is `TOO_FEW`; the receipt itself states **~110 publication dates** are needed for
  a usable confidence interval on a hit-rate near 50–56%. That is an *empirical* answer to a structurally
  similar problem (claims clustered by date, similar effect size) computed by this exact codebase days ago.
- *Independent check, proportion form*: to distinguish a hit rate from 50% to within ±5 points at 95%
  confidence (normal approximation, `p(1-p)=0.25` worst case): `n ≈ 1.96² × 0.25 / 0.05² ≈ 384`
  **independent** observations.
- *Independent check, return form*: to detect a 50bp mean 5-session abnormal return at 80% power,
  two-sided α=0.05, with a plausible 5-session cross-sectional return dispersion of 4.5–6.7% (from a
  1.9–3.0%/day figure elsewhere in this repo's own volatility work, compounded over 5 sessions):
  `n = ((1.96+0.84) × sd / MDE)² ≈` roughly **315–700** independent observations.
- All three estimates land in the same order of magnitude once date-clustering is accounted for.
  **Recommendation: do not let `policy_state` touch the alert threshold until `n_effective` (alert-DATES,
  not alert-count) reaches 100**, and treat 100–400 as the realistic range depending on how clustered the
  alerts turn out to be — which will not be known until the stream has run.

### (g) Kill rule

Reuse the project's own already-adopted bar rather than invent a new one: once `n_effective >= 100`
alert-dates, if **(i)** the hit rate / mean abnormal return vs. the matched control fails to clear
DSR ≥ 0.95 (the same bar `strategy_library`'s leaderboard already enforces — currently 0 of 336 cells
clear it), **or (ii)** a leave-one-period-out check (CLAUDE.md §11's rule: print by year/period before
trusting a positive) shows a majority of periods flat or negative, the live-push stream is declared noise:
demote everything to INFO-only (batched digest, no push) and mark the mechanism
`RETIRED_FROM_CURRENT_SEARCH` (never "STOP," per the Explore-Dirty canon) pending new evidence.

### (h) Cost and the spend-disagreement refusal

From `backend/data/optimus/llm_price/calibration_2026-09-27.json` (measured, not the prior table):
fitted DeepSeek rates are **$0.104/Mtok in, $0.00208/Mtok cached-in, $0.790/Mtok out**, and the
provider-measured spend was only **61–64% of the naive prior-table estimate** (`k_vs_prior 0.5903–0.6388`).
INFO alerts cost nothing beyond the ingestion the corpus already pays for (template rendering, no new
call). THESIS_CHANGE/SIGNAL_CANDIDATE alerts each cost roughly one `thesis_card`-equivalent synthesis:
$0.04–0.09 measured per card in the same calibration run. At the (d) cap of 6 non-INFO pushes/day, worst
case is **~$0.55/day, ~$17/month** — inside the ~$3/night DeepSeek budget Murat already runs today, and
far below it on any typical day (the 2026-09-27→28 session spent $0.02 total by the provider's own
balance).

**Refusal rule**, reusing the exact lesson already in memory ("a cap that reads a different ledger than
the writer cannot bind," 2026-09-21): before any alert that required a paid LLM call is sent, the sender
reads **both** the provider balance (`llm_cost_audit`) and local telemetry; if they disagree by more than
the calibration receipt's own established tolerance (~$0.01 balance granularity; the `k_vs_prior` bracket
is 0.59–0.64), further paid evaluations refuse for the remainder of the day, falling back to
INFO/deterministic alerts only, and the disagreement is logged as `DEGRADED` on the next `system_health`
probe pass — not silently absorbed.

### Reviewer's twelve scored components, scored against what is on disk today

| # | Component (as proposed) | Status | Why |
|---|---|---|---|
| 1 | Impact | COMPUTABLE NOW | `event_vocabulary`'s magnitude bucket + direction prior per event id |
| 2 | Novelty | COMPUTABLE NOW | `event_store`'s 3-clock history gives a real count of prior independent mentions |
| 3 | (1 − AlreadyPriced) | COMPUTABLE NOW | `sigma_move_1d/5d` against trailing realized vol, both already-computed inputs |
| 4 | EvidenceConfidence | COMPUTABLE NOW | `event_extraction`'s parse-fidelity tier (HIGH/MEDIUM/LOW/FAILED) |
| 5 | InformationScarcity | COMPUTABLE WITH WORK | needs a coverage-normalization denominator (article count per name over a trailing window) that `news_registry`/`news_pull` can supply per-source but isn't yet aggregated into one cross-source count |
| 6 | Exposure | COMPUTABLE WITH WORK | requires the causal-graph layer (company/supplier/commodity) the VISION file's §4.6 progression has not yet reached step 4; today this would have to be a hand-coded sector/theme tag, not a graph traversal |
| 7 | ValueCapture | NOT COMPUTABLE | needs a position-sizing / addressable-market estimate nothing on disk currently derives; would require new modeling, not a new collector |
| 8 | Tradability | COMPUTABLE NOW | ADV/liquidity data already used by `pc_broker`'s mandate limits |
| 9 | HistoricalSupport | COMPUTABLE WITH WORK | `source_scorecard`/`revision_flow` give this for the mechanisms they already cover (Dow Jones claims, revision flow); a new mechanism has none until it accrues its own history |
| 10 | Source-agreement / corroboration | COMPUTABLE WITH WORK | `three_source_compare` exists but must be redefined against rating CHANGE with the base rate printed (R5), not raw agreement, before it is safe to score |
| 11 | Crowding/attention | COMPUTABLE WITH WORK | `attention_z` exists in `pit_features.py`/`trends_sentiment.py` but its live-decision wiring is unverified this session |
| 12 | Analyst-consensus alignment | COMPUTABLE NOW, WITH A FLAG | `revision_flow` computes it, but the mechanism is currently `BETA_EXPLAINS`/2025-only per the 2026-09-28 handoff — computable, and currently should be **excluded** from a live score until re-cleared |

---

## PART 4 — source order and rate limits

| Lane | Source | Realistic free-tier limit | Cadence proposed | Where it fits today |
|---|---|---|---|---|
| Truth | SEC EDGAR (8-K current-filings Atom, XBRL company-facts) | Fair-access policy: max ~10 req/s with a declared, contactable User-Agent; recommend polling at 3–4 req/s for headroom | Current-filings feed: every 5–10 min (new 8-Ks appear within minutes of acceptance); XBRL facts: on-demand per name, not polled | `edgar_events.py`, `inflection.derive_q4` — already the HTTP-API-only path the constraints require |
| Truth | Company IR pages | No general rate limit; be polite (1 req per few seconds per domain) | Only on a triggered lookup (e.g. a THESIS_CHANGE candidate), not a standing poll | Not currently a running collector — would be new, small work |
| Truth | Regulators (FDA calendar etc.) | Source-specific; treat as low-frequency, cached | Daily | Referenced in VISION file, not confirmed built this session |
| Discovery | GDELT | No published limit; the repo's own puller uses 1.0s between requests; the underlying files only update every 15 min, so more frequent polling is wasted | Every 15 min | `scripts/gdelt_pull.py`, live |
| Discovery | Google News RSS | No official API/limit; empirically throttles aggressive polling; keep several seconds between requests per query | Every 15–30 min per tracked query/locale (matches the 15-min GDELT granularity anyway) | `news_pull.py` |
| Discovery | Alpaca news API | Documented free-tier limit ~200 req/min | Would be near-real-time if the credential were live | Currently REFUSED in this env (no `APCA_API_KEY_ID`) |
| Discovery | StockTwits public streams API | Historically documented at ~200 req/hour per unauthenticated client; self-throttle to ~1 req/sec with backoff regardless | Hourly snapshot per tracked name (matches the existing one-off pull's own per-hour framing in the 2026-09-27 handoff) | One-off snapshot exists; would need to become a scheduled loop to be a real "discovery lane," not just a research artifact |
| Discovery | Reddit | `.rss` largely 403s beyond a handful of names; treat as low-reliability, opportunistic only | Best-effort | `news_pull.py`, mostly blocked |
| Discovery | X (Twitter) | No free plain-HTTP path found; would need a paid API or browser, both out of scope per the binding constraints | N/A currently | 15/20 handles confirmed from company homepages only, no timeline reads |
| Discovery (paid, constrained) | WSJ / Barron's / MarketWatch | **Two paths only, per ToU §9.4.1**: (1) the free RSS headline-only feeds (`dowjones_feeds.py`), no browser, no limit beyond politeness; (2) Murat's own reading, either pasted via `digest_inbox.py` (any time, no limit) or read live by OpenClaw through the **marker-tab-confined, human-attended** browser session at the reviewed pace — **R4's recommendation, not yet reverted as of the 2026-09-28 handoff, is 20–90s gaps / 60s same-host**, ~60 pages/hour with three workers. **No unattended overnight full-text pull is compliant**, which is exactly what the 2026-09-28 handoff's failed night discovered the hard way. | RSS: every 15–30 min. Full text: only during an attended session, at the reviewed (slower) pace. | `dowjones_feeds.py` live; `digest_inbox.py` live; the attended reader exists but its pace decision is still open per handoff item R4/§8 |

**Net placement of the paid subscriptions**: they never become a standing collector. They enter the
pipeline as (a) free headline-only RSS on the same cadence as everything else, which is enough to produce
an INFO-level "WSJ just published something about X" alert with no ToU exposure, or (b) full text only
through Murat's own attended reading or paste — which means any THESIS_CHANGE/SIGNAL_CANDIDATE alert that
depends on Dow Jones full-text content should say so explicitly ("awaiting a human read") rather than
silently waiting forever, matching the "a refusal is a finding" house rule.

---

## Appendix: Part 2 literature detail (full citations)

**Post-earnings-announcement drift.** Bernard & Thomas (1989), *J. Accounting Research* 27:1–36
([jstor.org/stable/2491062](https://www.jstor.org/stable/2491062)): extreme-SUE-decile drift ~25%/yr
annualized over 60 trading days pre-costs; the authors themselves note it may be within round-trip costs
for small investors. Decay: Chordia et al. (2014); Zhao (Columbia CEASA working paper,
[link](https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf))
attributes most of the decline to falling *persistence* of the SUE signal itself; Martineau (2021) finds
post-2010 returns barely related to SUE rank. Costs: Ball (2008, *JAR*,
[doi](https://onlinelibrary.wiley.com/doi/10.1111/j.1475-679X.2008.00290.x)) vs. Zhang/Cai/Keasey (2014,
finding ~zero alpha after realistic costs). **Verdict: weak/dated today.**

**Guidance revisions.** Rees (2011, *Accounting & Business Research*,
[doi](https://www.tandfonline.com/doi/abs/10.1080/00014788.2011.550738)): −9.4% for downward guidance vs.
+2.7% for meeting/beating. Twedt (2015) shows wire dissemination speed dominates price discovery.
**Verdict: thin retail edge for wire-covered names; real for under-covered ones.**

**8-K items.** Lerman & Livnat (2010, *Rev. Accounting Studies*,
[ideas.repec.org](https://ideas.repec.org/a/spr/reaccs/v15y2010i4d10.1007_s11142-009-9114-7.html)):
only ~10/22 items show significant positive CARs, ~8 negative, several null; bankruptcy/receivership
largest (−12% mean). "Who Pays Attention to SEC Form 8-K?" (*Accounting Review* 2022,
[aaahq.org](https://publications.aaahq.org/accounting-review/article/97/5/59/336/)): most discovery happens
on the press-release event date, before the filing. **Verdict: structurally late for liquid names.**

**Insider cluster buying.** Cohen, Malloy & Pomorski (2012, *J. Finance* 67:1009-44,
[NBER WP](https://www.nber.org/papers/w16454)): opportunistic clusters 82bps/month (VW) / 180bps (EW),
t=2.15–6.07; routine trades ~zero. Practitioner cluster-alpha claims found in this search (unreviewed
blogs) roughly halve once look-ahead is removed from cluster assignment. **Verdict: real, smaller than
headline claims once the T+2 filing lag and look-ahead are handled honestly.**

**Analyst revision clusters.** Gleason & Lee (2003, *Accounting Review* 78:193-225); Womack (1996,
*J. Finance*): 3-day CAR ~+2.4%/−4.7% plus 6–12 month drift; Chen/Nie/Shi/Zhang (2024/25) confirm
persistence in recent samples, concentrated in non-herding, high-innovation revisions. **Verdict: most
durable of the eight in the literature — but see the project's own contradicting measurement in Part 1.**

**News novelty vs. repetition.** Tetlock (2007, *J. Finance*,
[doi](https://doi.org/10.1111/j.1540-6261.2007.01232.x)): sentiment effect fully reverses within a week.
Tetlock (2011, *Review of Financial Studies*,
[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1018221)): stale-vs-fresh decile difference of
413bps (EW) / 75bps (VW). Newer work ([ScienceDirect 2023](https://www.sciencedirect.com/science/article/pii/S0304405X23000685))
finds simple reprints increasingly ignored, but *recombined* old information still fools professional
investors. **Verdict: robust, directly actionable as a filter.**

**Attention/crowding.** Da, Engelberg & Gao (2011, *J. Finance* 66:1461-99,
[nd.edu](https://academicweb.nd.edu/~zda/Google.pdf)): +18.7–30bps over 2 weeks per 1-SD abnormal search
volume, fully reversing within a year, concentrated in small/retail-heavy names. **Verdict: small,
mean-reverting; a warning about crowding as much as a signal.**

**Price discovery speed.** Jiang, Lo & Valente (NBER SI 2015,
[PDF](https://conference.nber.org/confer/2015/SI2015/LE/Jiang.pdf)): ~half the informed price impact
within 5–6 minutes. von Beschwitz, Keim & Massa (Fed IFDP,
[PDF](https://www.federalreserve.gov/econres/ifdp/files/ifdp1233.pdf)): ~75% of a 2-minute reaction within
5 seconds for algorithmically-parsed releases on liquid names. SSRN 2567486
([PDF](https://www.wallstreethorizon.com/upload/SSRN-id2567486.pdf)): top-liquidity firms reach full price
discovery by the open; illiquid firms converge over 30 minutes with residual drift over subsequent days.
**Verdict: liquid names are too fast for a Telegram-latency pipeline; illiquid names carry genuine
minutes-to-days lag, which is also where costs are worst.**

This appendix was compiled by a research subagent from web search during this session; URLs should be
spot-checked before being cited in any external document, per this project's own "a headline number
belongs in a receipt" discipline.
