# C05 bounded offline IBES identity join

Current status, 27 October 2026: independent source review passed, including
237 synthetic tests. Two bounded actual runs on the same January 2025 partition
with different existing link maps also passed independent aggregate recomputation.
See [batch 7](BUILD_BATCH7.md) for results, provenance limits and exact evidence
pointers. This is an engineering diagnostic, with no PIT, research readiness,
inference, uniqueness of the original IBES records, or parent C05 completion claim.
The dated private build/review freezes retain the earlier documentation bytes;
this status-only update changes neither the consumer nor its tests.

`scripts/beta_v2_ibes_identity_join.py` is an offline CLI and aggregate-only
Python consumer. It binds January 2025 US summary `partition01.typed.jsonl` to
its exact job01 plan, root plan, completed acquisition receipt, independent
`READBACK_JOB01.json`, raw receipt freeze, original codec source, actual schema
and typed-schema witness. It neither imports the acquisition worker nor opens
its database workflow. Every source needs an explicit SHA256; absent, changed,
unqualified or contradictory evidence refuses. No file discovery or substitute
partition path exists.

The header must match the complete column order, source OID map, job/query
hashes, row count and retention flag. Only `ticker` and `statpers` are decoded,
using the original typed str/date/null roundtrip semantics. A bounded JSON
syntax scanner skips other cells without materializing their values. It never
decodes estimates, actual outcomes, fiscal labels, returns or `usfirm`; US scope
comes from the bound source table. `statpers` must be the declared PostgreSQL
DATE (OID 1082), with each parseable observation inside the job's January date
predicate. No timestamp, timezone or public-availability interpretation is made.

All source rows, including duplicates and nulls, enter the denominator. Null and
malformed required cells have separate per-column counts. Each row enters one
exclusive category:

| Category | Meaning at the raw observation DATE |
|---|---|
| `no_link` | No active historical interval for an otherwise qualified key |
| `one_unique_permno` | Exactly one active qualified link row |
| `multiple_permnos` | Multiple active qualified security identities; no selection by score |
| `overlap_one_permno` | Multiple active rows mapping to one permno, including exact duplicate link rows; unique claim refused |
| `unqualified_link` | Relevant missing/invalid interval, security identifier or score; unique claim refused |
| `missing_key_or_date` | At least one typed null required cell and neither required cell malformed |
| `malformed_key_or_date` | At least one required typed cell fails its exact type/shape/roundtrip |

Intervals are inclusive and never extended. Disjoint historical rows do not
create ambiguity at a date where just one row is active. An unknown interval
blocks that key conservatively. An unassignable link key blocks every unique
claim because its affected key cannot be established. Unqualified links with
valid intervals affect observations only inside those intervals. Source score
buckets and observation-weighted active score counts are descriptive, with no
invented pass threshold. Missing scores remain null/unqualified.

The exact historical Parquet file is SHA256 checked before decompression and
again after the full typed stream. Compressed bytes, footer size, primitive
schema, exact rows, and the sum of **all** column chunks' advertised uncompressed
bytes are checked before reading batches. Decoding projects five link columns,
disables threads/prebuffering, and checks Arrow batch bytes and per-key fanout.
These are file/metadata/materialized-batch bounds, not an OS RSS guarantee against
a malicious Parquet implementation or forged internal allocation metadata.
The file must also match the independently supplied exact source hash.

Default caps are 24 MiB/40,000 typed rows/64 KiB per line; 1 MiB per metadata
source; 1 MiB/25,000 historical link rows/128 KiB footer/16 MiB advertised
uncompressed data; 512 rows/2 MiB per Arrow batch; 512 links per ticker; 128 UTF-8
bytes per key; and 64 score buckets. A cooperative 90-second elapsed-time guard
is checked between operations. It cannot interrupt a blocked local read or
native decompressor. EOF, terminal newlines, exact bytes/rows/hash, file identity,
a second typed-file hash and all evidence/link post-read hashes must pass before
any diagnostic is returned. Failure discards all partial aggregates.

The CLI requires a caller-pinned private binding and an explicit
`--consume-one-partition` flag. It exclusively creates a new directory beneath
the private recovery-evidence root, emitting `RESULT.json` or `REFUSED.json`.
Refusals carry a controlled gate and no row counts; arbitrary exception messages
and tracebacks are suppressed. Outputs contain only aggregates and source
hashes, with no identifiers, key hashes, row examples or source paths. API
callers must retain this exception-redaction boundary.

The private build packet is under
`overnight-20261026/C05-link-readiness/build-r1` in the existing recovery-evidence
tree. `HANDOFF.md` contains the frozen source pins, exact future one-partition
command and acceptance conditions. That command has **not** been run. The
existing job-plan/receipt chain was validated using metadata and stat calls with
an audit guard forbidding opens of either the actual typed partition or the
historical link file.

Run only the focused synthetic test module with `--noconftest`, disabled plugin
autoload/bytecode/cache, a private pytest configuration and a new private
`--basetemp`; the exact invocation and results are in the private packet. This
avoids importing unrelated repository autouse fixtures that wire native stores
and model services. It is not a claim about the full backend suite.
