# Beta generated-output route manifest ? 2026-10-10

**Status: partial metadata route inventory, not consumer acceptance or grading evidence.** This maps all 519 accepted census file-family buckets and all 791 task/horizon cells (790 attached; one explicit row-only archived evidence_memory cell). It does not read raw datasets, outcomes, cloud volumes, archive members, or protected/heldout values. The accepted census is `complete=false`; reported 507 family routes await/unverified, and protected or inaccessible means unknown, not empty.

## Population and count semantics

As-of 2026-10-10, the accepted receipt covers 72,657 files in 519 file-family buckets and 791 distinct task/horizon cells; it decoded 2,256,155 raw record observations, 1,935,470 unique identities, and 294,832 duplicate records, with 25,869 errors. These are separate census counts, not a grade count or one fungible population. Unique is within family/task/horizon; `graded` is outcome-present rows only, not skill. `due_ungraded` uses recorded calendar date only, not market-close eligibility or grading authorization. `daily_delta` is rows whose own date equals the as-of date. Cells are not events.

| Route class | Family buckets |
|---|---:|
| byte_limit_awaiting_evidence | 1 |
| candidate_static_code_route_unverified | 3 |
| consumer_or_grader_awaiting_evidence | 62 |
| context_only_awaiting_evidence | 148 |
| documented_archive_operation_plus_static_consumer | 1 |
| footer_metadata_only_awaiting_evidence | 30 |
| inaccessible_or_invalid_awaiting_evidence | 1 |
| protected_metadata_only_awaiting_evidence | 262 |
| static_code_or_manifest_declaration_only | 11 |

The 504 `awaiting_evidence` annotations plus 3 candidate-unverified routes equal 507 family routes without verified actual-consumer evidence; none is evidence of zero data. The one row-only evidence_memory cell is retained separately from file-family buckets. Per-family reason, file dispositions, declared consumer, dated horizon/task cells, raw/unique/duplicate/conflict counts, state labels, date span, daily delta, and next bounded task are in the [machine-readable family map](BETA_OUTPUT_ROUTE_MANIFEST_2026-10-10.json). Preserve the recorded outcome-present `graded` counts; actual-consumer coverage remains unverified without a dated receipt and a proven family join. Static code paths and consumer names are routing hints only.

The October 11 field review checked the existing reports without another census
or grading run. `pending` is not a verified not-yet-due count. Persisted void
counts remain recorded; official quarantine eligibility is only partly covered.
Inaccessible file/family counts cannot establish inaccessible record counts,
which remain unknown. Five observed consumer entries have candidate family
associations; exact family joins and complete coverage remain unproved. Private
review: `family-report-field-coverage/independent/independent-review.json`,
SHA256 `1f381d9a9689f3bf7dba0d501795149981eb32562b90b109d0eac301427c0eab`.

## Separate existing populations and manifests

| Receipt | Value | Unit and timestamp | Treatment |
|---|---:|---|---|
| DATA_CATALOG summary | 5,406 = 4,810 files + 596 directory rollups; 834 runtime-built | Catalog dataset rows; generated 2026-10-07 01:00Z | Stale summary; catalog rows are not output events. |
| Night-factory daily receipt | 766 new; 137 due unresolved | New forecast rows in 10.5h, as cited 2026-10-06 | Delta and due rows stay separate; not cumulative. |
| Current forecast roster in compact state | 66,546 runtime unique; 216 calendar due; 736 cloud unique; 112 immutable overlap | Separate unique populations and overlap; current state cites the accepted census | Do not add or call a grade count. |
| NN/TableShrink Oct 10 run | 1,204,330 table rows; 1,201,400 grid rows; 517 dates; 5,901 new rows since prior run | Receipt `nightly_20261010T003004Z`; last grid date 2026-10-09; grid rows are not events | Receipt status OK. Forward-grade row/outcome values not opened; separate Oct 10 grade receipt not located in bounded check, not empty. |
| WRDS manifest | 1,378 files / 84 families / 1,931,802,994 rows | Parquet files, families, rows; manifest dated 2026-09-04 | Manifest-level counts only; source values not read. |
| L2 typed-event manifest | 73,247 | typed corpus-document rows; written 2026-10-01 | Manifest count; replay consumer not independently receipted. |
| September `llm_calls` archive | 287,041 | rows; 2026-09-03 through 2026-09-30 | Manifest says archived and round-trip verified; archive operation, not grading. |
| September `evidence_memory` archive | 102,030 | rows; 2026-09-05 through 2026-09-11 | Manifest says archived and round-trip verified; archive operation, not grading. |
| Aegis module NIGHT8 manifest | 11 artifacts / 380 scalars | run-scoped manifest; 6 prior nights consulted | Counts only, no values read; do not pool with census records. |
| Aegis Alpha Terminal | manifest header present | bars manifest; cloud remains unenumerated | No grade route inferred. |
| Archive-header correction | 3,232 headers | archive header names, still UNCLASSIFIED | Preserve corrected classification; no emptiness inference. |

The R29 summary pins the Oct 10 receipt SHA-256 `FB2D78D14FCFB721D2314BDFE11AD122F25A5B3655E0EFF45C21AD0B5F915DCF`; native health was manually classified ALIVE from receipt status/time, and the forward-grade JSONL hash match does not prove any grade rows.

The catalog consumer detector searches code and docs tokens by basename/stem/family/directory; this produces static references, not runtime-consumption proof. The existing catalog CLI is `python -m backend.services.data_catalog --query <substring>`; it answers catalog presence, not actual consumer execution. The forecast grader exists at `backend/services/forecast_grader.py`, but census candidate annotations explicitly do not prove its schema, target, or actual consumption. No command was executed in this inventory. Next bounded work is to inspect existing dated consumer receipts for the listed families; where absent, keep the family awaiting evidence. Protected output routes stay metadata-only until explicitly authorized.

**Input pins:** accepted census `sha256=e7c4172df8b3804e9dcf375f8a210b27638dc814f1347293c991abc6e6aa7f10`; prior family inventory `sha256=468ba9bf87e028c0a89b4ce6900e7d1cb346a2b1da8299327ee8b79495fedd1f`; all bounded code, docs, manifests and sibling manifest pins are included in the private freeze receipt. Output hashes are in that same freeze receipt.
