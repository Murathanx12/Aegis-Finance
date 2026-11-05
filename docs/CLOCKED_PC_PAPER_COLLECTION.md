# Clocked PC-PAPER read-only observation candidate

INACTIVE. No production reader/credential default, task, write, order or sender.
Base main b3116953507b09ad80c772f0475448b18e233e7e. Existing pc_broker.snapshot,
NAV/state writers and owner_event_warning thresholds are untouched.

## Interface and bounds

`pc_paper_collection.collect(read=..., expected_account_scope_sha256=...)` performs
one attempt, at most three GET requests: account -> positions -> account.
The caller MUST inject a lossless reader. The reader receives a frozen request
(method GET, exact paper host/path, unique attempt/request IDs), timeout and
max_bytes=1MiB. It must enforce both bounds while reading; the candidate checks
again on return. No broker client, credential/environment lookup, model,
filesystem or transport implementation is supplied. There are no retries or
latest-file/response fallback. One invocation never reuses a previous attempt.

Acquisition default 5s, hard configurable ceiling 30s; <=512 positions; <=1MiB
per response/3MiB total; numeric length/exponent/precision bounds. Strict local
UTC and monotonic clocks must advance consistently. Local request/receipt UTC
for all three endpoints are separate. Time checks include parsing/reconciliation;
a blocked injected reader cannot be preempted, so these are cooperative bounds,
not an OS watchdog. Future production transport/adoption requires separate review.

ReadResponse must echo attempt/request/host/path, HTTP 200, complete=true, exact
raw JSON bytes and caller-bound account scope. Account scope is SHA256 of the
canonical account UUID, NOT a credential hash. Both account bodies must match
that pinned identity; all three transport envelopes must share its binding.
The positions endpoint has no independent account ID: its binding is explicitly
TRANSPORT attestation, not authenticated provider-origin proof. A malicious
reader able to relabel all evidence is outside the trusted transport contract.

Duplicate/escaped duplicate JSON keys, null/non-list positions, truncated/error/
partial/oversized responses refuse without a snapshot. A genuine complete empty
list may be collected only if independent account totals reconcile; failed/null
fetches NEVER become [] or zero. Both COMPLETE count and n_positions are local/
transport assertions, not independent completeness proof.

## No splice or silent precision/classification repair

Entire decoded account objects must agree across the bracket, including extra
fields. Any movement refuses; account-after is never substituted for account-
before to salvage a positions sample. Response order/identity/correlation or
clock mismatch also refuses. Hashes bind all exact accepted response bytes.
One stable bracket does NOT establish atomicity or synchronized market marks.
A change away and back, cache lag or internally stale positions may remain
undetectable without independent source evidence.

Numbers are decoded directly into Decimal from raw JSON (no binary-float
intermediate). Original precision survives as strings in PRIVATE snapshot data;
no account totals are replaced by the positions sum and no row is dropped.
No rounding, zero fill, residual redistribution or threshold change occurs.
All three original warning constants are imported unchanged:
equity identity $0.01; quantity-price mark residual $0.01; position sum residual
max($1, equity*0.0001). Applying the mark rule to every position is deliberately
stricter than checking only a selected held symbol. Both residual signs and
exact boundary/precision controls are tested.

Require positive quantities/values/prices, unique symbols AND canonical asset
UUIDs, explicit side=long and asset_class=us_equity. Missing side/class refuses;
no long/us_equity defaults. A nonunit explicit leverage refuses. Missing leverage
stays literal UNKNOWN and yields COHERENT_CLASSIFICATION_UNRESOLVED, NOT warning
readiness. The returned row always includes leverage, preventing the old warning
adapter's absent-field default-to-one; its unchanged validator refuses UNKNOWN.
Account multiplier or position marginability never becomes leverage proof.

Leverage is not guaranteed by the ordinary positions API contract. The green
synthetic fixture provides an explicit unit field; that is NOT proof that a real
API sample will provide it. An actual missing classification remains unresolved;
a separately reviewed classification witness/adapter would be needed before
warning adoption. Explicit provider class/side/leverage fields remain caller-
transport metadata, not independent security/share-class/venue authentication.

## Clocks and provider marks

Only explicitly supplied transport VALUATION_AS_OF assertions can populate
provider as-of or per-asset mark clocks. Otherwise UNKNOWN. HTTP Date, account
created_at/updated_at, asset marginability and the local receipt clock are never
reinterpreted as valuation/mark clocks. Known future/naive or inconsistent provider
clocks refuse; mark-map keys must bind exact response asset IDs. Partial/absent
clock coverage stays UNKNOWN, never synchronized. A common reported clock is
labeled PROVIDER_REPORTED_COMMON_ASOF_NOT_ATOMICITY_PROOF, not independent truth.

The legacy-compatible `t` is only the positions RECEIPT time, explicitly labeled
POSITIONS_RECEIPT_NOT_ATOMIC_VALUATION. All six component clocks and source hashes
are retained beside it, as are per-position mark clocks. Later invocation does
not refresh any provider mark/as-of clock. Current/event-time holdings, broker
origin and independently aligned prices are not established by this candidate.

## Private sample versus sanitized receipt

Result contains a private snapshot (symbols/quantities/marks/classification) only
for coherent observations, and a separate allowlisted receipt. REFUSED returns
snapshot=None. Caller must protect private snapshots; no writer or serializing
CLI is supplied. Do not log the entire result or overwrite state_latest/nav.jsonl.
A future caller may persist a NEW dated evidence candidate after review, never
rewrite historical inputs or splice failed observations.

Receipt diagnostics contain only aggregate residuals/tolerances, counts, clocks,
span, status, byte hashes and explicit unknown/authority labels. No account UUID/
number, credential, symbol, quantity, per-position value, raw body, asset UUID,
private path or provider exception text enters diagnostics. Failed quantities
remain UNKNOWN, not 0. Warning/forecast/delivery/trade authority is NONE.

## Gate and evidence boundary

This is source candidate construction, not real Alpaca collection or adoption.
The prior cf3a4b... saved discrepancy is not repaired. If its explicit path no
longer matches the historical pin, report unavailable/drift without newest-file
fallback. Original BAD_EQUITY_OR_EXPOSURE remains unwaived. Synthetic coherent
explicit-classification inputs pass the existing byte-only warning arithmetic;
this does not authorize a warning, stale source, send, trade or task opt-in.

Official reference endpoints (documentation only; no API request in this build):
- https://docs.alpaca.markets/us/reference/getaccount-1
- https://docs.alpaca.markets/us/reference/getallopenpositions
The positions documentation describes live-updated marks; it does not guarantee
cross-endpoint atomicity. No additional asset/market-price request is added.
