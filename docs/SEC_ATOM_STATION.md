# Offline SEC current-Atom metadata station

PRODUCT_EXPERIMENT. Local metadata traversal only; no production adoption.
Independent Astra review is required separately. E1/E2/E3/E4 authority is unchanged.

## Explicit invocation

Create an existing dedicated output directory outside all repositories and the
source tree. Supply a trusted SHA-256 pin for a small explicit snapshot manifest:

```json
{
  "schema": "sec-atom-snapshot/1",
  "adapter": "sec-current-atom-station/2",
  "source": "sec_edgar_8k_current_atom",
  "relative_path": "sec_edgar_8k_current_atom/2026-11-04.jsonl",
  "sha256": "<whole-file SHA-256>",
  "bytes": 140430,
  "observed_at_utc": "<actual current snapshot observation in canonical UTC>"
}
```

```text
python -B -m scripts.sec_atom_station --source-root ABS_NEWS_CORPUS \
  --manifest ABS_MANIFEST --manifest-sha256 TRUSTED_MANIFEST_HASH \
  --output-dir ABS_EXTERNAL_STATION --start-line 0 --line-limit 100
```

There are no active-data defaults, recursive scans, network calls, application
imports, resolver calls or collector cursor access. Exit 0: accounted metadata/
replay or explicit NO_PENDING_ROWS; exit 1: accounted quarantines; exit 2: fixed
sanitized structural/integrity refusal, with no committed cursor advancement.
The first 100 means physical lines, including blank/malformed lines. Refusals do
not cause replacement reads to obtain 100 successes.

## Identity and authority

Filing key is exactly normalized ten-digit positive ASCII CIK plus accession.
The accession's submission-agent prefix need not equal issuer CIK. Title filer,
CIK tags and filing-index URL must agree where present. Raw CIK spellings retain
source roles. Index/document filename identity, metadata version identity and
source/file/line/byte occurrence identity are separate. Amendments retain their
own accession and UNKNOWN parent. Same accession/different CIK remains distinct
and appears in explicit cross-observation ambiguity metadata. Exact repeated
bytes share a version but each physical observation retains lineage. Changed
bytes remain versions; there is no automatic supersession or earliest-clock merge.

Only 8-K/8-K/A filing-index metadata is supported. Exhibit URLs are quarantined;
no exhibit row/body is acquired, and exhibit completion always remains false.
Reported item codes remain filing categories. Tickers are bounded
HEURISTIC_DISCOVERY_HINT values only. There is no issuer-subject, security, held,
cause, forecast, owner, delivery or trade authority. A validated filer label and
CIK are descriptive registry metadata, not E1 subject/security qualification.

Raw publication and first-seen claims retain separate parsed UTC values.
Publication is ATOM_UPDATED_AS_PUBLISHED, never acceptance time. Missing, naive,
invalid, future and contradictory clocks quarantine. Valid supported row clock
claims must also be no later than the pinned snapshot observation; later values
quarantine as ROW_CLOCK_AFTER_SNAPSHOT_OBSERVATION. Invocation is not substituted. Safe clock-shaped raw values
can survive quarantine; arbitrary invalid clock strings become UNKNOWN plus a
hash. Acceptance, filing/event dates and unproven amendment parent stay UNKNOWN.
Projection and snapshot-observation clocks are later real invocation observations.
No mtime, file date or accession year supplies availability. Retrospective output
never certifies historical PIT completeness or original collection authenticity.

Output rights are SAVED_REGISTRY_DECLARATION / METADATA_ONLY /
EXTERNAL_TERMS_UNVERIFIED. No summary/body, exhibit text, arbitrary tags, private
payloads or raw input exception strings are exported. Exact HTTPS SEC index links,
bounded validated filer labels, CIK/accession, item codes, clocks, hashes and
relative local pointers are allowlisted.

## Bounded transactions and recovery

Hard byte/row bounds: one file, <=100 attempted lines, 32 KiB per complete line,
1 MiB cumulative evidence input reads (including repeated hash verification),
1 MiB aggregate committed bundle/cursor, 256 KiB cursor. All evidence reads are
charged; oversized snapshots refuse before interpretation. Whole snapshot hashes
are checked before interpretation, after projection and just before cursor
commit. A shared source/manifest revalidation gate runs after before_cursor for
both cold and recovered commits. Its reads/deadline are charged in both paths.
Manifest bytes are rechecked before cursor commit. A 30-second monotonic
processing deadline is checked throughout; it cannot preempt a blocking OS file
operation. No external/network operation exists in this module.

Each pass atomically publishes a nonempty `pass-REQUEST_ID/bundle.json` directory
containing metadata records, occurrence lineage, quarantines, receipt and proposed
cursor. The separate `cursor.json` is fsynced then atomically replaced afterward.
An OS advisory lock is released by process exit. Exact request replay validates
the input and returns its immutable bundle without duplicate writes. A published
bundle with an unadvanced matching prior cursor recovers idempotently. Partial
unpublished staging is rebuilt under the lock. Unexpected staging or redirects
refuse. Immutable bundles are never overwritten. Atomic replacement is a process-
crash protocol; power-loss durability and hostile simultaneous filesystem swaps
are not independently certified.

Cursor binds adapter/schema, source-root identity, relative file, line/byte
boundary, processed-prefix hash, full prior snapshot hash/size, version sets and
last bundle anchor. Whole prior-snapshot bytes must remain an unchanged prefix
when admitting an appended snapshot under a new manifest. Truncation/rewrite,
parser drift, missing state and cursor/anchor tamper block resume. A different
file/root requires a separate station directory; occurrence IDs preserve file
lineage. `--start-line` must match the committed physical count. A stale older
request after later advancement refuses a cursor conflict rather than rewinding.
New snapshot observations never backdate earlier availability.

Receipts reconcile attempted = projected_new + exact_replays + quarantined +
explicitly_excluded, with changed_versions a subset of projected_new. They expose
remaining rows/bytes, cursor bounds/prefix, reason counts, read usage and explicit
empty/quarantine-only statuses. Coverage remains PARTIAL. State/resource exhaustion
refuses; it never drops history or leaps a cursor to stay within limits.

## Focused validation

`tests/test_sec_atom_station.py` covers identities, hints, rights, clocks,
physical-line accounting, amendments, collisions, versions, duplicate/reordered
rows, input/state/manifest tampering, missing paths, real Windows junctions,
resource caps, seven injected process-crash boundaries, partial staging, exact
replay and appended snapshots. The external evidence packet contains the exact
network/application/write-denying harness and the saved first-100 pilot. No full
backend suite, external terms verification, production scheduler, owner send or
independent review is claimed.


Version 2 changes the parser admission contract for snapshot-relative chronology.
Version-1 manifests/cursors/bundles are not silently reused or migrated. Review and
run in a fresh dedicated external station; original saved source bytes stay intact.
