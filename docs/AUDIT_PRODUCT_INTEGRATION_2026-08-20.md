# AUDIT — research component → real caller? (2026-08-20, ORDER 25 §0)

The question Murat asked, made mechanical: for each intelligence component,
is it consumed by any daily decision, any sizing, any paper book — or does it
run green and feed nothing? Verified against code, not memory. "Arena" in the
fix column = the ORDER 25 arena is now its first real consumer.

| Component | Was consumed by? | Now |
|---|---|---|
| `run_all_lanes` + book/ATR/tsmom lane engines | paper lanes (the 4 armed jobs) | unchanged (sacred) |
| multifactor PIT scores | nothing (descriptive) | **arena composite** (blended, cross-section untouched) |
| insider_opp / insider_cmp scores | nothing | **arena composite** |
| revisions scores | nothing | **arena composite** |
| PEAD / quality scores | nothing | **arena composite** |
| congress / ARK / 13F / smartgrowth / fragility-candidates | nothing | still descriptive (declared never-arms trials — correct; candidates for DISCOVERY_UNIVERSE v2 as *context*, never scores) |
| LPPL / fragility / alerts | nothing (`arms_lane: False` by design) | unchanged by design |
| COPY-LAB engine (2 seeded lanes) | **no scheduler — ran ONCE in 6 days** | **`pi_copy_lab_run` daily 10:00 ET** |
| EXPERIENCE store (night3, 16,320 rows) | no forward writer existed | **arena writes forward experiences daily (chosen + rejected + maturation)** |
| llm_analyzer product outputs | cache-only, never gradeable | unchanged (product surface) — arena perception is the gradeable path |
| llm_research (hypotheses/adversarial/diagnose) | research sessions only | **arena perception uses its ledgered `ask()`** |
| belief_state prediction ledger | IIF-1 nights + why_moved | **arena mints perception records to its OWN ledger** (never `predictions.jsonl`) |
| research_gym counterfactual surface | gym only | unchanged (G3-everywhere is a separate build item) |
| forecast_ledger (MC vs street) | measurement-only (matures 2027-07) | unchanged by design |
| winner_loser_factory / opportunity_funnel | research harness, unscheduled | v2 candidates for DISCOVERY_UNIVERSE |
| Unusual-volume tracker | **does not exist** | greenfield item (v2) |
| LGBM risk head (`risk_head_vol_lgbm_options@2.0.0`) | nothing spendable (5 routes lost to trailing vol) | stays research; arena uses the WINNING baseline (trailing 63d vol); the model enters later as a challenger book |

Bottom line: 16 of 20 daily collectors had no consumer; 6 now feed the arena
composite or are consumed by scheduled jobs; the rest are descriptive **by
declared design** (registered never-arms trials), which is not a gap.
