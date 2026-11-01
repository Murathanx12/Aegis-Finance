# C02 admitted-universe price coverage staging

This is an explicit offline/injected API for a **price coverage receipt**, not
a production funnel candidate snapshot. No production path calls it. It makes
no ranking, eligibility, IC acceptance, refresh, or parent-completion claim.
The existing `run()`, CLI, ranking signals and stage defaults are unchanged.
Do not use the existing runner or its `--dry-run` as an offline preflight.

## Interface

`opportunity_funnel.stage_price_coverage(*, universe, provider, limits,
start_date, end_date, min_rows)` delegates to
`funnel_staging.collect_price_coverage` and returns `PriceCoverage` only on full
success. Collection performs no filesystem writes. All arguments are explicit;
there is no default provider, universe fetch, cache lookup, or retry.

The caller supplies a previously admitted, pinned universe dictionary:

```python
{
    "tickers": ["AAA", "BBB"],
    "n": 2,
    "membership_sha256": membership_sha256(["AAA", "BBB"]),
    "truncated": False,
    "source": "caller-pinned admission source",
    "fetched_at": "2026-10-23T12:00:00+00:00",
    "exclusions": {"venue": 2, "type": 1, "symbol": 0},
    "cache_provenance": {
        "mode": "injected",  # injected, cache, or uncached
        "identity": "caller-pinned input identity",
        "sha256": "<64 lowercase hexadecimal characters>"
    }
}
```

The exact membership hash is SHA-256 of the sorted ticker list serialized as
ASCII JSON with separators `(',', ':')`, without deduplication or normalization.
For example the bytes for two names are `b'["AAA","BBB"]'`. Universe order is
preserved for batching and outcomes. Empty, duplicate, malformed, truncated,
count-mismatched or hash-mismatched inputs refuse before any callback. Admission,
source membership and exclusion counts remain the caller's responsibility:
matching a caller-supplied hash does not independently prove provider admission.
The staging API does not construct or shrink an admitted universe.

`Limits(batch_size=..., max_logical_calls=..., max_batches=..., max_symbols=...)`
requires positive integers. `batch_size` is the per-batch symbol ceiling;
`max_symbols` bounds the entire invocation's requested symbols. The complete
batch plan must fit all ceilings **before any callback**, otherwise it refuses
without truncation. Each planned batch receives exactly one callback, including
when earlier batches fail. These are logical callback/batch/symbol counts, not
HTTP request, spend, time, memory, or provider-internal retry bounds. An injected
callback is trusted code; this API does not sandbox it or cancel a blocked call.

`provider(batch_id, ticker_tuple)` returns a dictionary with `source`,
`fetched_at`, `cache_provenance` in the same form, and `prices`: a list of
`(ticker, pandas.DataFrame)` pairs. Use pairs rather than a dictionary so duplicate
symbols remain detectable. Frames must have exactly `Close` and `Volume`
columns, with a unique, increasing, midnight `DatetimeIndex`, no `NaT`, and
exactly the declared first/last dates. `min_rows` is explicit. Prices must be
positive finite real numbers; volume must be nonnegative finite integral
numbers. Numeric strings, booleans, complex values, duplicate columns, empty
frames, nonfinite values, missing symbols and unexpected symbols all refuse
full coverage. Actual zero volume is allowed; failed data is never synthesized.
Fetch timestamps must include a timezone, cannot be in the future, and price
fetch dates cannot precede the requested last date.

The immutable receipt's `.report` returns a detached copy. It pins the universe,
window, limits, batch IDs, returned symbols, batch provenance and one outcome
per admitted ticker. Valid outcomes include row count, schema, first/last date,
last close/volume and SHA-256 of normalized `[date, float(close), float(volume)]`
rows. The receipt retains summaries and hashes, **not the complete price panel**.
Internal trading-session gaps, market calendars, corporate actions, historical
survivorship and freshness tolerances are not adjudicated here. Callers choose
the intended dates/minimum rows; full coverage means each admitted ticker met
that declared schema/window contract.

## Refusal and writing

`accounting_complete` means every admitted symbol received a terminal acquisition
outcome, including explicit missing/error outcomes; it does not imply usable data.
`usable_price_coverage_complete` additionally requires every symbol to validate
with no unresolved batch errors. `screened` and `outcome_counts` reconcile the
actual attempted domain. Preflight refusals retain `not_attempted` outcomes and
do not claim completed acquisition accounting. `full_coverage` is a successful
price-collection flag only; a write refusal sets it false while retaining the
separate usable-price result. `downstream.stage3_enrichment` and `.ranking` are
always `not_evaluated`, and `promotion_eligible` is always false. A complete price
receipt cannot qualify partial/unassessed enrichment, ranking, or promotion.

`CoverageRefused.report` contains `full_coverage: false`, explicit errors, usage,
batches and all supplied ticker outcomes, including not-attempted entries for
preflight refusals. Invalid-universe duplicates retain their input ordinals.
Provider exceptions retain exception type rather than raw provider text. A valid
later batch does not erase an earlier gap. No partial run returns a full receipt.

`funnel_staging.write_price_coverage(receipt, staging_dir=...)` is a separate,
explicit writer. The caller must designate an existing directory named exactly
`funnel-price-staging`. No directory is implicitly created. The writer refuses
backend trees, configured `AEGIS_REPO_ROOT/backend` and `AEGIS_DATA_DIR`, and
paths with data/cache/history/production components. It checks both lexical and
resolved paths, refusing symlink and Windows junction ancestors. This is local
path protection, not protection against a concurrent hostile filesystem actor.

The filename is `price-coverage-<receipt SHA-256>.json`. Exclusive binary creation
refuses an existing file, including a symlink at that filename. This API never
overwrites prior receipts, archives them into history, or promotes them. A failed
write removes only its own newly created file. Immutability is an API contract,
not an OS tamper-proof seal. Never feed these bytes to the production candidate
snapshot writer or treat them as accepted by the IC.
The writer revalidates domain, limits, batches and per-symbol schema/date/value
summaries before creation. Provenance and row hashes are caller/provider
assertions; this receipt is not an authenticated independent acquisition proof.

## Verification and remaining gates

Tiny injected fixtures cover full success, exact membership, preflight limits,
universe/provenance errors, provider exceptions, missing/duplicate/unexpected
symbols, invalid schema/values/dates/volume, partial batches, immutable exclusive
creation, cleanup on write failure, and protected/alias destinations. The wrapper
test forbids calls to the existing runner, universe, batch fetch and snapshot
writer. No live provider, acquisition, production or cache operation was tested.

C02 still needs independent review, actual admitted-universe acquisition under
separately enforced operating limits, complete source/freshness reconciliation,
ranking and eligibility evidence, and separately scoped promotion/delivery and
actual IC consumer verification. This implementation closes none of those
operating gates and is not a full-universe refresh.
