# Thematic-Momentum & Exit-Discipline Workstream (V3)

> **Created 2026-06-15.** Origin: Murat's challenge — *"our results are awful vs
> SPY; we play it too safe. The winners (NVDA@20, MRVL@50, MU@100) come from
> buying the next big thing early — oil, batteries, AI compute, quantum — and
> the bug is I sell too early after +200%. Prove me wrong with real values or
> build the engine that does it. At worst we publish why it failed."*
>
> This doc is the **reconciliation of that thesis with the verified research**,
> the **chunked task plan**, and the **pre-registration** of the decisive
> experiment. It is governed by `docs/V2_GOALS.md` (anti-goals) and
> `docs/TRACK_RECORD_POLICY.md`. Companion evidence:
> `DEEP_RESEARCH_2026-06-14_DECISION.md` and the 2026-06-15 deep-research run.

---

## 1. The reconciliation — where Murat is right, and where the trap is

**Murat is right (and an earlier framing of mine was sloppy):** the
oft-cited "thematic investing underperforms" result (Ben-David et al., RFS
2023: new specialized ETFs lose ~30% risk-adjusted over 5 years) is about
**buying a basket *product* at peak attention.** That is **not** the thesis.
The thesis is **buying individual names early, before saturation, on a
secular-demand argument.** That is *early-stage cross-sectional momentum +
conviction*, and the evidence **supports** it:

- **Momentum is "the premier anomaly"** (Fama) — past winners keep winning,
  robust across asset classes and globally (Jegadeesh-Titman 30-yr survey;
  Asness/Moskowitz/Pedersen). This is *why* NVDA/MRVL/MU kept running. It is a
  factor with decades of peer-reviewed support, not luck.
- **The "sold too early" bug is the disposition effect** (Odean 1998): people
  sell winners >50% more readily than losers, and the winners they sell beat
  the losers they hold by **3.4pp/yr**. Documented, costly, *fixable*.

**The two real risks the engine must beat (this is what "prove me wrong"
actually means):**

1. **Hindsight survivorship.** For every NVDA there is hydrogen, 3D printing,
   cannabis, metaverse, solar-2008, cleantech-2010 — themes that were *just as
   logically obvious* and lagged SPY for a decade or died. The question is not
   "was AI a good call" (we know). It is: **can a mechanical rule pick the
   early winners *prospectively*, net of the themes that fail?**
2. **The profit mirage (the firewall on the LLM part).** Verified 2026-06-14:
   backtested LLM returns evaporate past the model's knowledge cutoff;
   lookahead inflates apparent skill by **~37%** (becomes insignificant
   out-of-sample, p=0.033). An LLM in 2026 *already knows* NVDA 20→1000 and
   that the war spiked oil. **You cannot backtest an LLM's theme-picks.** That
   number would be memory, not prediction.

**Resolution — two separable tests, neither self-deceiving:**

| Layer | What it is | How it's validly tested |
|---|---|---|
| **Mechanical** | Rules-only thematic-momentum + ATR exits, point-in-time data, no LLM | **Backtest** via leakage-safe `ReplayEngine` + DSR/PBO haircut (this doc) |
| **Judgment** | LLM/brain reasons over secular trends → conviction picks | **Forward-only** conviction lane (Goal 8 / A2) — never backtested |

The mechanical layer is what we build and backtest now. If it beats SPY after
the overfitting haircut, the structural thesis is vindicated with defensible
numbers. If not, we publish the negative result. The LLM layer accrues
forward, where the mirage cannot touch it.

---

## 2. What the engine already has vs. what's missing

From the 2026-06-15 code map:

**Have (≈70% of the plumbing):** leakage-safe `ReplayEngine` +
`MarketDataAtTimestamp`; `cross_sectional_momentum.py` (3M/6M/12M ranking,
honestly labeled weak-IC/descriptive); `sector_rotation.py`; the full
overfitting guard layer (`engine/validation/overfitting.py` — PSR/DSR/PBO/CSCV,
`effective_number_of_trials`, t>3.0 hurdle); the experiment registry +
guarded `rule_evolution`; the PIT data store (`pit_observations`, schema v7) +
EDGAR 13F collector; book lanes (mirror/conviction, dormant); options-implied
& earnings intelligence.

**Missing (exactly the two things the research says matter most):**

1. **Exit logic — entirely absent.** No trailing stops, no let-winners-run,
   no position sizing. *This is the literal mechanism by which the engine
   "sells too early": it has no way to express "let it run."* ← highest leverage.
2. **Secular theme baskets with point-in-time membership.** No notion of
   "AI compute / energy / critical minerals / quantum" as as-of investable
   sets (must be PIT to avoid hindsight inclusion).

---

## 3. Chunked task plan

> Discipline (per `feedback_phase_discipline`): hard stop at every chunk
> boundary; less code; each chunk ships tested before the next starts. No live
> lane touched, no `paper_nav` write-path change, nothing auto-adopted.

### ✅ Chunk 0 — Docs + reconciliation + pre-registration *(this session, 2026-06-15)*
- This doc. Thesis reconciled; firewall stated; trial pre-registered (§4).
- **Status: done.**

### ✅ Chunk 2 — Exit engine & position sizing *(this session — done out of order; it's the highest-leverage, fully standalone piece)*
- `backend/services/exit_engine.py`: Wilder ATR; **Chandelier trailing-stop**
  simulator (`simulate_trailing_exit`, ratchets up never down, conservative
  close fill); **volatility targeting** (`volatility_target_weight`);
  **fractional Kelly** (`fractional_kelly_fraction`). Pure/stateless → backtests
  leakage-free, unit-tests deterministically.
- Config block `config["exit_engine"]` (params + the `atr_multiple_grid` sweep).
- `backend/tests/test_exit_engine.py` — **19 tests, all green.** Asserts the
  exact behaviours that distinguish "let winners run" from "sold too early":
  a monotonic winner runs to the end; a winner that rolls over exits near the
  peak keeping most of the gain; the stop never ratchets down; sizing shrinks
  with vol; Kelly caps and zeroes on negative edge.
- **Status: done.** Descriptive-only; no lane uses it yet.

### ⬜ Chunk 1 — Secular theme baskets (point-in-time)
- Define a *small* set of secular-demand themes (AI_COMPUTE, ENERGY,
  CRITICAL_MINERALS, QUANTUM) as **as-of membership** records (ticker + the
  date it could honestly have been included — listing/relevance date), stored
  so the backtester can ask "what was in this theme on date D" without
  hindsight. Likely a YAML + a loader into the PIT store; reuse
  `pit_observations` semantics (`as_of` / `observed_at`).
- **Guardrail:** membership must be defensible as known-at-the-time. Document
  the inclusion rule; a reviewer must be able to falsify "you only added NVDA
  because you know it won." Survivorship of *delisted* names included.
- **Test:** as-of membership query returns no ticker before its inclusion date.

### ⬜ Chunk 3 — Thematic-momentum strategy (pure rules)
- `backend/services/thematic_momentum.py`: rank within each as-of basket by
  momentum **acceleration** (early-entry signal, not just level), combine with
  `exit_engine` sizing/exits. Pure functions: `(as_of_date, prices_as_of) →
  target_weights`. No LLM, no network in the core.
- **Test:** deterministic synthetic baskets → expected entry/exit/weights.

### ⬜ Chunk 4 — The decisive backtest (real values) + registry
- Run the Chunk-3 strategy through `ReplayEngine` over **2015→2025** (a window
  containing the NVDA run AND the failed themes), as-of prices only, realistic
  costs/slippage. Compare vs **SPY** (and the existing lanes). Apply the
  **DSR/PBO** haircut deflated against the cumulative trial count (now 3 → this
  becomes a counted sweep), nonlinear t>3.0 hurdle.
- Sweep `atr_multiple_grid` × a few momentum params **inside CSCV** so the
  multiple-testing count is honest (every variant counted, not cherry-picked).
- Record as **TRIAL-THEME** (§4) — adopted *or* rejected, with the number.
- **Deliverable:** a real CAGR/Sharpe/maxDD-vs-SPY table + DSR/PBO. This is the
  "prove me wrong with real values" output. **Publishable either way.**

### ⬜ Chunk 5 — Forward conviction/thematic lane *(only if Chunk 4 survives the gate)*
- Pre-register a **new** paper lane (never retrofit existing track record).
  The LLM/brain conviction layer plugs in here, **forward-only**.

---

## 4. TRIAL-THEME — pre-registered decision rule (commit-stamped before Chunk 4 data)

> Pre-registering the rule *before* the backtest is run is what separates
> science from curve-fitting. Filled in at Chunk 4 launch; frozen thereafter.

- **Hypothesis:** A mechanical thematic-momentum strategy (early acceleration
  entry within point-in-time secular baskets, ATR trailing-stop exits,
  vol-targeted sizing) achieves a higher **deflated** net-of-cost Sharpe than
  buy-and-hold SPY over a pre-specified out-of-sample window.
- **Primary metric (the only deciding one):** **Deflated Sharpe Ratio (DSR)**
  of the strategy's net daily returns, deflated against the cumulative trial
  count *including every parameter variant swept*. Ship-consideration only if
  **DSR ≥ 0.95 AND PBO < 0.5** (the registry's existing gate).
- **Secondary (reported, never deciding):** CAGR, max DD, vol, Calmar,
  turnover, total cost, hit rate, avg winner/loser, vs-SPY excess.
- **Backtest integrity:** as-of prices only (`MarketDataAtTimestamp`); themes
  via as-of membership (Chunk 1); costs = lane cost_bps + slippage_bps;
  survivorship handled (delisted names retained). No metric substitution, no
  window cherry-picking after the run.
- **Honest prior:** the surviving research says momentum's *existence* is
  robust but its *magnitude* has decayed (~10%/yr in the 90s → ~2%) and it has
  crash risk (loser decile +163% Mar–May 2009) — so net-of-cost survival is
  genuinely uncertain and may require volatility-managed momentum
  (Barroso–Santa Clara). **Expected outcome: unknown.** Publishing a clean
  negative result is an explicit success condition.
- **Hard constraint:** descriptive until the gate passes; no live lane armed,
  no buy/sell language, no skill claim before the 24-month policy.

---

## 5. Anti-goal compliance (checked against `docs/V2_GOALS.md`)

| Anti-goal | This workstream |
|---|---|
| No RL / online-learning on own P&L | ✅ Mechanical rules + offline DSR/PBO. "Learns each run" = registered trials with a haircut, **not** weight updates from P&L. |
| No skill claims before 24 months | ✅ Backtest is labeled methodology; forward lane (Chunk 5) respects the policy. |
| No backtested-LLM self-deception | ✅ Profit-mirage firewall: LLM layer forward-only; mechanical layer LLM-free. |
| No feature-count arms race | ✅ Two focused additions (exits, themes) that fill the research-identified gaps; reuses existing momentum/replay/guard plumbing. |
| No `paper_nav` / live-lane risk | ✅ Nothing live touched this arc. |

---

## 7. Results — Chunk 4, the decisive run (2026-06-15)

Backtest: `engine/research/thematic_backtest.py`. Window **2015-06 → 2025-06**
(10y), daily event-driven, monthly 12-1 momentum rebalance inside as-of theme
baskets, daily ATR trailing-stop exits, **10 bps** turnover cost, vs buy-and-hold
SPY. 46 theme tickers fetched. Full JSON: `thematic_backtest_results.json`.

| Strategy | CAGR | Sharpe | Max DD |
|---|---|---|---|
| **SPY buy & hold** | **+12.8%** | **0.75** | −33.7% |
| Thematic, neutral cfg (atr 3.0, lb 12) | +11.2% | 0.64 | **−25.6%** |
| Thematic, best-in-sample (atr 4.0, lb 6) | +18.9% | 0.89 | −33.0% |

Overfitting haircut: **PBO = 0.37 ("fragile")**, **DSR = 0.978** deflated
against **18 trials** (3 prior + 15 swept). The registry gate (DSR≥0.95 AND
PBO<0.5) mechanically reads PASS.

### The honest verdict: this is NOT a clean win — closer to a refutation with one real lesson.

1. **The neutral configuration LOSES to SPY** on both return (+11.2% vs +12.8%)
   and Sharpe (0.64 vs 0.75). Only the *best-of-15* config beats SPY.
2. **The "edge" is monotonic in stop-looseness** (atr 2.0→4.0 walks return
   +7%→+19% almost monotonically; shorter lookback helps too). That is the
   signature of **bull-market beta, not selection alpha**: the looser the stop
   and the less you trade, the closer the concentrated basket gets to
   buy-and-hold growth names in a decade-long bull run. The strategy isn't
   *picking* better — it's just *holding more beta* when you stop cutting.
3. **PBO 0.37 = "fragile."** A 37% chance the in-sample-best underperforms the
   median out-of-sample. The best config (atr 4.0 / lb 6) is exactly the
   most-beta corner — picking it is the overfit the PBO is warning about. The
   DSR "pass" does **not** override this, and DSR corrects for multiple testing,
   **not** for the survivorship problem below.
4. **Survivorship inflates even these numbers.** The baskets are curated
   survivors (NVDA/AVGO/LLY in; no delisted losers). The honest, delisting-aware
   version would be *worse* — so the true neutral result is below the already-
   losing +11.2%.

### The one real, repeatable lesson (this part supports Murat)

**Exit discipline cut the drawdown hard** — neutral cfg −25.6% vs SPY −33.7%,
for ~1.6pp/yr of give-up. The trailing stop works as **risk control**, exactly
the textbook "risk-managed gives up some upside, protects the downside" result
we saw in the lane backtest. Murat's *"let winners run, cut losers"* instinct is
real as a **drawdown tool**; it is **not**, on this evidence, an alpha source.

### Rebuild plan (the scientific next iteration — Chunk 4b)

To separate **theme-selection skill** from **bull beta** and **survivorship**:
- Add a **delisted-names** layer to the baskets (de-bias survivorship).
- Add an **equal-weight all-themes control** and a **plain SP500-momentum
  control** — if thematic ≈ generic momentum ≈ beta, the theme thesis is not
  adding alpha and we say so.
- Compare at **matched volatility** (beta-neutralize) so "more return" can't come
  from "more equity exposure."
- Test **volatility-managed momentum** (Barroso–Santa Clara) — the research's
  named fix for momentum's thin net edge.
This is recorded as **TRIAL-THEME = leaning REJECT** pending 4b; the negative
result is publishable as-is.

---

## 6. Status ledger

| Chunk | State | Artifact |
|---|---|---|
| 0 Docs + pre-registration | ✅ done 2026-06-15 | this doc |
| 2 Exit engine | ✅ done 2026-06-15 | `services/exit_engine.py`, `tests/test_exit_engine.py` (19✅), `config["exit_engine"]` |
| 1 Theme baskets (PIT) | ✅ done 2026-06-15 | `data/theme_baskets.yaml`, `services/theme_baskets.py`, tests (13✅ shared) |
| 3 Thematic-momentum strategy | ✅ done 2026-06-15 | `services/thematic_momentum.py` |
| 4 Decisive backtest + TRIAL-THEME | ✅ done 2026-06-15 → **leaning REJECT** | `engine/research/thematic_backtest.py`, results §7 |
| 4b Rebuild: de-bias survivorship + beta-neutral + controls | ⬜ next | the real test of *selection* skill |
| 5 Forward conviction lane | ⬜ (gated on 4b) | — |
