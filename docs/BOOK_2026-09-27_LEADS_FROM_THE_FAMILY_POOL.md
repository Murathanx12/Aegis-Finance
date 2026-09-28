# Book 2026-09-27: leads from the family pool, on the forward clock

> **PRODUCT_EXPERIMENT. HINDSIGHT leads, not claims.** Every rule here was registered 2026-09-26, after every month its backtest is scored on. These books exist so that the one comparison that produced each lead -- the rule against its characteristic-matched random twin -- is repeated on months nobody has seen. $0 LLM spend. Every number below is read from `backend/data/optimus/bridge/leads_2026-09-27.json` (the freeze log, written by `python -m scripts.bridge_report freeze-leads`) or the receipts it names.

- **Run:** `2026-09-27T082553Z` (`backend/data/optimus/signal_structure/family_pool_2026-09-27T082553Z.json`, `backend/data/optimus/signal_structure/matched_twins_2026-09-27T082553Z.json`, `backend/data/optimus/strategy_library/leaderboard_2026-09-27T082553Z.json`). No factory run: the stored receipts and parquets of that run.
- **Decision date** 2026-09-27, bars as of **2026-09-25**, entry at the **2026-09-28 open** (`llm_portfolio.entry_session`). $1M paper each, long-only, never re-weighted.
- **Chance.** The expected number of cells passing the (b) screen by chance was **≈ 0.8 of 288** (36 cells at t >= 2 vs the 21-draw twin in dev x P(t >= 2 | null) 0.023 in 2024-26); 2 passed. Two against 0.8 is roughly what luck alone produces; only the forward test can tell these leads apart from it.

## How the leads were chosen (written before entry)

- **(a)** `weighted` members whose mean monthly rule - twin21 is > 0 in BOTH windows, highest dev DSR (rule - twin21, dev window, n_trials = 288 cells) first, at most 3. The family `weighted` is the only one whose POOLED rule - matched twin clears t >= 2 in both windows (`family_pool_2026-09-27T082553Z.json`, `rule_minus_twin_t_ge_2_both_windows`).
- **(b)** matched_twins.cells_t_twin21_ge_2_both_windows: the cells with rule - 21-draw matched twin at t >= 2 in dev AND in 2024-26.

| `weighted` member | mean rule - twin21 dev /mo (t) | 2024-26 /mo (t) | beats twin both | dev DSR (n = 288) | picked |
|---|---:|---:|---|---:|---|
| `quality_composite_ivw@k20` | +0.54% (2.54) | -0.22% (-0.48) | no | 0.355 |  |
| `net_raises_ivw@k20` | +0.66% (2.43) | +0.34% (0.59) | yes | 0.324 | **yes** |
| `qc470_mom252_quarterly_riskparity@k20` | +1.24% (1.67) | +1.80% (1.60) | yes | 0.084 | **yes** |
| `mom_12_1_ivw@k20` | +1.27% (1.61) | +1.58% (1.28) | yes | 0.080 | **yes** |
| `gp_at_ivw@k20` | +0.40% (1.38) | -0.62% (-0.88) | no | 0.064 |  |
| `mom_flow_ivw@k20` | +0.37% (0.68) | +1.47% (1.73) | yes | 0.018 |  |
| `mom_12_1_liqw@k20` | +0.35% (0.25) | +4.78% (1.99) | yes | 0.004 |  |

"Beats its twin" is the family pool's own estimator (mean monthly rule - twin21). On the CAGR difference instead, `net_raises_ivw` is behind its twin in 2024-26 (the two estimators disagree on it; `matched_twins_2026-09-27T082553Z.json`, `rows[].sealed.rule_minus_twin`). No leaderboard field is a dev-window DSR, so the DSR here is computed on the dev-window rule - twin21 series at n = 288 (the cells the twin read looked at), and printed on the freeze log.

## The gate

The freeze gate on a lead is **construction + timing (`lead_gate`); the factory's full-rule verdict is kept beside it**: the selection booleans picked the library's headline books; these rows were picked by the matched-twin read, so selection is printed, not applied. A book that fails construction or timing is frozen as `__control` with its reasons and still accrues forward.

## The books

| book | id | cell (source) | status | gate (full factory rule) | cluster (full) |
|---|---|---|---|---|---|
| `lib_net_raises_ivw_lead_2026-09-27` | `40b3584ea3d6a2ae` | `net_raises_ivw@k20` (a) | NEW | PASS (PASS) | 103 |
| `lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control` | `4ffbfd2e83d06daa` | `qc470_mom252_quarterly_riskparity@k20` (a) | NEW | CONTROL(NAME_WEIGHT) (CONTROL(MAX_DD, FAMILY_CAP, NAME_WEIGHT)) | 170 |
| `lib_mom_12_1_ivw_lead_2026-09-27__control` | `3fd38f0d7a4dcb03` | `mom_12_1_ivw@k20` (a) | NEW | CONTROL(NAME_WEIGHT) (CONTROL(MAX_DD, FAMILY_CAP, NAME_WEIGHT)) | 170 |
| `lib_disp_short_avoid_2026-09-27` | `d93fbf2c301248ca` | `disp_short_avoid@k20` (b) | ALREADY_FROZEN_SAME_HOLDINGS | PASS (n/a) | 170 |
| `lib_mom_12_1_q_trend_lead_2026-09-27` | `1144c07902e67552` | `mom_12_1_q_trend@k20` (b) | NEW | PASS (CONTROL(TOP5_MONTH_SHARE, MAX_DD)) | 84 |

Construction notes, from the gate booleans on the log: `qc470_mom252_quarterly_riskparity` and `mom_12_1_ivw` are inverse-vol weighted and put ~15% on JAN, above the 10% name cap, so both are `__control` rows. The existing `lib_qc470_mom252_quarterly_riskparity_2026-09-27__control` (frozen by the factory's `freeze_book`) holds the SAME names at EQUAL weight, i.e. not the rule's inverse-vol construction; the new lead book is the rule's own weights. `disp_short_avoid@k20` was already frozen with identical holdings as `lib_disp_short_avoid_2026-09-27`, so no second book was frozen -- only the twins it lacked. In `docs/BRIDGE.md`, `qc470`, `mom_12_1_ivw` and `disp_short_avoid` sit in cluster 170 with the other 12-1 momentum books: they are ONE bet there, not three confirmations.

> **Annotation 2026-09-28 (lane M review F3/F4; books, ids and holdings unchanged):
> `disp_short_avoid` is a `CALENDAR_ARTEFACT`.** Under the roadmap's rule (ROBUST only if all three
> quarterly calendars beat the matched twin at t >= 2; ARTEFACT if the best one does and another
> does not reach t >= 1), read on two disjoint 21-draw twin seed sets that agree: JAJO +1.61%/mo
> t 2.32 (set B 2.35), FMAN +0.52%/mo t 0.96 (B 0.74), MJSD +0.21%/mo t 0.46 (B 0.51); cum since
> 2020 +1,207% / +275% / +233%. Per single draw the label is ARTEFACT on 22 of 42 draws and
> CANNOT_DISTINGUISH on 20. The first run's rule (v1) filed it CANNOT_DISTINGUISH; that rule was
> changed AFTER those verdicts were seen, for the reason recorded in the receipt. Calendar-neutral
> (1/3 on each calendar): rule - twin +0.81%/mo, t 1.80, 2024-26 t 0.61; cum since 2020 +466%
> (SPY +162%). The forward book was frozen on 2026-09-25 bars, i.e. on the MJSD calendar, its
> weakest. The other three leads read `CANNOT_DISTINGUISH` (seed sets agree). All four are ONE
> momentum bet: their calendar-neutral monthly returns correlate 0.84 to 0.98 (115 months).
> Receipt: `backend/data/optimus/strategy_library/calendar_offsets_2026-09-28T065615Z.json`.

## Twins (every book is graded beside these)

| book | ew | ranks k+1..2k | SPY | IWM | matched random (seed) | already on the parent |
|---|---|---|---|---|---|---|
| `lib_net_raises_ivw_lead_2026-09-27` | `bc59d47a14e8c3c4` | `0dc6584091230ad8` | `a0155f20d1f3d421` | `a834f30ec8d0538d` | `363b1e75a9e9991f` (159174771439939) | none |
| `lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control` | `2fb54ddd9dde0b04` | `380be9ef9d5ff617` | `e3bc8022d4614ea7` | `8f490967515aa87b` | `fd7efadd8fae58dc` (178737001608072) | none |
| `lib_mom_12_1_ivw_lead_2026-09-27__control` | `5d2ce60804a20d37` | `20b02566f94cbb04` | `10a06bf6b2b66c7d` | `3bdf3698ed0f0761` | `ba7cda26cb2cec30` (76948860154064) | none |
| `lib_disp_short_avoid_2026-09-27` | `9400f79fada66555` | `1201ed4bc42439f9` | `75919a39db978691` | `7f74a0198ddd1eb1` | `67903b85cf3c0b8c` (247824388598716) | ew `9400f79fada66555`, random_same_band `a46f8fec8b098b8e`, sector_etf `aa5b879f546b7cad`, spy `75919a39db978691` |
| `lib_mom_12_1_q_trend_lead_2026-09-27` | `8e78209f77acf36b` | `b67086822d079f24` | `ffa304a9e3982015` | `75e9ca596005c4f6` | `4f4b04f2d61cefcd` (210241658120454) | none |

The matched random twin is drawn by `matched_twins.draw_twins` on the factory panel of 2026-09-25: for each held name a random eligible name from the same size band x 63-session vol tercile x 12-1 return tercile, excluding the rule's own names, at the held name's weight, seeded by `matched_twins.seed_for(cell)` (the seed the backtest receipt used for that cell). Every draw on the log landed in its own cell (no fallbacks).

## Declared exposures and the stop

| book | expected sigma, 21 sessions | stop (2 sigma, 21 sessions) | beta SPY | IWM-SPY | SMH-SPY | MTUM-SPY | R2 | sigma of rule - matched twin, 21 / 63 sessions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `lib_net_raises_ivw_lead_2026-09-27` | +7.6% | -15.1% | 1.01 | 0.05 | 0.10 | 0.45 | 0.76 | +3.3% / +5.7% |
| `lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control` | +11.9% | -23.9% | 1.13 | 1.32 | 0.35 | 0.65 | 0.56 | +7.6% / +13.2% |
| `lib_mom_12_1_ivw_lead_2026-09-27__control` | +10.8% | -21.5% | 1.04 | 1.40 | 0.40 | 0.47 | 0.52 | +7.7% / +13.3% |
| `lib_disp_short_avoid_2026-09-27` | +13.3% | -26.5% | 1.11 | 1.39 | 0.30 | 0.43 | 0.53 | +8.2% / +14.2% |
| `lib_mom_12_1_q_trend_lead_2026-09-27` | +14.0% | -28.0% | 0.43 | 1.26 | 0.33 | 0.55 | 0.32 | +7.4% / +12.9% |

- sigma: book weights x the 63-session daily covariance of the held names, x sqrt(21). Betas: full-window monthly net return (cell_monthly) on etf_monthly.parquet (full window).
- Stop: declared, not traded: a frozen paper book is never re-weighted; a book at or below it on its 21-session return is flagged for review.
- sigma of rule - matched twin: sd of the monthly rule - single-draw matched twin (draw 0), full window.

## The forward test (declared now, before the first session)

**rule - matched twin over 21 and 63 sessions; the lead survives if the sign is positive in both and the 63-session z >= 1.** z_63 = (rule - matched twin over 63 sessions) / the 63-session sigma in the table above. A lead that fails is a failed forward reading of a hindsight lead, recorded in `docs/BRIDGE.md`, and nothing more; a lead that survives is a candidate for a longer forward record, not a claim.

## Holdings

**`lib_net_raises_ivw_lead_2026-09-27`** (`40b3584ea3d6a2ae`, 20 names): OKTA 3.3%, SNOW 5.6%, CRWD 3.6%, PANW 4.2%, CRM 4.4%, TGT 8.6%, GTLB 4.9%, ABNB 5.4%, ESTC 4.2%, AFRM 5.5%, NET 4.5%, AMGN 7.9%, P 3.6%, RVMD 7.0%, DELL 3.3%, DT 6.3%, FTNT 5.8%, S 4.2%, AMD 3.8%, CHYM 4.1%.

Matched twin pairs (held -> twin): OKTA->PRAX, SNOW->CSCO, CRWD->GEV, PANW->VRT, CRM->APP, TGT->WBD, GTLB->CELH, ABNB->EXEL, ESTC->HUBS, AFRM->CLX, NET->RBRK, AMGN->ADI, P->DY, RVMD->JHX, DELL->MRVL, DT->GEN, FTNT->WCC, S->ZBRA, AMD->WDC, CHYM->STM.

WORST CASE lib_net_raises_ivw_lead_2026-09-27: 20 names, sum|notional|/equity 1.00 of $1,000,000, no stop (monthly rebalance): every name at the 30% delisting fill = -$300,000; largest name (TGT 8.6%) to zero = -$86,199; whole book to zero = -$1,000,000.

**`lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control`** (`4ffbfd2e83d06daa`, 20 names): AKTS 6.3%, LIFE 5.2%, SNDK 3.2%, AXTI 2.5%, JAN 15.0%, WOLF 3.6%, MRNA 1.1%, NUAI 2.9%, ERAS 6.0%, SLS 3.7%, TXG 5.3%, ANRO 6.7%, TWST 4.3%, MU 5.0%, LITE 4.1%, MXL 3.0%, PRAX 6.8%, ORKA 7.1%, IMMX 4.8%, VICR 3.6%.

Matched twin pairs (held -> twin): AKTS->PDEX, LIFE->BW, SNDK->CRWD, AXTI->ONTO, JAN->NTCT, WOLF->APPS, MRNA->FIX, NUAI->XENE, ERAS->ADEA, SLS->VISN, TXG->SITM, ANRO->ACRS, TWST->TWLO, MU->AMD, LITE->VRT, MXL->FLEX, PRAX->FCEL, ORKA->VPG, IMMX->MRAM, VICR->PL.

WORST CASE lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27: 20 names, sum|notional|/equity 1.00 of $1,000,000, no stop (monthly rebalance): every name at the 30% delisting fill = -$300,000; largest name (JAN 15.0%) to zero = -$149,573; whole book to zero = -$1,000,000.

**`lib_mom_12_1_ivw_lead_2026-09-27__control`** (`3fd38f0d7a4dcb03`, 20 names): AKTS 6.2%, LIFE 5.2%, SNDK 3.2%, JAN 14.9%, AXTI 2.5%, WOLF 3.5%, ERAS 5.9%, ANRO 6.7%, QTTB 2.0%, SLS 3.6%, PRAX 6.7%, CLYM 5.3%, DMRA 5.2%, IMMX 4.7%, ORKA 7.0%, LITE 4.0%, MU 5.0%, MRNA 1.1%, ALMS 3.0%, TWST 4.2%.

Matched twin pairs (held -> twin): AKTS->ZURA, LIFE->IOVA, SNDK->GEV, JAN->NDSN, AXTI->ONTO, WOLF->SPHR, ERAS->RXT, ANRO->LB, QTTB->NVCR, SLS->EZPW, PRAX->EIX, CLYM->ENLT, DMRA->CGEM, IMMX->NGNE, ORKA->BELFB, LITE->MRVL, MU->ANET, MRNA->DOCN, ALMS->BHE, TWST->GH.

WORST CASE lib_mom_12_1_ivw_lead_2026-09-27: 20 names, sum|notional|/equity 1.00 of $1,000,000, no stop (monthly rebalance): every name at the 30% delisting fill = -$300,000; largest name (JAN 14.9%) to zero = -$148,507; whole book to zero = -$1,000,000.

**`lib_disp_short_avoid_2026-09-27`** (`d93fbf2c301248ca`, 20 names): AKTS 5.0%, LIFE 5.0%, SNDK 5.0%, JAN 5.0%, AXTI 5.0%, WOLF 5.0%, ERAS 5.0%, ANRO 5.0%, SLS 5.0%, CLYM 5.0%, DMRA 5.0%, IMMX 5.0%, ORKA 5.0%, LITE 5.0%, MU 5.0%, SYRE 5.0%, MLPI 5.0%, NUAI 5.0%, RVMD 5.0%, CHRN 5.0%.

Matched twin pairs (held -> twin): AKTS->PAYS, LIFE->BELFB, SNDK->STX, JAN->SLF, AXTI->TXG, WOLF->ACMR, ERAS->KALU, ANRO->FNKO, SLS->PUMP, CLYM->SUPV, DMRA->HLF, IMMX->GHM, ORKA->URGN, LITE->DELL, MU->GEV, SYRE->TNGX, MLPI->PFIS, NUAI->INBX, RVMD->JHX, CHRN->LB.

WORST CASE lib_disp_short_avoid_lead_2026-09-27: 20 names, sum|notional|/equity 1.00 of $1,000,000, no stop (monthly rebalance): every name at the 30% delisting fill = -$300,000; largest name (AKTS 5.0%) to zero = -$50,000; whole book to zero = -$1,000,000.

**`lib_mom_12_1_q_trend_lead_2026-09-27`** (`1144c07902e67552`, 20 names): AKTS 5.0%, LIFE 5.0%, SNDK 5.0%, JAN 5.0%, AXTI 5.0%, WOLF 5.0%, ERAS 5.0%, ANRO 5.0%, QTTB 5.0%, SLS 5.0%, PRAX 5.0%, CLYM 5.0%, DMRA 5.0%, IMMX 5.0%, ORKA 5.0%, LITE 5.0%, MU 5.0%, MRNA 5.0%, ALMS 5.0%, TWST 5.0%.

Matched twin pairs (held -> twin): AKTS->PUBM, LIFE->AGL, SNDK->CRWD, JAN->BBT, AXTI->ASX, WOLF->KALU, ERAS->MAN, ANRO->GSIT, QTTB->CHRN, SLS->CELC, PRAX->SIMO, CLYM->OILU, DMRA->QMCO, IMMX->JBIO, ORKA->PRM, LITE->DELL, MU->PANW, MRNA->LSCC, ALMS->MTRN, TWST->AGX.

WORST CASE lib_mom_12_1_q_trend_lead_2026-09-27: 20 names, sum|notional|/equity 1.00 of $1,000,000, no stop (monthly rebalance): every name at the 30% delisting fill = -$300,000; largest name (AKTS 5.0%) to zero = -$50,000; whole book to zero = -$1,000,000.
