# Session Post-Mortem — 2026-06-15 — Thematic-momentum REJECT + exit engine

## What this was

Murat's challenge: "we lag SPY, we play too safe — buy the next big thing early
(oil/batteries/AI-compute/quantum/pharma), stop selling winners too soon. Prove
me wrong with real values, or build it; at worst publish why it failed." Ran a
deep-research workflow, then built and backtested the mechanical version of the
thesis under the overfitting guards. Plan-first, chunked, nothing live touched.

## What shipped (`329d0f9`, `7e8539a`)

- `services/exit_engine.py` — the research-identified **#1 gap**: the engine had
  ZERO exit/sizing logic. Wilder ATR, Chandelier trailing stop (ratchets up never
  down), vol-target sizing, fractional Kelly. Pure/stateless. (19 tests)
- `data/theme_baskets.yaml` + `services/theme_baskets.py` — 5 secular baskets,
  **point-in-time membership** (as-of query; a ticker can't be held before its
  listing date). Survivorship correction added in 4b (QS/PLUG/FCEL/CHPT). (13 tests)
- `services/thematic_momentum.py` — pure 12-1 momentum entry.
- `engine/research/thematic_backtest.py` — decisive 2015→2025 vs-SPY run + 3
  controls + DSR/PBO haircut.
- Docs: `research/THEMATIC_MOMENTUM_2026-06-15.md` (plan + TRIAL-THEME + §7/§8
  results), BACKLOG Section T.

## The findings (the part the brain must remember)

**TRIAL-THEME = REJECT.** Mechanical thematic-momentum selection has no alpha:

1. **Theme-momentum selection LOSES to its controls.** Thematic Sharpe 0.79 <
   broad-universe momentum 0.86 < equal-weight-themes 0.87. Selection edge =
   **−0.08**. The clever within-theme momentum layer *subtracts* value. Momentum
   does not need themes.
2. **Equal-weighting the 5 themes beat SPY (+21.2% vs +12.8%)** — BUT that is
   **hindsight + survivorship**, not skill: the themes were chosen in 2026
   knowing AI/energy/pharma won, and the survivorship fix couldn't offset the
   huge winners (NVDA/AVGO/LLY/oil-2022; NKLA even failed to download). Deeper
   −38% drawdown too. **A backtest cannot validate "pick winning themes early" —
   it is the profit mirage in basket form.**
3. **PBO went 0.37 → 0.66 (overfit)** once losers were added — picking the best
   config is noise. DSR 0.984 "passes" but the gate (DSR≥0.95 AND PBO<0.5) FAILS
   on PBO. Correct rejection.
4. **Exits = drawdown control, NOT alpha** (consistent across every run): thematic
   maxDD −30.6% beat SPY −33.7% and EW-themes −38.1%, at a small return cost.

## Decisions / rejected approaches

- **REJECTED: backtesting LLM/brain theme-picks.** Profit mirage (canon A2,
  ~37% lookahead inflation). The LLM knows the winners. The conviction lane
  (forward-only) is the ONLY honest test of the secular-conviction instinct.
- **REJECTED: DRL / self-retraining-each-run** (deep research: algorithm choice
  p=0.640 negligible; "every backtest gets better" is the overfitting machine,
  demonstrated live by PBO rising to 0.66). Stays an anti-goal.
- **CONFIRMED real:** cross-sectional momentum (premier anomaly) + disposition
  effect (Odean, 3.4pp/yr) + the DSR/PBO gate as the thing that stops self-
  deception. The gate did its job here.

## What's next (so a future session doesn't re-run the same hope)

- Exit discipline is the real, keepable win → pre-register **TRIAL-EXIT** on a
  **NEW** lane (`conservative-atr`), never retrofit the live `conservative` lane
  (canon: no strategy change to an in-flight tracked lane).
- The secular-theme instinct → **forward conviction lane** (book seeded today at
  MV weights; decisions logged forward, leak-free). Backtest closed; do not tune.
- Do NOT add thematic-momentum selection to any live lane — it has no edge.
