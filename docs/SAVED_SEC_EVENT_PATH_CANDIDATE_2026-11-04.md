# Saved SEC event lineage — inactive P0 candidate (2026-11-04)

Base: `4a4aca16987395eaf580b633faab38bd2b5052db`.
Branch: `codex/saved-event-lineage-20261104`.
Worktree: `C:/Users/mrthn/aegis-saved-event-lineage-candidate`.
Only additions: `backend/services/saved_sec_event_path.py`,
`backend/tests/test_saved_sec_event_path.py`, this note.

`build_saved_sec_event_path` accepts frozen SEC JSONL and native PC-PAPER
snapshot bytes, ticker, explicit UTC cutoff and decision clock. It consumes
`build_saved_sec_input`, then passes the selected exact row bytes to existing
pure `build_saved_warning_bytes`. No path, sender or runtime configuration exists.
Publication and first_seen must be <= cutoff <= decision. Snapshot t must be <=
decision; it may postdate cutoff. Existing 24-hour source/snapshot age limits and
saved-equity reconciliation remain binding. Adapter bounds: 1 MiB, 64 lines;
snapshot bound: 1 MiB. Eligible byte conflicts and multiple documents refuse.
Identical daily row copies collapse to one evidence unit, within those bounds.

Event ID is the existing warning builder's ticker/accession event_key, independent
of snapshot and clocks; distinct exhibits still cannot be combined in one call.
Evidence packet hash is exactly the adapter packet_sha256 (canonical packet
including exact selected UTF-8 row bytes/terminator and cutoff). forecast_input_id
is `saved-sec-input:` plus that hash; it names evidence, not a generated forecast.
Decision ID is `saved-sec-decision:` plus SHA-256 of canonical JSON binding schema,
event ID, input ID, packet hash, exact snapshot hash, UTC decision and the entire
existing warning artifact. Canonical JSON: sorted keys, compact separators,
ensure_ascii=True, allow_nan=False, UTF-8. Exact snapshot whitespace changes its
hash and decision ID. Other-ticker/future rows and duplicate copies are not part
of the selected evidence packet hash; this is not a whole-file archive digest.

Success: PROVISIONAL, active=False, runtime_authority=NONE, new_allocation_usd="0",
forecast_status=NO_CALIBRATED_EVENT_FORECAST, forecast_id=None. Refusals carry a
reason, no decision ID, no replacement forecast. All artifacts stay in memory.
No model, network, broker, ledger, transport, runtime or input-file writes.
No caller wiring, push, PR, live action, generated forecast or delivery.

Validation (synthetic frozen fixtures, not native capture certification):
`python -m pytest -q -p no:cacheprovider --tb=short backend/tests/test_saved_sec_event_path.py backend/tests/test_saved_sec_forecast_input.py backend/tests/test_owner_event_warning.py`
157 passed, 1 skipped (existing platform-dependent test).
`python -m ruff check --no-cache backend/services/saved_sec_event_path.py backend/tests/test_saved_sec_event_path.py`
All checks passed. PYTHONDONTWRITEBYTECODE=1; caches disabled.
Tests cover exact builder parity/hashes, clock boundaries, duplication, ambiguity,
conflicts, malformed/oversize/deep inputs, snapshot refusals, reproducibility,
import allowlist and denied IO/delivery. Static refusal review found explicit
failure returns, no swallowed success or fabricated fallback. No deployed or
scheduled checks apply to this unconnected candidate. Owner independent review
remains pending; no independent agent review is claimed.

Limitations: hashes are unkeyed integrity identifiers, not authentication.
Capture authenticity, SEC semantics and PC-PAPER ownership/instrument identity
remain caller-attested/unverified. Source body is untrusted and retained in the
evidence packet; callers must handle it as evidence, never instructions. No
current quote, consensus, loss budget, calibrated direction/probability or new
allocation is inferred. Uses private adapter _utc helper pinned at this base;
future adapter changes require compatibility review. No persisted dedupe or
idempotent delivery is provided. Full repository suite was not run.
