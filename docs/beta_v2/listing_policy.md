# Original247 frozen-instrument calendar policy

This source build replaces the former six-identity default with a pinned,
explicit manifest of all 76 frozen native instrument/benchmark keys. It is a
calendar-classification policy for those frozen instruments. It certifies no
current listing status, freeze-date membership, point-in-time signal, vendor
delivery, grade or release acceptance. Independent source review and existing
source/task adoption remain separate; this change invalidates earlier child pins.

## Identity and evidence decision

`original247_listing_policy.json` contains the exact 56 US and 20 global keys
from the native inventory. Its sorted compact-JSON key-set SHA256 is
`d6c336ad9fe2e1f799c9fd038ea07c0121166726c78167cb19beb8f33f1b2331`.
The frozen 247-book ID-set hash is also bound, without copying any book IDs.
No private books, entitled prices, provider payload or original native history
is embedded. The loader never opens native evidence to reconstruct a policy.

The 71 direct public-body witnesses plus five inherited reviewed mappings support
calendar classification for all 76 exact instruments within the bounded policy
scope below. The `UNRESOLVED` schema disposition remains available: it requires
an explicit reason and no calendar, and cannot provide a fresh target. The
current manifest has zero unresolved calendar classifications; share-class,
source-date and current-status uncertainties remain explicit per instrument.

| Instrument group | Calendar policy | Authority and retained limits |
| --- | --- | --- |
| 56 US instruments | Common XNYS cash-equity session contract | Exact non-test Nasdaq Trader directory rows, directory definitions and explicit native-symbol equality. Actual venue stays separate: ASML is XNAS New York Registry Shares; SPY is ARCX; TMQ is XASE. XNYS does not relabel those venues. |
| 2308.TW, 2317.TW, 2330.TW, 2382.TW, 2454.TW, 6669.TW | XTAI | Exact official TWSE codes and named issuers in the 2026 factbook's end-2025 stock table; no continued-listing or class/ISIN certification. |
| 000660.KS, 005930.KS | XKRX | Issuer original/common-share tables with code and ISIN. Undated listing tables remain undated; nearby share-count or historical listed dates are not substituted. Samsung preferred 005935 and GDRs remain different lines. |
| 012450.KS | XKRX | Named issuer/code in the dated KRX June 9 filing, joined to issuer common-share issuance metadata. Two-body join and missing ISIN remain explicit. |
| 267260.KS | XKRX | Named listed corporation/code in the July 7 KRX filing supports this frozen code's market/calendar family. The body does not certify a per-security share class or ISIN. Those remain unresolved; this policy does not promote common-share/class certification or alias another line. |
| 6146.T, 6920.T, 8035.T | XTKS | Exact codes and named TSE Prime issuers in the retained JPX body. October 26 has no verified year; copyright 2022 is not the data year. This supports a scoped calendar-family assignment, not current-session listing certification. |
| 6857.T | XTKS | Advantest's April 1, 2026 organizational profile explicitly states TSE Prime and code 6857. No OTC substitution, ISIN or continued-listing claim. |
| ALL.AX | XASX | Issuer statement dated January 9, 2026 explicitly says ASX: ALL; no substitution of another ALL listing. |
| EVO.ST, SAAB-B.ST; HAG.DE, RHM.DE; KOG.OL | XSTO; XETR; XOSL | Previously reviewed exact mappings and saved calendar evidence. Their inherited receipt hash and exact packet excerpt are retained. No new public revalidation or newly certified venue MIC is claimed. |

This decision uses body-supported code/issuer/venue relationships to classify
frozen instruments. An undated table is not automatically useless for that
classification, and its collection date is not automatically a listing as-of.
The manifest preserves each URL, exact retained excerpt, excerpt SHA256, embedded
date or explicit null, retrieval interval/representation, class uncertainty,
vendor crosswalk and normalized actual MIC separately from the calendar role.
The public excerpts attest saved tool-extracted text, not raw HTTP bodies or
fresh fetches. Four structural hash receipts bind the input inventory and witness
packets without copying private native rows.

ASML/ASML.AS and TSM/2330.TW are distinct traded lines. Numeric official codes
are crosswalked individually to their existing .TW/.KS/.T/.AX keys; no suffix
rule, issuer nationality, cached-universe membership or price panel grants
calendar authority. Unknown keys remain unknown.

## Validity and expiry

The policy applies to grade sessions **2026-10-15 through 2027-04-19**, inclusive,
and observations on **2026-10-25 through 2027-04-20**, inclusive in UTC. A future
grade session relative to the observation is refused. The observation start is
the policy-build day, not an inferred witness as-of timestamp.

The first grade date follows the frozen October 14 cohort. Installed XNYS
sessions place April 19 at 126 sessions after the stated October 15 entry,
excluding entry, covering the longest declared horizon. One following observation
day permits its close-plus-90-minute check. This is an explicit finite
engineering scope for the frozen contract; it does not assert uninterrupted
listing during that interval or use witness recency as a trading signal.
Outside this scope the loader refuses with `POLICY_OUTSIDE_VALIDITY` and the
consumer WAITs. Extending scope requires a versioned source-policy change with
reviewed evidence, not an added owner-permission gate or an automatic fetch.

## Loader and consumer contract

`scripts/original247_listing_policy.py` reads the one source-owned manifest with
a fixed SHA256 pin. JSON must be UTF-8, sorted compact canonical bytes with no
trailing newline. Duplicate keys, nonfinite JSON, unknown schema fields, wrong
cohort/76-key hashes, missing/extra keys, broken source/excerpt hashes, absent
body matches, invalid crosswalks, missing calendars and invalid date scope refuse.
Every allowed calendar key must be installed. The manifest's single-line
canonical encoding avoids checkout newline conversion changing its byte pin.
Alternate path/pin/clock/calendar inputs are explicit fixture/review dependencies,
not runtime discovery or fallback. Reading the default policy is read-only.

`completed_session_targets` uses this policy by default and adds a compact
`listing_policy_receipt` containing its exact manifest pin, scope, identity hash,
validity and structural input receipts. The complete witness details remain in
the hash-bound manifest. The R1 validator binds this receipt to its independent
consumer reference alongside symbol, reviewed calendar, common S and clock.
Missing/contradictory policy provenance cannot authorize grade dispatch.

The default `run_original` additionally requires its verified books' complete
constituent/benchmark union to equal the 76-key policy binding. This check follows
the existing exact-ID/prior-valid-receipt lookup. A valid existing same-session
receipt is reused unchanged even if a later policy is unavailable or expired.
No regrade is performed to retrofit new provenance. Explicit injected mappings
remain available for synthetic fixtures and reviewed callers; they are not
production identity discovery.

The common XNYS S contract remains: S must be a local session for each admitted
listing, with local close plus exactly 90 minutes elapsed. A local holiday,
unclosed market, unsupported identity or failed policy remains WAIT. Calendar
classification does not prove S marks exist. The unchanged GP diagnostic and
authoritative `validate_marks` still require exact unique finite positive marks
on the same bounded shared-union snapshot. Panel selection, source hashes,
read-race guards, stdin G, exact 247 IDs, `grade_once`, `ALREADY_GRADED` and the
composite population1000 call remain intact. No GP/task/scheduler/runtime source
adoption or native writer changes are included.

## Verification and publication boundary

Focused tests cover the complete manifest and tiny synthetic price/247-ID
fixtures, clocks/expiry, local holidays, tampered/missing/extra/alias inputs,
canonical JSON, public excerpt/provenance refusal, default integration, R1 proof
refusal and the unchanged 64 KiB child-output ceiling. They mock the writer and
forbid fetch/ensure/downloader calls. Test output, exact source pins and limits
are recorded in the private `build-batch3-20261025/C10_POLICY_BUILD.md`.

The coordinator owns any separately reviewed native pure-helper qualification.
This builder performs no native writer, market-data fetch, source adoption,
task-pin change, financial action, commit, push or deployment. No tests/native
imports run during the 16:35–17:10 local quiet window.
