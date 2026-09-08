# VERIFICATION — 2026-09-08 — the nine-lane overnight build

Read-only audit of finance commits `7901d3b` / `7b09e91` / `6c04baf` and terminal
commits `9519bfd` / `382a6c4` / `1281486`, against receipts and code. Nothing was
modified, committed, deployed or killed. The finance suite was not run (CI is
running it: two `scripts.ci_watch --sha 6c04baf --wait` processes are live, PIDs
124096 and 142564).

Verdicts: **VERIFIED** / **WRONG** (with the right value) / **CANNOT DETERMINE** /
**PARTIAL**.

---

## 1. "Five books armed on 382a6c4, hack1 manage-only by declaration"

**Declaration: VERIFIED. Live state: CANNOT DETERMINE from the repository.**

`C:\Users\mrthn\aegis-alpha-terminal\alpha\fleet.py` carries `manage_only` on
exactly one role:

| role | line | `manage_only` |
|---|---|---|
| hack1 | `alpha/fleet.py:102` | `True` |
| hack2 | `alpha/fleet.py:118` | `False` (lifted 2026-09-07, comment at 109-117) |
| hack3 / hack4 / hack5 / hack6 | `:131 / :145 / :162 / :168` | field absent → dataclass default `False` (`alpha/fleet.py:59`) |

So five books (hack2-hack6) are ARMED **by declaration** and hack1 is manage-only
by declaration. `loop_args()` emits `--manage-only` from that field
(`alpha/fleet.py:270`).

**There is no deploy receipt.** The only Railway artefact in the repo is
`docs/RUNBOOK_2026-09-08_REARM.md`, which is an *instruction sheet* written
2026-09-05, not an observation: line 176 says "Nothing was pushed, deployed or
sealed by the session that wrote this," and §4 (lines 79-91) tells the human to
run `railway variables --service aat-loop-hack4 | grep -E "LOOP_ARGS|..."` to
verify. No `railway variables` output, no `--deploy` transcript, and no
`scripts.utilization` ENTRY-AUTHORITY dump is committed for 09-08. The build doc's
own §7 says the re-arm "requires redeploying all six Railway services" and that it
was "gated on their completion."

The runbook's live-account probe **is** recorded (`RUNBOOK_2026-09-08_REARM.md:615-618`):
all six accounts ACTIVE, `trading_blocked` false, **every book flat (0 positions)** —
hack1 $98,859 · hack2 $98,821 · hack3 $90,499 · hack4 $99,476 · hack5 $96,455 ·
hack6 $91,469. That reading pre-dates the re-arm and confirms the "empty" premise;
it does not confirm the deploy.

> **Whether `--manage-only` is absent from the six live `AAT_LOOP_ARGS` right now
> is CANNOT DETERMINE from the repo.** Verify with the runbook §4 commands.

---

## 2. "Verified against the live seal the loops hold (dc6b580d7faa1db3)…"

**Seal identity and terms: VERIFIED. "the seal the loops hold": WRONG.
"0 UNCLASSIFIED drivers": VERIFIED but NOT in the seal. Dollar figure: WRONG.**

The seal is `C:\Users\mrthn\aegis-alpha-terminal\state\predictions\2026-09-08.json`,
`content_sha256 = dc6b580d7faa1db3f28c6d9758ac0fc3468c0849ee5f8f3f3c2fa0fcfdd01605`,
`sealed_at_utc 2026-09-08T06:35:47Z`. Contract blocks read exactly:

| | hack3 | hack4 | hack6 |
|---|---|---|---|
| `expected_horizon_sessions` | **63** | 126 | **42** |
| `min_normal_hold_sessions` | **21** | 42 | **21** |
| `stop_frac` (operative) | **0.12** | 0.15 | **0.10** |
| `stop_fraction` (informational, stale) | 0.08 | 0.06 | 0.03 |
| `n_selected` / `k_target` | 10 / 10 | **0 / 5** | 15 / 15 |
| `rank_distinct_values` | 435 | **0** | 192 |
| `derived_gross` | 0.83 | 0.0 | 0.90 |
| `requires_catalyst` | false | **true** | false |

All the horizon / hold / stop numbers in the claim are **VERIFIED** against this file.

### (a) "the seal the loops hold" — WRONG
Two 2026-09-08 seals exist. The build doc's own §11-§12 says the loops synced the
**earlier** one and `sync_once` short-circuits on a valid local copy, so *"the loops
hold the OLD seal and will not re-fetch … today's books run horizon 21 / hold 10"*.

| file | sealed_at | sha (16) | hack3 horizon/hold/stop |
|---|---|---|---|
| `2026-09-08.pre_redeploy_0507.json` | 05:07:49Z | `f20929777f77fa55` | **21 / 10 / null** |
| `2026-09-08.json` | 06:35:47Z | `dc6b580d7faa1db3` | 63 / 21 / 0.12 |

`dc6b580d` is the *republished* seal that reaches the fleet **tomorrow**. The seal
the loops actually hold is `f20929777f77fa55`, whose contract is horizon 21 / hold 10
/ `stop_frac: null` (so the stop comes from the profile table: 12% basket, 10%
aggressive). The two seals also differ in hack6's names (hack3's ten are identical;
hack6's fifteen are not).

Both receipts that back the measurements — `docs/RECEIPT_2026-09-08_LIVE_TRANSFER.json`
and `docs/RECEIPT_2026-09-08_FLEET_INDEPENDENCE.json` (both in **finance**, not the
terminal repo) — state their method against **sha `f20929777f77fa55`**, i.e. the
pre-redeploy seal, not `dc6b580d`.

### (b) "hack3 10/10 admitted, zero refusals; hack6 15/15; 0 UNCLASSIFIED; largest driver 3 names" — VERIFIED, but the seal artefact says the opposite at face value
The seal's own `driver_exposure` field still reads
`hack3: {"UNCLASSIFIED": 0.83}` and `hack6: {"UNCLASSIFIED": 0.84, "solar_grid_alt_energy": 0.06}`.
The fix lives **downstream in the consumer**, not in the seal:
`alpha/drivers.py:135 sealed_sector_map(day)` (docstring 136-161) adds the sealed
`sector` as a third declared source, ordered index-beta → theme seed → sealed sector
→ UNCLASSIFIED (`alpha/drivers.py:190`, `:194-206`), prefixed `sector:`
(`:131 SECTOR_PREFIX`).

The claim is pinned by `tests_smoke_driver_sectors.py` (14 checks), which asserts
per book that the seal still holds 10 / 15 names, that **no** name is UNCLASSIFIED,
and that the largest driver holds ≤ 3 names. Confirmed against the seal's own sector
stamps: hack3 = {Biotechnology 3, Pharmaceuticals 3, Electrical Equipment 2, Health
Care 1, Chemicals 1}; hack6 = {Biotechnology 3, Pharmaceuticals 3, Health Care 3,
Financial Services 2, Electrical Equipment 2, Communications 1, Road & Rail 1}.
Max bucket = 3 in both. **VERIFIED.**

Caveat worth carrying: `1281486` fixed this suite to fall back to the committed
`pre_redeploy_0507.json` when the untracked live seal is absent — so on CI the
assertion runs against `f209…`, and on the dev box against `dc6b58…`. Both give the
same driver answer because the sector stamps are the same shape.

### (c) "≈25 positions, ~$165k of ~$575k" — positions VERIFIED, $165k WRONG, $575k VERIFIED
`docs/RECEIPT_2026-09-08_LIVE_TRANSFER.json` (finance) records the dry `run_pass`
per name:

| book | equity | live gross | live notional | rows |
|---|---|---|---|---|
| hack3 | $90,499.49 | 0.8288 | **$75,003** | 10 |
| hack6 | $91,468.74 | 0.8974 | **$82,086** | 15 |
| **total** | | | **$157,089** | **25** |

25 positions: VERIFIED. **$165k is WRONG — the receipt's own numbers give $157.1k.**
No receipt anywhere produces $165k (sealed weights against the $100k genesis equity
would give $173k; neither basis is $165k). $575k is VERIFIED: the six equities in
`RUNBOOK_2026-09-08_REARM.md:617-618` sum to **$575,579**.

---

## 3. hack4's $99k gated to zero by `requires_catalyst`

**VERIFIED, on every clause.**

- Account equity: `docs/RUNBOOK_2026-09-08_REARM.md:617` — hack4 **$99,476**.
- The book constraint: seal `portfolios.hack4.constraints.requires_catalyst = true`
  (hack3 and hack6 both `false`); code default and setter at
  `alpha/tracker.py:901` (`requires_catalyst: bool = False`), `:948` (the hack4-shaped
  personality sets `requires_catalyst=True`), enforcement at `alpha/tracker.py:1112`
  (`if p.requires_catalyst:`), serialised at `:1316` and
  `scripts/prediction_book.py:790`.
- The result: hack4 seals `n_selected = 0`, `rank_distinct_values = 0`,
  `derived_gross = 0.0`, `holdings = []`.
- The clause is `None`, not `False`, when the catalyst date is missing:
  `alpha/murat_rule.py:402` — `d = None if cat is None else bool(cat <= CATALYST_MAX_CALENDAR_DAYS)`
  (`CATALYST_MAX_CALENDAR_DAYS = 30`, `:94`), and `None` clauses are collected
  separately at `:422`.
- The generator's own contract lists it as unmeasured:
  `alpha/murat_rule.py:492` — `"clauses_not_measured": ["b_rating", "d_catalyst"]`,
  and `:493-498 why_not_measured` says verbatim: *"(d) had an EMPTY forward-catalyst
  calendar until 2026-08-30, so `days_to_next_catalyst` is null on essentially every
  panel row. The live rule is therefore STRICTER than the condition this base rate
  was measured under."*

So: a clause its own author marked "not measured" is used as a hard filter on a
$99,476 account, and the account seals empty. **The diagnosis is exactly right.**

---

## 4. hack1 / SPY and the seventh `market` account

**VERIFIED on the account; the crossbook half is PARTIAL / imprecise.**

- The benchmark is a separate seventh account: `alpha/genesis.py:77` —
  `"PA3I7VTCC0BM": ("role `market`. The passive-beta benchmark. 1 order, 0 positions…"`.
  Contract `PASSIVE_BETA_v1` at `scripts/contract.py:88-89`; `alpha/benchmark.py:1-11`
  (PASSIVE_BETA_v2) names the same account id. `alpha/arms.py:130` carries `role="market"`.
- **Its keys are not in `.env`.** Key *names* present (values never read):
  `AAT_HACK1_KEY_ID/SECRET_KEY` … `AAT_HACK6_KEY_ID/SECRET_KEY` — six pairs, and
  **no `AAT_MARKET_*` pair of any form**. VERIFIED.
- **The crossbook claim is imprecise.** `alpha/crossbook.py:peer_roles()` enumerates
  `fleet.FLEET` only, filtered to `SHARE_EXPRESSING_PROFILES = {conservative,
  aggressive, maximum, basket}`. The `market` account is **not a member of
  `FLEET`**, so crossbook is structurally blind to it: putting SPY into hack1 would
  duplicate the benchmark, but `overlap_refusal()` could never fire on that
  duplication. What crossbook *would* then flag is hack5 (profile `convex`,
  `alpha/fleet.py:166`) buying SPY premium while hack1 held SPY shares — a different
  and narrower thing. Also note crossbook refuses nothing on Railway by design: each
  service holds only its own key pair, so the check returns `CANNOT DETERMINE`
  (`alpha/crossbook.py:status()`).

The decision itself (SPY not added to hack1, pending Murat) is correctly recorded as
open in `BUILD_2026-09-08_FLEET_REARM_AND_PREMARKET_OFF.md` §7 and §12.

---

## 5. Suite counts

**Terminal 85 / 3903: VERIFIED as recorded. Finance 7821 / 0: PARTIAL — the number
is in a build doc, not in any commit, and three different counts circulate.**

Terminal (recorded, not re-run here):

| commit | recorded |
|---|---|
| `9519bfd` | 84 suites, 3875 checks, ALL PASS |
| `382a6c4` | **85 suites, 3903 checks, ALL PASS** |
| `1281486` | 14 checks either way in the one suite it touched |

Note `BUILD_2026-09-08_FLEET_REARM_AND_PREMARKET_OFF.md` §5 says **"84 suites, 3868
checks"** — that is the mid-session figure, superseded by `382a6c4`'s 85/3903. Two
different numbers for the same session are in the repo; the commit is the later one.

Finance:

| source | recorded |
|---|---|
| `7901d3b` body | Fast suite **7,794** passed |
| `7b09e91` body | Fast suite **7,820** passed; **one failure in the full run** (`test_receipts_come_back_newest_first`, attributed to a concurrent write by a still-running lane, "a quiet re-run is in flight") |
| `docs/BUILD_2026-09-08_R7_NEWS_REPRESENTATION.md:648` | `7821 passed, 20 skipped, 124 deselected, 501 warnings in 519.88s`; `:651` "**0 failed**" |
| `docs/BUILD_2026-09-08_R5_STRATEGY_PORTS.md:294` | baseline 7410 / 0 |
| `docs/BUILD_2026-09-07b_L_FREE_INFERENCE.md:435` | 0 failed (was 6 failed / 7348 before the lane's fixes) |

So "7821 passed, 0 failed" is a real pytest tail pasted into R7's build doc, but the
**newest commit records 7,820 with one failure in the full run**, and no commit
records 7821. CI on `6c04baf` is still running as of this writing.

---

## 6. "No joined text-and-return panel" — the news-representation numbers

**Sub-claims (b)-(f) VERIFIED against receipts and raw parquet. The headline
sentence as paraphrased is WRONG; the docs' own wording is right.**

| claim | verdict | evidence |
|---|---|---|
| 21,841 of 993,005 event rows carry a headline **and** a permno | **VERIFIED** | raw `event_table_v1.parquet`: `len=993,005`, `title.notna()=95,228`, both non-null `=21,841`, 91 distinct permnos. `docs/BUILD_2026-09-08_R3_ARCHETYPES.md:42-44`, §5.1 line 500 |
| 9,457 labelled cells across 135 names | **VERIFIED** | `backend/data/optimus/r7_news_representation/R7_panel_receipt.json`: `labelled_cells 9457`, `distinct_permnos 135`, `distinct_months 115`, span `2015-02 → 2024-11` |
| from-scratch encoder loses to TF-IDF on 528k headlines | **VERIFIED** | `R7_evaluate.json`, era `ALL` (83 pooled test months), mean cross-sectional rank-IC of `excess_vw_1m`: `tfidf_svd` **0.04172 (t 2.976)** vs `pit_mean` **0.00554 (t 0.385)** vs `rand_mean` **0.00441 (t 0.360)**. `adjudication.n_survivors = 0` under both BH-FDR and Holm on the 21-test per-era family |
| archetype grades collapse into a corpus-level effect | **VERIFIED** | `backend/data/optimus/archetypes/U_archetypes_nim.json`: corpus-level event−control `diff_mean_pp −0.8479, t −3.032`; `U-ARCH-A18-h5` `−0.8086, t −3.021`, Holm-adjusted p `0.04843`. `U_archetypes_posthoc_vs_other_events.json`: against the *other-events* control A18 is `−0.45 pp, t −1.99, p 0.0544` and **0 of 10 archetypes survive Holm**; the file's own `why` field states the mechanism |
| manifest fields | **VERIFIED** | `backend/data/optimus/events/event_table_v1_manifest.json`: `rows 993005`, `distinct_symbols 31626`, `distinct_permnos_linked 5516`, `permno_link_share 0.2214`, `year_range_present [2015, 2026]`; by_source `alpaca:benzinga 80,631` · finnhub ~14,537 · `edgar_8k 276,978` · `ibes_surpsumu 618,419` · `sec_ownership 2,380` · `company_ir 60` |

**Two denominator traps to carry forward.** The manifest's `permno_link_share`
**0.2214** is over *all* 993,005 rows (including textless 8-K/IBES rows); the doc's
"21,841 (22.9%)" is over the 95,228 **headline-bearing** rows. They are near-identical
numbers measuring different things and will read as a contradiction to a skimmer.

**And the headline is over-stated as paraphrased.** A joined text-and-return panel
*does* exist and every return number in R7 and R3 is computed on it
(`backend/data/optimus/r7_news_representation/panel.parquet`; the 21,841 joined rows
in `event_table_v1.parquet`). What is true — and what R7 §0.1 (lines 25-31) actually
says — is that the panel is **tiny and disjoint in time**: CRSP forward returns end
2024-12 while dense whole-market news coverage is 2025-26, so the years with coverage
have no prices and the years with prices have ~1% coverage. "No panel" is a
compression that loses the real finding.

---

## 7. "11.5M Form 4 rows" (I1 SEC insider lane)

**VERIFIED, on all four sub-questions.**

- Row count: `backend/data/optimus/sec_insider/coverage_by_year.json:172` —
  `"rows_total": 11522229` (also mirrored in `sec_insider/_cursor.json:90`).
  Companions: `filings_total 4,062,913`, `distinct_issuers_total 17,999`,
  `distinct_insiders_total 225,779`. All match `BUILD_2026-09-07b_I1_SEC_INSIDER.md:15`.
- Coverage by year: the same receipt's `by_year` object is keyed **2006–2026** with
  `rows / filings / distinct_issuers / distinct_insiders / open_market_purchases /
  open_market_sales / link_rate / cmp_routine / cmp_opportunistic / cmp_unclassifiable`
  per year. Spot-checks on 2006, 2009, 2016, 2024, 2025, 2026 match the doc's §1 table
  exactly — including 2025/2026 `link_rate: 0.0` with `REFUSED_OUTSIDE_CRSP_VINTAGE`
  as the sole refusal reason. Quarters pulled: 82/82, 0 failed (doc line 14).
- Routine-vs-opportunistic split: **exists**, classifier
  `backend/services/sec_insider_bulk.py:687 classify_routine_opportunistic`
  (three-strictly-prior-years CMP rule; unclassifiable is never defaulted to
  opportunistic), with `build_purchase_history` at `:661` and
  `is_discretionary_open_market_purchase` at `:423`. Receipt `cmp_totals` =
  `{opportunistic 185,555 · routine 78,444 · unclassifiable 940,379 ·
  open_market_purchases 1,204,378 · insiders_with_purchase_history 80,675}`,
  cross-checked against `insider_events_v1_receipt.json → event_type_counts`. Parity
  with the live scorer (`backend/services/cmp_insider.py:72 classify_buy`) is pinned by
  `backend/tests/test_sec_insider_bulk.py:433
  test_bulk_classifier_agrees_with_the_live_cmp_scorer`.
- PIT test: **exists**, guard `sec_insider_bulk.py:279 assert_pit_sane` (fails a row
  whose `observed_at_utc` is not derived from `filing_date`), red-test
  `backend/tests/test_sec_insider_bulk.py:293
  test_pit_test_goes_red_on_a_lookahead_join` (rebuilds `observed_at_utc` from
  `TRANS_DATE` and asserts the raise). Receipt `insider_events_v1_receipt.json →
  pit_check`: `{rows_checked 3,127,624, violations 0, future_dated_transactions 670}`.

---

## 8. "Every lane ran at $0.00 — DeepSeek untouched at $9.28, on local Qwen"

**Local inference and $0.00 lane spend: VERIFIED. "$9.28, untouched": WRONG /
CANNOT DETERMINE — the figure is a day stale and the ledger says $9.38.**

- Model: `Qwen2.5-7B-Instruct-Q4_K_M.gguf`, declared at
  `backend/services/model_provider.py:94-105` (`PROVIDERS["local"]`), weights at
  `C:\Users\mrthn\llama\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf`, served by
  `llama-server.exe -m <gguf> --port 8080 -ngl 99`.
- Invocation: llama.cpp's OpenAI-compatible endpoint at `http://127.0.0.1:8080/v1`
  over raw `urllib.request` (`model_provider.py:53-54` imports, HTTP call at
  `:214-221` inside `complete()`). Not ollama, not transformers.
- A **real** generation receipt exists:
  `backend/data/optimus/free_inference_2026-09-07/L3_known_answer_local_gguf.json` —
  genuine per-document token counts, latencies and outputs, 6/6 correct, 2/2 nulls
  refused. It was produced by a manual `scripts/local_review_run.py --known-answer
  --backend local_gguf`, **not** by a CI-enforced test: every test in
  `backend/tests/test_free_inference.py` and `test_local_review.py` monkeypatches the
  transport, and none is marked `slow`/`network` (the fast suite blocks sockets). So
  there is a receipt of a real run and **no regression test that re-verifies it**.
- Lane spend $0.00: **VERIFIED** — every receipt in `free_inference_2026-09-07/`
  prices calls at `cost_usd: 0.0`, and
  `test_the_default_backend_is_free_and_is_never_the_paid_one` pins `nvidia_nim` as
  the default.
- **The $9.28 is stale and slightly wrong.** The DeepSeek balance ledger
  `backend/data/optimus/deepseek_balance.jsonl` has **three** entries; the newest is
  `{"read_at": "2026-09-05T12:23:33Z", "total_usd": 9.38}` — **$9.38, read 2026-09-05**,
  and the file has not been appended since. The "$9.28" traces to
  `backend/data/optimus/night_lab_2026-09-07/N6b_fantasy_exams_round2.json`
  (`generated_at_utc 2026-09-06T17:11:43Z`, `spend.balance_usd_before/after 9.28`) —
  the **previous** session. `BUILD_2026-09-07b_L_FREE_INFERENCE.md` itself only ever
  says "~$9" (lines 358, 389); the "$9.28" is quoted by
  `BUILD_2026-09-08_FLEET_REARM_AND_PREMARKET_OFF.md`'s scoreboard and by three other
  09-07 docs, all inheriting the same 09-06 number.
  **No before/after DeepSeek balance probe was taken for the 09-07/08 window.**
  Per CLAUDE.md's own rule ("the provider's balance is the truth"), this is exactly the
  check that should have been run: `python -m scripts.llm_cost_audit --snapshot`.

---

## 9. "The MMC prereg blocked at R13, the missing measurement named"

**VERIFIED.**

File: `C:\Users\mrthn\Aegis module\TRIALS\PREREG_MMC_SECOND_SELECTOR.md` — the
fourth repo, *not* `aegis-finance/docs/TRIALS/` (which holds only
`PREREG_AEGIS_NET_TOURNAMENT_1.md`).

- Status line, `:3-4`: **"Status: NOT REGISTERED — BLOCKED by R13 at
  `MISSING_POWER_FIELDS`, deliberately left blocked."**
- R13 line, `:8-13`, verbatim: *"**WHY IT IS BLOCKED, AND WHY THAT IS THE RIGHT
  ANSWER.** R13 requires `declared_effect_size` and `outcome_dispersion` **in
  percentage points** — i.e. in the units of the thing the book would actually earn.
  Every number this trial has is in CORRELATION space, and the S8 receipt says so in
  its own `not_claimed` field…"*
- The missing measurement is named at `:21-26`: run `be_me` and `at_gr1` (plus two
  correlation-matched near-zero-MMC controls) through `run_one` as
  `PRODUCT_EXPERIMENT` books to get net excess return in **pp**, dispersion, turnover
  and `breakeven_fee_bps` per month. None of it exists yet; everything measured so far
  (`backend/data/optimus/strategy_ports/S8_mmc.json`, present in finance) is
  correlation-space.
- Cross-referenced independently in
  `docs/BUILD_2026-09-08_FLEET_REARM_AND_PREMARKET_OFF.md:316-319` and
  `docs/DECISIONS_2026-09-08_FABLE_ON_THE_REARM_AND_THE_ACTIVE_BOOK.md:49-51`.
- The power arithmetic in the commit body (109 months for `be_me`, sd_mmc 0.0642) is
  reproduced in the prereg.

---

## 10. E1 / H1 / S1 / hygiene rows

### E1 — resumable news puller: **DONE**
Repo: **terminal**, not finance (`aegis-alpha-terminal/scripts/news_backfill.py` +
`scripts/pull_journal.py`).

| requirement | file:line |
|---|---|
| cursor | `scripts/pull_journal.py:149` `self.cursor_path = self.dir / "cursor.json"`; load at `:159` |
| log | `pull_journal.py:150` `run.log` |
| PID | `pull_journal.py:151` `run.pid`; liveness + stale-owner handling `:193-211`, `pid_alive()` `:92` (uses `OpenProcess`, never signals — Windows-safe) |
| `--start` / `--end` | `scripts/news_backfill.py:411-412` |
| tradable universe | `news_backfill.py:415-418` (`--universe` choices include `tradable`) and `:126-140` `_universe()` → `tradable_universe.load()` which **raises `UniverseRefusal`** rather than silently falling back |

Proving suite: `tests_smoke_news_pull.py` — **71/71 checks, ALL OK** (run directly).

### H1 — candidate surface: **DONE**
`backend/routers/candidates.py`, `APIRouter(prefix="/api/candidates")` at `:67`; six
GET routes at `:642 /vintages`, `:692 /universe`, `:814 /universe/{symbol}`,
`:847 /watchlist`, `:898 /bands`, `:959 /allocator`. Registered at
`backend/main.py:533`. Page: `frontend/src/app/candidates/page.tsx` (43,847 bytes),
nav entry `frontend/src/components/sidebar.tsx:66`. Tests:
`backend/tests/test_candidates_router.py` — **53/53 pass** (collected count matches;
the gap between 30 `def test_` lines and 53 is parametrisation).

### S1 — Strategy interface: **DONE, with two phrasing corrections**
- The Strategy contract is `backend/strategy/contract.py:374-375` — a **frozen
  dataclass**, not an `abc.ABC` or `typing.Protocol`. The build doc says "the
  `Strategy` record" and never claims ABC/Protocol, so this is a mis-statement in the
  question, not in the doc.
- `run_one` at `backend/strategy/run.py:96`. The byte-for-byte test is
  `backend/tests/test_strategy_run_one.py:361
  test_run_one_REPRODUCES_the_growth_books_sealed_DEVELOPMENT_cells`, asserting
  (`:386-391`) `assert list(got) == list(sealed_cell)` then
  `assert run_bytes == sealed_bytes` on `json.dumps(..., indent=1, default=str)`.
  **Correction: it reproduces two cost-basis cells (`10bps`, `25bps`) inside ONE
  sealed receipt** — `backend/data/optimus/growth_book/G4_seal.json`
  (`seal["development"]["10bps"]` / `["25bps"]`) — not two separate receipt files.
  The on-disk receipt `backend/data/optimus/strategy_interface/S1_reproduction.json`
  (regenerated 2026-09-08 18:30) still shows both cells `"byte_identical": true` with
  sha256s matching the doc (`c1663dde…`, `e976d531…`). The second reproduction test
  (arena book) is a live dict comparison, not a stored-file byte comparison, and R7's
  §2(a) says so.
- Multiple-testing library: `backend/strategy/multipletesting.py` (vendored, MIT
  header `:15-32`) — `sharpe_ratio:216`, `probabilistic_sharpe_ratio:253`,
  `expected_maximum_sharpe:317`, `deflated_sharpe_ratio:357`,
  `benjamini_hochberg:411`, `probability_of_backtest_overfitting:481`. Tests:
  `backend/tests/test_multipletesting_port.py` **20/20 pass**;
  `test_strategy_contract.py` 21/21.

### Xf / Xt hygiene rows

| row | verdict | implementation | test |
|---|---|---|---|
| **clock-skew guard** | **DONE** | `alpha/runner.py:355 CLOCK_SKEW_LIMIT_S = 300.0`; `:370-397 class ClockSkew`; `:403-425 venue_clock_skew(client)` (one `GET /v2/clock`, `seconds = local − venue`, never raises); call site `:1233-1241` → `_refuse_whole_pass("clock_skew", …)`, ordered **after** the expiry gate (`:1200-1211`); `"clock_skew"` in `REFUSAL_CLASSES` `:213`; `alpha/refusal_classes.py:263` maps `CLOCK_SKEW → DATA_STALE` | `tests_smoke_labor_faults.py:516-598` case C1-8 (`_SkewedVenue(±20)`, asserts ±1200s measured, `.refuses` True both directions, `classify(...) == "CLOCK_SKEW"`, and that `exits.evaluate` still closes an 11%-underwater position under skew); `tests_smoke_session_fixture.py` |
| clock skew in **`alpha/exits.py`** | **NOT PRESENT** (as the doc states) | grep for `clock|skew` in `alpha/exits.py` returns one unrelated comment at `:133`. **The guard is in `runner.py` only.** | — |
| stale NAV | **PARTIAL** (doc's own label, accurate) | `scripts/growth_g7_forward_lanes.py:191 STALE_MARK_MARKET_MOVE = 0.0010`; `:194 mark_freshness`; `:230 admissible_returns_from_nav`; row fields `stale_marks_excluded` / `beta_admissible_as_exposure` at `:428-429, :564, :573` | `backend/tests/test_x2_stale_nav_marks.py::test_carried_marks_hide_beta_and_exclusion_gives_it_back` (plants β=1.20, asserts raw β < 0.80 and post-exclusion β ≈ 1.20 ± 0.06) and `::test_a_uniformly_one_session_old_mark_is_reported_not_repaired` (plants the unrepairable case; asserts exclusion does **not** fix it and the row is stamped `beta_admissible_as_exposure False` with "STALE MARKS") |
| **Sunday fixtures** | **DONE for 3 of the 4 named suites** | `tests_fixtures.py` (new, 175 lines): `session_clock()`, `expiry_after_session()`, `open_clock()`, `closed_clock()`, `event_date_pending()`, `US_MARKET_HOLIDAYS` (2025-2027), all derived from `alpha.exits.now_et()`. New refusal class `session_closed` (`runner.py:213`) → `SESSION_CLOSED → MANDATE` (`refusal_classes.py:258`) | Imports of `tests_fixtures` confirmed in **`tests_smoke_equity.py:48`**, **`tests_smoke_pair.py:42`**, **`tests_smoke_entry_timing.py:62`** — and **NOT in `tests_smoke.py`** (zero grep hits). Sweep: `tests_smoke_session_fixture.py:80-113` reproduces the old derivation inline over 500 days × 24 hours and asserts `old_collisions > 1000`, `new_collisions == 0` |
| VENUE_REJECTED | **DONE** | `alpha/refusal_classes.py:105-106` (pattern, deliberately last in `PATTERNS`); `:131 VENUE_CLASSES`; `:178-189 kind_of() → "venue"`; `:221-239 TERMINAL_STATES` (18 entries); `:293 CLASS_TO_TERMINAL` | `tests_smoke_terminal_state.py:59-70` (`REQUIRED` set asserted `== set(rc.TERMINAL_STATES)`); `tests_smoke_labor_faults.py:763,804` case C1-14 |
| `verdict_from` | **DONE** | `scripts/weekend_lab_jobs.py:228 SEPARATION_ALPHA = 0.05`, `:231 def verdict_from(inf, eras, *, holm_p=None)`, wording at `:316`; `learner/evidence_memory.py:121` adds `SEPARATED_NOT_SURVIVING` to `VERDICT_VOCABULARY`, `:828-835` to `_CAPPING_WORDS` beside `NOISE` | `backend/tests/test_x5_separated_not_surviving.py` (11 tests, incl. `test_the_derived_path_never_invents_it`, `test_the_b1_fast_receipt_shows_the_flip`) |
| ERAS callers | **DONE** | `learner/evaluate.py:758 eras_covering(df, date_col)` (tries `ERAS`, falls back to `long_eras()`, else refuses — so sealed 2016-2024 receipts still reproduce); `:843-850 grade_by_era` docstring; callers `scripts/learner_run.py:239-240` and `scripts/learner_v2_run.py:346-347` both pass `eras=E.eras_covering(sub)` | `backend/tests/test_x6_era_grid_callers.py:102-108 test_the_known_answer_bare_really_does_refuse_on_the_long_panel`; real AST sweep at `:116-146`. Minor: the sweep is scoped to `_SCAN = ("scripts","learner","backend","lab","engine")`, not literally "every call site in the repo" |
| one price table | **DONE** | `backend/services/llm_research.py:74 PRICE_PER_MTOK = _config.LLM_PRICE_PER_MTOK` and `:109-117 _price()` re-reads `_config.LLM_PRICE_PER_MTOK` **at call time**; canonical table `backend/config.py:1832` | `backend/tests/test_one_price_table.py` — AST-based (`_module_level_rate_tables()` parses, never imports), plus `test_config_is_the_only_literal_rate_table_for_a_priced_model` and the one sanctioned exception `era_replay_v2.NANO_PRICE_PER_MTOK` |
| STATE_SEMANTICS | **DONE** (a module-level dict, not a separate file — as the doc says) | `learner/potential_universe.py:164-166 STATE_SEMANTICS = {"status": "CANNOT_DETERMINE", "admissibility": "INFORMATIONAL-ONLY — never a sizing, admission or routing input"…}`; verdict block `:179-193`; embedded into the written payload at `:617` | `backend/tests/test_x8_state_semantics_header.py:122 test_the_written_vintage_round_trips_the_verdict` (writes to `tmp_path`, not the real vintage) |
| **taskkill hook** | **NOT DONE** | No `PreToolUse` hook in `C:\Users\mrthn\aegis-finance\.claude\settings.json` (only a `SessionStart` hook) nor in `C:\Users\mrthn\aegis-alpha-terminal\.claude\settings.json`. No `.claude/hooks/` dir in either repo. **`aegis-finance\.claude\settings.local.json:19` actually contains `"Bash(taskkill:*)"` under `permissions.allow` — a grant, the opposite of a block.** | none. Neither build doc claims it is done; `BUILD_2026-09-07b_Xt_TERMINAL_HYGIENE.md` §4.8 explicitly says X11 "belongs to whoever owns `.claude/settings.json`; nothing here changed it" |

---

## 11. Is the news backfill running?

**YES.** `Get-CimInstance Win32_Process`:

```
ProcessId 50240  CreationDate 2026-09-07 18:35:18
  python.exe -m scripts.news_backfill --start 2025-01-01 --end 2026-07-01
             --universe tradable --no-finnhub
```

(Also live: PIDs 124096 and 142564, both `scripts.ci_watch --sha 6c04baf --wait`.)
**Nothing was killed.**

Journal — `C:\Users\mrthn\aegis-alpha-terminal\state\pulls\news_2025-01-01_2026-07-01_tradable\`:

- `run.pid` — owns pid **50240**, `started_at 2026-09-07T10:35:18+00:00`, argv and
  log/cursor paths recorded. Owner is alive, so the journal's `open()` refusal is
  working as designed.
- `cursor.json` (updated **2026-09-08T11:37:13Z**):
  - `meta`: `n_symbols` **12,198**, `legs ["alpaca"]`, `months` **18**, `max_pages 40`
  - `done.alpaca`: **12 of 18 months complete** — 2025-01 … 2025-12
  - `partial.alpaca`: `{"month": "2026-01", "index": 105}` — currently mid-2026-01
  - `totals`: **items 328,589 · stored 314,994 · duplicate 13,595 · http transport errors 331**
  - `resumed: 0` (never crashed and restarted)
- `run.log` (17 lines) — one line per completed month. Throughput ~1,350-1,650 s/month
  normally; two long stalls are visible: **2025-04 took 62,510 s** (17.4 h, overnight)
  and 2025-09 took 9,237 s. 3,000-4,600 of 12,198 names carry news per month.

**Progress: 12/18 months (~67%) after ~25 h.** At the normal ~25 min/month rate the
remaining six months are ~2.5 h; the 2025-04 stall shows that estimate is not
reliable. Two sibling runs exist and are idle:
`news_2025-01-01_2026-09-08_fleet` and `news_2026-07-01_2026-09-01_tradable`.

---

## VERDICT TABLE

| # | Claim | Verdict |
|---|---|---|
| 1 | Five books armed on `382a6c4`, hack1 manage-only by declaration | **VERIFIED** (`alpha/fleet.py:102,118,59,270`) |
| 1b | A receipt of the Railway deploy (variables, `--manage-only` absent) | **CANNOT DETERMINE** — no deploy receipt in either repo; the runbook is an instruction, not an observation |
| 2a | Seal `dc6b580d7faa1db3` exists with those contract terms | **VERIFIED** |
| 2b | It is "the live seal **the loops hold**" | **WRONG** — the loops hold `f20929777f77fa55` (05:07Z, horizon 21 / hold 10 / `stop_frac` null); `dc6b580d` (06:35Z) reaches the fleet tomorrow. Both 09-08 receipts state `f209…` as their method basis |
| 2c | hack3 63/21/12%, hack6 42/21/10% | **VERIFIED** in `dc6b580d` |
| 2d | hack3 10/10 and hack6 15/15 admitted, zero refusals | **VERIFIED** (pinned by `tests_smoke_driver_sectors.py`, 14 checks) |
| 2e | 0 UNCLASSIFIED drivers, largest driver 3 names | **VERIFIED in the consumer** (`alpha/drivers.py:135,190`), but the **seal's own `driver_exposure` still reads UNCLASSIFIED 0.83 / 0.84** — read the code, not the artefact |
| 2f | ≈25 positions | **VERIFIED** (10 + 15) |
| 2g | ~$165k deployed | **WRONG — $157,089** per `RECEIPT_2026-09-08_LIVE_TRANSFER.json` (hack3 $75,003 + hack6 $82,086) |
| 2h | of ~$575k | **VERIFIED — $575,579** (`RUNBOOK_2026-09-08_REARM.md:617-618`) |
| 3 | hack4's $99k gated to zero by `requires_catalyst: true` | **VERIFIED** (equity `RUNBOOK:617`; constraint `tracker.py:901,948,1112`; seal `n_selected 0`) |
| 3b | against a clause `murat_rule` lists under `clauses_not_measured` | **VERIFIED** (`alpha/murat_rule.py:492`) |
| 3c | EMPTY forward-catalyst calendar until 2026-08-30 | **VERIFIED** verbatim (`alpha/murat_rule.py:493-498`) |
| 4a | The benchmark is a seventh `market` account `PA3I7VTCC0BM` | **VERIFIED** (`alpha/genesis.py:77`, `scripts/contract.py:88`, `alpha/benchmark.py:11`) |
| 4b | Its keys are not in `.env` | **VERIFIED** — six `AAT_HACK{1..6}_*` pairs, no `AAT_MARKET_*` |
| 4c | Putting SPY in hack1 would trip crossbook | **PARTIAL / imprecise** — `crossbook.peer_roles()` enumerates `fleet.FLEET` only, and `market` is not a member, so the *benchmark duplication* is invisible to it. What would fire is hack5 (`convex`) buying SPY premium against hack1's shares |
| 5a | Terminal 85 suites / 3903 checks ALL PASS | **VERIFIED as recorded** (`382a6c4` body). Note the build doc §5 says 84 / 3868 — mid-session, superseded |
| 5b | Finance 7821 passed, 0 failed | **PARTIAL** — the pytest tail is at `BUILD_2026-09-08_R7…md:648-651`, but no commit records 7821; `7b09e91` records **7,820 with one failure in the full run** and `7901d3b` records 7,794 |
| 6a | "No joined text-and-return panel" | **WRONG as paraphrased** — a joined panel exists (`r7_news_representation/panel.parquet`; 21,841 joined event rows) and every return number is computed on it. The true finding is that it is **tiny and time-disjoint**: returns end 2024-12, dense news is 2025-26 |
| 6b | 21,841 of 993,005 rows carry headline + permno | **VERIFIED** (raw parquet) |
| 6c | 9,457 labelled cells across 135 names | **VERIFIED** (`R7_panel_receipt.json`) |
| 6d | From-scratch encoder loses to TF-IDF | **VERIFIED** — 0.0055 (t 0.39) vs 0.0417 (t 2.98); 0 survivors under BH-FDR and Holm |
| 6e | Archetype grades collapse into a corpus-level effect | **VERIFIED** (`U_archetypes_nim.json`, `U_archetypes_posthoc_vs_other_events.json`) |
| 6f | `permno_link_share` in the manifest | **VERIFIED — 0.2214**, but over a **different denominator** than the doc's 22.9% |
| 7a | 11.5M Form 4 rows | **VERIFIED — 11,522,229** (`sec_insider/coverage_by_year.json:172`) |
| 7b | Coverage by year exists | **VERIFIED** — `by_year` 2006-2026, 10 fields per year |
| 7c | Routine-vs-opportunistic split exists | **VERIFIED** (`sec_insider_bulk.py:687`; 185,555 / 78,444 / 940,379) |
| 7d | PIT test exists | **VERIFIED** (`sec_insider_bulk.py:279`; red-test at `test_sec_insider_bulk.py:293`; 3,127,624 rows, 0 violations) |
| 8a | Every lane at $0.00 | **VERIFIED** for lane L's own receipts |
| 8b | Local model = Qwen | **VERIFIED** — `Qwen2.5-7B-Instruct-Q4_K_M.gguf` via llama-server on `127.0.0.1:8080/v1` (`model_provider.py:94-105, 214-221`) |
| 8c | A real local generation happened | **VERIFIED by receipt** (`L3_known_answer_local_gguf.json`, 6/6 correct) — but **no automated test re-verifies it**; every test monkeypatches the transport |
| 8d | DeepSeek untouched at $9.28 | **WRONG / CANNOT DETERMINE** — the ledger's newest entry is **$9.38 at 2026-09-05**; $9.28 comes from the **09-06** night-lab receipt. No before/after probe was taken for the 09-07/08 window |
| 9 | MMC prereg blocked at R13, missing measurement named | **VERIFIED** (`Aegis module/TRIALS/PREREG_MMC_SECOND_SELECTOR.md:3-4, 8-13, 21-26`) |
| 10-E1 | Resumable news puller: cursor, log, PID, `--start/--end`, tradable universe | **DONE** (terminal repo; `pull_journal.py:149-151`, `news_backfill.py:411-418,126-140`; 71/71 checks) |
| 10-H1 | Candidate surface: endpoints + page | **DONE** (`routers/candidates.py:67,642-959`; `main.py:533`; `frontend/src/app/candidates/page.tsx`; 53/53 tests) |
| 10-S1 | Strategy interface + `run_one` byte-for-byte + multiple-testing lib | **DONE** — with two corrections: it is a frozen dataclass not an ABC/Protocol, and the byte-for-byte test compares **two cost cells in ONE sealed file** (`G4_seal.json`), not two receipt files |
| 10-X1 | Clock-skew guard in `runner.py` | **DONE** (`alpha/runner.py:355,370-397,403-425,1233-1241`) |
| 10-X1b | Clock-skew guard in `alpha/exits.py` | **NOT PRESENT** — by design; `exits.py` has no skew check |
| 10-X2 | Stale NAV | **PARTIAL**, honestly labelled |
| 10-X3 | Four Sunday suites have a venue-open fixture | **3 of 4** — `tests_smoke_equity.py:48`, `tests_smoke_pair.py:42`, `tests_smoke_entry_timing.py:62` import `tests_fixtures`; **`tests_smoke.py` does not** |
| 10-X4 | VENUE_REJECTED | **DONE** (`refusal_classes.py:105-106,131,178-189,221-239,293`) |
| 10-X5 | `verdict_from` | **DONE** (`weekend_lab_jobs.py:228-316`; 11 tests) |
| 10-X6 | ERAS callers | **DONE** (`evaluate.py:758`; AST sweep, scoped to 5 dirs) |
| 10-X7 | One price table | **DONE** (`llm_research.py:74,109-117`; `config.py:1832`) |
| 10-X8 | STATE_SEMANTICS | **DONE** (`potential_universe.py:164-193,617`) |
| 10-X11 | taskkill hook | **NOT DONE** — and `settings.local.json:19` *allows* `Bash(taskkill:*)` |
| 11 | News backfill running | **YES**, PID 50240, **12 of 18 months done**, 314,994 rows stored, mid-2026-01 at index 105, `resumed: 0` |

---

## THINGS THE BUILD DOCS CLAIM THAT A RECEIPT DOES NOT SUPPORT

1. **"~$165k deployed."** `BUILD_2026-09-08_FLEET_REARM…md` §14 and
   `DECISIONS_2026-09-08_FABLE…md:24`. The only receipt that measures it —
   `RECEIPT_2026-09-08_LIVE_TRANSFER.json` — gives **$157,089**. No basis in any file
   produces $165k. ($575k is right.)
2. **"DeepSeek untouched at $9.28."** The balance ledger
   `backend/data/optimus/deepseek_balance.jsonl` stops at **$9.38 on 2026-09-05**.
   $9.28 is inherited from the 09-06 night-lab receipt. **No balance probe was taken
   for this session's window**, so "untouched" is asserted, not measured — against
   this project's own standing rule that the provider's balance is the truth.
   `python -m scripts.llm_cost_audit --snapshot` closes this in one command.
3. **"the live seal the loops hold (`dc6b580d`)."** The build doc's own §12 says the
   loops hold the older seal and "a seal fix is never same-day"; both 09-08 receipts
   name `f20929777f77fa55` as their basis. Any summary that attaches the 63/21/12%
   terms to today's *executed* book is a day early.
4. **"0 UNCLASSIFIED drivers" read off the seal.** The seal artefact still stamps
   `driver_exposure: {"UNCLASSIFIED": 0.83}` (hack3) and `0.84` (hack6). The claim is
   true of `alpha/drivers.py`'s resolution, not of the seal. Anyone auditing this by
   opening the JSON will conclude the fix did not land.
5. **Terminal suite count stated twice, differently.**
   `BUILD_2026-09-08_FLEET_REARM…md` §5 says 84 / 3868; commit `382a6c4` says 85 /
   3903. The doc was not updated after the last commit.
6. **Finance suite count: 7821 appears in no commit.** `7b09e91` records 7,820 with
   one full-run failure. The 7821/0 line is a build-doc paste from a different run.
   CI on `6c04baf` was still in flight at audit time.
7. **X3's row status lists `tests_smoke.py` among the fixed Sunday suites.** It does
   not import `tests_fixtures` at all. `BUILD_2026-09-07b_Xt_TERMINAL_HYGIENE.md` §4.2
   admits this in prose ("I have no evidence about it") but the row-status table does
   not carry the caveat forward.
8. **R7/R3's "no joined text-and-return panel," as summarised.** The docs themselves
   are careful; the compression into "no panel" is what is wrong. Both lanes build and
   compute on a joined panel — it is just 9,457 cells / 21,841 events across ~83-135
   large-cap names, and the coverage-rich years have no returns.
9. **The lane L "real integration test."** There is a genuine local-generation
   **receipt**, but no test in the fast suite ever calls the local server (all
   monkeypatched, none marked `slow`). If llama-server changes shape, nothing goes red.
10. **The deploy itself.** Five books are armed **by declaration**. Whether the six
    Railway services carry `AAT_LOOP_ARGS` without `--manage-only`,
    `AAT_MANDATE_END_UTC=2027-12-31T15:00:00Z` and `AAT_LOOP_EXPIRY=2027-12-31`
    **cannot be determined from the repository**. That is the single check that
    decides whether anything trades on 09-08, and it has no receipt.
