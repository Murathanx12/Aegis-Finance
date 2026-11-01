# Verified price input bridge

`backend.services.funnel_price_bridge.stage_verified_prices` consumes explicit
in-memory bytes from **one full_us C02 acquisition** and returns immutable JSON
bytes containing original per-symbol eligibility inputs. It performs no file
reads/writes, SDK import, provider operation, production funnel call or promotion.
It does not accept native panels or infer their provenance. Five-constituent
qualification is deliberately refused as a full-domain input.

```python
from backend.services.funnel_price_bridge import (
    PriceBridgeRefused, stage_verified_prices,
)

try:
    stage = stage_verified_prices(manifest=approved_manifest,
                                  artifacts=explicit_artifact_bytes)
except PriceBridgeRefused as exc:
    diagnostic = exc.report  # Unknowns remain in the full parent denominator.
else:
    unranked_inputs = stage.report["inputs"]
```

The caller supplies an independently approved manifest and exact artifact bytes.
Hashes bind those supplied bytes; they do not authenticate the provider, certify
calendar authority, qualify the account, or prove that caller-supplied source
pins received review. There is no implicit filesystem loader or discovery scan.
Any operating loader must separately qualify explicit file paths, byte hashes,
calendar/session authority, source/runtime pins and acquisition freshness under
the reviewed owned-process resource/window policy.

## Manifest

Required fields:

- `schema`: `verified_price_manifest_v1`.
- `universe`: the complete C02 full_us universe object, including exact unique
  membership hash, exclusions, provider raw-response hash/row lineage, declared
  extras and provenance. It must equal the acquisition object exactly.
- `acquisition`: `{file, sha256}` (optional `bytes` count). The file is an exact
  key in the bytes map, not a path to open.
- `source_pins`: the independently approved acquisition source/runtime pins;
  exact equality with the acquisition is required. No installed SDK is loaded
  or source files read to infer qualification.
- `required_sessions`: sorted, unique ISO local session dates for the complete
  requested history. The final date is the expected completed coverage session.
- `calendar_provenance`: `{source, sha256}` identifying the separately qualified
  session evidence. The API validates shape and preserves the binding; it does
  not construct, fetch or independently qualify this calendar.
- `limits`: positive integers `max_input_bytes`, `max_artifacts`, `max_rows`,
  `max_symbols`. `max_rows` caps each raw history, the calendar, and raw universe
  response row count. Set it for the complete raw response, including exclusions.

The bytes map contains exactly the acquisition JSON, its raw universe response,
every referenced plan/history artifact and its successful price-coverage receipt
when present. Transport/binding journals are not inputs to this seam. Unreferenced
files and duplicate references/JSON keys are refused. All referenced hashes and
provided byte counts are rechecked. The raw universe is replayed through C02's
existing deterministic admission filter, with unchanged declared extras. The
helper's minimum transport-plan compatibility argument is not a transport quota:
this bridge has no transport and makes no HTTP/wire-attempt claim.

JSON structural nesting is limited to 64 levels before parsing (brackets inside
quoted strings do not count). Malformed, duplicate-key and nonfinite JSON and
parser/manifest recursion failures raise `PriceBridgeRefused`; none can produce
a complete export. The same nesting check applies to the supplied manifest.

These caps bound supplied byte/count sizes. They are not a wall-time, worker-tree
memory, RSS or decoded-object allocation limit. Inputs already exist in caller
memory. Full-domain loading/verification must run inside a separately qualified
owned execution context when those operating bounds are required; this pure
source API supplies no process runner and makes no unsupported enforcement claim.

## Export and refusal

For each admitted symbol the bridge checks returned raw columns, numeric finite
positive Close, finite nonnegative integral Volume, unique increasing normalized
dates, and the unadjusted capture basis. It reconstructs the original timezone
and checks every original timestamp against the explicit local session labels;
European midnight is never serialized through UTC to choose a session date.

The coverage receipt is revalidated by the existing staging validator. Each
symbol's projected Close/Volume hash, window, counts, latest values and history
artifact provenance must agree with the original raw rows. Each coverage identity
must name the exact history artifact that supplied that symbol, and its digest
must equal that already verified artifact's digest. A correctly hashed plan with
ticker-named keys cannot substitute for history. Multi-symbol batches and
distinct history batches retain their actual per-symbol artifact bindings.
The original raw
history (including OHLCV/extra fields, timezone, local dates and recorded missing
values) is retained unchanged. A separate Close/Volume projection contains the
original values/dates used by eligibility, without synthesized OHLC fields.
Missing OHLC fields remain explicit and OHLCV/native grade admission remains
`not_evaluated`, including on a successful CV/history export.

`PriceBridgeRefused.report` retains the full parent universe, per-symbol unknown
reasons and any verified projections available before the refusal. Structural
artifact failures mark all parent symbols unknown; they cannot produce a success
artifact. Missing histories, price failures, partial/failed acquisition, failed
transport, missing successful coverage, duplicate/unexpected symbols, mismatched
membership/source pins, and absent/extra history sessions refuse a complete
export. Under the existing funnel's `MIN_HISTORY_DAYS`, short observed history
stays **unknown**, not an inferred listing date or an eligibility exclusion.
This conservative version does not admit IPO-specific shortened calendars.
Legitimate new listings retain their names in the complete admitted denominator;
their shorter history is uncertainty for the later original eligibility phase,
not a reason for this bridge to remove them or evaluate strategy eligibility.

The receipt distinguishes:

- `accounting_complete`: all supplied symbols reached per-symbol accounting;
- `usable_price_coverage_complete`: every latest declared coverage projection
  agrees with the successful coverage receipt;
- `declared_history_coverage_complete`: every original history matches the pinned
  full session list and supplies the existing minimum history rows;
- `complete`: only this verified CV/history input export completed.

Every receipt keeps `eligibility`, `enrichment` and `ranking` unevaluated and
`promotion_eligible=false`. No stage filters, size stratification, scores,
shortlists, defaults or canonical files are changed. The next consumer must use
these verified data through a reviewed pure eligibility seam; calling the existing
`stage1` would still invoke its provider default. This module does not do that.
No complete canonical refresh, current calendar qualification or full C02 parent
acceptance follows from source tests or from an input export alone.

## Source-only verification

Use the native virtualenv with `AEGIS_IGNORE_DOTENV=1` and
`PYTHONDONTWRITEBYTECODE=1`:

```powershell
python -B -m pytest backend/tests/test_beta_v2_funnel_price_bridge.py backend/tests/test_beta_v2_funnel_staging.py backend/tests/test_beta_v2_funnel_acquisition.py -q -p no:cacheprovider
```

Fixtures use two small histories and explicit synthetic calendars. One exercises
the actual C02 `_collect` artifact writer with fake history/HTTP functions and
feeds its files to the pure bridge. No provider, native Job or financial operation
is performed. Shared missing-input enrollment is
`validate_manifest({}) -> PriceBridgeRefused`; it must occur before all I/O.
The module is private development tooling pending an owned operating consumer;
coordinator integration must preserve that reachability classification.
