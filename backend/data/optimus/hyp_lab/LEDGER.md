# hyp_lab ledger (generated; the truth is ledger.jsonl)

Rows: 67. Generated 2026-10-02T12:53:47+00:00.

## Verdicts

| hyp_id | title | family | verdict | confirm mean | t | MDE |
|---|---|---|---|---|---|---|
| H-c12383c5f7 | Oil shock -> airlines lag | macro_readthrough_commodity | CANNOT_DISTINGUISH | 0.003524 | 1.1 | 0.008971 |
| H-fc9a95991b | Yield spike -> regional banks lag | macro_readthrough_rates | CANNOT_DISTINGUISH | 0.004133 | 2.15 | 0.005386 |
| H-9ac0049bfe | Yield spike -> utilities lag | macro_readthrough_rates | FAILED_VARIANT | -0.00083 | -0.39 | 0.005888 |
| H-ae6502fd26 | Yield spike -> homebuilders lag | macro_readthrough_rates | CANNOT_DISTINGUISH | 0.002689 | 0.99 | 0.007595 |
| H-3c9e80c849 | AI leader shock -> semi equipment lag | equity_readthrough_supply_chain | FAILED_VARIANT | -0.005201 | -2.33 | 0.006256 |
| H-4d7c66c90d | Earnings shock read-through to text-linked names (next-session size) | event_readthrough_text_link | CANNOT_DISTINGUISH | 0.028808 | 0.39 | 0.20796 |
| H-242b74a461 | Earnings shock read-through to correlation peers (factor-beta control) | event_readthrough_corr_peer | CANNOT_DISTINGUISH | 0.043783 | 1.29 | 0.0951 |
| H-0508c8b2b4 | Abnormal attention predicts move size beyond priors and TF-IDF | size_attention | FAILED_VARIANT | -0.001074 | -1.72 | 0.001747 |
| H-d90a84da8c | Cross-source disagreement predicts move size beyond TF-IDF | size_disagreement | FAILED_VARIANT | -0.000128 | -0.4 | 0.000902 |
| H-57ab67541e | Event-type size prior, 2025 as a second fold | size_event_prior | FAILED_VARIANT | 9.6e-05 | 0.31 | 0.000871 |
| H-f4c998e55b | Rate spike compresses REIT dividend yield spread | macro_readthrough_rates | FAILED_VARIANT | -3.7e-05 | -0.01 | 0.009808 |
| H-70ee91a160 | Oil shock lifts tanker stocks next session | macro_readthrough_commodity | FAILED_VARIANT | -0.000884 | -0.33 | 0.007484 |
| H-d7e3faf5cb | LLM within-date size-surprise ranking adds to numbers + TF-IDF | llm_size_reading | FAILED_VARIANT | 0.004 | 0.22 | 0.049 |
| H-a37261d4a8 | DeepSeek reads earnings-surprise size from the text | llm_size_reading | FAILED_VARIANT | -0.068 | -2.41 | None |
| H-fe59c56bfe | Quality / cash-lowvol / ope_be / revision flow as investable spreads (hedged, short-twin, size-hedged, top-500 overlay) | investable_spread | FAILED_VARIANT | None | None | None |
| H-e1b7ce3a8e | Volatility-managed market exposure driven by the size forecast (rv, HAR, HAR + earnings-season intensity) | risk_timing | FAILED_VARIANT | None | None | None |
| H-ca95f10775 | Insider cluster buys (>=3 officer/director buyers in 30 days) entered at the next open after the filing | insider_event | CANNOT_DISTINGUISH | None | None | None |
| H-3b254e9abc | Part of quality_composite / cash_lowvol's twin t is restated (current-vintage) data | data_vintage | FAILED_VARIANT | None | None | None |
| H-baefacbdf9 | Tanker rates read through to refiners' crude sourcing cost | macro_readthrough_commodity | FAILED_VARIANT | -0.001873 | -0.53 | 0.009811 |
| H-3c5504c060 | Crude spike lifts integrated majors over E&Ps | macro_readthrough_commodity | FAILED_VARIANT | -0.001865 | -0.96 | 0.005417 |

## Queue (ranked by EV)

| rank | hyp_id | title | target | cell | EV | P(change) | value | source |
|---|---|---|---|---|---|---|---|---|
| 1 | H-1270b5a351 | Vol-managed market exposure for the preservation personality: drawdown-constrained utility, not log utility | return | NEEDS_CELL | 1.8234 | 0.1833 | 10.0 | hyp_lab_night_2026-09-30 |
| 2 | H-81f3e3c259 | Volatility compression breakout with frictions | return | NEEDS_CELL | 1.2756 | 0.14 | 9.54 | day_notes |
| 3 | H-65079244f4 | Yield spike lifts money-center banks next session | direction | macro_lead_lag | 1.0185 | 0.1063 | 9.68 | deepseek_gen |
| 4 | H-7cd2a074c9 | Macro lead-lag effect on interest rates | return | NEEDS_CELL | 1.0121 | 0.1063 | 9.62 | local_gen |
| 5 | H-4e1d453114 | Oil price shock lifts energy sector but drags transports | co_movement | NEEDS_CELL | 0.9996 | 0.1029 | 9.81 | deepseek_gen |
| 6 | H-811fe2c09c | Macro lead-lag effect on commodity prices | return | NEEDS_CELL | 0.9791 | 0.1029 | 9.61 | local_gen |
| 7 | H-575b8c97c1 | Post-2023 regime: yield spike -> regional banks fall next session (forward log) | return | NEEDS_CELL | 0.8338 | 0.0862 | 9.69 | hyp_lab_verdict |
| 8 | H-039df299c0 | Oil shock -> refiners and chemicals (input cost) lag | return | macro_lead_lag | 0.7967 | 0.0823 | 9.7 | world_digest |
| 9 | H-3aac7667ef | Insider cluster drift captured by passive execution (limit orders inside the spread) | return | NEEDS_CELL | 0.7809 | 0.0791 | 10.0 | hyp_lab_night_2026-09-30 |
| 10 | H-f7adb864b0 | Guidance-cut read-through to correlation peers | co_movement | event_readthrough | 0.765 | 0.1318 | 5.88 | deepseek_gen |
| 11 | H-54e0f8e467 | Regulatory approval for one firm lifts co-mentioned peers | direction | event_readthrough | 0.7643 | 0.1318 | 5.874 | deepseek_gen |
| 12 | H-ba83bf6c68 | Equity issuance dilution read-through to cash-poor peers | return | event_readthrough | 0.7619 | 0.1318 | 5.856 | deepseek_gen |
| 13 | H-f954946c67 | Clinical trial failure of one firm drags peers with similar pipeline | direction | event_readthrough | 0.7611 | 0.1318 | 5.85 | deepseek_gen |
| 14 | H-a6243b7de4 | Peer analyst downgrade spills over to thinly covered rivals | return | event_readthrough | 0.7603 | 0.1318 | 5.844 | deepseek_gen |
| 15 | H-4c3cedbde3 | Clinical trial success lifts correlation peers next session | direction | event_readthrough | 0.7603 | 0.1318 | 5.844 | deepseek_gen |
| 16 | H-ea5c9d656a | Equity issuance dilution signals overvaluation, peers follow | direction | event_readthrough | 0.7587 | 0.1318 | 5.832 | deepseek_gen |
| 17 | H-14a2b25709 | Event readthrough via peer correlations | return | event_readthrough | 0.7587 | 0.1318 | 5.832 | local_gen |
| 18 | H-7b0d6b3b19 | Co-mention read-through after regulatory approval events | return | event_readthrough | 0.7571 | 0.1318 | 5.82 | deepseek_gen |
| 19 | H-0e85ce079f | Equity issuance dilution readthrough to correlated peers | co_movement | event_readthrough | 0.7571 | 0.1318 | 5.82 | deepseek_gen |
| 20 | H-71c0a4d5c5 | Correlation-peer spillover after a clinical trial miss | co_movement | event_readthrough | 0.7556 | 0.1318 | 5.808 | deepseek_gen |
| 21 | H-10260cfe4e | Event readthrough via news co-mentions | return | event_readthrough | 0.7516 | 0.1318 | 5.778 | local_gen |
| 22 | H-08c1c21b68 | Customer guidance cut drags suppliers next session | direction | event_readthrough | 0.7296 | 0.125 | 5.916 | deepseek_gen |
| 23 | H-ae33cf8a3a | Equity issuance by peer predicts dilution fears next session | direction | event_readthrough | 0.7266 | 0.125 | 5.892 | deepseek_gen |
| 24 | H-67c554cd0c | Guidance cut by bellwether triggers supplier sell-off | direction | event_readthrough | 0.7183 | 0.125 | 5.826 | deepseek_gen |
| 25 | H-196f010209 | Supplier shock passes through to customer margin expectations | direction | event_readthrough | 0.7131 | 0.125 | 5.784 | deepseek_gen |
| 26 | H-5825bf5c78 | Digest second-order, unmentioned implications beat the vol prior | size | NEEDS_CELL | 0.523 | 0.144 | 3.66 | world_digest |
| 27 | H-9f4e8de708 | Volatility compression post-earnings | return | NEEDS_CELL | 0.5035 | 0.056 | 9.17 | local_gen |
| 28 | H-0defa565ca | Supplier shock transmits to customer via input concentration | return | NEEDS_CELL | 0.4786 | 0.05 | 9.77 | deepseek_gen |
| 29 | H-318b9f77c9 | Customer demand shock read-through to supplier basket | return | NEEDS_CELL | 0.4736 | 0.05 | 9.67 | deepseek_gen |
| 30 | H-5b816c9c97 | Size effect on analyst downgrades | return | NEEDS_CELL | 0.4696 | 0.05 | 9.59 | local_gen |
| 31 | H-ab4e3e874a | Event-prior feature increment on next-session size | size | size_feature_increment | 0.4666 | 0.125 | 3.812 | deepseek_gen |
| 32 | H-ab5ceb6f48 | Belief elasticity (X2) graded against returns | llm_capability | NEEDS_CELL | 0.4575 | 0.24 | 2.073 | closed_list_open_item |
| 33 | H-5c87bc3618 | Rate shock hits high-duration small caps asymmetrically | return | NEEDS_CELL | 0.4023 | 0.0425 | 9.7 | deepseek_gen |
| 34 | H-38ff307f01 | Commodity input shock hits downstream specialty chemical margins | return | NEEDS_CELL | 0.391 | 0.0412 | 9.74 | deepseek_gen |
| 35 | H-a23adb4c06 | Oil spike transmits to airline basket with one-day lag | return | NEEDS_CELL | 0.3811 | 0.0412 | 9.5 | deepseek_gen |
| 36 | H-3a7509ea7a | TRIAL-LEAK-1 difference-in-differences never computed | llm_capability | NEEDS_CELL | 0.3107 | 0.14 | 2.505 | closed_list_open_item |
| 37 | H-3336ff8cdd | Earnings and guidance cells as a straddle-sizing multiplier | size | NEEDS_CELL | 0.2735 | 0.075 | 3.78 | hyp_lab_verdict |
| 38 | H-92ccb2d9f9 | House PTR purchases entered after disclosure (TRIAL-CONGRESS-PTR-FWD-1) | return | NEEDS_CELL | 0.27 | 0.028 | 10.0 | hyp_lab_night_2026-09-30 |
| 39 | H-15e49ac24c | 10Y yield shock hits unprofitable small caps next open | direction | NEEDS_CELL | 0.1144 | 0.0425 | 2.928 | deepseek_gen |

## Family track record

| family | + | - | ? | P(positive) |
|---|---|---|---|---|
| macro_readthrough_commodity | 0 | 3 | 1 | 0.1176 |
| macro_readthrough_rates | 0 | 2 | 2 | 0.125 |
| event_readthrough_corr_peer | 0 | 0 | 1 | 0.1818 |
| equity_readthrough_supply_chain | 0 | 1 | 0 | 0.1667 |
| event_readthrough_text_link | 0 | 0 | 1 | 0.1818 |
| size_disagreement | 0 | 1 | 0 | 0.1667 |
| size_attention | 0 | 1 | 0 | 0.1667 |
| size_event_prior | 0 | 1 | 0 | 0.1667 |
| vol_compression | 0 | 0 | 0 | 0.2 |
| llm_size_reading | 0 | 2 | 0 | 0.1429 |
| risk_timing | 0 | 1 | 0 | 0.1667 |
| insider_event | 0 | 0 | 1 | 0.1818 |
| digest_forward | 0 | 0 | 0 | 0.2 |
| llm_belief_elasticity | 0 | 0 | 0 | 0.2 |
| llm_leakage | 0 | 0 | 0 | 0.2 |
| investable_spread | 0 | 1 | 0 | 0.1667 |
| data_vintage | 0 | 1 | 0 | 0.1667 |
| official_disclosure | 0 | 0 | 0 | 0.2 |

## Status counts

DUPLICATE_IN_LEDGER: 7, DUPLICATE_OF_CLOSED: 1, NEEDS_CELL: 20, PROPOSED: 19, RUN: 20
