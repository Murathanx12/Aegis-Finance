# Tonight's runbook — the PC as a live market node

**Licence: `PRODUCT_EXPERIMENT`.** Paper only. No significance gate, no
pre-registration, no 24-month floor. What does not relax: PIT discipline, no
target leakage, costs never omitted, a frozen policy version once it trades.

---

## RESULTS SCOREBOARD (2026-09-22, before tonight)

| line | state |
|---|---|
| best historical net strategy vs market | **none validated** — see §3 |
| best forward paper strategy | fleet $543,738 of $600,000, **−9.4%**, all six books down |
| independent selector count | 1 (the stale funnel) → the ranker is the second |
| new actionable finding | **the decision funnel is a static file dated 2026-08-11**; and **fundamentals carry 39 bps/month gross where price/volume carries ~0** (GO on the FMP vintage) |
| external execution drag | not yet measured — no PC fills exist |
| LLM spend this session | **$0.00** |

**RESULT IMPROVEMENT: NONE YET.** Nothing has moved capital. What changed is
that the machine can now *see* 2,861 names instead of 40, hold a book, and tell
the truth about its own NAV.

---

## 1. What was wrong, measured

| # | finding | evidence |
|---|---|---|
| 1 | decision funnel frozen 42 days | `funnel_generated_at: 2026-08-11T02:33:48Z`, 40 candidates |
| 2 | ROI ranker saw two names | today's contract: `n_considered: 2, n_scored: 0` |
| 3 | 1.27M fresh bars unread | `prices_2025_26/bars.parquet`, 3,060 × 430, to 09-21 |
| 4 | no live market process existed | `night_run_until` = phase1 → grade → queue → STOP |
| 5 | 3 of 4 broker credentials dead | 401 on `ALPACA_API_*`, `ALPACA_ARENA_*`, `ALPACA_LANE_D_*` |
| 6 | the bars panel is survivor-selected | **0 of 3,060** symbols stop trading early |
| 7 | hack6 is levered | cash **−$5,388** on a paper account |

Murat's complaint — *"it is not taking risks, it is limiting itself"* — has a
cause that is not cowardice. `RESEARCH_CLAIM` gates (significance, MDE,
multiplicity) had drifted onto decisions that only ever spend PAPER money.
CLAUDE.md already says they must not. That is fixed by licence, in
`live_market_loop._ranking_verdict`, which refuses **exactly one** thing:
knowingly buying a **measured negative**. "Nobody has measured this" now sizes a
position down instead of vetoing it.

## 2. What was built

| module | job |
|---|---|
| `backend/services/xs_ranker.py` | cross-sectional 21-session ranker over the whole liquid universe; purged walk-forward; decile → **realised OOS** return calibration |
| `backend/services/pc_broker.py` | the PC's own paper account: execution lease, broker-truth NAV, hard mandate limits |
| `scripts/live_market_loop.py` | the missing process — runs the US session on the venue clock, holds the book, never exits because a queue drained |
| `scripts/night_rank_bakeoff.py` | champion/challenger: composite / prior-composite / lgbm_full / lgbm_small, with a breadth sweep k=10..500 |
| `scripts/night_fundamental_amplitude.py` | the GO/NO-GO on the next input class, answered offline before the data work is funded |
| `scripts/pull_deep_bars.py` | 2016→now history (12-1 momentum costs a year per name) |
| `scripts/pull_delisted_bars.py` | the **1,784 dead** names the survivor panel could never show (1,574 stop trading before the end) |
| `backend/tests/test_pc_live_stack.py` | 29 tests pinning the properties that cost money |
| `backend/services/policy_state.py` | what the night may change about ITSELF: declared preferences, never code, never a risk limit |

`night_run_until.py` changes:
* `--live` / `--live-mode` start the market loop **first**; it outlives every queue.
* **`GRADE_LEAD_MIN = 60`** — reality grading runs at T−60, before anything is
  killed. On 09-22 the 06:30 pass was still inside a 160-minute analyst snapshot
  when the kill came at T−5, so the night produced a contract and no scoreboard.
* `NIGHT_STOPPED.json` is written **before** the morning report and rewritten
  after, fixing the report that had to describe a stop that had not happened.

## 3. The ranking — measured, and the answer is no (for now)

Four runs, each changing one variable. The numbers are net relative return per
21 sessions, out of sample, purged, costed.

| run | panel | blocks | best net | best gross |
|---|---|---:|---:|---:|
| 1. first fit | 2025-26 survivors | 14 | −4.30% | −4.12% |
| 2. bake-off | 2025-26 survivors | 14 | **+3.13%** | +3.47% |
| 3. deep | **2016-26** survivors | **122** | −0.12% | +0.04% |
| 4. **survivorship-free** | 2016-26 **+ 1,784 dead names** | 122 | **−0.06%** | **+0.28%** |
| 5. liquid only | ≥$50M ADV, 1,870 names | 122 | −0.02% | +0.09% |

Run 2's **+3.13% at t +3.59 did not survive run 3**, and nothing about
survivorship or costs changed between them — only the amount of history. Seven
effective month-blocks cannot support a t of +3.6.

**The real finding is sharper than "it does not work":**

* **The signal is real.** `lgbm_full` carries IC **+0.0227 at t +7.56** over 122
  blocks. `composite_prior` is **gross positive at every book size from k=10 to
  k=500** (+0.20% to +0.28%).
* **It cannot pay its own toll.** That +0.28% is earned in small, illiquid names
  whose round trip costs ~**35 bps**. The edge is 28 bps; the toll is 35.
* **It cannot be bought cheaply.** Raising the liquidity floor to $50M ADV
  collapses `composite_prior` from gross **+0.28% to −0.18%**. The edge *is* the
  illiquidity — the premium is compensation for it, and it goes back out in
  spread. Restricting the universe to cut costs deletes the thing being bought.
* **Momentum is independently dead** (every momentum feature t ∈ [−0.18, +0.30]),
  reproducing `opportunity_funnel`'s standing `momentum_12_1: CLOSED` verdict
  from a separate implementation over a different panel.

Full write-up and scope: `NEGATIVE_RESULTS.md` §59.

### So tonight the loop OBSERVES, and that is not the old failure

This must not be read as the behaviour Murat complained about. The distinction
is in `live_market_loop._ranking_verdict` and it is the whole point:

> *"Lack of statistical significance is NOT sufficient reason to refuse a PAPER
> decision. Uncertainty changes position size."*

The loop refuses **exactly one** thing: knowingly buying a **measured negative**.
This is not `p > 0.05`; it is a top-20 book that **lost money net over 122
month-blocks and 3,578 names**. `UNMEASURED_TRADE_SMALL` — "nobody has measured
this" — still trades, sized down. Had the ranking come back merely uncertain, the
book would go on tonight.

### What would change the answer — MEASURED, not guessed

The obvious next move was "try fundamentals", but building a current fundamental
vintage is days of data work. So it was tested first on data already on disk.

`scripts/night_fundamental_amplitude.py` runs the same purged walk-forward over
`aegis_panel_v2.parquet` (JKP factors, 480,395 rows, **240 months 2005-01..2024-12**,
US common, mega/large/small only), at a 1-month horizon, comparing three feature
sets on **the same panel** so the comparison is like-for-like:

| feature set | n | IC | IC t | k=20 | k=50 | k=100 |
|---|---:|---:|---:|---:|---:|---:|
| price | 15 | +0.0372 | +4.60 | −19.7 | −0.8 | +13.8 |
| **fundamental** | 25 | +0.0295 | +3.99 | **+38.8** | **+39.5** | **+38.4** |
| both | 40 | +0.0402 | +4.80 | +13.8 | +7.3 | +19.9 |

*(gross spread, basis points per month, top-k vs the month's cross-section,
131 out-of-sample months)*

**VERDICT: GO on the data work.** Three things in that table:

1. **Fundamentals hold 38.4–39.5 bps at every book size** — roughly double the
   20 bps cost floor, and ~3x the amplitude price/volume could muster. The
   *stability* is the tell: a real effect barely moves with k, while price
   swings −19.7 → +13.8, which is what noise looks like.
2. **Adding price features DILUTES it** (39 → 7–20 bps). Same lesson as §59's
   `lgbm_full` losing to `lgbm_small`. Ship the smaller feature set.
3. **The highest IC is the worst portfolio.** `price` has IC +0.0372 (t +4.60),
   *above* fundamental's +0.0295, and still loses money at k=20. IC measures the
   whole ordering; a long-only book only ever buys the top of it. Never promote
   on IC alone.

Scope, so this is not over-read: monthly rebalance, no fills, a research panel
that **ends 2024-12-31**, and JKP's own universe rather than ours. It is a GO on
building the vintage, not a claim of live alpha.

**So the build order is now measured rather than argued:**

1. **A current fundamental vintage.** `FMP_API_KEY` is in `.env`. The target is
   the 25 features above (`gp_at`, `cop_at`, `ope_be`, `be_me`, `qmj`, `f_score`,
   …) on our own ticker universe, PIT-dated. This is the one job that unblocks a
   tradeable book, and it is now justified by a measurement rather than a hope.
   It also explains the repo's own near-miss: `profitability_small` (net +5.11%,
   t 2.78, Holm 0.065) is `gp_at` under another name.
2. **Analyst revisions**, already collected here.
3. **Typed news events** — the L2 lane, already built.

## 4. What Murat must do

**1. Save the PC-PAPER keys.** They are not on disk — `.env` was last written
23:09 on 09-21 and ends at `ALPACA_SECRET_2`. Exactly these names:

```
ALPACA_PC_KEY_ID=...
ALPACA_PC_SECRET_KEY=...
```

Then verify in one command:

```bash
python -c "from backend import config; from backend.services import pc_broker as P; import json; print(json.dumps(P.account(), indent=1)[:400])"
```

Until they exist the loop runs, ranks, and writes the book it *would* hold —
`pc_book/<date>/intended_book.json` — and sends nothing.

**2. hack3's account is still open.** Deleting the Railway loop (done) and
deleting a book in one's head do not close a brokerage account. `PA3JYEG4DF9G`
still answers and still holds 9 positions worth ~$69k.

**3. OpenClaw needs an operator.** Gateway is running and probing OK on
loopback; `Capability: connected-no-operator-scope`. `openclaw channels add`,
then sign the dedicated Google account into the managed profile.
See `docs/OPENCLAW_2026-09-22_SETUP.md`.

## 5. Launch

```powershell
# from C:\Users\mrthn\aegis-finance
Start-Process -FilePath ".\.venv\Scripts\python.exe" -WindowStyle Hidden -PassThru `
  -ArgumentList "-m","scripts.night_run_until","--stop-at","07:30",
                "--live","--live-mode","trade",
                "--first","P6_bars_and_regret:60",
                "--queue","J1_error_dataset:20,J2_missed_opportunity:30",
                "--lab","--paid"
```

Write the PID down. **Never `taskkill /IM python.exe`** — on 2026-09-06 that
killed two other agents' jobs and 1,676 already-billed extractions.

`--live-mode trade` is safe to pass even if the ranking fails validation: the
loop downgrades itself to `observe` and says so in `LIVE_LOOP_STOPPED.json`.

## 6. The Bloomberg Challenge (12 Oct – 13 Nov)

$1M virtual, long-only, no leverage, 20% single-name cap, scored on
time-weighted relative return vs the WLS index. The ranker is already the right
shape: `MAX_NAME_FRAC = 0.12` sits deliberately below the 20% cap so the
competition rule is never the binding constraint, and the target is
next-21-session **relative** return — the competition's own unit.

What is owed: the WLS eligible universe. Until Murat has Terminal access the
proxy is the liquid US cross-section already built. Swapping in the real list is
a universe file, not a model change.

## 7. What was NOT done, and why

* **Fundamentals are not in the LIVE ranker**, because `aegis_panel_v2.parquet`
  ends 2024-12-31 and carries `permno`/`gvkey` but **no ticker**, so it can
  neither rank today nor join to the Alpaca book. It was used for what it CAN
  answer — whether the input class has amplitude — and the answer is yes (§3).
  A current vintage is the next build, and it now has a measurement behind it.
* **The funnel itself was not repointed.** `IC_FUNNEL_PATH` still serves the
  August file. The ranker is a SEPARATE selector, which is what CLAUDE.md
  requires ("a new mechanism arrives as its own book, never as a weight").
  Retiring the stale funnel is a decision, not a refactor.
* **No LLM was called.** $0.00 this session.
