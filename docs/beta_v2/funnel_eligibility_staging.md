# Original eligibility over verified price inputs

`backend.services.funnel_eligibility_staging.stage_original_eligibility` is an
inactive private adapter. It revalidates explicit manifest/artifact bytes through
the price bridge and then consumes that verified original Close/Volume export.
It does not acquire data, call the production funnel, change globals, write a
canonical snapshot, rank downstream candidates or promote an artifact.

```python
from backend.services.funnel_eligibility_staging import (
    EligibilityRefused, stage_original_eligibility,
)

try:
    receipt = stage_original_eligibility(manifest=approved_manifest,
                                         artifacts=explicit_artifact_bytes)
except EligibilityRefused as exc:
    diagnostic = exc.report
else:
    original_stage1_candidates = receipt.report["candidates"]
```

The public API verifies the underlying bytes again rather than trusting a
caller-constructed `VerifiedPriceStage` or an asserted completion flag. All
bridge trust-anchor, calendar qualification, acquisition-freshness, input-size
and external owned-execution requirements still apply. This adapter adds no
provider, loader, wall-time, RSS or process-owner mechanism.

## Original behavior preserved

The existing `opportunity_funnel.stage1` has no separate pure post-fetch helper.
Its inline arithmetic is reproduced in `_original_stage1`, referring to the
existing `F` constants and `Candidate` class. The original file is unchanged.
Candidate fields and explanations, ordering, and the exact size-stratification
warning are checked against the actual original function code in tests.

The adapter retains the original history minimum, inclusive price limits,
60-observation median dollar volume, retail ticket/ADV check, volatility and
display-only momentum calculations. It retains liquidity ordering, stable ties,
the existing size-band sample, remainder allocation and final ordering. It
neither activates momentum as a picker nor introduces a signal or alternative
strategy. The default `keep` is the existing `F.STAGE1_KEEP`. Explicit positive
integer `keep` values retain the original sampling behavior; zero, negative,
boolean and noninteger values are refused at this private interface.

Original volume alignment/fill semantics remain in the arithmetic kernel.
They cannot repair missing acquisition in this public route: the bridge first
requires verified finite joint CV sessions. Short or missing histories and price
gaps therefore remain upstream unknown/refusal conditions. Legitimate new
listings are retained in the full parent denominator; this version has no
independently qualified short-listing exception and cannot infer one. Kernel
tests of the original under-minimum rejection are not listing qualification.

Complete eligibility accounting distinguishes each parent name as `filtered`,
`eligible_kept` or `eligible_not_scored`. Intentional sampling is recorded in
`warnings.stage1_truncated` with the original text; it does not shrink the parent
universe or become an acquisition failure. Verified inputs with no eligible
names may produce a complete empty stage-1 selection; missing data may not.

The immutable receipt binds the exact bridge payload, manifest and input
artifact hashes, retains the full parent universe and per-symbol decisions,
and contains all original selected `Candidate` fields. Its detached report can
be reconstructed without shared mutable state. Finite raw prices that overflow
original candidate arithmetic produce a serializable refusal, never fabricated
zeroes or an invalid success artifact.

`eligibility_complete` means this stage only. Stages 2, 3 and 4 stay
`not_evaluated`; `promotion_eligible` and `full_funnel_complete` remain false.
Nothing updates the existing process-global `STAGE_FAILURES`. The source is
private development tooling pending reviewed operating integration. The C02
parent remains open for full-domain acquisition/history qualification,
enrichment, downstream ranking, immutable publication and consumer readback.

## Offline equivalence and integration

Tests run original `stage1.__code__` in a separate test namespace with a tiny
injected history function, private failure dictionary and inert logger. They
do not monkeypatch the production function or any `F` globals. This test oracle
compares every Candidate field, order and warning for positive keep values,
size-band sampling/remainders, stable ties, original price/liquidity/history
boundaries and momentum-display boundaries. Public-interface tests retain the
full parent ledger on filtering, sampling, gaps and arithmetic refusal.

Use the native virtualenv with `AEGIS_IGNORE_DOTENV=1` and
`PYTHONDONTWRITEBYTECODE=1`:

```powershell
python -B -m pytest backend/tests/test_beta_v2_funnel_eligibility_staging.py backend/tests/test_beta_v2_funnel_price_bridge.py -q -p no:cacheprovider
```

Coordinator owns the shared missing-input case:
`stage_original_eligibility(manifest={}, artifacts={}) -> EligibilityRefused`,
with forbidden-I/O counters asserted outside the call. Coordinator also owns
the development/inactive classification in
`backend/services/signal_reachability.py` (`CLASSIFIED`). No default application
or scheduled consumer is introduced here. Operating qualification must bind
the original `F`, corrected bridge and adapter source pins together; historical
C02 carrier pins/refreezes remain a separate reviewed operation.
