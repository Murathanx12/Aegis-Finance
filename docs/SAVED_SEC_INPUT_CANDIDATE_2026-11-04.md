# Saved SEC forecast input — inactive P0 candidate

Base: fetched `origin/main` at `cac7f219e3074c3ef0f3ff51ce2b4d96fcc5788f`.
Worktree: `C:/Users/mrthn/aegis-saved-sec-input-candidate`.
Branch: `codex/saved-sec-input-candidate`. Uncommitted; no push/PR.

Scope: new `backend/services/saved_sec_forecast_input.py` and focused test only.
`build_saved_sec_input(event_bytes, ticker=..., cutoff_utc=...)` consumes injected
UTF-8 SEC JSONL bytes and returns `EVIDENCE_ONLY` with exact source row text/body,
accession, URL, row SHA256, publication/first-seen clocks and canonical packet
SHA256, or `REFUSED` with an explicit reason. UTC cutoff is mandatory. Both source
clocks must be at or before cutoff. Input bounds: 1 MiB, 64 lines. Exact duplicate
rows collapse; conflicting eligible versions and ambiguous documents refuse.
`verify_saved_sec_input` rebuilds against independently retained packet bytes/hash
and injected source bytes; changed selected-row bytes or context invalidate it.

Validation:

- `python -m pytest -p no:cacheprovider backend/tests/test_saved_sec_forecast_input.py -q`:
  **33 passed**. Tests use a labelled synthetic Apple-shaped row; block filesystem,
  socket, subprocess and application/model imports around adapter execution.
- `python -m ruff check --no-cache backend/services/saved_sec_forecast_input.py backend/tests/test_saved_sec_forecast_input.py`:
  **PASS**. Python bytecode generation disabled for validation.
- Separate native saved-byte replay read (no modification) from
  `C:/Users/mrthn/aegis-finance/backend/data/optimus/news_corpus/sec_edgar_8k_ex99_body/2026-11-02.jsonl`,
  line 245, selected by raw_id
  `0000320193-26-000024:a8-kex991q4202609262026.htm`: **4,629 bytes**.
  Cutoff `2026-11-03T16:08:33Z`: **EVIDENCE_ONLY**.
  At `2026-11-02T22:50:12Z`: **NOT_AVAILABLE_AT_CUTOFF**.
  Repeated exact line: identical packet. Changed report bytes: original packet
  verification fails. Adapter execution ran under IO barriers; corpus hash before
  and after replay matched.
- Native row SHA256:
  `2dd852f669eb318e1353b6ad3c20d26a3689b706bffddb8743bb71a45565138c`.
  Native replay packet SHA256:
  `e9909d9c5c14702696a7ec97dbc302e9340d7374fcc026880fed1039b4e00d9c`.

Limitations: byte integrity is not source authentication, semantic review, current
freshness, calibrated prediction or owner delivery. Caller asserts ticker and cutoff;
only the supported single-ticker SEC 8-K/EX-99(.1) document shape is admitted.
No beat/miss, Item 2.02, direction or numeric financial interpretation is inferred.
Hashes cover the selected exact line (including terminator) and resulting packet,
not unrelated/blank lines or the full caller-owned corpus. A modified row can form
a new packet; it cannot verify against the independently retained original packet.
Unkeyed hashes are not signatures. Source text is untrusted content, not instructions.

Runtime remains inactive: no caller wiring, clock reads, filesystem reads/writes,
network/model calls, forecasts, decisions, delivery or activation in the adapter.
No scheduler, Railway, Telegram, NAV, order, policy-pinned source or frozen forecast
changes. This qualifies an offline input candidate, not the completed runtime edge.
Independent review is owner-arranged and pending. No full-suite or deployment claim.
Consistent with CANON §§5–6 and the execution roadmap's certification-first standard;
no trial, capital authority or performance claim is introduced.
