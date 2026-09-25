# Build plan — 2026-09-25 — Fable 5.1 (plan) → Opus 5.5 (build)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`, one chunk at a time, Fable validates each.
> Steps use `- [ ]` checkboxes. **Nothing here was built on 2026-09-25.**

**Goal:** put the information the repo already collects (analyst revisions,
investigator forecasts, the committee shortlist) on the one path that reaches
`pc_broker.submit()`, restart forecast accrual, freeze the human + AI book with
its twins, and be ready for the Bloomberg challenge on Oct 12.

**Architecture:** every new input enters as a *book with a twin* or an *explicit
gate on `u_plan`*, never as a feature in `xs_ranker.FEATURES` by default. The
LLM extracts typed evidence and emits a probability; a deterministic
aggregator (shrink → floor → log-odds pool → extremize) turns arms into
weights; the numeric engine sizes. Receipts everywhere; a zero is red.

**Tech stack:** Python 3.11, pandas/pyarrow, LightGBM (`xs_ranker`), FastAPI,
pytest (`backend/tests/`, network-blocked, `AEGIS_PERSONAL_MODE=0`), DeepSeek
only, local Qwen3-30B-A3B via llama-server, OpenClaw gateway on 18789.

**Spec:** `docs/ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md` (the plan argues
from it). Evidence: `docs/research_notes/2026-09-25/*.md`.

## Global constraints (copied from CLAUDE.md and the roadmap)
- Suite: `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`; gate any push on `exit=0`, then `python -m scripts.ci_watch --wait`.
- Never `taskkill /IM`; never `git reset --hard` (`predictions.jsonl` is tracked and grows).
- Every new `backend/services/*.py` module gets a caller or a `signal_reachability` classification.
- New services exceptions enrol in `test_guard_missing_input_contract.CASES`.
- Parameters in `backend/config.py`; `np.random.default_rng`; type hints; no `fillna(0)` on feature matrices.
- `portfolio_farm.Policy` refuses zero costs; `learner/benchmark.py` is the only market leg.
- Dates in fixtures derive from `today`; never a literal calendar moment.
- A running sim session (`backend/data/optimus/sim/`) must not be written to.
- Before any sizing change print the worst case in dollars for the largest admissible book.

**Read before the first chunk (30 min):** `scripts/sim_run.py` (units, the
heartbeat, `u_learn` rota at ~570), `backend/services/xs_ranker.py:100-200`,
`backend/services/llm_portfolio.py` (all), `backend/services/pm_catalysts.py:170-200`,
`backend/services/forecast_grader.py`, `scripts/night_specialist_scoreboard.py`,
`backend/services/analyst_ledger.py`, `backend/services/investigator_triggers.py`,
`backend/services/openclaw_client.py`, `Aegis module/TRIALS/PREREG_ANALYST_SKILL_1.md`.

---

## Chunk C0 — receipts that can go red (half a day)

**Files:**
- Create: `backend/services/accrual_canary.py`
- Modify: `backend/services/health.py` (or wherever `ic_health` / `/api/health/full` composes its rows — find with `grep -n "funnel_staleness" backend/`)
- Modify: `scripts/sim_run.py` (session index on crash; OpenClaw spend row)
- Modify: `backend/services/openclaw_client.py` (`agent()` writes a telemetry row)
- Test: `backend/tests/test_accrual_canary.py`, `backend/tests/test_openclaw_telemetry.py`

**Interfaces:**
- Produces `accrual_canary.forecast_accrual(ledger_path: Path, *, today: date, window_days: int = 3) -> dict` with keys `status` (`"ok" | "DEGRADED" | "UNKNOWN"`), `rows_by_day: dict[str,int]`, `last_new_row_utc: str|None`, `reason: str`.
- Produces `accrual_canary.collector_liveness(db_path: Path, *, today: date) -> list[dict]` — one row per registered collector (`congress`, `ark`, `13f`, `insider_cmp`, `revisions`, `pead`, `quality`, `multifactor`, `smartgrowth`) with `n_rows_7d`, `last_row_date`, `status`.
- Produces `accrual_canary.stuck_counter(values: list[int], *, min_run: int = 5) -> bool` (true when the same integer repeats ≥ `min_run` times).

- [ ] **Step 1: failing test — zero new rows for three days is DEGRADED, an undateable ledger is UNKNOWN**

```python
# backend/tests/test_accrual_canary.py
import json
from datetime import date, timedelta
from backend.services import accrual_canary as ac

def _write(tmp_path, days_ago_list):
    p = tmp_path / "predictions.jsonl"
    today = date(2026, 9, 25)
    with p.open("w", encoding="utf-8") as f:
        for d in days_ago_list:
            made = (today - timedelta(days=d)).isoformat() + "T12:00:00Z"
            f.write(json.dumps({"made_at": made, "p": 0.5}) + "\n")
    return p, today

def test_three_quiet_days_is_degraded(tmp_path):
    p, today = _write(tmp_path, [10, 9, 8])
    r = ac.forecast_accrual(p, today=today, window_days=3)
    assert r["status"] == "DEGRADED"
    assert "0 new rows" in r["reason"]

def test_a_row_yesterday_is_ok(tmp_path):
    p, today = _write(tmp_path, [1])
    assert ac.forecast_accrual(p, today=today, window_days=3)["status"] == "ok"

def test_missing_made_at_is_unknown_not_ok(tmp_path):
    p = tmp_path / "predictions.jsonl"
    p.write_text(json.dumps({"p": 0.5}) + "\n", encoding="utf-8")
    assert ac.forecast_accrual(p, today=date(2026, 9, 25))["status"] == "UNKNOWN"

def test_stuck_counter():
    assert ac.stuck_counter([2, 2, 2, 2, 2, 2]) is True
    assert ac.stuck_counter([2, 3, 2, 2, 2]) is False
```

- [ ] **Step 2:** run `pytest backend/tests/test_accrual_canary.py -v` → FAIL (`No module named accrual_canary`).
- [ ] **Step 3:** implement `accrual_canary.py` (read the last N MB of the ledger, not the whole 25k rows on each health call; parse `made_at`; count by UTC day; UNKNOWN when no parseable stamp).
- [ ] **Step 4:** add the three rows to the health composer; make `test_health_full` assert the row *exists*, not that it is ok (protocol item 5).
- [ ] **Step 5:** `openclaw_client.agent()` appends `{provider:"deepseek", model:<from OpenClaw's config>, purpose:"openclaw:<quest>", cost_usd:None, cost_status:"UNPRICED_OPENCLAW", ...}` to the same `llm_calls_<month>.jsonl` `llm_telemetry` writes. Test: a fake subprocess result produces exactly one row with `purpose` starting `openclaw:`. An **empty quest log** must produce a row with `status:"EMPTY_LOG"` and the health row goes DEGRADED — the 09-24 `q2_power_bottleneck` case.
- [ ] **Step 6:** `sim_run`: write the session row at **start** (`state: STARTED`) and update at end; a crashed session is then visible as `STARTED` with no end stamp. Test by simulating a session that raises after cycle 1.
- [ ] **Step 7:** wire `stuck_counter` over the last six `decisions/*.json` `roi_ranking.n_considered` values into the decision contract's own `warnings`; also print the funnel's `n_candidates` beside it so the two counts sit on one line.
- [ ] **Step 8:** suite green → commit `C0: five receipts that can go red`.

**Acceptance:** `/api/health/full` shows `forecast_accrual: DEGRADED` **today**
(it is true today); OpenClaw quest → one telemetry row; the two crashed
sessions from 09-22/23 would have been visible.

---

## Chunk C1 — run ANALYST-SKILL-1 as registered (one day, WRDS on disk)

**Files:**
- Create: `scripts/analyst_skill_1.py`
- Create: `docs/ANALYST_SKILL_1_VERDICT_<date>.md`
- Test: `backend/tests/test_analyst_skill_1.py` (synthetic panel: a planted skilled broker must raise ΔIC; a null world must not)

**Interfaces:**
- Consumes the prereg's exact spec: `tr_ibes.ptgdetu` (nominal targets, `estimid` broker, `amaskcd` analyst, `anndats` PIT bound) from the WRDS parquet manifest (`docs/DATA_MANIFEST.md`), CRSP prices via the existing learner tape (`learner/benchmark.py` for the market leg).
- Produces `analyst_skill_1.run(*, train_months: int, eval_start: str) -> dict` with `delta_ic_mean`, `t_nw3`, `n_months`, `verdict` in `{"ADOPT","REJECT","POWER_FAILED"}`, and a **report-only** table `broker_skill.parquet` (`estimid`, n, hit rate vs SIC2, mean 63d excess, persistence half-to-half) plus the analyst-level (`amaskcd`) version.

- [ ] Step 1: read the prereg §2-§4 and copy its decision rule into the script docstring verbatim; run `python scripts/lint_prereg.py` in `Aegis module` to confirm the registration is intact.
- [ ] Step 2: failing tests on a synthetic panel (planted skill → ΔIC > 0, t ≥ 2 at n=60 months; null → |t| < 1).
- [ ] Step 3: implement; the POWER gate runs first as registered; if it fails no arm number is printed (ANALYST-IDENT-1 precedent).
- [ ] Step 4: run on the real panel; write the verdict doc with by-year ΔIC and the small/largemid split; add the trial to `NEGATIVE_RESULTS.md` if REJECT.
- [ ] Step 5: commit `C1: ANALYST-SKILL-1 ran — <verdict>`.

**Acceptance:** a verdict exists. ADOPT → the identity branch (Lane R actors) is
funded; REJECT → the analyst-identity idea in the external queue is a corpse
with a receipt and Bloomberg `ANR` export is a curiosity, not a plan.

---

## Chunk C2 — revision FLOW: feature, sweep, and a frozen book (two days)

**Files:**
- Modify: `backend/services/analyst_ledger.py` (add `revision_flow`)
- Create: `scripts/revision_flow_sweep.py`
- Create: `backend/data/optimus/first_books/contracts/revision_flow_v0.json` (via `llm_portfolio.freeze`)
- Test: `backend/tests/test_revision_flow.py`

**Interfaces:**
- Produces `analyst_ledger.revision_flow(revisions: pd.DataFrame, *, asof: pd.Timestamp, window_days: int = 90) -> pd.DataFrame` indexed by `ticker` with columns `net_raises` (raises − lowers), `n_firms` (distinct `firm` acting), `median_target_change` (median of `target_change / prior_target`), `days_since_last`, `n_events`. **Only rows with `event_date < asof`** (strict) and `pit_safe == True`.
- Produces `xs_ranker.walk_forward(..., extra_features: pd.DataFrame | None)` — the panel join is PIT by `(ticker, date)` using the last flow row strictly before each date.

- [ ] **Step 1: failing tests**

```python
# backend/tests/test_revision_flow.py
import pandas as pd
from backend.services.analyst_ledger import revision_flow

def _rev(rows):
    return pd.DataFrame(rows, columns=["ticker","event_date","firm","target_action","prior_target","current_target","target_change","pit_safe"])

def test_flow_is_strictly_before_asof():
    asof = pd.Timestamp("2026-09-24")
    df = _rev([
        ["AAA", pd.Timestamp("2026-09-24"), "F1", "raise", 10, 12, 2, True],   # same day: excluded
        ["AAA", pd.Timestamp("2026-09-20"), "F2", "raise", 10, 11, 1, True],
        ["AAA", pd.Timestamp("2026-09-01"), "F3", "lower", 10,  9, -1, True],
    ])
    out = revision_flow(df, asof=asof, window_days=90)
    assert out.loc["AAA", "net_raises"] == 0            # +1 raise, −1 lower
    assert out.loc["AAA", "n_firms"] == 2

def test_not_pit_safe_rows_are_refused_not_dropped_silently():
    df = _rev([["AAA", pd.Timestamp("2026-09-20"), "F1", "raise", 10, 11, 1, False]])
    import pytest
    with pytest.raises(ValueError, match="pit_safe"):
        revision_flow(df, asof=pd.Timestamp("2026-09-24"))

def test_window_excludes_old_events():
    df = _rev([["AAA", pd.Timestamp("2026-01-01"), "F1", "raise", 10, 11, 1, True]])
    out = revision_flow(df, asof=pd.Timestamp("2026-09-24"), window_days=90)
    assert "AAA" not in out.index
```

- [ ] Step 2: run → FAIL. Step 3: implement. Step 4: PASS. Step 5: commit `C2a: revision_flow, PIT-strict`.
- [ ] **Step 6: the sweep.** `scripts/revision_flow_sweep.py` runs `walk_forward` on the survivorship-free panel (`prices_2025_26/bars.parquet` ∪ delisted) **with and without** the flow columns; horizons 5/21/63; k ∈ {20, 50, 100}; prints — before any t — `by_year`, `leave_one_year_out`, `loo_worst_mean_net`, the **worst breadth cell**, and the **small vs largemid split** (ANALYST-IBES-1's UNRESOLVED cell). Blocking unit derived from the horizon (`feedback_a_t_whose_bias_depends_on_the_swept_parameter`). Receipt: `backend/data/optimus/analyst/revision_flow_sweep_<date>.json` with `n_date_blocks`.
- [ ] **Step 7: the book.** Regardless of the sweep sign, freeze `revision_flow_v0` as a `PRODUCT_EXPERIMENT` (top-20 by `net_raises × n_firms`, liquidity band ≥ the ranker's floor, equal weight, 21-day cadence) **and its twin** (same band, random names, same cadence, seeded `default_rng(20260925)`). It is graded nightly with the other first books. Do **not** put the flow in `FEATURES`.
- [ ] Step 8: commit `C2b: revision-flow sweep + revision_flow_v0 book frozen`.

**Acceptance:** a receipt with by-year and LOO tables; a frozen contract with a
twin; the sweep's honest sentence in `RESEARCH_QUEUE.md` Q-4 (RUNNING → result).

---

## Chunk C3 — the committee shortlist reaches `u_plan` (one day)

**Files:**
- Modify: `scripts/sim_run.py` `u_plan` (candidate source), `u_funnel`
- Modify: `backend/services/investment_committee.py` (a pure `shortlist(asof) -> list[str]` that `u_plan` can import without the router)
- Test: `backend/tests/test_u_plan_candidates.py`

**Interfaces:** `u_plan` takes `candidates = shortlist(asof) ∪ ranking.top_k` under the PROBE state (§16.2): PROBE positions are sized at the probe cap already in `pc_broker` mandate; `acting` for PROBE is **not** gated on `top20_net_rel_21d` (that gate measures the ranker, not the shortlist), it is gated on the shortlist's own forward grade once ≥ 21 days exist, until then it is `UNMEASURED_TRADE_SMALL`. Print the worst case: `n × probe_cap × stop_sigma` in dollars on the receipt.

- [ ] Step 1: failing test — with `ranking.top20_net_rel_21d = −0.2` and a non-empty shortlist, `u_plan` produces PROBE orders and zero EXPLOIT orders; with an empty shortlist it produces none and the receipt says `shortlist: 0` (red, not silent).
- [ ] Step 2-4: implement, pass, commit `C3: the shortlist is a candidate set, under PROBE`.

**Acceptance:** the next sim session's `decisions/*.json` shows `n_considered`
equal to the funnel's `n_candidates`, and PC-PAPER (if connected — Murat's
answer) holds probe-sized positions.

---

## Chunk R — the reputation layer (two days; pure arithmetic over the ledger)

**Files:**
- Create: `backend/services/forecast_reputation.py`
- Modify: `scripts/sim_run.py` `u_grade` (call `refit` after grading; write `reputation_<date>.json`)
- Modify: `scripts/night_specialist_scoreboard.py` (read the weights; print `new_rows_since_last_run`)
- Test: `backend/tests/test_forecast_reputation.py`

**Interfaces:**
- `forecast_reputation.arm_skill(graded: pd.DataFrame, *, arm_col="arm", p_col="p", y_col="y", split="date_half") -> pd.DataFrame` with `n`, `brier`, `clim`, `skill`, `disc` (discrimination), computed **on the held-out half by date**.
- `forecast_reputation.weights(skill: pd.DataFrame, *, k_prior: float, gamma: float, floor: float = 0.0) -> pd.Series`: `s_shr = n/(n+k) * skill`, `w = clip(s_shr, floor, 1) ** gamma`, normalised.
- `forecast_reputation.pool(ps: dict[str,float], w: pd.Series, *, kappa: float) -> float`: `sigmoid(kappa * Σ w_i logit(p_i))`.
- `forecast_reputation.calibration_curve(graded, *, arm_prefix="investigator:", horizon: int) -> pd.DataFrame`: decile of p → realised base rate and realised 1-day relative return, **by year**.

- [ ] **Step 1: failing tests**

```python
# backend/tests/test_forecast_reputation.py
import numpy as np, pandas as pd
from backend.services import forecast_reputation as fr

def test_negative_skill_arm_gets_zero_weight():
    skill = pd.DataFrame({"n":[2000, 5000], "skill":[0.05, -0.28]}, index=["investigator:a","persona:x"])
    w = fr.weights(skill, k_prior=500, gamma=2.0, floor=0.0)
    assert w["persona:x"] == 0.0
    assert abs(w.sum() - 1.0) < 1e-9

def test_shrink_by_n_moves_small_samples_toward_zero():
    skill = pd.DataFrame({"n":[10, 10000], "skill":[0.10, 0.10]}, index=["small","big"])
    w = fr.weights(skill, k_prior=500, gamma=1.0)
    assert w["big"] > w["small"]

def test_pool_is_log_odds_and_extremized():
    w = pd.Series({"a":0.5, "b":0.5})
    p = fr.pool({"a":0.6, "b":0.6}, w, kappa=1.0)
    assert abs(p - 0.6) < 1e-9
    assert fr.pool({"a":0.6, "b":0.6}, w, kappa=2.0) > 0.6

def test_arm_skill_is_held_out_by_date():
    rng = np.random.default_rng(0)
    n = 4000
    y = rng.integers(0, 2, n)
    df = pd.DataFrame({"arm":"good", "p": np.clip(0.5 + 0.3*(y-0.5) + rng.normal(0,0.1,n), 0.01, 0.99),
                       "y": y, "resolved_at": pd.date_range("2026-01-01", periods=n, freq="h")})
    out = fr.arm_skill(df)
    assert out.loc["good","skill"] > 0
    assert out.loc["good","n"] < n           # the test half only
```

- [ ] Step 2-4: implement; tune `k_prior`, `gamma`, `kappa` by leave-one-quarter-out on the real ledger and **write the tuned values to the receipt**, not to config, until two refits agree.
- [ ] Step 5: `calibration_curve` on `investigator:*` at h=1 and h=5, by year → `backend/data/optimus/reputation/calibration_<date>.json`. This is the object §61 said was missing before a probability may be sized.
- [ ] Step 6: **Profit-Mirage check**: rerun `arm_skill` restricted to `made_at ≥ 2026-08-11` rows whose ticker-date pairs post-date the DeepSeek model's stated cutoff; print both numbers side by side. If the restricted skill is ≤ 0, say so in the roadmap's scoreboard.
- [ ] Step 7: commit `R: reputation weights with a negative-skill floor; investigator calibration curve`.

**Acceptance:** `reputation_<date>.json` names every arm with `n`, `skill`,
`weight`; personas carry `0.0`; the calibration table exists by year.

---

## Chunk H — the human + AI book, frozen with twins (half a day, after Murat's edit)

**Files:**
- Input: `docs/research_notes/2026-09-25/book_human_ai_thematic_v0.draft.json` (AI draft) → Murat's edited copy `book_human_ai_thematic_v0.json`
- Modify: `backend/services/llm_portfolio.py` (`build_briefing` gains `revision_flow` columns from C2 and a `catalysts` field from the YAML; twins helper)
- Create: `backend/data/optimus/pm_catalysts/catalysts_2026-Q4.yaml` (the 11 primary-verified PDUFA dates + confirmed earnings dates, each with its source URL, `verified_from: primary`)
- Test: `backend/tests/test_llm_portfolio_twins.py`

**Interfaces:** `llm_portfolio.twins(book: dict, *, asof, seed: int) -> dict[str, dict]` returns `{"ew": ..., "sector_etf": ..., "ai_only": ..., "spy": ...}`; each is a book in the same schema, frozen with the parent's hash inside. Sector-ETF map lives in `backend/config.py` (`THEME_ETF_MAP`: semis→SMH, power/grid→GRID or XLI, lithium→LIT, quantum→QTUM, nuclear→URA, biotech→XBI, gambling→BETZ, robotics→BOTZ, policy→SPY).

- [ ] Step 1: failing test — twins sum to 1.0, carry `parent_hash`, `ai_only` equals the draft's positions exactly, `ew` has equal weights over the same non-cash names.
- [ ] Step 2: implement; extend the briefing; **refuse to freeze if `asof` is not today or if any ticker is not in the price panel** (a book on a name nobody prices cannot be graded — the 2,911 stranded rows).
- [ ] Step 3: `python -m scripts.llm_portfolio freeze book_human_ai_thematic_v0.json --twins` → five contracts; `grade` runs nightly under `u_grade` (or a new `u_books` unit that beats the heartbeat).
- [ ] Step 4: commit `H: human+AI thematic v0 frozen with four twins; Q4 catalyst calendar`.

**Acceptance:** five hashes in `first_books/contracts/`; the first `grade`
receipt prints NAV vs SPY vs `ew` vs `sector_etf` vs `ai_only` at 1d.

---

## Chunk W — OpenClaw as a triggered investigator that ends in a forecast (two days)

**Files:**
- Modify: `backend/services/investigator_triggers.py` (five triggers, each a pure function over the day's data returning `list[Trigger]`)
- Modify: `backend/services/investigator_night.py` (a quest per trigger; the ten questions; JSON → `web_events`; then `scripts/night_investigator_forecast.py`'s process on the packet → forecast rows at h=1 and h=5)
- Modify: `backend/services/openclaw_client.py` (`quest()` returns `EMPTY_LOG` as a failure)
- Modify: `scripts/sim_run.py` (`u_learn` rota gains `investigate`: `("investigate", "survivorship_audit", "breadth_check")`; `idle` goes)
- Test: `backend/tests/test_investigator_triggers.py`, `backend/tests/test_quest_ends_in_forecast.py`

**Interfaces:** `Trigger(kind: Literal["shortlist_entry","rank_jump","revision_cluster","filing_or_earnings","unexplained_move"], ticker: str, asof: date, evidence: dict)`. `revision_cluster` fires when `revision_flow.n_firms ≥ 3` within 10 days. `unexplained_move` fires on |1d return| > 2σ_63 with no typed event in `event_store` for that ticker-date. Each quest's JSON has the ten fixed keys and a `falsifier` string; the packet plus JSON goes to the investigator process which returns `p_up_1d`, `p_up_5d`, `confidence`, `facts_used`. DeepSeek and local Qwen both answer; both rows are frozen with `model`, `cost_usd`, `latency_s`.

- [ ] Step 1: failing tests — a synthetic day with 3 firms raising AAA in 5 days yields one `revision_cluster` trigger; a 3σ move with no event yields `unexplained_move`; a quest whose log is empty raises `QuestEmpty` and writes a refusal row (not a forecast).
- [ ] Step 2-4: implement, pass; cap quests per night in `config.py` (`INVESTIGATOR_MAX_QUESTS_PER_NIGHT = 12`) and dollars (`INVESTIGATOR_NIGHT_CAP_USD = 3.0`, read from the **same ledger the writer writes** — `feedback_a_cap_that_reads_a_different_ledger`).
- [ ] Step 5: Q-3 executed here: the nine thematic persona arms are removed from the cadence job (a spending decision); the receipt lists them as `RETIRED_WEIGHT_ZERO`.
- [ ] Step 6: commit `W: triggered investigator; every quest ends in a forecast or a refusal; personas retired`.

**Acceptance:** the accrual canary from C0 goes back to `ok` the first night
this runs; `reputation_<date>.json` shows `investigator:evidence_v2` `n`
growing nightly; DeepSeek vs local rows exist in pairs.

---

## Chunk K — the challenge (must be done by Oct 9)

**Files:**
- Create: `backend/data/optimus/competition/wls_members_2026-10.yaml` (Murat exports the WLS constituent list or checks candidates one by one on the Terminal; the file records `checked_on`, `source`)
- Create: `backend/services/competition_book.py` — the contract: `validate(book) -> list[str]` refuses shorts, weight > 0.20, non-WLS names, cash > 0 after Oct 16, ETFs.
- Create: five books via `llm_portfolio.freeze` with `objective: "Relative P&L vs WLS, Oct 12–Nov 13 2026"`: `event_earnings`, `analyst_revision` (C2), `product_bottleneck` (Q-5's triangulation as a filter), `llm_investigator` (Lane W names with p_up_5d in the top decile), `ensemble` (Lane R weights over the four).
- Test: `backend/tests/test_competition_book.py`

- [ ] Step 1: failing tests — a 25% weight is refused; a non-WLS ticker is refused; a book that is 30% cash on Oct 17 is refused; a valid book passes.
- [ ] Step 2-3: implement; freeze on Oct 9 with the objective Murat chose (`top_quartile` → 15-25 names, catalyst-diversified; `grand_prize` → 5-8 names, variance on purpose, still ≤ 20%).
- [ ] Step 4: daily grade against the WLS proxy (URTH is not WLS — record the proxy and its tracking error as a caveat; the real number comes from the portal).
- [ ] Step 5: commit `K: competition contract + five frozen books`.

---

## Chunk D — data feeds (only after a consumer exists)

House Clerk PTR bulk ZIP → `congress_trades` (and find why the local collector
writes zero rows); Polymarket Gamma → `prediction_markets` (probabilities for
the PDUFA tickers, joined to the catalyst YAML); Federal Register API + DOE /
USTR RSS → `policy_events` typed feed (`event_vocabulary` ids); openFDA with a
key; evaluate `austin-starks/sec-ownership-disclosures` for the PIT column and
the grant/open-market split against our own insider collector. Each with a
liveness row in C0's `collector_liveness`.

---

## Self-review (done 2026-09-25)
- Spec coverage: roadmap lanes C/R/H/W/K/D → chunks C0-C3, R, H, W, K, D. Q-3 lives in W step 5. The Profit-Mirage check lives in R step 6. Murat's five decisions are inputs to C3 (PC-PAPER), H (the edit), K (objective, registration, WLS list).
- Placeholders: none; every chunk names files, interfaces and a first test.
- Type consistency: `revision_flow` returns a DataFrame indexed by ticker (C2) and W's `revision_cluster` reads its `n_firms`; `weights` returns a Series (R) and K's `ensemble` consumes it; `Trigger.kind` literals match between W's tests and implementation.
