# What we already know about LLMs here — read BEFORE proposing any LLM experiment

Built 2026-09-28 by SEARCHING both repos and the memory folder (not from recollection).
**[AF]** = `C:\Users\mrthn\aegis-finance` · **[AM]** = `C:\Users\mrthn\Aegis module` ·
**[MEM]** = `C:\Users\mrthn\.claude\projects\C--Users-mrthn-aegis-finance\memory\` ·
**[AAT]** = the terminal repo, seen only through memory files. `NF/` =
`[AF] backend/data/optimus/night_factory_`. Newest first. Every number has a file behind it.

**The standing answer:** no LLM arm here has shown DIRECTION or RETURN skill once a matched
control, placebo or post-cutoff window is applied. Masking works and is verifiable. The one
positive is MAGNITUDE (the investigator at h=1), and a free trailing-volatility formula beats it.

| ID | date | question | sample | verdict (key numbers) | file | open |
|---|---|---|---|---|---|---|
| AMNESIA-2 / fiction backtest, model-agnostic | 09-28 | Masked/fictional earnings set-ups, any model; scenario answer; text features | 569 clean earnings events (07-01..09-02 2026) + 30 famous, 3 levels, 3,584 DeepSeek calls, $0.66 | DeepSeek FAILED_VARIANT at every level: hit 43-45%, AUC 0.43-0.44 (inverted, week t -0.7..-1.5); ranges tie the vol prior, lose to past-earnings prior; text features ~0 after vol; A3 fiction identified 0/599; A2 with headlines 4/30 famous | [AF] `docs/TRIALS/TRIAL-AMNESIA-2-event-reaction-model-agnostic.md`; `backend/data/optimus/fiction_backtest/fb_20260928/receipt_analyze.json` | file arm (Opus) cases written, unanswered |
| X2 blind (StockBench idea) | 09-28 | DeepSeek 5-session direction/range after cutoff; named vs blinded | 40×12 weekly + 30 famous; 1,020 rows | FAILED_VARIANT: hit 48.8% / 47.9%; ranges lose to trailing sd; famous gap +23 pp SE 9 = CANNOT_DISTINGUISH | [AF] `backend/data/optimus/experiments_2026-09-28/x2_blind_20260928_receipt.json` | — |
| X2 cutoff probe | 09-28 | DeepSeek's real cutoff | 5 tickers × months | measured **2025-12**; self-report "early 2025" | [AF] `experiments_2026-09-28/x2_blind_20260928_probe.json` | — |
| X1 Kronos-small (TS model) | 09-28 | vol forecast / top-20 vs random | 26 dates post-cutoff | FAILED_VARIANT: QLIKE worse 26/26; +0.06%/mo t 0.07 | [AF] `experiments_2026-09-28/x1_kronos_20260928_post_receipt.json` | — |
| E-G1 extraction bake-off | 09-26 | which provider types news best | 240 items × 4 | DeepSeek 0.631 = NVIDIA 0.631 > local 0.622 > rules 0.556; invented analysts NVIDIA 9.7% | [AF] `backend/data/optimus/model_routing/bakeoff_E-G1_2026-09-26.json` | — |
| Investigator vs vol prior | 09-26 | LLM vs free formula on magnitude | h=1, 8 days | vol prior wins +10.2% vs +5.7% | [AF] `docs/reviews/ADJUDICATION_2026-09-26_WAVE1.md` | re-read 09-29..10-05 |
| Investigator direction | 09-26 | direction or magnitude? | return_sign h=5 | direction **−8.7%**; magnitude +5.6% | [AF] `docs/reviews/ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md` | recalibration owed |
| Thesis cards v1 | 09-25..27 | do cards forecast | 166 rows | 112/166 at p=0.50; LLM direction −7.9% | [AF] `backend/data/optimus/thesis_cards/` | delete-or-freeze listed |
| LLM factory books | 09-25 | LLM books vs twins | 61 books + 245 twins | PENDING; DeepSeek "cannot add weights" | [AF] `backend/data/optimus/llm_portfolio/leaderboard_2026-09-27.json` | read 10-26 |
| §64 ledger grading | 09-24 | are frozen LLM forecasts skilled | 14,703 → 17,484 | overall −17% / −19%; investigator +8.97% recal.; personas −28%, weight 0 | [AF] `backend/data/optimus/specialists/scoreboard_2026-09-24.json`; `NEGATIVE_RESULTS.md` §64 | — |
| N9 autopsy + measure | 09-20/21 | LLM-proposed precursors | 8,338 candidates; 11,383 reads | 0 BH-FDR survivors; $10.05 vs $2 cap | [AF] `NF/2026-09-21/N9_*` | — |
| S2 scenario gym (Qwen 7B) | 09-21 | does the call move with story twins; does it forecast | 300 cells × 6, 1,800 calls | NOT_ADOPTED: moves with story (t 4.9) but sign acc 0.42, ECE 0.315 | [AF] `NF/2026-09-21/S2_scenario_gym_run01.json` | no forward record |
| X_anon_gap | 09-14..27 | named vs masked text | 300 cells, 19 blocks | MASKED adopted every run (gap −1.6..−2.9 pp/yr, |t|<0.6); 09-27 FAILED | [AF] `NF/2026-09-22/X_anon_gap_*` | instrument broken |
| X2 belief elasticity | 09-14..27 | does the call move when only the news changes | 10,063 pairs | 0.463 vs placebo 0.350, t 31.9; not graded vs returns | [AF] `NF/2026-09-22/X2_elasticity_run01.json` | grade vs returns |
| L2 typed events (local / DeepSeek) | 09-13..27 | extraction yield, refusals | 3.5k–20k rows | refusal 0.02–2.9%; kappa 0.67–0.87; wire v1 refused 54% (enum never sent) | [AF] `NF/2026-09-13/L2_*`, `NF/2026-09-22/L2_*` | — |
| E1 event head | 09-13..26 | typed events vs shuffled events | ~280 blocks | FAILED_VARIANT every run (IC +0.0037 t 0.81) | [AF] `NF/2026-09-26/E1_event_head_run01.json` | — |
| TRIAL-R2 PANEL-B | 09-13 | masked monthly digest vs shuffled (decisive) | 19 blocks | **REJECT** net −0.26%/yr t −0.10 | [AF] `NF/2026-09-13/R2_widened_panelB_run02.json`; `docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md` | PANEL-A vs B attribution |
| L3 lookahead (LAP) | 09-12/13 | accuracy pre vs post cutoff | 435 cells | post 0.471; pre arm EMPTY; DeepSeek REFUSED | [AF] `NF/2026-09-13/L3_lookahead_deepseek_run02.json` | LAP on PANEL-A owed |
| N3 frozen embeddings | 09-11 | bge-small vs TF-IDF / shuffled | ~278 blocks | FAILED_VARIANT IC −0.003 | [AF] `NF/2026-09-11/N3_*` | — |
| L4 Qwen3-30B | 09-10..18 | throughput / refusals | — | 19.8 tok/s; refusal test never ran | [AF] `NF/2026-09-14/L4_qwen3_measure_run01.json` | — |
| C2 curriculum / C1 counterfactuals | 09-08/09 | pretrain on LLM counterfactuals | 336k cells | CURRICULUM_NOT_EARNED | [AF] `NF/2026-09-09/C2_*` | — |
| TRIAL-R2 PANEL-A | 09-08 | masked digest vs shuffled 2015-24 | 112 blocks | CONDITIONAL +16.2%/yr t 3.9, gross, canary passed | [AF] `NF/2026-09-08/R2_monthly_llm_2015_2024_run01.json` | answers not persisted |
| Lane L free inference | 09-07 | known-answer extraction | 6 docs, 47 NIM models | Qwen 7B 6/6; 12/47 NIM served | [AF] `docs/BUILD_2026-09-07b_L_FREE_INFERENCE.md` | — |
| N6b fantasy exams | 09-07 | monotone to a causal clause | 55 pairs | monotone 1.0; rank only | [AF] `backend/data/optimus/night_lab_2026-09-07/N6b_*` | — |
| Era replay v2 (blinded) | 09-06 | blinded ranking 2016-19 | 768 decisions | NOISE; 0/768 named the year | [AF] `docs/FINDING_2026-09-06_ERA_REPLAY_V2.md` | — |
| W4b supply-chain extraction | 09-06 | LLM edges carry momentum | 2,020 edges | CANNOT DETERMINE (t 1.45 → 0.30) | [AF] `docs/BUILD_CONTINUATION_2026-09-06.md` | — |
| DeepSeek price / identity probes | 08-12..09-14 | which model answers, is the ledger right | billing | chat=reasoner=v4-flash; `deepseek-flash` since 09-14 | [MEM] `reference_deepseek_v4_models.md` | — |
| Scenario bridge | 09-03 | LLM scenarios map to owned data | 20 | 5/15 fields map; models agree 0/8 | [AF] `backend/data/optimus/tracker_backtest/scenario_bridge_20260903.json` | — |
| Blind tournament | 08-29 | name-swapped sealed book | 120 | NO INFORMATION: hit 45% vs 47% null | [MEM] `project_session_20_2026_08_29_leverage_was_the_loss.md` [AAT] | — |
| IIF-1 internet investigator | 08-14 → | investigation vs snapshot | 12 nights | no verdict; below first look (40) | [AM] `TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md` | 28 nights |
| TRIAL-LEAK-1 canary wave | 08-12 | know or remember | 1,600 calls | recall 0/419; masking 0/399; positive control 7/7 | [AF] `backend/data/leakage_probe/run_meta.json` | **DiD never computed** |
| ARCHITECTURE-ARENA-1 | 08-12 | pipeline vs persona variation | halted 55% | no verdict | [AM] `TRIALS/PREREG_LLM_ARCHITECTURE_ARENA_1.md` | resume or close |
| ABLATION-1 | 08-12 | LLM portfolio value vs shuffled | 16k calls | PRESENTATION_AND_RESEARCH_ASSISTANCE (+3.4, MDE 8.2) | [AF] `docs/GRAND_ARENA_ABLATION.md` | — |
| MARKET-GRAPH-1 | 08-12 | LLM edges predict co-movement | 3,637 calls | H1 DETECTABLE ΔR² +0.001 t 4.35 (only clean positive); portfolio route closed | [AF] `docs/MARKET_GRAPH_1.md` | — |
| LLM-SWARM-1 | 08-12 | 14 personas forward | 22,607 preds | 0.30 effective ideas; graded in §64 | [AF] `docs/GRAND_ARENA_SWARM.md` | — |
| NIGHT-3 masked picker | 08-09 | LLM picks better 20 than engine | 16,320 decisions | REJECT (t 0.04 / 0.93) | [AM] `docs/NIGHT3_VERDICT_2026-08-09.md` | — |
| COHERENCE-BATTERY-1 / NAME-ONLY-1 | 08-09 | monotone; ticker+date memory | 500 pairs; 120 | MISS 3/5; UNRESOLVED (120/120 abstained) | same | — |
| **TRIAL-LLM-AMNESIA-1** | 08-08 | can an instruction make it forget | 120 events, 4 arms | instruction does nothing (15.8% = 15.8%); masked/synthetic 0/240 identified; synthetic ≈ masked (0.0004 Brier); task unlearnable | [AM] `docs/AMNESIA_VERDICT_2026-08-08.md`; `runs/AMNESIA/AMNESIA_1.json` | AMNESIA-2 (now run, row 1) |
| AMNESIA-1B positive control | 08-08 | recall when asked directly | 120 | answered 5/120, 5/5 correct (famous collapses) | [AM] `runs/AMNESIA/AMNESIA_1B.json` | — |

**Registered or designed, never run or never read:** LAP on PANEL-A (answers never persisted) ·
TRIAL-LEAK-1 difference-in-differences · ARCHITECTURE-ARENA-1 (halted) · TRIAL-N4-LLM-VETO-CAL-1
([AM] `TRIALS/PREREG_N4_LLM_VETO_CAL.md`, data absent) · TRIAL-LLM-VETO-1 / PERSIST-1
([AM] `TRIALS/PREREG_LLM_NEXT_CAMPAIGNS.md`) · TEXT-SEMDIFF-1 (power-failed) · ANALYST-LEDGER-1 ·
NIGHT-3 stratified environment · R2-Qwen3 adoption / L4 refusal test · TRIAL-DRAFT-L2 typed-events-v1
and FOREIGN-ENTRANT-IC-v0 (unsigned) · `scenario_forecasts.py` (never executed) · IIF-1 first read at
40 nights · PANEL-A vs PANEL-B attribution · X_anon_gap repair. Each path is in
`docs/research_notes/2026-09-28/llm_text_to_data_blinding_scenarios_2026-09-28.md` §1 or the table above.

**Rules this record earned:** an instruction is not a control (AMNESIA-1) · mask, then prove it with a
canary on every case (AMNESIA-1, TRIAL-LEAK-1) · contamination is sparse and dramatic, so measure it
per case (AMNESIA-1B) · always beat the free trailing-vol prior before crediting magnitude (09-26) ·
a model that remembers the REGIME by its date looks skilled on famous windows (X2) · print the served
model: `deepseek-chat` is served as `deepseek-flash`.
