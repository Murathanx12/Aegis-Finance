# SEC login CIK correction: local review scope

Follow-up to 387c843f and independent Astra P2. No deployment, send,
adoption, runtime reads or runtime writes are authorized by this patch.

SEC's official explanation identifies the accession prefix as the login CIK,
which may belong to a filing agent:
https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/understand-select-set-default-login-cik

The legacy warning builder already separates login and issuer. This follow-up
removes the same invalid equality from saved_sec_forecast_input and from the
runner's manual suppression validator. Title issuer/URL subject equality,
full accession directory, exact filename, ticker constraints, clocks, byte
hashes, reviewed manual proof/ACK bindings and all-or-none selection remain.
The suppression schema has no independent issuer field: its exact reviewed URL
and corpus hash matching remain mandatory, not a fabricated login/issuer link.

## Remaining provenance boundary

This is consistency and byte integrity, not issuer authentication. A coordinated
title CIK plus URL subject change retaining the ticker can still pass. A synthetic
runner regression explicitly pins that limitation; preview remains PROVISIONAL,
NOT_SENT, with NO_CALIBRATED_EVENT_FORECAST and zero new allocation.

Inspected code paths:
- scripts/news_pull.py fetch_edgar_ex99: fetches index-headers.html and parses
  exhibit documents, but emits title, URL, body, accession/filename and entity
  tags rather than a separately qualified, saved issuer/header proof.
- scripts/news_pull.py row normalization: ticker resolution is metadata, not an
  independently captured issuer-to-ticker proof consumed by this runner.
- backend/services/edgar_events.py: SEC company_tickers lookup and submissions
  exist with in-process expiring caches; this warning path does not inject or
  qualify that mapping as saved evidence.
- scripts/edgar_8k_items.py: a separate research ticker/CIK cache with fetch
  metadata exists, but is not a warning input bound to this capture/cutoff.
- scripts/owner_event_warning.py run: consumes frozen corpus/snapshot bytes;
  it does not consume an authenticated saved SEC index/header or mapping.

No qualified provenance input was found in the inspected warning pipeline.
Adding one requires a separately reviewed capture/schema and qualification
contract, including provenance, time, conflicts and refusal behavior. Fetching
current mappings or trusting an unrelated cache would not establish provenance
of these saved bytes. No unsourced linkage was added. This patch makes no claim
of issuer authenticity, automatic delivery eligibility or owner receipt.

Verification uses synthetic saved rows only, no licensed body. Runner previews
exercise lineage plus both builders, preserve filesystem bytes, reject hostile
title/URL subjects, accession directories, filenames and ambiguous tickers before
any delivery invocation. Existing tests retain send/review and refusal coverage.

Focused validation: AEGIS_IGNORE_DOTENV=1 python -m pytest on
backend/tests/test_owner_event_warning.py, test_owner_event_warning_runner.py,
test_saved_sec_forecast_input.py and test_saved_sec_event_path.py:
247 passed, 1 skipped. Ruff check passed for the warning builders, runner and
touched test modules. git diff --check passed. This is local test evidence,
not an independent Astra re-review or deployed/runtime proof.
