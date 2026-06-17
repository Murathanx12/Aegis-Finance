# TRIAL-INSIDER-IC — Opportunistic open-market insider buying (forward IC)

> **Pre-registered 2026-06-16, BEFORE any forward data is collected.** This is the
> honest form of roadmap item 3 (insider signal). T7 proved no backtest on our
> survivor-only data can certify selection alpha, so this signal is validated
> **forward only**: snapshot it point-in-time from today, then measure its forward
> information coefficient. Registering the hypothesis + estimator + decision rule
> in advance is the anti-p-hacking guard.

## Hypothesis

Cross-sectionally, stocks with **more distinct insiders making open-market
purchases** (SEC Form 4 code `P`) in the trailing window earn higher forward
returns than stocks with none. Evidence base: Lakonishok-Lee (2001), Jeng-Metrick-
Zeckhauser (2003), Cohen-Malloy-Pomorski (2012, opportunistic-vs-routine). The
mechanism: insiders sell for many reasons but **buy on the open market for one** —
they think the stock is cheap; clusters of distinct buyers are the strongest form.

## Signal definition (frozen)

`compute_opportunistic_buy_score` (`backend/services/insider_trading.py`):

    score = n_distinct_open_market_buyers + tanh(buy_value / $1M)

- **Open-market purchases only** (code `P`). Awards (`A`), option exercises (`M`),
  gifts (`G`), tax withholding (`F`) and all sales are excluded — routine, no view.
- Distinct-buyer count is the cluster signal; `tanh(value/$1M)` is a saturating
  dollar-conviction bonus (so one whale can't dominate a cross-sectional rank).
- Selling is deliberately ignored (noisy: diversification/estate/10b5-1).
- **Cluster** flag = ≥3 distinct buyers.

## Data source (the honest finding)

Two sources were probed and **rejected** before settling on raw Form 4:

| Source | Verdict | Why |
|---|---|---|
| **Finnhub free tier** | ❌ unusable | Returns `transactionCode: ""` and `transactionPrice: 0` (derivative grants). The code + price that *define* the signal are absent. |
| **edgartools** | ❌ unusable in prod | Parses Form 4 correctly but **hung ~50 min on ~24 filings** in testing — cannot live in a scheduled collector. |
| **Raw SEC Form 4 XML** | ✅ adopted | `backend/services/insider_form4.py` — stdlib XML + `requests` with hard 10s per-request timeouts. End-to-end ~1.8s/filing, hang-proof. Has code `P` + price + reporting owner. |

v1 limitation (documented, not hidden): true routine-vs-opportunistic
classification (Cohen-Malloy-Pomorski) needs per-insider multi-year trade history
we don't store; the **`P`-code-only filter is the opportunistic proxy**. Refining
to per-insider routine detection is a future upgrade.

## Estimator (frozen, pre-registered)

Forward **rank information coefficient** = Spearman correlation between the
cross-sectional `opp_score` at snapshot date *t* and the forward total return over
the next **21 / 63 / 126 trading days** (≈1/3/6 months). Reported with a
block-bootstrap CI and the cross-section size *N* each period. The signal is
sparse (open-market buys are rare), so IC is computed only on periods with ≥ a
minimum number of non-zero names (recorded, not silently dropped).

## Decision rule

- **Descriptive until proven.** The score never arms a lane, never sizes a
  position, never enters `paper_nav`. (Same envelope as the LPPLS/fragility flags.)
- Adoption is considered **only after ≥ a forward window of accrual** and **only**
  if the forward IC is positive with a CI excluding 0 across horizons, *then* run
  through `evaluate_candidate` (DSR/effective-N) and recorded in the registry. No
  forward signal, no claim. (No profit-mirage risk: the signal is collected
  forward, never backfilled.)

## Forward-collection plan (wires at seed time, attended)

The signal + source ship now as a tested descriptive utility (NOT yet scheduled).
The forward clock starts when the collector is wired — ideally alongside the book-
lane seed, so the insider IC and the lane NAV accrue against the same calendar.

- **Universe:** the 12-name book ∪ a capped small/mid-cap watchlist (where insider
  buys are strongest), NOT the full 190-name universe (≈1.8s/filing makes that too
  slow synchronously).
- **Cadence:** weekly (insider holdings change slowly), throttled + idempotent.
- **Store:** `pit_observations`, key `insider_opp:{ticker}`, `as_of`=snapshot date,
  `observed_at`=now — leak-safe by construction (`snapshot()` no-ops on unchanged).
- **Wiring:** a `collect_insider_opp_scores` step in the PI scheduler, wrapped like
  the existing descriptive evals so a failure can't break lane processing.

## Status

- ✅ Signal (`compute_opportunistic_buy_score`) + data source (`insider_form4.py`)
  built and unit-tested offline (`test_insider_form4.py`, 12 tests).
- ✅ **Forward collector WIRED 2026-06-16** (`insider_collector.py` →
  `scheduler._daily_check`). Snapshots `insider_opp:{ticker}` for the 12 book names
  into the PIT store, weekly-throttled, descriptive, wrapped. **The forward IC clock
  starts on the next deploy's daily check.** Tests: `test_insider_collector.py`
  (6) — PIT write, UTC leak-safe stamp, idempotence, throttle, per-ticker failure
  isolation. (UTC stamp matters: a local HK-time stamp would sit past the UTC read
  cutoff and be invisible — caught by `test_value_lands_in_pit_store_leak_safe`.)
- ✅ **PROD-403 BUG CAUGHT + FIXED 2026-06-17.** Live check found the collector
  failing **100% of SEC fetches in prod** (50 warnings, all 403 on
  `www.sec.gov/Archives/`) — the exact silent-fragility pattern this project hunts:
  green offline tests, dead in prod. Root cause: `insider_form4` made **raw,
  unpaced** `requests.get` calls, bypassing the process-wide SEC rate limiter that
  `edgar_events` already enforces ("ALL EDGAR HTTP must go through it"). A collector
  run fires ~360–1000 fetches at `www.sec.gov`; on Railway's fast egress that trips
  SEC's 10 req/s threshold instantly → 403 (SEC returns 403, not 429). Local dev's
  few calls never tripped it, so it passed there. Fix: every SEC call now routes
  through one `_sec_get` choke-point — shared `_RATE_LIMITER` pacing (≤8/s), a
  declared UA (env-overridable via `SEC_USER_AGENT`), and one 403-retry with
  backoff. Verified live end-to-end (AAPL fetch: paced, no 403, no hang). The
  asymmetry that pinpointed it: prod warned only on the high-volume Archives host,
  never on the low-volume `data.sec.gov` submissions call — same UA, different
  request count. Logged in `NEGATIVE_RESULTS.md` §5.
- ⬜ IC accrual + measurement — runs forward; compute rank-IC @ 21/63/126d once a
  forward window exists. v1 cross-section = 12 names (small-N, reported not hidden);
  widening to a small-cap watchlist is the next step.
