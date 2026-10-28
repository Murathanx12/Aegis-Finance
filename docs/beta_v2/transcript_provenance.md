# Offline transcript version availability

`scripts/beta_v2_transcript_provenance.py` is a pure, standard-library helper for
H19 temporal metadata. No acquisition, backend, database, model or network imports,
file access, trial registration or runtime adoption occurs. It is standalone:
the existing C05 acquisition module loads database/credential dependencies; the
offline research checker currently has no bound CIQ input. Neither is modified.

The existing intake is `scripts/wrds_c05_incremental.py`: a reviewed
`C05_INCREMENTAL_PLAN/1` creates `C05_WRDS_incremental_receipts/1` and hashed
creation-date artifacts. That receipt and its acquisition time are not public
release/first-seen evidence. See [the existing intake](wrds_c05_incremental.md).

Call `validate_availability(TranscriptMetadata(...), decision_at=<aware ISO time>)`.
`SourceVersion` requires source ID, record ID, exact version ID, content SHA-256
and evidence reference. `Clock` contains optional `at`, plus source field,
evidence reference, full `source_version` binding and evidence basis. The binding
must equal the complete SourceVersion identity/digest/reference, not just a
potentially reused version label. Missing instants stay
`None`; metadata is frozen and retained separately from UTC-normalized clocks.
There is no text or price field, version auto-selection, receipt authentication,
implicit current time or timestamp fallback.

Creation, event, publication, observed and revision clocks stay separate. Creation
and revision describe this source version, not just the original call. Event/call
time never establishes release or first availability. Publication for a correction
must describe that correction, not copy the original version's release clock.
Use `source_metadata` or `archival_receipt` for creation/event/publication/revision;
use `collector_observation`, `archival_receipt` or `acquisition` for observation.
References must identify the evidence for that exact version; the helper checks
bindings and consistency, not whether the external assertion is truthful.

| Result | Meaning |
|---|---|
| `eligible` | Exact-version public release and non-acquisition observation are both at/before decision; supplied metadata passes temporal checks. `usable_from` is their later instant. |
| `prospective-only` | Bound observation exists by decision, but historical public/first-seen evidence is incomplete or observation is acquisition-only. `usable_from` is no earlier than observation; this is not historical admission or authority to trade. |
| `unknown` | No bound observation, invalid/ambiguous clocks, provenance/version mismatch, future version/release/observation or contradictory ordering. Explicit reason codes explain refusal. |

Naive/date-only timestamps are unresolved, not UTC. Acquisition-as-publication is
refused. Even a separately supplied old publication time cannot backdate a later
acquisition. Unknown creation/event clocks need not defeat independently supplied
exact-version release/observation evidence; they remain unknown in the result.
A future event is labelled separately and does not itself prove a future version.
Future creation/revision/release/observation does refuse eligibility.

`historical_eligible` is false for prospective-only/unknown. Retain the complete
result; do not interpret a nonempty `usable_from` as overall H19 readiness.
Rights, role/section quality, historical security links, price availability,
earnings controls and research validation remain separate. Existing source fields
are not manufactured, enriched or retroactively promoted by this helper.

`supersedes_version_id` records a relationship without loading/replacing its parent.
Validate each version separately; old observations cannot qualify a new version.
The helper cannot verify completeness/order of an external revision chain or
infer that an earlier version was never replaced. A caller must bind the selected
version and preserve prior results. No persistence or intake activation is added.

Focused synthetic tests, bypassing protected pytest conftest and all backend imports:

```powershell
& 'C:/Users/mrthn/aegis-finance/.venv/Scripts/python.exe' -I -B 'C:/Users/mrthn/aegis-worktrees/beta-v2-owner-20261025/tests/standalone/test_transcript_provenance.py'
```

Fixtures contain invented IDs and clocks only, no acquired text or outcomes.
Candidate tests are builder validation; independent review remains separate.
