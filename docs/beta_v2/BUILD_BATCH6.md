# Beta V2 build batch 6: native fairness adoption and private evidence

Current source and evidence update, 25 October 2026 at 15:53 UTC.
The source branch now includes the cross-host front-burst correction. It counts
actual dequeues under the existing pool lock and allows an article to break a
front burst only when the unchanged scheduler places that article in its original
ready, minimum-in-flight winning group. It preserves the key tuple, readiness,
non-front ordering, pacing and quotas; it promises no elapsed time or body yield.
Independent source/portable review passed, followed by actual build-checkout
102 tests and 26 subtests, plus 154 guard/reachability tests. Native adoption of
this global correction is still pending. The existing native per-host reader
continues; its separate 900-second window and one article are described below.

Original full local CI finished with 41 failures and 16,201 passes. Its log is
retained. Independent triage identified 37 mocked-browser tests contending with
the real shared paper lock and four public-mode assertions observing personal
mode. A test-only fixture now redirects only the exact paper-lock path in four
mocked test modules, retaining the real lock implementation and unrelated paths.
Actual checkout verification passed 306 tests with three skips, including all
41 original failure nodes. Child test processes explicitly set public mode and
dotenv opt-out. This targeted closure is not a fresh full-suite PASS.
Hosted runs for 41ef5c4b and 3808c4ff never started either job: annotations report
payment failure OR an Actions spending-limit condition. No account settings or
manual reruns were changed. The older c598 hosted PASS is dated source evidence.

WRDS January-August 2025 now has 32 completed private IBES table partitions:
2,370,282 raw table rows and 1,272,979,903 typed-file bytes. Each month has its own
independent all-row hash/column/OID/date/count and owner-closure checks. These are
raw partial historical records, not unique entities, PIT qualification or current
coverage. August contributed 328,992 rows and 173,967,676 bytes; its owner and
worker exited, connection closed and exclusive lock was released. Further fixed
months require separate reviewed packets within the existing bounded window.
Licensed rows, stored article text and operational receipts remain outside Git.

The one-article copied-file auditor also passed independent source review and
an actual private frozen-file consistency audit. The claim pointer is null and
all downstream event/forecast/position consumption remains UNKNOWN. This proves
consistency of the supplied copies; it does not prove native authenticity, text
quality, publisher completeness or inference. Full C04 and Beta acceptance remain
open. Draft PR55 is unmerged and undeployed; NAV/history and the IIF task remain
protected. Earlier pending statements below are dated history.


Latest snapshot after the completed follow-up and independent article review.
The separate900.221594-second window retained59 hash-bound snapshots:52 with
two open tabs and7 with one; page starts18 to34, zero reader errors/orphans and
two still open. The receipt has32 cumulative generation timings, while15 recorded
completion clocks fall inside this window:11 fronts,3 robots and1 article;
14 OK and1 BLANK front. These are distinct clocks and denominators.

One new article is now file-bound in this generation. The earliest sampled
witness is13:59:16Z within the900-second window. Independent readback joined
the source/item/generation IDs,14,245 file bytes,5,915 text characters, file/text
hashes, page_kind=article and duplicate=false. Its stored first_seen13:58:40 is
metadata, distinct from the witness and later independent readback. This item
was not among the100 initial carry IDs; input carry accounting does not prove
those articles were read. Text quality, publisher completeness, typed inference
and forecast/position delivery remain unqualified. Both observers are closed;
the existing native reader continues.

January-April's16 private IBES partitions now total1,190,196 raw table rows and
644,211,660 typed-file bytes. April contributed322,030 rows/172,579,205 bytes;
each month has a separate coordinator full-stream hash/column/OID/date/count
and closure-identity audit. These totals are not unique/PIT/current coverage.
May is a new source packet in preparation, not a completed download here.

A pure source counterexample also confirms a remaining cross-host limitation:
continuously replenished fronts on another eligible host can delay an article
despite the per-host burst rule. This is not permanent native starvation; the
new article demonstrates actual progress. A separately staged global-burst
candidate is being built privately, with no native or build-source adoption.
The current `_key` tuple, scheduler readiness, quotas and existing guards remain.

The following600-second and initial adoption details remain separate historical
captures; their earlier900-second pending statements are superseded above.

Refreshed after independent review, 25 October 2026. The completed window is
**QUALIFIED_PROGRESS_BODY_OPEN**: 13:33:36.698703–13:43:36.767150Z,
600.068447 seconds,40 hash-bound snapshots:37 with two open and3 with one,
pages2→12,10 completed front reads/allOK, zero reader errors/orphans/bodies.
Twelve owned targets are10 completions plus2 still open. Six
PAYWALL_CHECKOUT_FRAME log observations are not extra completions, bodies or
transactions. Mechanics/progress is qualified; body/inference/C04 acceptance
remains open. A separate900-second follow-up/session16525 started once at
about21:49 on the same pool/generation and a different output directory. It is
running, NOT ACCEPTED; no final900-second counts are asserted.

## Actual reader transition

The old pool99808 finalized with zero active/unaccounted/open/orphan state and
100 pending carry entries. The new carry SHA256 is
`70cb8715775b56d52abfde5c38a4a023e8fed04fbb4427c521036170fb26530f`.
It is not the historical 72-entry B5 carry. The reviewed strict validator checked
native JSON, exact generation/birth, counts and original canonical item IDs.

The existing STOP protocol completed naturally: supervisor15388 ended at
21:12:20 SGT after its final digest. The independently joined log/inventory proof
records no forced pool stop or killed IDs in that transition interval. No second
STOP or unused drain alternative was needed.

At21:20:44 the coordinator installed the reviewed minimal native pool5534455 and
new fairness helper31c638, preserving native carry accounting and unrelated
runtime source. All280 source pins matched;278 other entries were retained.
Explicit preimage/atomic backups were verified. Existing Task XML/security and
settings remained unchanged. One clean Task dispatch at21:23:27/28 used the
existing owner route.

Pool89828 launched at21:24:50. Its first fresh status at13:33:09Z/21:33:09 SGT
binds source5534455 and generation
`90382c70925516a578a5722202c3513c7dd039d634094f7c00a99761f40a3639`.
It reports reading, max/target2, two owned open tabs, and all100 carry entries
accepted/ACCOUNTED, zero rejected or unaccounted. Input consumption means queue
decisions completed, not100 articles read. Independent actual adoption review
passed with the environmental qualifications below. The completed600-second window
now has the separate qualified mechanics/body-open verdict above.

The fairness cap counts dispatches under the existing pool lock: after two
consecutive fronts on a host, a discovered admissible article can proceed after
the existing budget filter. Scheduler choice, readiness, slots, cooling, robots,
pacing and budgets remain authoritative. There is no elapsed-time/FIFO/body-yield
guarantee.

## Environment and body evidence remain scoped

The classified current-tree snapshot contains23 processes with zero sampled
broker credentials. Python/cmd processes have IGNORE_DOTENV=true; seven Chrome
processes lack that flag; the cause is unproved. The strict
all-descendant flag assertion **has NOT passed**. Its original failure remains
preserved. The separate source-scoped classification/adoption review is qualified
PASS; it is not a waiver of the stricter assertion. Future children are unobserved.

B5's exact prior600-second window had zero bodies. Later, before fairness
adoption, an independent file/text-hash readback qualified17 witnesses:
12 new article texts,2 new stock_text and3 duplicate front_text. That is14 new
persisted texts, not17 new articles. The193,714-byte readback has exact source
IDs/hashes; text quality/completeness, typed inference, forecast and affected
position joins remain separate. Do not transfer those old-pool witnesses into
the new pool's separately measured window.

## Private historical acquisition

Transcript coverage remains49 verified source creation-days, August24–October11:
10,697 headers and487,235 components. This is partial historical coverage, not
current-through-today or PIT/identifier qualification.

| Private IBES partition | Raw table rows | Stored typed-file bytes | Coordinator independent readback |
|---|---:|---:|---|
| January2025, four tables |287,586|157,621,652|PASS, no DB calls|
| February2025, four tables |323,347|174,987,267|PASS, no DB calls|
| March2025, four tables |257,233|139,023,536|PASS, no DB calls|
| Raw arithmetic total |868,166|471,632,455|Not a unique/PIT denominator|

February and March independent full-stream coordinator readbacks have completed.
April is preparation only and has not launched. All source IDs,
activation clocks and repeated/version rows remain retained. The totals are raw
table rows and artifact bytes, not distinct securities, companies or events.
No native publication, research inference or financial action follows from them.

## Source qualification and hosted CI

The budget-observability four-file change is independently source-qualified and
inactive: controlled refusal reason/no_wire metadata feeds enum counters in the
existing receipt summary. R/W semantic differences and charge/cap/routing/retry
behavior are preserved; exact native candidates are separate artifacts. W tests
passed9 with2 native-only skips; the native candidate passed11. Coordinator local
checks report9+81 PASS. No native budget-source adoption, unblock or paid retry
was performed; the historical522 refusals remain unclassified.

Current pushed source is41ef5c4b4cf77894a5239739e43d757d9e446889.
Hosted run40198323984 is **UNQUALIFIED**: both jobs did not start because the
account gate reported a recent payment failure OR a spending-limit condition.
Which alternative applies is unresolved. The earlier BlobNotFound404 was log
retrieval failure, not the code-failure cause. No hosted tests ran on this head;
no billing change or retry was made. Prior c5981b4 hosted run40191426210 remains
backend/frontend PASS for that older source only.

Draft PR55 remains unmerged and undeployed. Protected NAV/history, frozen books,
scheduler definitions and existing browser ownership remain preserved; no seed,
financial retry or strategy activation occurred. Source tests and local adoption
are not cloud deployment or parent Beta acceptance.

Optimus handoff readback verified18 files/19 pages and an exact7,830-character
page body; this is a context-transfer receipt, not runtime or inference proof.

## Exact private handoff

Private root:
`C:/Users/mrthn/aegis-recovery-evidence/beta-v2-owner-20261025/`.

- B6: `build-batch6-front-fairness-20261025/reader-transition/`:
  `NATURAL_EXIT_INDEPENDENT_REVIEW.md`, `ACTUAL_INSTALL_INDEPENDENT_REVIEW.md`,
  `NEW_POOL_FIRST_STATUS.json`, `NEW_POOL_ADOPTION_INDEPENDENT_REVIEW.md`,
  `NEW_OWNER_PROCESSES_ENV_CLASSIFIED.json`, and
  `NATIVE_600_WINDOW_INDEPENDENT_REVIEW.md` with its readback.
- B6: `HOSTED_CI_41EF_BILLING_GATE.json`,
  `C04_BUDGET_OBSERVABILITY_BUILD.md` and its independent review.
- Prior body joins:
  `build-batch5-reader-threads-20261025/reader-transition/BODY_READBACK_POST_WINDOW_2006/`.
- IBES coordinator readbacks under `build-batch3-20261025/WRDS/`:
  `raw-ibes-jan2025-to2115-20261025/COORDINATOR_ACTUAL_READBACK.json` and
  `raw-ibes-feb2025-to2200-identity-r1-20261025/COORDINATOR_ACTUAL_READBACK.json`,
  and `raw-ibes-mar2025-to2300-20261025/COORDINATOR_ACTUAL_READBACK.json`.

Wait for the coordinator's completed900-second result and independent review
before updating follow-up counts or acceptance. The600-second window is complete
with body delivery still open. Next C04b work is a bounded read-only source/body→typed/event→forecast/
position trace plan, distinguishing declared IDs from actual consumption and
co-mentions from causal evidence. No inference/provider/DB writer or new native
adoption is authorized by this handoff. Preserve prior [batch5](BUILD_BATCH5.md)
and the daily16:35–17:10 SGT quiet window and IIF task.
