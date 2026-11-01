# Staged global-price admission

This is a source-only, separately reviewed admission layer. It performs no fetch,
price adjustment, FX conversion, strategy decision or grading. It has not been
installed in any native owner. The six reviewed calendar-policy files remain
frozen. A later private acquisition and native promotion are separate workflows.

## Three explicit stages

`backend.services.global_price_admission` exposes:

1. `plan_admission(staged, *, existing, preimage_sha256, receipt,
   receipt_sha256, source_hashes, required_sessions, observed_at, owner_context)`
   is pure. It constructs a private immutable candidate parquet in memory and a
   hash-bound summary, with no file access. Pure plans have no cache-path binding
   and cannot publish directly.
2. `prepare_admission(staged, *, cache_path, receipt, receipt_sha256,
   source_hashes, required_sessions, observed_at, owner_context)` validates those
   authority inputs before touching a file, then reads one explicit existing
   cache preimage. It binds the exact raw preimage SHA256 and resolved cache path
   to a private plan. It creates no cache/candidate/audit/marker files.
   `GP.prepare_staged_admission` is a thin read-only entry to this operation.
3. `publish_admission(plan, *, cache_path, audit_dir, expected_preimage_sha256,
   owner_context, lock_timeout=60)` is the separate actual publication API.
   It requires verified ownership/source closure and the exact reviewed plan,
   path and preimage; it never discovers or defaults to a native cache path.

`prepare_admission()` with no arguments raises `AdmissionError` before file
access or publish. This is the genuine coordinator-owned shared missing-input
case; no exemption is requested. Missing receipt/target/owner inputs likewise
refuse before reads. Owner/source closure is checked before publish path access.

The returned `AdmissionPlan.summary` is a fresh decoded copy; candidate bytes
remain private in memory. `plan.sha256` binds its complete record, including
candidate hash, source receipts, targets, clocks, owner and prepared cache path.
Source and staging arguments are never mutated.

## Staged frame and externally verified receipt

The explicit frame has exactly GP's first seven columns, in order:
`symbol, date, open, high, low, close, volume`. There are 1–256 rows, one exact
row per requested symbol/target. Symbols must already be canonical exact vendor
keys; no case folding, alias or suffix inference occurs. Date values must already
be local session dates: canonical ISO date strings, `date`, or naive midnight
timestamps. A timezone-aware timestamp or intraday timestamp is refused rather
than stripped, shifted or guessed into a session. Original timestamps/timezones
and original session labels remain in the externally retained raw artifact.

All OHLC values must be finite, numeric, positive and not boolean. Volume must
be finite, numeric and nonnegative; zero volume is valid, zero price is not.
Low must be no higher than open/close, which must be no higher than high.
Duplicate keys, missing columns, partial coverage or different target dates
refuse the entire batch. No missing or invalid value is synthesized.

The generic receipt is independent of C02's internal file format. Its canonical
JSON SHA256 is supplied separately as `receipt_sha256`, from external receipt
verification. Hash matching alone does not authenticate a vendor: the coordinator
must verify the retained raw artifact/receipt before providing its expected pin.
`source_hashes` is the nonempty externally verified artifact-name/SHA256 mapping,
which must equal the receipt's mapping. The layer does not open those sources,
fetch missing data or claim it independently verified their contents.

Required receipt fields:

| Field | Contract |
| --- | --- |
| `schema` | `staged_ohlcv_receipt/1` |
| `receipt_id`, `source` | Nonblank receipt identity and actual source label for new cache rows |
| `staged_sha256` | `staged_sha256(frame)` over the exact ordered logical OHLCV rows |
| `source_hashes` | Exact supplied nonempty artifact-name/SHA256 mapping |
| `auto_adjust`, `fx_converted`, `dividend_adjusted` | Exactly boolean false |
| `price_basis` | `UNADJUSTED_LOCAL` |
| `session_label_basis` | `EXPLICIT_LOCAL_SESSION_DATE` |
| `observed_at` | Aware instant exactly equal to the supplied observation |
| `retrieved_at` | Aware source acquisition instant, no later than observation |
| `currency_by_symbol` | Exact requested keys and explicit three-letter local currency labels |
| `calendar_policy_sha256` | Externally verified completed-session policy/proof authority binding |
| `completed_sessions` | Exact symbol keys, with the per-symbol fields below |

Each completion item supplies `symbol`, `session`, `calendar`,
`exchange_timezone`, `close_at`, `eligible_at`. Symbol/session must match the
requested key and exact target. Calendar is an explicit four-character key;
exchange timezone is a valid named timezone. Aware close must fall on that local
session date; eligibility must be exactly close + 90 minutes and no later than
retrieval/observation. The caller owns the reviewed calendar/listing authority:
this layer checks the bound receipt's internal clock/key consistency, not an
independent exchange/vendor query or new listing classification. Required-session
coverage cannot be inferred from historical presence or the legacy `n_ok` count.

New cache rows use `receipt.source` and the verified acquisition instant as
`pulled_utc`. This metadata does not update the separate daily fetch marker.
All full receipt/source/clock/policy bindings appear in the plan/audit summary.

## Append and preservation rules

The existing cache must be readable parquet with exactly `GP.COLUMNS` in order,
naive `datetime64[ns]` dates, unique keys and stable `(symbol, date)` sort order.
Missing/incompatible, duplicate or unsorted preimages are refused, not repaired.
The candidate uses GP's stable mergesort and `index=False` parquet semantics.

An existing key with exactly equal numeric OHLCV is skipped idempotently. Its
OLD `source` and `pulled_utc` values remain untouched. Any changed existing
OHLCV field refuses the whole batch, including otherwise admissible new symbols.
No historical restatement, deletion or existing-key correction is performed.

New rows are cast to existing dtypes only when numeric values and metadata are
exactly representable. Lossy casts (including fractional volume into integer
volume) refuse. Candidate construction preserves object scalars before casting;
the lossless checks compare directly with the original normalized rows, before
any pandas inference can become the reference. A mixed integer/fraction batch
cannot silently round an exact integer such as 2**53+1. Exactly representable
mixed values remain supported. The old rows must remain an exact dtype-preserving subsequence
of the sorted candidate, both before serialization and after parquet readback.
Unrelated legacy NaNs are preserved rather than repaired. Summary provenance
includes preimage/candidate byte hashes, old/new/skipped counts, exact new keys,
source bindings and the preservation convention. The raw predecessor copy also
preserves all original parquet bytes, independently of logical row equality.

## Publication and owner closure

Planning context requires `workflow: STAGED_PRICE_ADMISSION`, a nonblank
`owner_id` and a safe unique `operation_id`. Planning makes no owner-exclusivity
claim. Actual publish additionally requires all of:

- `legacy_writers_closed`, `exclusive_owner_verified`,
  `source_adoption_verified`: exactly true, based on coordinator-verified facts;
- `ownership_receipt_sha256`, `source_adoption_sha256`: exact verified evidence
  and complete source-adoption bundle pins;
- `admission_plan_sha256`: the exact prepared plan hash;
- `cache_path`: the exact resolved cache path bound by that plan.

These are required attestations from the coordinator's separately verified
workflow, not a capability acquired by setting unchecked booleans. This library
does not inventory/stop processes, install source, authenticate an operator,
infer exclusivity from process absence, or turn a receipt hash into authority.
The future native caller must supply verified closure; this build supplies none.
An unrelated financial carrier/R6 token does not satisfy this cache workflow.

`GP.ensure` and admission now use the same canonical cache `FileLock`. Ensure
holds it across its existing read/download/append/marker/receipt transaction.
Its UTC cutoff, fetch clock, once-a-day behavior, state path, append rule,
receipt fields and returned rows are otherwise unchanged. Invalid target/start
arguments still refuse before file access. No admission path accesses or resets
`*_pulls.json` or overwrites a normal GP ensure receipt.

**The lock does not protect against old already-imported runtime GP code.**
The coordinator must close over all actual writers and their source roots,
including long-lived processes, before promotion. DailyPass and SimOwner use R.
PrivateGrade instead runs from the pinned population-memory worktree and reads
R price panels through LB.SOURCE_ROOT; it is not an installation target of this
build. A process snapshot with no observed writer, a scheduled next-run time,
or a read-only grader receipt is not proof of exclusive ownership. Existing
PrivateGrade/calendar source pins remain untouched.

Under the cooperative lock, publish checks the expected preimage again and
revalidates preserved rows/dtypes. An idempotent no-change plan returns without
replacing bytes or creating audit/backup files. Otherwise it exclusively reserves
`admission_<operation_id>.json`, writes an exact predecessor copy with exclusive
creation, fsyncs a uniquely owned candidate temporary file beside the cache,
checks hashes and rechecks the preimage immediately before `os.replace`.
The replacement is atomic. The owned audit becomes PUBLISHED only after cache
hash readback; preimage mismatch never overwrites the new predecessor.

Failed pre-replacement operations retain a REFUSED audit/predecessor copy when
already created, and remove the owned candidate temp. Failures before authority
or preimage validation create no audit/backup files. Operation receipt collisions
never overwrite somebody else's evidence. Failure after replacement is reported
as `AdmissionError(..., published=True)` / PUBLISHED_UNVERIFIED; no automatic
rollback can overwrite another writer's changes. Audit finalization failures
are explicit. The raw backup is retained for later attended assessment.
FileLock's persistent `.lock` file is not an orphan candidate and is not deleted
as lock cleanup.

## Verification and native boundary

All publish exercises use fresh pytest temporary caches, fake raw receipt pins,
fixture owner-closure attestations and no native paths or downloader. Tests cover
concurrent publishers, ensure/admission serialization and two concurrent ensures,
stale and mid-operation changed preimages, overlap conflicts, partial-input zero
file access, source/clock/FX/mark refusals, backups, old values/dtypes/order,
idempotency, atomic-replace failures, post-publication audit failure and cleanup.
Existing GP tests verify legacy once-daily markers, cutoff and receipt behavior.
The coordinator owns the shared missing-input test; independent review follows.

Frozen source pins, commands and outcomes are in the private
`build-batch3-20261025/C10_PRICE_ADMISSION_BUILD.md`. No native promotion, market
API call, install/adoption, scheduler or paper-history mutation, commit, stage,
push or deployment is part of this source build.
