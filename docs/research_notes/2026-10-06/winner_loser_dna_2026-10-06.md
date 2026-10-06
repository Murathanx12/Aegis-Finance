# Winner vs loser DNA — the 148 paper books ahead of SPY (2026-10-06)

**Licence: PRODUCT_EXPERIMENT.** Nothing here is a claim; CLAUDE.md rule 4 ("study
losers as hard as winners") and the 2026-09-24 lesson ("the first question is
WHICH PART OF THE SAMPLE") govern this note. Every number cites the receipt it
came from. Primary receipt: `backend/data/optimus/paper_accounts/roi_2026-10-06.json`
(362 priced rows, 307 with an own-window SPY leg, 148 ahead / 159 behind,
generated 2026-10-06T04:59:34Z). Secondary: `llm_portfolio/books.jsonl` (320
frozen books with holdings), `paper_accounts/fleet_manager/state/hack*.json`
(live positions), `paper_accounts/pc_snapshot/state_latest.json` (PC-PAPER),
`prices_2025_26/bars.parquet` (1.3M daily bars), `docs/PAPER_ACCOUNTS.md`,
`docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md`, `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md`.

## Headline, before the table

**"148 ahead of SPY" is not 148 bets.** Of the 148, **105 (71%) are `twin`
control accounts** — literal re-pricings of 64 underlying books under a
different benchmark/weighting convention (`ew`, `sector_etf`, `random_same_band`,
`spy`, `iwm`, `matched_random`) — not independent strategies
(`aggregate.by_family`, `roi_2026-10-06.json`). Strip twins and the picture is
**40 ahead / 40 behind of 91 priced** (`aggregate.priced_excluding_control_twins`).
Of the 35 remaining non-twin winners (lib/personal/competition parents), a
Jaccard-overlap clustering on actual holdings (below) collapses them to **~6
genuine clusters**, one of which (19 of 35 books) shares a semiconductor/
memory/AI-datacenter-capex basket (MU in 54% of winner books, AMD/SNDK in 37%,
DELL/STX/TXG/RVMD in 29%). **The named website lanes (conservative-atr,
aggressive, tsmom-overlay, …) are NOT among the 148 — all ten trail SPY on their
own window**, despite five of them having positive absolute return, because SPY
itself returned +3.8% to +7.4% over their windows (`market_benchmark`,
`lane_nav_series`).

---

## 1. Every book ahead of SPY — by family, not by name

148 individual accounts is too many rows to be informative; the honest unit is
the **family** (`aggregate.by_family`, `roi_2026-10-06.json`):

| family | n ahead | n in family | underlying distinct books | inception | sessions graded | note |
|---|---:|---:|---:|---|---:|---|
| `llm_portfolio:twin` | 105 | 254 | **64** (46 have ≥1 ahead variant) | 2026-09-28/29 | 6–8 | controls of lib/personal/competition parents, not new strategies |
| `llm_portfolio:lib` | 20 | 32 | 20 (parents) | 2026-09-28 | 6 | momentum/revision/quality screens over an XS ranker |
| `llm_portfolio:personal` | 15 | 23 | 15 (parents) | 2026-09-28/29 | 6–7 | thematic/LLM-authored baskets (revision flow, Asia supply chain, AI power, …) |
| `night_books` | 3 of 9 | 9 | 3 | 2026-09-11/10-01 | 7 (or 1) | momentum / "always invested" / Book D comparator books |
| `night_books_twin` | 3 of 17 | 17 | twins of the above | 2026-09-11/10-01 | 7 (or 1) | same shape as `llm_portfolio:twin` |
| `pc_paper` | 1 of 1 | 1 | 1 | 2026-09-22 | ~9 | PC-PAPER, 80% cash, see §4 |
| `alpaca_fleet` | 1 of 5 priced | 6 | 1 (hack2) | 2026-08-28 | ~27 | see §5 — 4 of the other 5 are the worst losers in the fleet |
| `website_lane` | **0** of 10 | 10 | — | 2026-06-08 to 07-27 | 39–74 | ALL ten behind SPY own-window; see §3 |

**Top-1-holding / sector / beta, for the non-twin winners that have holdings
(`llm_portfolio:lib` + `:personal`, n=35, via `books.jsonl` positions × daily
closes from `bars.parquet`, entry = first session after `asof`, exit =
2026-10-05):**

| book | inception→exit | ROI | SPY leg | excess | top-1 contributor | top-1 share of excess | top-3 share | beta vs SPY |
|---|---|---:|---:|---:|---|---:|---:|---|
| lib_resid_mom_12_1_large_sealed | 09-26→10-05 | +7.93% | +0.84% | +7.09pp | AAOI +25.6% | 15.5% | 39.8% | NOT_COMPUTABLE (6 obs) |
| lib_qc395_sharpe252_above_trend_large | 09-27→10-05 | +6.94% | +0.84% | +6.10pp | LITE +18.5% | 22.7% | **61.7%** | NOT_COMPUTABLE |
| lib_net_raises | 09-26→10-05 | +6.34% | +0.84% | +5.50pp | S +11.8% | 13.3% | 38.7% | NOT_COMPUTABLE |
| pers_revision_flow_leaders | 09-25→10-05 | +5.97% | +0.84% | +5.12pp | OKTA +8.0% | 19.3% | 49.5% | NOT_COMPUTABLE |
| revision_flow_v0 | 09-25→10-05 | +6.41% | +0.84% | +5.57pp | S +11.8% | 14.0% | 40.8% | NOT_COMPUTABLE |
| pers_asia_supply_chain | 09-25→10-05 | +4.76% | +0.84% | +3.92pp | TER +10.8% | 46.0% | 95.9% | NOT_COMPUTABLE |

Beta is NOT_COMPUTABLE for the `llm_portfolio` books — 6–8 daily observations
is too short to regress against SPY (the 2026-09-24 lesson on a t-stat whose
bias depends on the swept parameter applies here directly: do not fit a slope
on 6 points). The TAIL check (CLAUDE.md rule 2 / "check the tail before the
mean") shows **one or three names carry 14–96% of the excess** in every book
above — `pers_asia_supply_chain`'s "alpha" is 96% two tickers (TER, ASML).
These are **narrow, short, concentrated results**, not a diversified edge.

---

## 2. Clustering the winners — how many independent bets are there really?

Jaccard similarity on actual ticker holdings (`books.jsonl` positions,
`CASH` excluded), 35 non-twin winners:

- **Threshold ≥0.30 (strict — "largely the same book"):** 17 clusters, largest
  size 6.
- **Threshold ≥0.15 (loose — "shares a meaningful chunk of the same names"):**
  **6 clusters.** One cluster of **19 of 35 books (54%)** — every `lib_mom_*`,
  `lib_qc*`, `lib_skill_mom*`, `lib_disp_short_avoid`, `probe_*` book plus
  `SHADOW_BAYES_v0` — sharing a semiconductor/storage/optical basket (MU, AMD,
  SNDK, DELL, STX, MRVL, LITE, AXTI, WOLF, MXL, TWST, TXG, TSM, INTC). A second
  cluster of 7 (`cards_supports`, `pers_ai_power_global`, `pers_asia_supply_chain`,
  `pers_catalyst_calendar`, `pers_ensemble`, `pers_quality_momentum`,
  `reviewer_opus`) and a third of 5 (`lib_net_raises*`, `pers_revision_flow_leaders`,
  `revision_flow_v0`, `lib_skill_raises`) share an enterprise-software/
  analyst-upgrade basket (OKTA, CRWD, PANW, SNOW, CRM, GTLB, AFRM, S, ESTC, NET).

**Ticker frequency across the 35 winners confirms it:** `MU` appears in **54%**
of winner books, `AMD`/`SNDK` in 37%, `DELL`/`STX`/`TXG`/`RVMD` in 29%. This is
exactly the shape CLAUDE.md's "mega-cap is a SENSOR" and the 2026-09-27
feedback item ("IS BETA WAS NO POWER") warn about: a late-September/early-October
semiconductor-memory/AI-datacenter-capex rally lifted almost every momentum or
revision-screen book that happened to hold 2–4 of these names, and the LLM
book-authoring process (same `briefing_asof`, overlapping universes) converged
on the same basket independently 15+ times. **Plain statement: the 148-ahead
headline is not 148 independent discoveries — it is roughly two sector rallies
(chips/memory/AI-capex; enterprise-software upgrades) multiplied by many
near-duplicate book constructions and then multiplied again by 3–7 control
twins each.** Collapsing twins (§0) and overlap clusters (this section) together,
**the 148 "winners" reduce to on the order of 6–10 genuinely distinct exposures.**

---

## 3. Website lanes: why conservative-atr is "ahead" of aggressive/conviction/mirror — and why none of them beat SPY

None of the ten website lanes are ahead of SPY on an own-window basis (§0); the
owner's question is about their RELATIVE ranking against each other, where
conservative-atr (+3.34%) and tsmom-overlay (+3.71%) sit above aggressive
(+1.99%), far above conviction (−9.07%) and mirror (−24.48%)
(`docs/PAPER_ACCOUNTS.md`, `lane_nav_series`).

**Decomposition (daily NAV series, `lane_nav_series.lanes`, 2026-06-08 to
10-05):**

| lane | n sessions | ann. vol | beta vs SPY | corr vs SPY | max drawdown | monthly path (Jul / Aug / Sep / Oct) |
|---|---:|---:|---:|---:|---:|---|
| conservative-atr | 67 | 7.1% | 0.10 | 0.15 | **−3.9%** | +2.71 / +2.63 / −3.09 / +0.30 |
| conservative | 74 | 7.7% | 0.02 | 0.03 | −4.2% | — |
| aggressive | 74 | 9.3% | 0.04 | 0.05 | −4.5% | +1.68 / +2.07 / −3.40 / +0.71 |
| tsmom-overlay | 39 | 6.2% | 0.21 | 0.37 | **−1.4%** | n/a / +2.50 / +0.03 / +1.04 |
| conviction | 68 | **36.9%** | 0.77 | 0.24 | **−20.9%** | −15.46 / **+8.10** / −8.22 / +1.68 |
| mirror | 68 | **30.9%** | 0.60 | 0.22 | **−26.6%** | −14.28 / **+7.44** / −11.30 / +2.17 |
| SPY (same window) | — | 11–12% | 1.00 | 1.00 | — | +0.03 / +2.68 / −0.33 / +1.60 |

**What this says:**
- **Beta cannot be the differentiator.** All six lanes have *low* correlation
  to SPY (0.03–0.37, except mirror/conviction at ~0.22–0.24) — none of them is
  "the market with leverage." Conservative-atr is ahead of aggressive mostly
  on **cutting volatility**, not on timing SPY.
- **Selection is the same underlying bet for mirror/conviction**: both were
  seeded from the SAME 12-name discretionary book (SOC, DKNG, NTLA, AARD, BHVN,
  HUBS, KYTX, PRCH, QUBT, AMSC, ABSI, SLDP; `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md:433`),
  normalised to $100k at market-value weights on 2026-06-16. **conviction has
  no position cap at all; mirror's cap is 25% of book (one micro-cap can be a
  quarter of NAV)** (same doc, line 494). Both swung **+7–8% in August and
  −8% to −15% in July/September** — the SAME directional bets, amplified by
  concentration, not a different signal: August was a good month for the
  underlying 12-name book, July and September were bad ones, and nothing
  bounded how much of NAV rode on a single micro-cap name either month.
- **So "conservative-atr constantly ahead, aggressive behind" is a SIZING/vol-
  scaling story, not a selection or timing story.** All of conservative,
  conservative-atr and aggressive share the same monthly SIGN pattern
  (positive Jul/Aug, negative Sep, positive Oct) — same underlying signal family
  (corr 0.89–0.98 to each other, `lane_nav_series` pairwise correlation) — and
  conservative-atr's ATR-based position sizing simply shrinks exposure, which
  caps both the gains and the September bleed. It is NOT differentiated stock
  selection: it is lower volatility applied to the same trades. tsmom-overlay
  looks different in kind (lower corr to the conservative/aggressive cluster,
  0.48–0.57) and has the smallest drawdown of any lane (−1.4%) — the most
  defensible of the ahead-of-the-pack lanes, but n=39 sessions is short.
- **Mirror/conviction's loss is NOT beta.** Their beta to SPY (0.60/0.77 over
  this window; the 08-02 dossier's longer-window measurement was ~1.05–1.07)
  cannot explain a −20 to −30pp gap when SPY itself was flat-to-up most months.
  It is **idiosyncratic concentration risk** in a structurally uncapped
  (conviction) or weakly capped (mirror, 25%) micro-cap book, exactly as the
  dossier concluded in August and as this window reconfirms.

---

## 4. PC-PAPER: is +0.19% "cash drag avoided in a down window"?

**No — the window was not down, so that mechanism does not apply.** Raw line
(`roi_2026-10-06.json`, `pc_snapshot/state_latest.json`):

- Inception 2026-09-22, first trades 2026-09-25, 9 sessions to 2026-10-05.
- Equity $1,001,903 vs start $1,000,000 → **+0.19%**.
- SPY same window: **+0.17%**. Excess: **+0.018pp** — two basis points.
- Cash **$800,653 / equity $1,001,903 = 79.9%** invested 20.1%, 10 positions
  (AAPL, AMZN, AVPT, GOOGL, INCY, JAZZ, META, NVDA, SNDR, TSM), roughly
  $19–21k each (2% of equity per name).
- Unrealized P&L sum across the 10 positions: **+$2,101**; top contributor
  AVPT +$2,286 (109% of the total — i.e. AVPT alone explains the whole gain
  and everything else nets to roughly zero), followed by TSM +$1,610 and NVDA
  +$1,133, offset by INCY −$2,238 and META −$348.

**Verdict: this is noise, not a cash-timing story.** SPY was essentially flat
(+0.17%) over PC-PAPER's 9-session window — there was no "down window" for
cash to protect against. The +0.018pp edge is one micro-cap position (AVPT,
software/security, +11.4% unrealized) outweighing a loser (INCY, biotech,
−11.1% unrealized) inside a 20%-invested sleeve; at n=9 sessions this is
EARLY_EVIDENCE at best, really CANNOT_DISTINGUISH from zero. The 80% cash
fraction means PC-PAPER's realized beta to the market is mechanically ~0.2,
which is why its return tracks SPY's own-window number almost exactly
regardless of what the 10 names do — that mechanical fact, not stock
selection or market timing, is what keeps it "ahead."

---

## 5. The 10 worst — one row each, error type named

(`roi_2026-10-06.json` sorted by `roi_pct`; `fleet_manager/state/hack*.json`
for current holdings; `docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md` for fleet
history; `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md` for mirror/conviction
construction.)

| account | family | ROI | vs SPY | error type | evidence |
|---|---|---:|---:|---|---|
| mirror | website_lane | −24.48% | −28.26pp | **SIZING (unmanaged concentration)** | seeded from a 12-name discretionary book at market-value weights, 25% single-name cap (one micro-cap = a quarter of NAV); swung +7.4% Aug, −14.3%/−11.3% Jul/Sep — same bets, amplified by concentration, not a different signal |
| hack4 | alpaca_fleet | −19.74% | −20.48pp | **SELECTION / SIZING, legacy loop still live** | 11 positions incl. **RZLV 8,650 shares** — an outsized share-count bet in a speculative micro-cap alongside AAPL/AMZN/GOOG/META/NVDA-sized positions of 4–17 shares; `aat-loop-hack4` on Railway is still an active, carrying mandate (not retired) |
| hack6 | alpaca_fleet | −18.50% | −19.23pp | **SIZING / OPERATIONAL DRIFT (unmanaged positions)** | 41 fragmented odd-lot positions (ADBE 3 sh, MSFT 1 sh, GOOGL 2 sh down to ABEO 1,079 sh, ARDX 1,693 sh); ran **negative cash (−$5,388)** on 2026-09-22 (`ACCOUNTS_2026-09-22`) — a margin/leverage defect, not a selection call |
| conviction | website_lane | −9.07% | −12.86pp | **SIZING (unmanaged concentration), structurally worse than mirror** | same 12-name seed book as mirror but **no position cap at all** (`book_management.py:221`, dossier line 503) |
| hack1 | alpaca_fleet | −8.42% | −9.15pp | **SELECTION (thematic concentration)** | 24-name basket concentrated in speculative biotech/uranium/quantum (AGIO, BBIO, COGT, VKTX, PRAX, CCJ, LEU, IONQ, SYM) — a sector-concentrated bet, not diversified stock-picking |
| hack5 | alpaca_fleet | −4.19% | −4.93pp | **TIMING / EXIT (late capitulation)** | current holding is **117 shares of SPY and nothing else** — fully de-risked into the index — yet trails SPY's own +0.73% window by 4.9pp, meaning the loss was locked in by PRIOR positions before the account rotated to cash-equivalent; rotating into the benchmark after the damage, not before |
| night_books_twin "Insider SAME-DAY clusters" twin | night_books_twin | −4.63% | −6.26pp | **CONTROL DESIGN, not a strategy failure** | the PARENT book refused entry (0.00% — never traded); its `random_same_band` twin control WAS forced into the market and lost 4.6% while SPY gained 1.6% — informative about twin methodology, not about the signal |
| lib_mom_12_1_small | llm_portfolio:lib | −3.84% | −4.68pp | **SELECTION, small-cap momentum, n=6 sessions** | identical loss on parent and `__ew` twin — a real (if tiny-sample) small-cap momentum result, opposite sign from the large-cap momentum winners in §1/§2 |
| murat_live | murat_book | −3.83% | −4.64pp | **DATA QUALITY, not a real P&L** | receipt itself flags `confirmed: False`, `cash unknown`, "NOT a P&L since purchase", one name (AARD) absent from the bars panel — this number should not be read as a performance result at all |
| smallmid-quality | website_lane | −3.47% | −7.40pp | **SELECTION (pre-falsified signal, running anyway)** | the underlying `fusion (gp-small ⊕ insider)` signal **failed its own pre-registered DSR test (DSR≈0.10 after 61-candidate deflation, bar 0.95)**; the lane is a `PRODUCT_EXPERIMENT` paper-trading a signal already known not to clear a significance bar — expected behavior, not a new failure |

**Pattern across the ten:** 4 of 10 are SIZING/concentration defects (mirror,
conviction, hack4, hack6 — no cap, 25% cap, an outsized single-name bet, and
negative-cash drift respectively), 2 are SELECTION bets in a concentrated
theme that went the wrong way (hack1, smallmid-quality — the latter already
pre-falsified), 1 is a TIMING/EXIT failure (hack5, de-risked after the loss),
1 is a CONTROL-DESIGN artifact rather than a strategy failure (the insider
twin), 1 is a tiny-sample SELECTION result on the opposite side of the
large-cap momentum winners (lib_mom_12_1_small), and 1 is not a real number at
all (murat_live). **Not one of the ten losses is explained by "the market went
down" — SPY's own window was flat-to-up for every one of them.**

---

## 6. Honest verdict

**EARLY_EVIDENCE, not proven alpha, for a small number of distinct mechanisms**:
(a) the large-cap momentum/residual-momentum family behind
`lib_resid_mom_12_1_large_sealed` and its cluster-mates (6–8 sessions, n=19
books sharing one semiconductor/AI-capex basket — one rally, not 19
discoveries) deserves a frozen replication once it has 60+ sessions, not
before; (b) `revision_flow_v0` / `pers_revision_flow_leaders` (net-raises /
analyst-revision basket, 6–8 sessions, a DIFFERENT exposure from (a) by
Jaccard) is a second candidate worth a longer shadow twin; (c) `tsmom-overlay`
(39 sessions, lowest drawdown of any website lane, lowest correlation to the
conservative/aggressive cluster) is the one website lane that looks like it
might be doing something other than "less volatility" — worth tracking past
60 sessions. **Everything else that is "ahead" is an exposure clone**: the 105
twin accounts are controls, not strategies; conservative/balanced/aggressive/
conservative-atr are one risk-dial family (pairwise corr 0.89–0.98); mirror and
conviction are the same 12-name book at two different (missing) risk caps; and
roughly half of the remaining 35 non-twin "independent" winners share 2–4
tickers from one semiconductor/memory/AI-datacenter-capex rally that happened
to lift whatever momentum or revision screen was holding them in late
September. No number in this note should be read past what its session count
supports — most of the winning side is 6–9 trading sessions old.

---

## Follow-ups for an Opus builder

1. **Build `xs_ranker`-style holdings-overlap + correlation clustering as a
   scheduled receipt** (not a one-off research note): run the Jaccard
   clustering of §2 on every `llm_portfolio` refresh and print
   `n_nominal_winners`, `n_distinct_clusters`, `largest_cluster_share` on the
   paper-accounts ROI receipt itself, so "148 ahead" is never reported again
   without its collapse factor beside it.
2. **Give mirror and conviction the position cap the 2026-08-02 dossier
   already specified and never shipped** (`book_management.py:221`, "the lane
   the concentration finding is about has no cap at all") — this is a
   one-line enforcement of an already-diagnosed defect, not new research, and
   it is the single highest-leverage fix in this note (−24.5% and −9.1% are
   both attributable to the same missing guard).
3. **Investigate hack4/hack6 as an operational audit, not a strategy
   question**: confirm whether `aat-loop-hack4`/`aat-loop-hack6` are still
   live on Railway, whether hack6's negative-cash margin state recurred after
   2026-09-22, and whether RZLV-sized bets are a one-off or a recurring
   pattern in hack4's policy — this is closer to `silent-fragility-audit`
   territory than to a signal-quality question.
