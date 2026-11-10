# E6 fixed-META provisional owner notice - offline candidate

Status: INACTIVE / INDEPENDENT REVIEW REQUIRED. Base 40f98f4c, with unchanged
E2/E3/E4/E5 implementations. No installation, scheduler, production sender,
owner grant, broker refresh, forecast, portfolio or natural-warning authority.

## One explicit saved packet

`build_assessment(Pin(manifest_path, externally_supplied_sha256))` reads one
closed `e6-saved-input-manifest/1`, max 64 KiB. It names SAVED_REPLAY, one selected
E2 event, one E4 RowLocator, corpus root, E2 receipt, full page, caller subject,
mapping selection and all four mapping inputs, saved broker observation,
message policy and code/dependency hashes. All object keys and duplicate JSON
keys are checked. Code pins include E2/E3/E4/E5, E6 and runner, plus unchanged
Telegram reference and legacy private-journal qualification helper.

Whole E2 schema/integrity validation precedes E4 selection and E5 linking.
The source/receipt chain is validated again immediately before an injected
attempt. Inputs stay immutable and are never copied to a forecast/outbox.
Fixed META CIK/name/Class A/NASDAQ/asset-ID checks remain E5's caller-attested
rules; E6 does not upgrade security, PIT, origin or holding authority.

The semantic key uses stable E2 event AND source-document identity plus the fixed
issuer/security profile. It excludes report time, container hash and refreshed
portfolio snapshot. The exact source version and complete input digest are
separate bindings. Container/snapshot/review refresh cannot mint a new notice.
Source amendments or changed message policy need explicit new review; there
is no automatic material-update resend policy.

## Message and authority

One fixed metadata-only description code, not arbitrary article paraphrase or
model text, is allowed: META_INFRASTRUCTURE_DISCUSSION_CALLER_ATTESTED. The
pinned policy attests the description to the exact source and raw-line hashes.
That attestation is caller supplied, not authenticated independent semantics.
Its source/holding max ages and validity interval are mandatory. Holding max
age is capped at 24h and source max age at 7d, never supplied as defaults.

The card states publisher claim, source first-seen, original saved holding
interval, new review clock, inference basis and missing evidence. It includes
no title/body/URL, quantity/account/raw asset ID/private path, invented direction,
probability, expected return, urgency or trade. Header explicitly says it is
not current holding confirmation. E2's decision/reasons stay as received,
including NO_CHANGE_WITH_REASON. E5 caller-attested candidacy is separate;
E2 direct issuer and E3 warning authority remain false. Broker origin is
UNVERIFIED_SAVED_RECEIPT; event-time holding UNKNOWN; PIT security UNVERIFIED;
owner decision UNOBSERVED; upstream delivery NOT_ATTEMPTED; forecast/action NONE.
Fresh review does not refresh holdings. Stale policies return PREVIEW_BLOCKED;
missing inputs refuse. There is no empty-input NO_EVENT success.

## Preview runner and OFFLINE injection boundary

`python -m scripts.provisional_owner_notice --manifest <absolute> --manifest-sha256 <sha>`
is read-only preview; it never qualifies or writes a journal. `--send` always
refuses PRODUCTION_SENDER_NOT_IMPLEMENTED. There is no task opt-in or live
Telegram adapter in this candidate. `telegram_bridge.send_owner_once` is not
imported or called, and is unchanged.

Lifecycle unit tests explicitly pass `OfflineHarness(sender, verify_suppression)`
to `run_notice(..., send=True, ...)` plus a pinned `e6-offline-injection-grant/1`.
The grant MUST say test_only=true and exact caller-attested candidate authority,
manifest/input/semantic/code/message-policy/suppression hashes, private recipient
and a validity interval <=1h. These are test grants, not production owner grants.

The suppression review must cover LEGACY_AUTO, ALL_KNOWN_MANUAL and E6_JOURNAL,
include a pinned APPLE_MANUAL proof, have <=64 bounded proofs and a review no
older than five minutes. An injected contract verifier must validate the
original proof bytes and return a verdict bound to their hashes and semantic
key. Missing/invalid/unknown coverage blocks attempts; prior confirmed proof
suppresses with zero sender calls. Production legacy/manual adapters and actual
suppression inventory qualification are NOT implemented or claimed. The test
proof schema is explicitly synthetic; no fake native ACK is recast into a
legacy/manual production proof. Fixed META cannot become an Apple lane.

A preexisting private external journal is mandatory (unchanged legacy ACL/
identity validator); repository/reparse/UNC/input-corpus destinations refuse.
Commit/fsync exclusive SENDING_INJECTED_ONLY before one callback, then revalidate
inputs, suppression, grant, directory identity and remaining deadline. Dispatch
window is bounded by 30s, grant/policy expiry and explicit source/holding ages.
The callback supplies a transient native witness (recipient/message ID/private
chat) and the existing native ACK/text/tag hash contract. Wrong or late bindings
refuse. Raw recipient/native ID never persist. Durable outer result is labeled
INJECTED_ACKNOWLEDGED, with NOT_ESTABLISHED_BY_TEST native delivery; original
E2/E4/E5 receipts never gain delivery state.

Orphan/truncated SENDING, unknown timeout, wrong ACK or result/fsync failure
requires reconciliation, with no automatic retry. Duplicate exact event returns
ALREADY_SENT_INJECTED_ONLY only after strict closed-schema record/hash checks.
Changed source version/policy/recipient blocks resend. The receipt directory is
not a hostile concurrent path-swap proof or a portable parent-directory fsync
power-loss guarantee; the known single-writer/static filesystem assumption remains.

## Bounds and stop line

Manifest <=64 KiB, policy/grant/review <=16 KiB, aggregate unique assessment
inputs <=8 MiB, each cross-lane proof <=64 KiB/64 proofs, each local journal
record <=64 KiB, one approved event, at most one injected callback. Existing E4
file/line/byte and E5 bounds remain. Source validators may reread the bounded
pinned set. A cooperative monotonic deadline is checked before/after validators
and before dispatch/publication; blocked filesystem operations are not preempted.
There is no corpus traversal, provider/broker/model call or paid-digest fallback.

This is the pure B candidate plus a C OFFLINE lifecycle harness from the E6
plan, not completion of production C/D. Actual private suppression adapters,
real Telegram/native ACK integration, independently approved message policy/
input/send grant, wrapper duplicate-key refusal repair, unchanged legacy/DDOG
refusals, PR81/PR82 local adoption and natural trigger proof remain gates.
BAD_EQUITY_OR_EXPOSURE is not fixed or bypassed. No E6 success may erase a
legacy SEC refusal. Independent Astra review is required before any later
production adapter, source/task adoption or actual message permission.
