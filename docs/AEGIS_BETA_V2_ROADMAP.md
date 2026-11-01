# AEGIS Beta V2 roadmap

Generated from `docs/beta_v2/registry.json` by `scripts/beta_v2_registry.py`; edit the registry, then render.

Private planning baseline: 17 workstreams, 146 request mappings, 28 hypotheses. V1/V1.1 remains unverified; no runtime activation or investment acceptance is asserted.

Source rows refer to the archived owner workbook. Blank evidence and legacy aliases mean unresolved, never completed or retired. Hypothesis assignment to C09 is proposed administrative ownership only.

| ID | Workstream | Status | Owner | Dependencies | Requests | Source |
|---|---|---|---|---|---|---|
| C00 | Reconcile and preserve context | in-progress | Coordinator | None | R001, R002, R003, R004, R005, R006, R007, R008 | Roadmap row 5 |
| C01 | One roadmap and safe workspace | in-progress | Builder + coordinator | C00 | R009, R010, R011, R012, R013, R014, R015, R016 | Roadmap row 6 |
| C02 | Repair live service connections | in-progress | Operations builder | C00 | R017, R018, R019, R020, R021, R022, R023, R024 | Roadmap row 7 |
| C03 | Persistent agent and Telegram control | proposed | Integration builder | C00, C01 | R025, R026, R027, R028, R029, R030, R031, R032, R033 | Roadmap row 8 |
| C04 | News acquisition and interpretation | in-progress | Data + investigator | C02 | R034, R035, R036, R037, R038, R039, R040, R041, R042, R043 | Roadmap row 9 |
| C05 | WRDS and existing-data use | in-progress | Data engineer | C00, C01 | R044, R045, R046, R047, R048, R049, R050, R051 | Roadmap row 10 |
| C06 | ATLAS universe and task graph | in-progress | Data engineer + coordinator | C00, C01 | R052, R053, R054, R055, R056, R057, R058, R059, R060, R061 | Roadmap row 11 |
| C07 | Dynamic decisions and paper lifecycle | proposed | Portfolio builder | C02, C04, C06 | R062, R063, R064, R065, R066, R067, R068, R069, R070, R071 | Roadmap row 12 |
| C08 | RF and net-raises policy branches | proposed | Research builder | C07 | R072, R073, R074, R075, R076, R077, R078, R079, R080, R081 | Roadmap row 13 |
| C09 | Broad historical experiment factory | in-progress | Research builder | C00, C05 | R082, R083, R084, R085, R086, R087, R088, R089, R090, R091 | Roadmap row 14 |
| C10 | Population census and outcome branching | in-progress | Research + operations | C02, C09 | R092, R093, R094, R095, R096, R097 | Roadmap row 15 |
| C11 | Forecast, decision and execution learning | proposed | Data scientist | C07, C09 | R098, R099, R100, R101, R102, R103, R104, R105 | Roadmap row 16 |
| C12 | Models, retrieval and reusable skills | in-progress | Model + skill builder | C00 | R106, R107, R108, R109, R110, R111, R112, R113, R114, R115, R116, R117 | Roadmap row 17 |
| C13 | Six broker mandates and ATLAS epoch | proposed | Coordinator + owner | C07, C08, C10 | R118, R119, R120, R121, R122, R123 | Roadmap row 18 |
| C14 | Readable cockpit, workbook and design | proposed | UI + reporting builder | C01, C02, C06 | R124, R125, R126, R127, R128, R129, R130, R131, R132 | Roadmap row 19 |
| C15 | Integrated review and continued operation | proposed | Independent reviewer + coordinator | C03, C07, C09, C11, C14 | R133, R134, R135, R136, R137, R138 | Roadmap row 20 |
| B01 | AEGIS Business Plan parking area | deferred | Business researcher (deferred) | None | R139, R140, R141, R142, R143, R144, R145, R146 | Roadmap row 21 |

## C00 — Reconcile and preserve context

Deliverable: Current repo/local/runtime/Optimus differences, original review archive and override ledger

Acceptance: A context receipt names latest sources, unresolved conflicts and actual working paths; no reset

Evidence: None verified.

Revisit: Five supplied originals and full returned Consensus research archived; latest raw review TXT is heading-only. See DELIVERY.md; complete original context remains unresolved.

Legacy aliases: V1:B00

## C01 — One roadmap and safe workspace

Deliverable: Canonical task registry; logical Aegis root; branch/worktree map; source paths

Acceptance: Every active request maps to one task; unmerged and dirty work is preserved

Evidence: None verified.

Revisit: Registry, source attestation and prerequisite/slice boundaries independently reviewed; 13 legacy tasks and 73 subchunks retained. Reconcile unresolved subchunk applicability before full acceptance.

Legacy aliases: V1:B00

## C02 — Repair live service connections

Deliverable: Diagnose health alarms, protect existing paper writers, restore missing consumers

Acceptance: Producer output is read by the intended consumer and survives restart; intentional stops remain explicit

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B01, V1:B09

## C03 — Persistent agent and Telegram control

Deliverable: Owner-authenticated two-way queue; native Codex harness; resumable scheduler

Acceptance: A benign Telegram task returns evidence through the right thread, rejects impostors and resumes once

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B00

## C04 — News acquisition and interpretation

Deliverable: Adaptive multi-tab and feeds; raw/fact/hypothesis separation; source latency

Acceptance: Material event captured, interpreted and delivered to affected positions without duplicate processing

Evidence: None verified.

Revisit: Reviewed reader limits and scope-lock repair adopted locally; qualify the exact native two-tab window and stored bodies, then trace interpretation and affected-position delivery. See docs/beta_v2/BUILD_BATCH5.md; parent acceptance remains open.

Legacy aliases: V1:B06, V1:B07

## C05 — WRDS and existing-data use

Deliverable: Catalogue-first incremental CIQ transcripts plus entitled missing fields

Acceptance: Downloaded partitions join existing identifiers, support a named test and are not fetched again

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B03

## C06 — ATLAS universe and task graph

Deliverable: Versioned financial graph and linked operational/task namespace, reusing existing stores

Acceptance: Source-to-company-to-thesis-to-decision and task-to-evidence queries return traceable results

Evidence: None verified.

Revisit: Typed saved-receipt projection and eight CLI consumers independently reviewed. No causal or live portfolio adoption claim; qualify missing native lineage next.

Legacy aliases: V1:B11

## C07 — Dynamic decisions and paper lifecycle

Deliverable: BUY/ADD/TRIM/SELL/SHORT/COVER/HOLD/WAIT state machine; review triggers

Acceptance: No silent inactivity; actions and reasons reconcile to marks, orders or deliberate no-order receipts

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B02, V1:B07, V1:B11

## C08 — RF and net-raises policy branches

Deliverable: Static controls plus dynamic ranks, exposure, exits, re-entry and explicit-short variants

Acceptance: Same dates/input clocks/costs, per-family attribution and forward inception maintained

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: Unresolved; inherited-unverified.

## C09 — Broad historical experiment factory

Deliverable: Shared event panels, batch hypothesis matrix, counterfactuals and independent finalist replication

Acceptance: A resumable batch produces scoped diagnoses including invalid/underpowered cases, not just a winner

Evidence: None verified.

Revisit: Existing-data readiness adapter reviewed: five families, 21 proposed arms, zero evaluations. Qualify clocks, keys, matched controls and instruments before broad actual batches; R6 engineering proceeds independently.

Legacy aliases: Unresolved; inherited-unverified.

## C10 — Population census and outcome branching

Deliverable: Reconcile original 247, new 1,000/886/114 and dynamic descendants by IDs

Acceptance: Every requested spec has a disposition; no pending count is presented as entered or profitable

Evidence: None verified.

Revisit: Corrected exact-ID saved census independently reviewed: original247/new886; 114 waits; positive market exposure247/883; zero matured horizons. Global Oct23 marks, remote registration and intended consumers remain separate.

Legacy aliases: V1:B03, V1:B04

## C11 — Forecast, decision and execution learning

Deliverable: Calibrated forecasts, paired marginal decision contribution, regret baselines and learned trust

Acceptance: Resolved evidence reaches the learner and changes or explicitly retains a versioned policy

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B02, V1:B05

## C12 — Models, retrieval and reusable skills

Deliverable: RAG/context benchmark, investigator skill, task-specific model tournament and optional tuning

Acceptance: Same-case equal-budget comparisons identify quality/latency/cost; proposed skills remain separate from installed

Evidence: None verified.

Revisit: Source-bound packet/resume contract reviewed, changed source refusal demonstrated. Exact Optimus pickup page works; broad ranking and persistent startup adoption remain unresolved.

Legacy aliases: V1:B06

## C13 — Six broker mandates and ATLAS epoch

Deliverable: Archive/reset/identity map, new policies, single writers, $1m and $40k views

Acceptance: Owner-confirmed alias mapping and preserved predecessor histories; paper-only execution is reconciled

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B08, V1:B10

## C14 — Readable cockpit, workbook and design

Deliverable: Live health and lineage, shared stock dossiers, portable workbook/PDF and tested SVG geometry

Acceptance: Every shown metric has a clock/source; static diagrams cannot impersonate live telemetry

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B09

## C15 — Integrated review and continued operation

Deliverable: End-to-end incident/restart/replay tests, publish private evidence and truthful release status

Acceptance: Exact changed boundary reviewed; remaining work queued without repeated orientation or false completion

Evidence: None verified.

Revisit: Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.

Legacy aliases: V1:B01, V1:B12

## B01 — AEGIS Business Plan parking area

Deliverable: Retain pitches, grants, customer/product hypotheses, IP and publication tasks

Acceptance: Separate preserved register; no university endorsement, live performance or applications invented

Evidence: None verified.

Revisit: Reopen only when the owner reactivates parked business work.

Legacy aliases: V1:B10

## Hypothesis register

These are candidate questions, not registered trials or results. H01–H18 require inherited-trial reconciliation; H19–H28 are proposals.

| ID | Question | Status | Proposed task | Source |
|---|---|---|---|---|
| H01 | News adds incremental return information beyond revision flow. | inherited-unverified | C09 | Hypotheses row 5 |
| H02 | First analyst changes predict later diffusion. | inherited-unverified | C09 | Hypotheses row 6 |
| H03 | Thin analyst coverage can contain useful specialist information. | inherited-unverified | C09 | Hypotheses row 7 |
| H04 | Unusual public insider buying improves a business-economics model. | inherited-unverified | C09 | Hypotheses row 8 |
| H05 | Management execution adds information beyond industry and ratios. | inherited-unverified | C09 | Hypotheses row 9 |
| H06 | Policy surprise converts to shareholder value. | inherited-unverified | C09 | Hypotheses row 10 |
| H07 | Review tone predicts changing consumer fundamentals. | inherited-unverified | C09 | Hypotheses row 11 |
| H08 | Recovery requires improving economics, not merely a drawdown. | inherited-unverified | C09 | Hypotheses row 12 |
| H09 | Public customer shocks transmit to suppliers before full pricing. | inherited-unverified | C09 | Hypotheses row 13 |
| H10 | Fiscal spending matters only for exposed contractors. | inherited-unverified | C09 | Hypotheses row 14 |
| H11 | Negative-event information can support profitable shorts. | inherited-unverified | C09 | Hypotheses row 15 |
| H12 | Relative-value divergence is temporary rather than structural. | inherited-unverified | C09 | Hypotheses row 16 |
| H13 | Event-conditioned exits preserve more value than blunt stops. | inherited-unverified | C09 | Hypotheses row 17 |
| H14 | Scenario-linked evidence improves long-horizon thematic selection. | inherited-unverified | C09 | Hypotheses row 18 |
| H15 | Non-US events add genuinely new information. | inherited-unverified | C09 | Hypotheses row 19 |
| H16 | Agent cooperation adds value at equal cost. | inherited-unverified | C09 | Hypotheses row 20 |
| H17 | Retrieval quality improves decision reliability. | inherited-unverified | C09 | Hypotheses row 21 |
| H18 | Compact forecasting models improve a specific existing target. | inherited-unverified | C09 | Hypotheses row 22 |
| H19 | Transcript role separation improves decisions beyond full-call sentiment. | proposed | C09 | Hypotheses row 23 |
| H20 | New analyst questions and answer specificity reveal incremental operating information. | proposed | C09 | Hypotheses row 24 |
| H21 | Management promise delivery predicts later fundamental changes beyond past returns. | proposed | C09 | Hypotheses row 25 |
| H22 | A material event benefits from faster detection only while tradable price response remains. | proposed | C09 | Hypotheses row 26 |
| H23 | Context-first agent startup prevents repeated or contradictory work at lower total cost. | proposed | C09 | Hypotheses row 27 |
| H24 | Alarm-led investigation improves exit/re-entry versus price stops alone. | proposed | C09 | Hypotheses row 28 |
| H25 | A graph adds decision information beyond flat retrieved evidence. | proposed | C09 | Hypotheses row 29 |
| H26 | Adaptive browser concurrency raises usable event throughput without lowering correctness. | proposed | C09 | Hypotheses row 30 |
| H27 | Quality-adjusted independent consensus improves ranking over raw counts. | proposed | C09 | Hypotheses row 31 |
| H28 | Capacity-aware short event policies improve net portfolio outcomes. | proposed | C09 | Hypotheses row 32 |
