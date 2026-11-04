# Archived contest universe coverage diff

`scripts/contest_universe_diff.py` accounts for exact `(market, symbol)` strings
in two explicit local archives. It imports no contest collector, never selects
a directory's latest file, never calls a provider, and writes only JSON to stdout.
It does not certify inclusion in the contest. Membership remains
`UNCONFIRMED_MEMBERSHIP`; first-seen and point-in-time availability remain
`UNKNOWN`. There are no returns, strategy tests or portfolio decisions here.

```powershell
python -m scripts.contest_universe_diff `
  --old-parquet C:/archive/universe_2026-10-22.parquet `
  --old-receipt C:/archive/universe_2026-10-22_receipt.json `
  --new-parquet C:/archive/universe_2026-11-01.parquet `
  --new-receipt C:/archive/universe_2026-11-01_receipt.json
```

Exit 0 means validated descriptive accounting. Exit 2 means refusal. Input
refusals emit a fixed reason code without exception messages, paths or receipt
payloads. Argument usage errors also emit fixed JSON/exit 2; `--help` prints usage.
Success emits only counts, market codes, validated dates, fixed labels and source
SHA-256 digests. No symbol lists, company names or original receipt paths escape.
Hashes identify the bytes examined; legacy receipts do not cryptographically
authenticate their parquet. Matching provenance is established only by the
available name, date and count checks.

## Input contract and memory scope

Pass explicit regular local files, copied with their original archive basenames
`universe_YYYY-MM-DD.parquet`. The receipt's `path` basename must agree; its
strict `written_utc` UTC stamp must have the archive date. `rows_after` and
`by_market.n` must reconcile with physical rows and observed market counts.
Zero-count receipt markets represent absent coverage. The later receipt clock
must be strictly later. Screening dates are separately preserved and may precede
the archive/receipt date; future screening dates are refused.

Required columns are Arrow strings: `market`, `symbol`, `membership`,
`screened_on`. Market codes are uppercase ASCII letters (2–8 characters).
Symbols are nonblank strings up to 128 characters without ASCII control codes.
Keys are compared exactly, without case folding, stripping or issuer matching.
Duplicate keys across any batches/row groups invalidate the snapshot. Every
membership value must remain `UNCONFIRMED_MEMBERSHIP`.

The bounded CLI refuses more than 50,000 rows per archive, parquet over 8 MiB,
receipt over 64 KiB, or projected uncompressed column chunks over 16 MiB per
archive. Only four columns are decoded, in batches of 512 without parallel
decoding or prefetch; hashing uses 64 KiB blocks. No pandas/full-table load is
used. Bounds are deliberately conservative for the requested 256 MiB added-memory
budget and these small archives; this is not an OS-enforced sandbox for hostile
parquet decoders. Both input hashes are checked again after reading each archive;
use immutable copies to prevent subsequent concurrent changes.

## Interpretation

`persisted`, `old_only`, `new_only` are raw observed key accounting. For markets
present in both archives, `observed_key_entries` and `observed_key_exits` describe
per-key differences. They do not identify actual listings, delistings or ticker
renames. For an absent entire market, `coverage` explicitly says
`MISSING_OLD_MARKET` or `MISSING_NEW_MARKET`; entry/exit/persistence-percentage
fields are null. Raw old-only/new-only counts still reconcile, but must not be
interpreted as security exclusions. Provider coverage and screening changes
remain unresolved. Empty archives are supported, without invented percentages.

## Examination ledger: 2026-11-05

Engineering coverage diagnostic under CANON; no new signal or trial. The supplied
`universe-membership-20261105-r1/PROTOCOL.txt`, `REPORT.md` and `result.json`
define the initial descriptive replay and remain unchanged. Existing
`contest_calendar.py` builds/selects snapshots; this CLI intentionally does not
import it because selection/provider/runtime behavior is outside this scope.
NEGATIVE_RESULTS' survivorship and universe limitations continue to apply.
No reader, owner-warning, NAV, active runtime, scheduler or execution changes.

Focused offline validation:

```powershell
$env:AEGIS_IGNORE_DOTENV='1'
python -m pytest backend/tests/test_contest_universe_diff.py -q -p no:cacheprovider
```

The tests cover exact keys, missing markets, invalid receipts/clocks/schema,
duplicate keys across batches, counts, empty archives, separate screening dates,
sanitization, source immutability, input limits and nested unrelated columns.
The copied real pair is an explicit acceptance replay, not part of the test suite.

### Local acceptance receipt

Base: `1d2319a87c2959bd044fc1b52a37b1a10472ac18`. Focused suite:
**29 passed**. Copies live outside Git at
`C:/Users/mrthn/aegis-recovery-evidence/universe-diff-build-20261105-r1`.
At initial acceptance, the CLI ran on these real copies **once**, returned 0,
and its JSON parsed.
This validates both receipt reconciliations, uniqueness and dates. The wrapper's
resident peak assertion passed (<256 MiB for the whole CLI child process), but
its subsequent private-commit assertion failed (>=256 MiB). Private committed
memory therefore does **not** satisfy a 256 MiB ceiling. Exact memory numbers
and the parsed payload were lost because the wrapper saved them after those
assertions. The expected numerical comparison assertion was never reached.
At that point no second real invocation had been made. The original receipt
and failed wrapper are now preserved as `validation.initial.json` and
`validate_real.initial.py`. That initial run was a resident-memory pass,
not an unqualified memory-budget or complete acceptance pass. The focused
follow-up below resolves the missing persisted evidence.

Source and copy SHA-256 digests agree after execution:

| File | SHA-256 |
|---|---|
| universe_2026-10-22.parquet | `c13262db006bcabe01413abcfea7c53a06d3bdd970b176cc898fcb51aa112b8f` |
| universe_2026-10-22_receipt.json | `0699c3d507cfdc4184582c85981057550181403695104a0a8275f0cbbff68e38` |
| universe_2026-11-01.parquet | `86a58cc34b44682113f0830c431a1ecb7475025cf6ae57ba08528d1dd727d27d` |
| universe_2026-11-01_receipt.json | `eacfdaec821cb6560b52a9f68c18c3230af552ff8801750a23b1dba37c042596` |

### Focused acceptance follow-up: 2026-11-05 local

The owner authorized one additional invocation on the exact frozen copies.
Candidate source commit remains
`0b2044f93176c1b9ec787d6f8ca345c884b52a5c`; no CLI or test source was edited.
Only the external `validate_real.py` wrapper changed. It now uses
`check=False`, parses sanitized stdout and memory measurements, then writes and
flushes `real_result.json` and `validation.json` **before** evaluating any
acceptance limits or count comparisons. Nonzero child exits are retained too;
raw stderr and exception payloads are not copied into the receipt.

The additional invocation returned **0**, with persisted JSON and exact memory
measurements. `validation.json` records **PASS_LOCAL_RESIDENT_BOUND**:

| Observation | Result |
|---|---:|
| Old / new rows | 17,407 / 17,261 |
| Persisted exact keys | 17,060 |
| Old-only / new-only | 347 / 201 |
| Peak resident working set, whole CLI child | 51,412,992 bytes (49.03125 MiB) |
| Peak private committed memory | 707,887,104 bytes (675.09375 MiB) |
| Resident baseline before candidate import | 14,831,616 bytes |

Counts match the initial supplied replay's **17060 / 347 / 201**, and every
market is present in both snapshots. Source/copy SHA-256 digests above still
match; the candidate source hash is unchanged. This follow-up invoked the
candidate once (two real invocations total across initial build and follow-up).
No broad tests were rerun; the 29-test result above belongs to the initial build.

The same reader-pool PIDs **14136 / 61968** and supervisor PIDs **13572 / 6984**,
with unchanged process creation times, were observed before and after the run.
These process observations are saved in `reader_before.json`,
`reader_after.json` and the validation receipt. They establish process continuity,
not reader throughput or health. No reader process was stopped or reconfigured.

Resident RAM is the acceptance bound for this local run and passed below
256 MiB, including the child's interpreter/import footprint. Private commit is
reported separately and exceeds 256 MiB. This measurement is **not an
unconditional 256 MiB guarantee** for other files, machines, concurrent loads or
allocator behavior. No certified inclusion or historical availability conclusion
follows. No push, adoption or deployment occurred.
