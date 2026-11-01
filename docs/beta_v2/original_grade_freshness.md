# C10 original247 completed-session freshness

This is a source build for independent review. It does not authorize an actual
grade, a cache repair, source adoption, task-pin updates or deployment. Changing
`scripts/local_branching_grade_child.py` invalidates existing child/task source
adoption pins. The coordinator must review and adopt the changed package before
any later native writer operation. Existing grade receipts are never retrofitted.

## Common-session contract

`run_original()` still requires the native parent's stdin byte `G` before imports.
The latest eligible XNYS session S must close at least 90 minutes before the
timezone-qualified observation. The frozen cohort, strict verified book reader,
247-ID pins and early `prior_valid_grade` / `ALREADY_GRADED` path remain unchanged.
`run()` still invokes the separate population1000 operator after `run_original()`;
this build's tests call only the original consumer.

The read-only `completed_session_targets` adapter takes an injected clock,
calendar loader and optional reviewed identity mapping. Its default loader uses
the existing `market_sessions._xnys()` and installed `exchange_calendars` for
the explicitly mapped foreign markets. Every listing must have the same session
S on its calendar, with local close plus 90 minutes elapsed. A holiday, missing
calendar, unclosed session or unresolved identity produces no target. Yesterday
is never substituted. Calendar completion does not prove vendor delivery.

## Exact identity policy and provenance

The **default US allowlist is exactly `SPY`**. Its authority is the original
consumer's explicit frozen US benchmark / XNYS session contract, preserved in
`scripts/local_branching.py` and the pre-change child at baseline
`4f59e6e337ed846d97b81d5b5ebd74b79b3fdec0`. XNYS describes that US session contract;
it does not assert SPY trades on the NYSE venue.

The only default foreign identities are those explicitly supplied in the C10
consumer packet and its saved `global_prices/native-five-symbol-freshness-final.json`:

| Exact listing | Calendar |
| --- | --- |
| EVO.ST | XSTO |
| SAAB-B.ST | XSTO |
| HAG.DE | XETR |
| RHM.DE | XETR |
| KOG.OL | XOSL |

The saved original247 receipt
`oct14-continuation-20261014/local-branching/2026-10-14/grade_20261019T000004439995Z.json`
(SHA256 `c01f15c7903a3b0b1d97844af98498730f9a596d7fb7ff71c52ec4b216ad0e47`)
records 56 US-panel symbols among 76 constituent/benchmark identities. **Panel
membership is price-source provenance, not listing authority.** This build does
not admit the other 55 US-panel names using that receipt, an unsuffixed symbol,
a ticker alias or an SEC registrant record. The remaining 15 foreign identities
also stay unresolved. NVDA, ASML, OTHER.ST and 2330.TW therefore remain unknown
under the default policy even if valid marks exist. Additional identities require
separate reviewed listing/calendar evidence and source adoption. No suffix rule
broadens these sets.

Fixtures inject an explicit SPY/NVDA XNYS mapping and the five foreign mappings
to exercise the completed-S success path. That injection is a trusted testing or
reviewed-caller dependency, not production identity discovery. Default original247
coverage remains incomplete until the unresolved identities are independently
qualified. No current cohort or population reread was used to promote identities.

## Snapshot and refusal behavior

The existing `LB.cached_bars` / `LP.union_bars` still chooses a whole series per
symbol, using the later-ending panel and US on a tie. Source selection occurs
before the snapshot is bounded to S. A newer winning global series cannot have
its missing S row filled from the losing US panel. Both the unchanged pure
`GP.freshness_diagnostic` and the writer receive the same copied bounded snapshot.
Newer rows never qualify S; an all-stale snapshot returns diagnostic refusals.
The default strict behavior of `snapshot_through` still requires S; only readiness
uses its new `require_session=False` option to diagnose an all-stale snapshot.

Complete target coverage and the existing authoritative `validate_marks` are
both required. Absent, duplicate, nonfinite, boolean or nonpositive marks fail.
Missing columns and invalid cached dates produce explicit snapshot refusals.
Partial targets, missing completion proofs or a different constituent target
cannot change the common grade date. These cases use the existing
`WAIT_CONSTITUENT_MARKS` action with per-symbol reasons and target provenance.
There is no new WAIT action or task-receipt classifier change.

The consumer validates the entire adapter completion contract before admitting
a target. It builds its own calendar reference from a snapshot of the reviewed
mapping, S and observation before calling an injected adapter. Header policy,
mapping hash, authority, common session and exact observation instant must match;
the lag must be the integer 90. Each returned symbol proof must identify the
requested symbol/listing and reviewed calendar, S and completion status. Close
must match that calendar's S close, and eligibility must be exactly close plus
90 minutes and no later than the consumer observation. All supplied times must
be timezone-qualified; equivalent aware offsets represent the same instant.
Missing/malformed proofs, extra identities, invented but self-consistent close
times and promotion of an unresolved listing are refused. Validation failures
add per-symbol `proof_validation` reasons and an additive
`completion_proof_validation` record; they cannot reach the writer.

On success, `panel_identity`, both source hashes and the before/after stat-race
guard still apply. The existing grade evidence fields are retained, with additive
`completed_session_targets` and `freshness_diagnostic` fields. Target evidence
contains policy/version, the exact identity/calendar mapping hash, observation,
common date, per-listing calendar, close, eligibility time and refusal/completion
status. Race detection still returns `WAIT_SHARED_REFRESH`. An already-valid
same-session receipt is reused before cache or freshness checks and remains byte
stable; incomplete or changed-ID receipts still raise.

## Focused verification

Use the runtime interpreter with `AEGIS_IGNORE_DOTENV=1`. New offline fixtures:
`backend/tests/test_beta_v2_original_grade_freshness.py`. Existing contracts reused:
`test_beta_v2_global_prices.py`, `test_global_prices.py` and
`test_local_branching_task_receipt.py`. No full suite is required for this source
slice. The native writer, fetch/ensure/downloader and population operation are
never invoked by the new tests; fixture parquet/receipt writes stay under pytest
temporary paths. Detailed source pins, commands, counts and limitations are in
the private `build-batch2-20261025/C10_FIX_BUILD.md` report. The original
`C10_BUILD.md` is preserved as the failed freeze: independent C10-R1 review
demonstrated seven inconsistent-proof cases that previously dispatched the
mocked writer. The fix adds contract regressions and reruns the unchanged
reviewer probes. Source adoption and final independent acceptance remain separate.
