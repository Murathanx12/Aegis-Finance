# Beta V1 operational review — 12 October 2026

Checkpoint at 08:14 Singapore time; reader observation at 08:10:35. Later evidence is additive to the frozen review. This is current evidence, not an activation or whole-beta acceptance. It supersedes the older delivery/restoration statements that CI was pending and the collection stack was still paused. Original receipts and failures remain unchanged.

| Existing book | Recorded window | Return | Matched SPY |
|---|---|---:|---:|
| Revision flow, personal simulator | September 28–October 9 | +10.599% | +1.330% |
| Net raises, library simulator | September 28–October 9 | +9.759% | +1.330% |
| Hack2, broker paper; 10/30 daily observations | August 28–October 9 | +5.517% | +1.219% |
| Website mirror | June 16–October 9 | −24.547% | +4.289% |
| Hack4 / Hack6, broker paper | August 28–October 9 | −22.048% / −18.183% | +1.219% |

Revision flow, net raises and Hack2 worked over those periods. They remain separate from the new Beta experiments. Net raises exceeded its matched random comparison by 7.066 percentage points. Complete dollars, cash flows, fills and historical loss attribution remain unavailable. See the [measured results](BETA_SPRINT_MEASURED_RESULTS_2026-10-11.md) for policies, sizing, exits and available contributors.

The new H21 retrospective check charges basket and SPY the same 50 basis points per round trip. Across 109 overlapping windows, mean returns were 8.1464% versus 2.7555%; 39 baskets lost and 45 underperformed. Eight strictly non-overlapping windows reduced the mean gap to +0.6401 percentage points, with a −4.8753-point median gap and five losses. These are direction checks on partially qualified price history, not a new forward track record or demonstrated news/analyst advantage.

| Area | Current status | Evidence and limits |
|---|---|---|
| Release | Implemented, tested, integrated and deployed | PR #31; 15,130 local backend tests passed, three frontend checks passed. Required PR/main CI passed. Production subsequently reached `97a9129a` with the exact two reviewed public health assets. |
| Health panel | Publicly observed | 82 reviewed rows; `health_alarm/1`; RED 34, AMBER 3, BLUE 17, GREEN 28 at the saved readback. Expired evidence does not remain green. This is a published PC snapshot, not a continuously refreshed PC stream. |
| Strict deployment canary | Failed, preserved | Exact commit, fresh NAVs, scheduler, jobs, registry and every existing lane segment passed. The unchanged 36,921-record migration warning and newly exposed system warning verdicts keep the saved full canary false. A separate 08:14 machine refresh reports 50 due unresolved arena forecasts and zero forecast accrual for three calendar days; this later alert is being checked against the trading-day schedule, not overwritten into the frozen canary. No checks were waived. |
| OpenClaw | Restored and advancing | Original gateway/browser reused; owned reader holds removed and original tasks restored. The latest bounded metadata observation recorded 309 pages, READING, and 157 successful reads in the preceding hour. Across a separate 223-second short monitor, 13 new records were classified, 12 OK. Reader-status metadata was fresh but its state field remained UNRECOGNIZED_OR_MISSING; that was not coerced to green. The first twenty bounded new storage records had verified producer identities, all front/front_text. A later twenty-record subset contained front, stock_text and search context, with seventeen new URL/text pairs and no article in that subset. Novelty does not establish validated producer identity or publication dates. This does not prove a complete article-to-forecast chain. |
| Default local Qwen | Owned readiness and bounded inference observed; interpretation refused; now normally idle | Existing Qwen2.5-7B, no download. One local request completed in 5.422 seconds, 1,484 input/185 output tokens, zero API cost. It returned an invalid event enum and unsupported forward claims. The exact owned PID's native ledger records its normal idle-reaper shutdown at 06:05:57 Singapore time; later readiness is false. This is neither a crash nor a claim of currently resident inference. The on-demand lifecycle and memory/reaper guards remain enabled. A final preflight at 08:05:39 recorded 4.796 decimal GB free, below the existing 5 GB admission threshold: no restart was attempted and no memory guard was bypassed. |
| Hosted quality check | Actual refused; prospective accounting repair source-tested only | The historical DeepSeek reply contained unsupported predictions. One separately authorized current-prompt DeepSeek flash request subsequently completed: 204 uncached plus 1,280 cached input tokens, 182 output, native price estimate USD0.00016761, invoice unavailable. It returned no forward claims but an invalid fiscal event enum; the old-source/precall-cutoff quality check also refused. The original outer refusal is preserved. A disjoint-token accounting repair passed 68 inert tests, independently reviewed, with no second request or retroactive qualification. This is not validated production news. |
| Current numerical plan | Unqualified; bounded repair branch parked | The H21 numerical fit completed and all 100 instrument provenance/window/liquidity checks passed in a separate diagnostic. Two independently reviewed streamed preparation attempts were refused by the unchanged aggregate 512 MiB high-water guard with last recorded phase SERIALIZE. A distinct reviewed selective-copy constructor then used its one permitted actual attempt and was also refused at RSS_CAP/SERIALIZE, leaving only a 252,762-byte partial pending file, never parsed or consumed. All these branches are parked; the earlier 254,774-byte partial remains unchanged. No candidate or outer qualification was published. This identifies these runs' refusal, not an OS out-of-memory event or the causal allocation phase. No further preparation retry is authorized in this branch. Validation diagnostics are not a plan or a cash decision. |
| Broker safety | Observed within accessible accounts | 36 read-only GETs: five accessible accounts, 85 positions, every position stopped, zero reconciliation mismatches. Sixth-account credentials invalid. The separate protection sweep was never installed; old ownership refusals remain inactive. Existing GTC stops and scheduled reconciliation continue. |
| Learning and coverage | Implemented and partially observed | Idempotent catch-up added 22 genuine grades and zero on rerun; later fit/build artifacts consumed them. Whole-population completeness, authentic six-month news/analyst coverage and demonstrated decision/P&L improvement remain unproved. |

Private proof directory: `C:/Users/mrthn/aegis-recovery-evidence/beta-build-sprint-20261011`. Key receipts are `public-health-deployment-and-readback-independent-r1.json` (SHA `7e06149dddfee3b18fe2553c609fd03d17bfe5535ad11ff29a3f2e014fc94ef8`), `current-native-instrument-guard-fixtures-and-actual-independent-r1.json` (SHA `9904ac315644588bb5862abc88d0ab1417f648bed031e3a6ec9efe585224284f`) and `fleet-readonly-current-safety-r1.json`. The exact strict canary is `new-beta-release/after-20261011T224708Z-21b84f88/receipt.json` (SHA `915865894555567c78d660892f4127e0610407ede23de9d0d58e77ef57666330`).

The initial Astra review rated the scoped research candidate **6.5/10**. The completed additive review rates **research Beta 7.0/10** and **autonomous readiness 5.5/10, not certified**. These are maturity judgements, not profit probabilities or activation approval. See the [final review and priorities](BETA_ASTRA_OPERATIONAL_REVIEW_2026-10-12.md). The [fresh inactive Beta portfolio](BETA_V1_PORTFOLIO_2026-10-11_REVIEW.md), older ATLAS drafts and real histories remain separate. SPY has no strategic core weight.

Monday's authentic WLS membership, TMSG rules/window, instrument eligibility, policy choice, quotes and fills remain distinct Terminal gates. The original full-US-session acceptance observation has not occurred for this release. It cannot be fabricated before the market session. See the [Monday packet](BLOOMBERG_MONDAY_TERMINAL_PACKET_2026-10-12.md).

The [post-beta investment reasoning backlog](DEFERRED_INDEPENDENT_INVESTMENT_REASONING_2026-10-11.md), EXE improvements and connectors remain deferred. None was silently added to beta acceptance.

## Restoration status and exact recovery commands

The latest owner authorized restoration after review, superseding the original off-tonight instruction. Restoration was actually executed successfully. **Do not rerun it just because an older document says OFF.** The dedicated browser/profile, raw data, cursors, model files and broker services were preserved. The pause had recovered about 2.9155 GiB of free RAM; no new recovery claim is made after restarting the stack.

If a later interruption requires recovery, first inspect the current owner/task/listener state. Outside the protected 16:35–17:05 Singapore-time admission exclusion, use the reviewed existing script:

```powershell
& 'C:\Users\mrthn\aegis-recovery-evidence\beta-build-sprint-20261011\restore-stack.ps1' -Restore -EnableLocalInference
```

The model flag removes only this sprint's owned hold when its memory condition passes; it does not start or certify inference. The existing native lifecycle starts the default model on demand; its reaper remains enabled. Verify ownership and readiness before claiming model availability. Never kill process families, create a second browser owner, bypass failed ownership checks, or alter the IIF launcher.

Verified coordinator continuation:

```powershell
codex resume 01a123fa-5176-7d41-87a6-35291db143f3 -m gpt-6.1-sol -c model_reasoning_effort="medium" -C C:/Users/mrthn/aegis-finance-budgeted-roadmap
```

Reload the latest compact checkpoint and dependency queue; do not restart the historical recovery audit. Checkpoints are continuation records, not beta completion messages.
