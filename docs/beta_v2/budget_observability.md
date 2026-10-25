# Budget refusal observability

This source-only change adds controlled metadata at existing refusal returns.
`llm_analyzer.call_named` now adds `budget_reason_code` and `no_wire` to its
production-gate and billing-breaker refusals. The separately staged native
candidate also tags its existing shared-reservation refusal. Status, legacy
error result, dispatch, charge, routing and retry behavior are preserved.

Reason codes are `production_gate`, `billing_breaker`, `endpoint_authority`,
`request_contract`, `shared_envelope_unavailable`, `shared_envelope_blocked`,
`shared_incremental_cap`, `shared_production_cap`, and `unknown_budget_refusal`.
Only fixed source messages/prefixes map to those codes. A blocked-state value,
exception text, path, URL, prompt or key never enters a new diagnostic field.
Unknown messages remain unknown. The existing transient legacy `error` field
is unchanged and is not copied into these counters.
`production_gate` retains the existing daily-cap-or-breaker ambiguity;
`shared_envelope_unavailable` retains the loader's collapsed failure reasons.

`no_wire=True` is added at the existing explicit pre-dispatch gates or when
the shared refusal carries the exact boolean flag. Uncertified flags remain
`None`; integers and strings are not coerced into a wire claim. This records
the source flag, not a measured HTTP request count or quota bound.

`Meter.summary()` adds `budget_refusal_reasons` and `budget_refusal_no_wire`.
The latter has `true`, `false`, and `unknown` buckets for exact boolean/unknown
metadata. Reasons outside the fixed enum map to unknown. Counters update
under the existing call-accounting lock, only for returned `BUDGET_REFUSED`
results. Local `BudgetExceeded` exceptions remain a separate mechanism.
The existing world-digest receipt already persists `Meter.summary()` as
`spend`; no additional writer or database is introduced. Old receipts are
unchanged and their missing reasons are not backfilled.

Native R and worktree W are different source profiles. R already has shared
reservation/unknown-charge protection; W has separate evidence-call controls
and no `provider_budget.py`. Each profile retains its original behavior.
The native candidate is an additive patch against its exact preimage; copying
the whole W files over R is not qualified. The two native-only tests skipped
in normal W testing run against that candidate in the private acceptance
packet. Full-module AST restoration after removing only the diagnostic
additions proves all existing logic in both profiles is preserved.

Tests AST-load only the relevant definitions and inject stubs for provider,
quote, cost, telemetry and application imports. They cover safe classification,
unknown/untrusted metadata, concurrency, early caps and retained unknown
charges/outcomes. There is no native adoption, inference retry, budget
unblocking, provider call, financial operation or historical reason claim.
