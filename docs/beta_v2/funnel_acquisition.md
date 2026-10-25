# C02 private acquisition adapter

Source build only. No provider, native Job, acquisition, append, deployment or
financial operation was exercised during build. Production `F.run()` is unchanged.
The operating default refuses unsupported platforms and requires a private Windows
Job. Test injection seams are not operating authority.

## Explicit operating interface

`source_pins()` reads the installed provider sources, curl native wrapper, adapter,
worker and accepted coverage dependencies without importing the SDKs. Save/review
that exact dictionary; `acquire(request, finnhub_key=...)` checks it in the parent
and gated worker before SDK imports. Drift refuses. The coordinator supplies the
reviewed request; this document does not authorize running the example.

All request inputs are required:

```python
request = {
    "mode": "frozen_five",  # or full_us
    "symbols": ["EVO.ST", "HAG.DE", "KOG.OL", "RHM.DE", "SAAB-B.ST"],
    "extras": [],
    "run_dir": "<existing-private-parent>/funnel-acquisition-staging/<NEW-run-id>",
    "history_start": "<reviewed YYYY-MM-DD>",
    "history_end": "<reviewed YYYY-MM-DD inclusive>",
    "coverage_start": "<reviewed original session date>",
    "coverage_end": "<reviewed original session date>",
    "coverage_min_rows": 1,
    "source_pins": saved_reviewed_source_pins,
    "entitlements": {"yahoo": {
        "qualified": True, "scope": "private_personal_research_history",
        "evidence_ref": "<coordinator-held qualification reference>"}},
    "limits": {
        "max_transport_attempts": approved_attempts,
        "request_seconds": approved_per_transfer_timeout,
        "wall_seconds": approved_worker_wall,
        "cleanup_seconds": approved_cleanup_reserve,
        "job_commit_bytes": approved_worker_tree_committed_memory,
        "max_response_bytes": approved_post_transfer_response_size,
        "max_artifact_bytes": approved_per_artifact_size,
        "max_raw_rows": approved_full_universe_response_rows,
        "max_symbols": approved_complete_domain_size,
        "batch_size": approved_logical_batch_size,
    },
}
```

For the frozen-five diagnostic, `finnhub_key=None` is mandatory and there is no
Finnhub call. The exact five names are preserved; no ticker aliases, smaller
subset or US-universe label is allowed. The artifact is explicitly
`frozen_five_constituent_qualification_not_full_funnel`.

For `full_us`, `symbols=[]` requests the complete fresh Finnhub US symbol response;
`extras` are explicit canonical US-format symbols. A nonempty explicit credential
and `entitlements.finnhub={qualified: True, scope: "stock_symbol_US", evidence_ref:
"<qualified account/endpoint reference>"}` are required before process/network
access. Credentials travel only over the bound worker's stdin, never argv, child
environment, receipts or logs. Entitlement references are trusted coordinator
inputs, not an independent account/rate-limit verifier. Endpoint/rate/entitlement
remain UNKNOWN until qualified; there is no assumed free tier or paid fallback.

## Transport and ownership

Installed yfinance has cookie/crumb, metadata, transient retry and auth-strategy
calls below its history interface. The child alone replaces curl's session
aliases with a synchronous bound session. Every actual `Curl.perform` entry is
reserved/journaled before native transfer. SDK-created sessions share that meter.
Limits are actual transfer-entry counts, not logical batches or wire-packet/HTTP
server billing counters. No exact wire-level retry count is asserted.

At the final Python/native boundary the adapter disables redirects, automatic
HTTP/proxy authentication, proxies and connection reuse, and forces HTTP/1.1.
Redirect responses and 429 latch refusal; no second hop or provider fallback is
followed. Unsupported hosts, POST consent flows, streaming, websockets, alternate
thread engines and cross-thread requests refuse. Each request timeout is clamped
to aggregate remaining time. Response-size checks occur AFTER transfer; they are
not a wire-byte budget. Each artifact/journal has a size cap; this is not a total
disk quota. Unsupported Yahoo consent contexts may therefore fail qualification.

The parent uses a NEW private Job (kill-on-close plus aggregate child-tree commit
limit) and verifies the configured limit by native readback. It never imports the
branching task owner or borrows Qwen's global Job handle. A `-I -S -B` stdlib-only
worker runs the pinned CPython 3.12 Windows base interpreter directly; a venv
launcher is refused. Source qualification includes the base executable, core and
stable-ABI Python DLLs, and runtime version/classification identity. Before `A`,
the parent verifies that exact PID's image/hash and membership in its specific
private Job using native readback, then writes `owner_control.json`. Merely
binding a venv launcher cannot contain an interpreter it already spawned. SDK
site paths are added only after binding; no sitecustomize/.pth startup runs. SDK
state/session/cache changes occur only in this worker. HOME/APPDATA/cache/temp/cwd
are per-run; proxies/credentials are not inherited. Existing SDK SQLite caches are
isolated, not a new application database. There is no native/shared-cache fallback.

The worker-tree limit is COMMITTED memory, not RSS and not parent+child RAM.
The parent monitors wall time/cancellation and closes only its Job/owned PID on
failure, with a bounded cleanup wait. Admission reserves worker wall plus cleanup
before the conservative Singapore 16:35-17:10 quiet window; running calls are
also checked. Unsupported OS/Job contexts refuse. Build tests use fake owners,
not a native kernel calibration; real ownership/cap proof remains a later gate.

## Payloads and accepted coverage handoff

Full-US collection retains original successful universe response bytes/hash,
per-admitted-row canonical hashes, provider membership, venue/type/symbol
exclusions, duplicate counts and explicit added/already-admitted extra lineage.
Empty provider admission cannot become an extras/watchlist fallback. A full plan
that exceeds symbol/minimum-transfer limits refuses without truncation. The
response remains provider-asserted completeness, not an independent exchange census.

Private `history-B*.json` captures ALL returned unadjusted fields BEFORE the
Close/Volume projection. It preserves column order/values, offset-bearing original
timestamps, IANA timezone name and explicit `original_session_dates`. Consumers
must use those local session labels, not dates inferred after UTC serialization.
Nonfinite numeric cells are null plus explicit row/column/value markers; nothing
is synthesized. Missing OHLCV fields are enumerated and structurally unready.
`raw_ohlcv_structurally_ready` is a data-shape/value check only;
`grade_admission_ready` is always false pending separate owned review/append.

Coverage receives only a separate Close/Volume copy, bounded to the explicitly
declared coverage window after dropping timezone WITHOUT changing local dates.
Raw history extents/short history stay separate from exact-session coverage and
one-year eligibility. CV-only mocked/providers may complete CV coverage while
OHLCV structural readiness remains false. No eligibility, enrichment or ranking
is qualified by either flag.

Full-US prices use reviewed `stage_price_coverage` and its create-only staging
writer. The reviewed US ticker validator cannot represent foreign dotted names;
the five diagnostic therefore reuses the pinned frame validator in a DISTINCT
artifact and never pretends to be an admitted-universe receipt. `acquisition.json`,
`plan.json`, symbol/transport journals and raw batches preserve failures. Kill or
timeout may leave partial private files; none is promotion authority. No prior run
or artifact is overwritten, and there is no production/default-path promotion.

## Verification boundary

Offline tests use tiny fake transfers, clocks, frames and process/Job owners.
They cover internal transfer counts, redirect/auth/timeout/cap refusal, source
pins, input/entitlement preflight, isolation, cancellation, full universe/extras,
partial coverage, immutable files, secrets, short raw history, OHLCV preservation
and European-midnight round trips. They do not prove real provider entitlement,
network success, native kernel limits, completed-S eligibility or native append.
Shared CASES enrollment belongs to the coordinator and calls
`validate_request({}, finnhub_key=None)` expecting `AcquisitionRefused` with zero
outside-observed I/O/process calls. See the B3 build receipt for exact frozen pins.
