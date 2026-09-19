# 2026-09-19 — the root-cause round (Sonnet research, Fable synthesis, Opus build)

Murat, 2026-09-19 morning, condensed: *we work on the roadmap a lot but make no decisions;
first settle HOW we work (value proposition → root of the problem → how it has been solved:
patents, research, public data); Sonnet researches, Opus builds, Fable validates and writes the
roadmap; the local model reads past/present/future news and the engine must DECIDE (buy, short,
size, why); strip the educational disclaimers for the personal build; social/video/earnings-call
text as engine inputs; attach existing repos, do not rebuild; a thesis on every closed family —
doable? why did it fail? would something else have worked?; a comprehensive context document.*

External input: `C:\Users\mrthn\Downloads\deep-research-report.md` (GPT deep-research dossier,
2026-09-18): the bottleneck is the research→decision→paper-execution artery, not discovery;
proposes a Decision Contract as the only transferable object; flags the historical FRED key in
`market-engine` history (rotate), `.mcp.json` path leak, session ids in commit trailers.

| note | agent | question |
|---|---|---|
| `research_failure_thesis.md` | Sonnet | every NEGATIVE_RESULTS section: mechanism-dead vs ruler-dead vs construction-dead; the five cheapest re-tests |
| `research_external_repos_round4.md` | Sonnet | Kronos, FreqTrade, "EskiFolio", NautilusTrader, Hummingbot, Scrapling, Osiris, Xfield: attach / later / ignore |
| `spec_social_video_pipeline.md` | Sonnet | YouTube/Reddit/X/StockTwits/earnings-call text → local-model typed variables → panel, with nulls |
| `research_murat_ideas_adjudicated.md` | Sonnet | CXMT/Micron, supplier discovery, CEO buys, politicians, options flow, ICT ritual, overnight, decision theory for construction |
| `spec_decision_contract_and_path_audit.md` | Sonnet | why the engine never says "buy X": the path, the seam, the Decision Contract, personal mode |
| `research_infra_cost_audit.md` | Sonnet | Railway ×2, DeepSeek ledger, the $1,000, the scheduler failures, the lab owning the pass and the launcher |

Facts read by Fable before the agents launched (2026-09-19 11:50-12:10 HKT):

- fleet live: hack1 $93,673 · hack3 $80,947 · hack4 $89,362 · hack5 $92,239 · hack6 $84,686 = **$440,907**
  (09-18 $448,555; 09-13 $452,832); hack2 401 (keys rotated to lane D). Never deployed.
- `AegisDailyPass` and `AegisIIF1NightLauncher` both "Interactive only", both failed today with
  0x80070520 (no logon session) after the Windows session ended overnight; last week 0x80070420 for
  four days. The lab (Startup .vbs) died and restarted three times since 09-18 13:41 (pids 10128 →
  33736 → 14192), no STOP file, no reboot (System log: last boot 09-18 06:57). The lab DID start the
  model server itself today (start 1 of 3) — chunk 16a works.
- already answered in the ledger: overnight-vs-intraday (`docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`,
  ANOMALY_CONFIRMED / STRATEGY_REJECTED; survivor = reduce exposure intraday, never overnight);
  option-implied family incl. flow (NEGATIVE_RESULTS §27, seven arms, OptionMetrics); supplier
  thesis at monthly cadence (§12; revival = event-conditioned links on daily data); LLM/agent
  trading alpha (§19: three external receipts to rebut before any LLM-signal registration);
  social media (`docs/research_notes/2026-09-11/research_social.md`, six batches).
- accruing forward, must not be re-registered: TRIAL-INSIDER-IC, TRIAL-CMP-INSIDER-IC,
  TRIAL-CONGRESS-IC, TRIAL-ARK-IC.
- CXMT: Micron −5%, SanDisk −12%, SK Hynix −8% on the CXMT IPO / Apple-testing headlines (Sept 2026);
  CXMT ~10% DRAM share, two to three generations behind on HBM.
- DeepSeek topped up $50 (Murat, 09-19). Lab cap `LAB_DAILY_SPEND_CAP_USD` = $3.

## Results (all six landed 12:20-12:40 HKT; synthesis in roadmap §14 and `docs/AEGIS_CONTEXT_DOSSIER_2026-09-19.md`)

- failure thesis: ~14 genuine mechanism deaths; SIX ruler-caused kills (§32/34/36/38/40/41); the
  short-leg rank information as an exclusion screen was flagged three times and never run; five
  re-tests ranked (exclusion screens · 13D event-window book · LLM-autopsy library · $10M re-audit ·
  TAQ costs on §22).
- ideas: 3 accruing forward (insider, congress, ARK — do not re-register); overnight and options
  flow closed with named reopeners; CXMT → a missing event class; construction → the Kelly book.
- decision path: the engine sizes (`investment_committee.compose_book`) and the fleet refuses with
  a 43-class taxonomy; no chat surface reaches either; the Ask prompt forbids sizing → Decision
  Contract spec §4; personal mode §5.
- infra: 2 Railway projects, 9 services; `aat-loop-staging` orphaned; seal-authority 404s on
  `/2026-09-19.json`; DeepSeek $56.98; lab $0; the lab owns its clock (spec §4.3).
- social: Reddit + YouTube + SEC 8-K Ex.99 lawful and free; Instagram no; X metered; five variables.
- repos: Scrapling now; Nautilus + Kronos later; Xfield unidentified.
- 12:55: the seal-authority 404s on `/2026-09-19.json` are BENIGN — 2026-09-19 is a Saturday; the loops poll for a session book that does not exist on a weekend. Not a defect; struck from the terminal list.
