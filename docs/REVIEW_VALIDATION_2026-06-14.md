# External Review Validation — Real vs. Noise Ledger

> **Date:** 2026-06-14 · **Author:** Claude Code session (Opus 4.8)
> **Inputs:** four external AI reviews of the public repo — two Claude passes,
> one GPT, one DeepSeek (raw text in `Downloads/REVIEWS.txt` +
> `Downloads/claude feed back with tasks.txt`).
> **Method:** every concrete claim was checked against the *actual code* (Explore
> agents + git queries + file reads) before being accepted. The reviewers saw the
> public GitHub snapshot without this repo's two weeks of context, so many of
> their "missing" items are already built and labelled. Strategic advice is mostly
> generic pattern-matching to "solo quant repo" — filtered hard.

This file is the permanent record of **what was real, what was stale, what was
noise.** The action items it generates live in [`BACKLOG.md`](./BACKLOG.md).

---

## TL;DR verdict

| Reviewer | Signal | One-line |
|---|---|---|
| **Claude (pass 1 + 2)** | **Highest** | Cloned and read real code; findings concrete and mostly verifiable. The alert-engine + "paper lanes trade your alerts" architecture (pass 2) is genuinely good and is now logged as vision items. |
| **GPT** | Low-medium | Technically literate, strategically wrong for the goal (this is an OSS/personal tool, not a startup). "Amputate 70%" rejected — correctly. Three salvageable UX/quant points kept. |
| **DeepSeek** | Lowest | Graded a personal/read-only OSS tool as a multi-tenant production SaaS. Most of it (OAuth2, auth, rate-limiting-as-D, query-injection) is inapplicable FUD. Two cheap real wins (dep pinning + the pickle-as-reproducibility-landmine reframe). Asserted version-specific CVEs **without checking our lockfile** — verified independently below. |

**The single cross-review point that is settled fact: data is too thin (2 primary
sources).** Everyone flagged it; we agree. It is the backbone of the V3 data-layer
work ([`V3_DATA_LAYER_DESIGN.md`](./V3_DATA_LAYER_DESIGN.md)).

---

## A. REAL — verified against code, worth fixing (cheap, no track-record risk)

| # | Claim | Verdict | Evidence | Action |
|---|---|---|---|---|
| A1 | `lab/` scratch JSON committed, not gitignored | **REAL (size overstated)** | `git ls-files lab` = **2,587 files / 7.7 MB** (reviewer said ~2,243 / 16 MB). No `lab/` rule in `.gitignore`. | [H1] gitignore added; untrack command documented. |
| A2 | `docs/v2 session transcript` (space in name, no ext, raw chat log) committed | **REAL** | tracked; begins "# Aegis Finance — V2 Planning Session Transcript". | [H1] gitignore added; untrack command documented. |
| A3 | Deps unpinned (`>=`) | **REAL** | every line in `backend/requirements.txt` uses `>=`; `engine/requirements.txt` inherits via `-r`. | [H2] security floor bumped + `pip-audit` in CI; full lockfile logged. |
| A4 | No CI | **REAL** | no `.github/workflows/` existed. | [H3] `ci.yml` added (pytest offline + ruff + pip-audit + next build). |
| A5 | `CLAUDE.md` counts stale | **REAL** | claimed 13 routers / 44 services / 1177+ tests; actual **19 / 104 / ~2,467 fast**. | [H4] CLAUDE.md updated. |
| A6 | Backtest underperformance buried | **REAL — numbers exact** | `backend/BACKTEST_RESULTS.md`: strategy **+250.9%** vs B&H **+740.0%**, Sharpe **0.675** vs **0.921**, sell hit-rate **28.6%** vs 55% target. Not surfaced in README/UI; no `NEGATIVE_RESULTS.md`. | [M1] `NEGATIVE_RESULTS.md` written, framed per `TRACK_RECORD_POLICY` + canon A5. |
| A7 | Crash Brier 0.046 = single-path walk-forward, ~4–7 events, no CI | **REAL** | `engine/validation/walk_forward.py` is expanding-window single-path; CPCV exists (`purged_cv.py`) but is **not** producing the headline; no bootstrap CI / event-count attached in README. | [M2] logged: attach bootstrap CI + positive-event count, or route through CPCV. |
| A8 | Model reproducibility loose | **REAL** | `crash_model.py` uses `joblib.load`; saved state has `feature_names` but **no** train-date / sklearn-version / feature-hash / checksum. `BACKTEST_RESULTS.md:85` — trained 1.4.0, served 1.8.0, "should retrain". | [M3] logged: metadata sidecar + retrain on pinned sklearn (low urgency — model is `model_not_deployed` in prod). |
| A9 | 479 broad `except Exception` | **REAL (count 469)** | 469 across 104 files; **0 bare `except:`**. Sample: ~85% log-and-degrade, ~15% silent-swallow (e.g. `cache.py`, `db.py`). | [M4] logged: targeted audit of the swallowers, not a blanket rewrite. |
| A10 | `CAPABILITY_MATRIX.md` missing (V2 Goal 3) | **REAL** | file does not exist; planned in `V2_ROADMAP §4c` and `V3_SCOPE §(c)`. | [M5] first-pass [`CAPABILITY_MATRIX.md`](./CAPABILITY_MATRIX.md) created. |

## B. CVE claims (DeepSeek) — verified independently, do not trust the numbers

| CVE | Claim | Verdict | Reality |
|---|---|---|---|
| **LightGBM CVE-2024-43598** | RCE, fix in 4.6.0 | **REAL CVE, surface NOT exercised** | Heap overflow in **distributed-training socket init** (`linkers_socket.cpp`). Aegis trains single-node — surface never touched. Floor bumped to `>=4.6.0` anyway (free). [Snyk](https://security.snyk.io/vuln/SNYK-PYTHON-LIGHTGBM-8516056) |
| **Starlette ReDoS CVE-2025-62727** | DoS via Host header | **REAL CVE, low relevance** | ReDoS on a read-only personal deploy is a self-DoS at worst. `pip-audit` in CI will pin the real fixed version; not worth asserting a number by hand. |
| **pandas `query()` injection** | command injection | **FUD here** | We never pass untrusted strings to `df.query`. No exercised surface. |
| **joblib/pickle RCE** | unsafe deserialization | **Reframe, not RCE** | We load *our own* gitignored model, not stranger-supplied pickles. The real issue is the **reproducibility landmine** (A8), not RCE. |

**Lesson logged:** DeepSeek stated version-specific CVEs without checking our
resolved deps. Treat any AI-asserted CVE as a lead to verify, never a fact. CI
`pip-audit` is the durable answer — it reads the *actual* installed versions.

## C. STALE — reviewers were behind the real code (do NOT re-recommend)

| Reviewer claim | Reality (already built) |
|---|---|
| "No validation discipline / add overfitting checks" | `engine/validation/overfitting.py`: PSR/DSR (Bailey–LdP), PBO via CSCV, Harvey–Liu t≥3.0, effective-N participation ratio — **wired into the adoption gate**, candidate that *passes* triggers human review, not auto-adopt. |
| "Crash model should be the killer feature / time the crash" | Verified research (`DEEP_RESEARCH_2026-06-14_DECISION.md` §1) found short-horizon crash **timing ≈ 0 IC**; LPPLS predictive skill refuted twice. Canon A5 reframed the thesis to **measure fragility, scale exposure** — not time the crash. |
| "Where are institutional flows / options / sentiment" (data-starved) | Partially built: `options_intelligence.py`, `insider_trading.py` (Finnhub + Form 4), fragility composite already ingests turbulence/absorption/net-liquidity/OAS. The *gap* is breadth + a point-in-time store, not absence. |
| "Add a forward track record" | Live forward NAV since **2026-06-08**, 4 lanes, `TRACK_RECORD_POLICY.md`, 24-month skill-claim embargo, pre-registered trials (HRP-vs-EW, LPPLS, CRASH). |
| "LLM could manage money" | A2 LLM-conviction lane is **forward-only by firewall**; the "profit mirage" research (arXiv 2510.07920, 2512.23847) quantifies why backtested LLM returns are hindsight-contaminated (~37% inflation, OOS p=0.033). |

## D. NOISE — considered and rejected (so it is never re-litigated)

- **"Amputate 60–70%, become a crash-prediction startup" (GPT, Claude pass 1).**
  Rejected. This is an OSS + personal investing tool; breadth is the surface area
  that makes it useful, and the moat is the forward track record + private brain +
  experiment registry, not a single feature. Claude *retracted* this in pass 2.
- **OAuth2 / authentication / "no auth = grade D" (DeepSeek).** Inapplicable — no
  untrusted users, no real money through endpoints. For a public read-only deploy
  the only real concern is protecting *our own free API quotas* (a ~20-line
  `slowapi` limit) — logged as a minor, not a security gate.
- **Rate-limiting as critical, "production-readiness F" (DeepSeek).** The tool
  does not claim to be multi-tenant production SaaS.
- **pandas `query()` injection / "no input validation" (DeepSeek).** FastAPI +
  Pydantic already validate typed bodies (`schemas/`); we don't feed untrusted
  strings to `query()`.

## E. STRATEGIC — kept as direction (folded into BACKLOG vision section)

- **Claude pass 2: "the paper lanes trade your alerts → the lane NAV becomes the
  live proof that acting on Aegis beats ignoring it."** Genuinely good; maps onto
  the existing lanes + comparator. Logged as [V4] event-driven lane + [V3] alert
  engine. This is the entrepreneurial resolution to A6 (the backtest can't prove
  edge; a forward alert-driven lane can).
- **GPT: "make the simulation a *decision* engine, not a path-printer" and "lead
  with the answer, not 50 charts."** Valid V3 UX framing. Logged [V6].
- **GPT: "HRP + regime is more honest than Black-Litterman for retail because
  garbage expected returns make BL elegant-but-wrong."** Legit quant point; revisit
  when the optimizer is touched. Logged [V7]. (Note: TRIAL-001 is already testing
  HRP forward.)
- **Claude pass 2: persist the real portfolio server-side (it's localStorage
  today) + a point-in-time store as the linchpin.** Logged [V2]/[V3] — this is the
  V2 Goal 8 mirror lane + the V3 as-of data layer.
