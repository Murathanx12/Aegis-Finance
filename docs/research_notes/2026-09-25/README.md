# research_notes/2026-09-25 — the seven Sonnet reads behind the 09-25 roadmap

Planning session, Fable 5.1, $0 LLM spend on our side (Sonnet subagents ran on
Claude; DeepSeek untouched). Nothing was built. Each file is one agent's full
report; the roadmap cites them by name.

| file | question | one line |
|---|---|---|
| `audit_services.md` | which built services reach `u_plan`? | only `xs_ranker` (23 price features). Three other allocators reach nothing. congress/ARK/13F collectors write ~zero rows locally. |
| `audit_ops_7d.md` | what did the machines do this week? | §64 reproduced live; forecast accrual dead since 08-27; $19.03 DeepSeek lower bound; OpenClaw spend invisible; PC-PAPER flat and possibly unconnected; fleet loops Online. |
| `research_bloomberg.md` | the challenge, verified | Oct 12–Nov 13, register by Oct 5, WLS incl. small caps, ≤20%, Relative P&L; winners by variance; top-3% ≈ +5%. |
| `research_fda_catalysts.md` | FDA dates + free sources + analyst literature | 11 primary-verified PDUFA dates; openFDA key; analyst NAMES only via paid Benzinga; revision/identity literature. |
| `research_themes.md` | Murat's themes, 34 candidates with verdicts | power bottleneck confirmed; HOOD on the winning side of betting; MCD evidence against; screener fabricated upside 4-20×. |
| `research_repos.md` | small undiscovered repos + a 94-query cue | `sec-ownership-disclosures` (PIT column), `capitol-alpha`, `edgar-scanner`, `ats-jobs-mcp`; real gaps listed. |
| `research_llm_engine.md` | LLM beside the engine, 2025-26 literature | extractor → calibration → numeric sizing; no fine-tune; negative-skill floor; formulae. |
| `external_gpt_research_queue_2026-09-24.md` | the queue Murat pasted | external; its repo claims verified/refuted in the roadmap §1. |
| `book_human_ai_thematic_v0.draft.json` | the AI side of the book | 26 names + 10% cash; Murat's edits owed before freeze. |

Reuse: a future Sonnet pass should start from `research_repos.md` § RESEARCH
CUE (94 queries + rubric) rather than re-inventing searches.
