# Copied local-claim row audit

`scripts/beta_v2_local_claim_copy.py` is the unchanged reviewed R2 module. Its pure
`verify_local_claim_copy(trace_raw, row_manifest_raw, row_raw=None, *, manifest_sha256)`
API accepts supplied bytes only and is portable on POSIX and Windows. It does not
search native files, reopen an article, call a model/provider or query a ledger.

The independently pinned c91 TRACE carries source/item/generation/reader-source/PID
at its top level and the raw text digest at `copy.text_sha256`. The row's
`article_sha` must equal the TRACE's 20-character source ID; row `source_id` is a
column label with unverified provenance. First-seen/publication metadata must
agree after timezone normalization. A matching ID does not establish semantic
grounding, producer generation or actual consumption.

TRACE and manifest each have a 64KiB cap; the optional single complete copied
JSONL row has a 256KiB cap, including LF or CRLF. Strict UTF8/JSON, duplicate-key,
finite-number, nesting, type, digest, length and row-profile checks fail closed.
No pointer means `ROW_LOCATOR_REQUIRED`/UNKNOWN, not absence of claims. A valid
row can yield only `LOCAL_CLAIM_COPY_BODY_ID_MATCH_ONLY`. Native offset/row hash
remain declared and unread; a prefix reference remains declared, never verified
by a row-only read. Quote/paraphrase/URL/ticker are not included in the report.
`actual_consumed_ids` is always null; typed/event/forecast/position/delivery stay
UNKNOWN. Supplied-copy consistency does not authenticate native production.

The private filesystem wrapper/CLI is intentionally PC-specific and fixed to its
private evidence root. It cannot be widened by a caller-provided root. Unsupported
platforms refuse. Outputs are create-only; copied input identities and bytes are
re-read for stability before a new report. This is not an OS sandbox or a runtime
adoption. Portable tests use only synthetic bytes and negative pre-I/O path traps;
they do not patch root authority or certify positive filesystem admission.

The tests directly exercise `guard_contract.assert_refuses_missing_input` for the
pure API, with forbidden-effect counters asserted outside the shared helper.
No services registry, exemptions, shared fixtures or classification are changed.
Private qualification of the original R2 module (including the exact accepted
TRACE profile and real namespace result) remains separate evidence; no private
fixture, machine path or native data is needed by the public suite. No new claim
consumption, strategy, signal, financial writer or runtime operation is introduced.
