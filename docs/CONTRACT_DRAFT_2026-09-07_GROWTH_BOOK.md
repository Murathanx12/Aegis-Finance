# CONTRACT DRAFT — GROWTH BOOK on hack4, 2026-09-07

**Status: DRAFT. NOTHING IS ENABLED.** No flag flipped, no lane seeded, no
order placed, no Railway variable set. Murat freezes this or declines it.
Licence sought: `PRODUCT_EXPERIMENT` (external PAPER only). It is **not** a
`CAPITAL_CANDIDATE` and this draft does not ask for one.

**Read the recommendation before the numbers: take rung 1× or decline.** The
evidence for the book is one sealed-era look that met the wealth condition and
failed the deflation and PBO conditions, and the evidence *against* the ladder
is arithmetic, not opinion — see §6.

---

## 1. What is frozen

| field | value |
|---|---|
| **beta (sealed era, 25 bps)** | **0.6681** |
| genome id | `m12_quality_mom\|dd` |
| champion sha256 | `39ab3224c1a12e14…` (recipe + every development monthly return at both cost rates, 10 dp) |
| search declaration sha256 | `0397b9bfae7d53c1…` (`backend/data/optimus/growth_book/DECLARATION.json`) |
| lineage | `quality_mom` → `quality_mom\|dd` → `m12_quality_mom\|dd` (G3 mutation 12, corpse named: see `G3_mutations.json`) |
| selection | monthly top-**110**, **value weighted**, score = `(rank_pct(ROE_pit) + rank_pct(mom_12_1)) / 2` within month |
| hysteresis | buy at rank ≤ 110, **hold until rank > 160** |
| universe | floored: ≥ $3,000,000/day 20-day dollar volume **and** close ≥ $5. Universe fingerprint `616fa0a5dac735be…` |
| quality leg | `roe` from WRDS `wrdsapps_finratio` (early 1990-2012 + modern 2013-2024), as-of merge on `public_date ≤ entry_date`. **Not** gross profitability — `gprof` starts 2013-01 in this repo's pull |
| overlays | `dd` (exposure = clip(1 − \|trailing 7-month book drawdown\| / 0.30, 0.05, 1), the drawdown lagged one month) **then** `bsc` (exposure = PIT-median trailing 24-month vol / trailing 24-month vol, capped 1.8) |
| costs | 25 bps per side, both sides, on measured weight turnover (**mean turnover 0.205/month**) |
| financing | RF + 100 bps annualised on borrowed notional; unused cash **earns RF** |
| rebalance | monthly, at the panel's entry date |
| measured book size | 110 names/month over 309 months |

The frozen object is a **recipe**, not a model file. There is no fitted artefact
to persist: the score is two cross-sectional ranks and the overlays are
closed-form functions of the book's own history. `growth_lab.Genome.sha256()`
hashes the recipe; a change to any constant changes the hash.

## 2. The evidence, with beta first and the bars named separately

> **beta 0.6681** (intercept +4.907%/yr, HAC t 0.968): on 2016-2024, unseen in
> development, the champion returned **3.6684×** against SPY TR **3.6707×**
> after 25 bps, at maxDD **−29.66%** against SPY's **−30.99%**. Sized to the
> same drawdown budget the book runs 1.3027× for **4.6616×** and levered SPY
> runs 1.2471× for **4.4823×**. Leverage-neutral TW **3.6044** — below SPY.

| bar | value | verdict |
|---|---|---|
| sealed TW at the budget > levered-SPY at the budget | 4.6616 vs 4.4823 | **MET** |
| constraints on the sealed era | maxDD −0.297 vs budget −0.387; CVaR₅ −0.135 vs −0.203; worst month −0.297 vs floor −0.40 | **MET** |
| positive in ≥ 2 of 3 development eras | 1999-2007 **+0.340%/mo**, 2008-2015 **+0.756%/mo** | **MET** |
| DSR over the family | **0.0046** over 128 cells, bar 0.95 | **FAILED** |
| family PBO < 0.5 | **0.6429** (`SELECTION_IS_OVERFIT`) | **FAILED** |

Unlevered, the book delivered SPY's terminal wealth at two-thirds of SPY's beta
and a smaller drawdown. **Leverage-neutral it loses to SPY** (3.6044 vs 3.6707):
the vol match costs more in financing than the lower beta earns. That is the
honest shape of this candidate — a lower-beta way to hold the market, not an
edge over it.

## 3. B2 hold fields

| field | value | why |
|---|---|---|
| `horizon_sessions` | **21** | the book is monthly; the horizon is the rebalance interval and not a guess |
| `min_normal_hold_sessions` | **10** | C2 of the Labor Day lab found hack1/2/5 carry `0` and the min-hold rule is vacuous on three of six books. This one is not exempt |
| `hysteresis_band` | buy ≤ 110, hold ≤ 160 | the frozen rule; hysteresis is what holds turnover at 0.205 |
| `exit_reasons_permitted` | `REBALANCE_MONTHLY`, `HARD_RISK_LIMIT`, `UNIVERSE_EXIT` (name drops the $3m/$5 floor), `CONTRACT_END` | any other close needs a typed reason recorded before it is sent |
| `no_close_before_min_hold_without_a_typed_reason` | enforced | C2's assertion, unchanged |

## 4. Attribution, nightly

Every night the report decomposes the day's P&L into five terms that sum to it:

1. **β × market** — 0.6681 × SPY TR over the same window (the beta is the
   *sealed-era* estimate and is re-estimated forward, never re-fitted in place)
2. **intercept** — the residual after (1)
3. **sizing** — the exposure the overlays chose vs a flat 1.0×
4. **costs** — measured turnover × 25 bps, both sides, plus financing on
   borrowed notional
5. **cash drag** — the RF the unheld fraction earned, printed as a *positive*
   term so it can never be silently zeroed (amendment §2.3)

A night where the five terms do not sum to the day's NAV change is a red line,
not a rounding note.

## 5. The leverage ladder, and the rung rule

Rungs **1× → 1.5× → 2×**, B9's 20-session rule: a rung advances only on
**compound wealth after drawdown over ≥ 20 sessions**, attended, never
automatically. A rung never advances on a single good week and never on an
unrealised mark.

## 6. WORST CASE IN DOLLARS PER RUNG, $100,000 BOOK

Peak-to-trough and worst single month of the **frozen champion's own history**,
1999-2024, 25 bps, financing charged. `P(ruin)` is
P(peak-to-trough ≤ −50%) from a 2,000-draw stationary block bootstrap.

| rung | maxDD | **worst case $** | worst single month | **worst month $** | P(lose half) | median worst DD |
|---|---|---|---|---|---|---|
| **1.0×** | −46.88% | **−$46,882** | −29.66% | −$29,663 | **0.232** | −41.5% |
| **1.5×** | −65.44% | **−$65,435** | −44.64% | −$44,636 | **0.797** | −59.8% |
| **2.0×** | −78.29% | **−$78,293** | −59.61% | −$59,609 | **0.985** | −74.6% |

**The 2× rung is REFUSED by the declaration and this draft does not ask for
it.** It breaks two of the four hard constraints outright: the worst month
−59.61% is past the −40% floor, and the drawdown is far past 1.25× SPY's. On the
sealed era the largest admissible size was **1.3027×**, so the ladder's real
ceiling is **1.3×, not 2×**, and the third rung exists in this table only so the
number it would cost is written down rather than imagined.

At 1.5× the book loses half its value in **four cases out of five**. At 1.0× it
does so in roughly **one case in four**. Those are properties of a
110-name long-only equity book at beta 0.67 through 2000-02 and 2008-09; they
are not a defect of this candidate, and no sizing rule in G5 improved them.

## 7. What G5 says about sizing this book, and why it matters here

The nightly report may **display** a suggested exposure. It may not **set** one.
On the development era, at the same drawdown budget and 25 bps:

| arm | beta | TW at budget | DSR |
|---|---|---|---|
| flat 1× (the null) | 0.7224 | **5.6264** | 0.4206 |
| Moreira-Muir trailing vol | 0.8970 | 3.7599 | 0.3380 |
| NN seed-mean, quarter-Kelly | 0.6035 | **1.0546** | 0.0073 |

Neural sizing was worse than the baseline and **both were worse than doing
nothing**. Seed spread at the budget was 0.7275 → 5.7383 across eight seeds.
Until that reverses on the sealed era with DSR > 0.95, **the frozen exposure
rule is the contract's own `dd`+`bsc` overlay and nothing else may size this
book.**

## 8. What would make this a CAPITAL_CANDIDATE

Not this document. The gaps, in order of how much they matter:

1. **DSR 0.0046 over 128 cells.** The search opened 128 cells and the winner's
   Sharpe is what the maximum of 128 draws produces under no edge. Either the
   family shrinks (a pre-registered single genome) or forward evidence
   accumulates on its own clock.
2. **PBO 0.6429.** The leaderboard's top row is worse than a coin flip out of
   sample. A second, independent sealed window — not available until 2025 data
   is on disk — is the only clean way past this.
3. **Forward n.** Zero sessions. The website lanes' 41-47 sessions are already
   inside the noise (G7); this book has none.
4. **The mark problem.** G7 found every forward lane's NAV is marked on stale
   prices — R² vs SPY of 0.0015-0.05 with Dimson betas 2-5× the contemporaneous
   ones. A book seeded before that is repaired will report a beta it does not
   have.

## 9. Recommendation

**Take rung 1×, or decline.** Rung 1× buys a forward record on a book whose
sealed-era behaviour is documented and whose worst case is written above in
dollars. Rung 1.5× buys an 80% chance of halving the book for a candidate that
failed two of five gate conditions, and rung 2× is refused by the declaration.

If seeded: `seed-a-lane` (attended, env-gated), `lane-integrity-check` before
and after, and `pre-register-trial` for the forward claim — the sealed-era
result is a `PRODUCT_EXPERIMENT` observation and is not a `RESEARCH_CLAIM`.

## 10. Receipts

- `backend/data/optimus/growth_book/DECLARATION.json` — objective, constraints,
  benchmarks, eras, 44 generation-0 genomes. Hashed before the first evaluation.
- `G2_generation0.json` · `G3_mutations.json` (+ `G3_mutations_round01_ALL_REFUSED.json`)
- `G4_CHAMPION_DECLARATION.json` — written before the sealed era was opened
- `G4_seal.json` — `sealed_era_openings: 1`
- `SEALED_ERA_OPENINGS.jsonl` — one line, append-only
- `G5_sizer.json` · `G7_forward_lanes.{json,md}`
- `docs/BUILD_GROWTH_BOOK_2026-09-07.md` — the session deliverable
