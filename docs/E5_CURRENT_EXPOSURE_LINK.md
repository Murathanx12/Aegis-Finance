# E5 local current exposure linker

PRODUCT_EXPERIMENT. Sol builder implementation; independent Astra review pending.
No production caller or E2/E3/E4 schema/authority changes.

`scripts/current_exposure_link.py` exposes `build_link(...)` (read-only) and
`write_link(evidence_dir=..., filename=..., ...)` (build plus exclusive external
write). Every path/hash and the one E4 event/source locator must be explicit.
No defaults, discovery, provider, broker client, network, ledger, scheduler,
forecast, outbox, owner send or trade path. External replay is its local caller.

## Inputs and authority

`Pin(absolute_path, expected_sha256)` binds the whole E2 receipt, linked page,
subject assertion, mapping selection, four mapping inputs and broker receipt.
E4 validates the complete multi-group E2 receipt and exact selected source row.
E5 requires one source, its linked full page URL, and an explicit full-subject
E1 caller assertion on the exact payload/raw-line/page hashes. A tag or mention
cannot substitute. The assertion is caller-attested, not a new model decision.

Subject schema `e5-subject-assertion/1`: schema, source_sha256, raw_line_sha256,
page_sha256, issuer_cik, issuer_name, qualification, observed_at_utc, rights.
Requires FULL_ISSUER_SUBJECT, CIK 1326801, Meta Platforms, Inc., LOCAL_METADATA_ONLY.

Mapping schema `e5-mapping-selection/1`: schema, observed_at_utc, provenance_mode,
input_sha256, candidates, issuer_candidates, rights. `issuer_candidates` is the
actual PR79 `CandidateMapper.candidates('1326801', observation)` result.
`candidates` is the separate proposed META/Class A Common Stock/NASDAQ/us_equity
profile with no conflicts. Its class/venue binding is an inference, never PR79
certification. The four input pins are master/master_meta/proxy/proxy_receipt.
E5 rereads their bytes, checks master CIK/symbol uniqueness, normalized name,
unique US META/NMS proxy and row counts. Only current-observation provenance is
accepted; a fabricated pinned historical manifest is not an availability proof.
The replay uses the unchanged reviewed PR79 pure mapper in its separate local
checkout and records the code hash; that module is not adopted into this branch.

The existing `aegis_current_paper_asset_witness/v1` receipt is bounded to 64 KiB,
three explicit META/TGT/XYZ entries, exact field sets, ordered common interval
<=60 seconds and response hashes. Only active NASDAQ META Class A us_equity with
strict boolean nonzero and equal opaque asset/position IDs can qualify. Other
symbols cannot join. Without a broker receipt, a pinned older PC snapshot can
support only SYMBOL_OVERLAP_ONLY and cannot identify a security.

## Clocks, output and trust

E5 captures real invocation UTC itself. Optional cutoff_utc filters earlier views
without replacing invocation time. Missing/naive/future clocks refuse. Source,
subject and mapping after cutoff refuse. Broker observation after cutoff yields
HOLDINGS_AFTER_CUTOFF with no relation chain. At 06:29:55 the real replay refuses
the later subject assertion; the 08:02 holding cannot establish event-time holding.

Strongest saved result: CURRENT_HELD_ASSET_CANDIDATE_CALLER_ATTESTED at the saved
08:02 common observation interval. Separate asset/position clocks and position
as-of remain UNKNOWN because only a common interval is supplied. Broker origin
is UNVERIFIED_SAVED_RECEIPT; issuer security basis is NAME_SYMBOL_CLASS_VENUE_INFERENCE;
event_time_holding=UNKNOWN; PIT_security=UNVERIFIED. Stronger verified status is
unavailable. No owner decision, delivery, forecast or portfolio action follows.

Pins bind bytes, never authorship or historical dates. Obtain them from a trusted
handoff. A fabricated caller timestamp cannot be independently detected from its
own self-hashed bytes, and it confers no independently verified PIT authority.
The external subject assertion is newly observed from saved E1 review, and the
mapping selection has its actual current observation clock, not Sep/Nov vintage.

Malformed/missing/extra/duplicate inputs and identity/hash/clock collisions fail
loud with sanitized codes. The bounded E4 reader rejects redirected paths. The
writer requires an existing external directory, rejects repository ancestors and
redirects, and exclusively creates a freshly built receipt. No licensed text/URL,
account, quantity, price, P/L or raw asset ID appears in output. Only hashes,
clocks, safe IDs, fixed labels and a nonzero boolean are retained.

## Validation

Focused E5 tests cover false Binance->TGT and Nasdaq->XYZ, class/CIK/venue/reuse
collisions, wrong page, missing inputs, zero/mismatched position, hash/clock tamper,
bounded reads and exclusive writes. E2/E3/E4/sidecar regressions remain unchanged.
The external packet contains exact replay/test harnesses, sanitized receipts and
input pins. Network is denied and writes confined to that packet. The regression
harness permits only the pre-existing synthetic junction test's mklink command,
with both target paths checked inside the external packet. Real private source
files are read only and never copied. No push or production adoption.
