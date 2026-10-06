# REVIEW 2026-10-06: C4 Opportunity Explorer (adversarial investor pass)

Reviewer: Opus 5.5, read-only. Build under review: `backend/routers/opportunities.py`,
`backend/services/opportunities.py`, `scripts/opportunities_build.py`,
`backend/tests/test_opportunities_router.py`, `frontend/src/app/opportunities/page.tsx`,
`frontend/src/app/brain/page.tsx`, edits to `backend/main.py`, `frontend/src/lib/api.ts`,
`frontend/src/lib/control-api.ts`, `scripts/stock_lists_v3_build.py`.
Receipt read: `backend/data/optimus/opportunities/opportunities_2026-10-06_20261006T161647Z.json`
(947 rows across 10 lists).

## VERDICT: MERGE WITH FIXES

Fixes required before the owner is told "done": F1, F2, F3, F4, F5, F6. The rest can follow.

The plumbing is honest. Every price, target, insider trade and news item in the 947 rows carries a
`source`. A missing field has a `missing_because`. The router is read-only and returns 404 rather than an empty
table. Receipts are chosen by the name stamp, not the mtime. The contest sheet's warning is a
visible banner. The trouble is in the labels a reader acts on. The High-Risk badge points the
wrong way on the owner's own examples. "Direction UP" sits beside a negative upside. The
insider window claims 180 days when the table holds 18. None of these is fabrication. Each one
makes a confident-looking cell mean something different from what it says.

## Tests run

- `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_opportunities_router.py backend/tests/test_signal_reachability.py -q`
  -> **17 passed, 1 warning (starlette deprecation)**.
- `npx tsc --noEmit -p frontend` -> **exit 0, no diagnostics**.
- Tests that assert their own fixture: the null-reason loop in
  `test_latest_shape_and_serve_time_age` builds rows whose `missing_because` it already filled in
  (`_row()`), then asserts the reasons are there. It cannot fail. No test asserts a mock outright.
  But **the 906-line builder that produces every number on the page has zero tests**. All eight tests
  cover the 202-line reader or `links()`. `resolveApiBase` (the site fix) also has no test.

## Findings

**F1. HIGH: the High-Risk Innovation badge is wrong on the owner's own names.** `build_row`
(`scripts/opportunities_build.py`, the `# lane` block) puts a row in HIGH_RISK_INNOVATION for ANY
flag: fewer than 5 analysts, a 21-session move of 15% or more, an `against` card, or a regex hit on
`pdufa|fda|topline|phase 3`. Result from the receipt:
- `roi_v3 KYTX`: clinical-stage CAR-T, BLA guided for Q4 2026, +406% to median → **lane CORE, flags []**.
  Its regulatory catalyst says "rolling BLA", which the regex does not match.
- `roi_v3 QUBT`: quantum micro-cap, the research note vetoed it for "thin fundamentals" → **CORE, flags []**.
  It has n=6, so the analyst-count rule does not fire.
- `roi_v3 RHI` (Robert Half, a staffing firm with 9 analysts) → HIGH_RISK_INNOVATION because its card is
  `against`. `MAN` (ManpowerGroup) gets the same badge because sigma63 puts its move at 16%.
- 30 of the 65 ROI rows and 371 of the 700 screen rows carry the badge, so it no longer separates anything.
- No runway or cash-burn flag exists, though the owner named runway.

So 2 of the 5 names the owner listed carry no badge, and two staffing companies are labelled
"innovation". Fix: split the badge into "Thin coverage", "Binary event" and "High vol". Add BLA,
NDA, sNDA, CRL, readout and "regulatory" to the event regex. Add a runway flag where XBRL cash and
burn exist. Keep "High-Risk Innovation" for thin coverage AND (binary event OR pre-revenue).

**F2. HIGH: "Direction UP" contradicts the upside cell in the same row.** Direction is the sign of
the consensus rating plus the sign of 90-day revisions. It ignores where the price sits against the
targets. 14 rows show `direction UP` with a NEGATIVE median upside. Examples: `EXEL` (median
52.5 vs price 58.85, -10.8%, UP), `RHI` (-9.7%, UP), `RGEN` (-2.4%, UP). An investor reads a green
UP pill beside a red -11% and has to guess which one to believe. Fix: when the median upside is
below 0, cap the label at NEUTRAL or MIXED. Or rename the column "Analyst stance", which is what it
measures, and keep "Direction" out of the UI until something forecasts direction.

**F3. HIGH: the owner's "low-upside" complaint is not implemented as a flag.** FIZZ shows a green
"+4% to median" from **one** analyst (L=M=H=31). MANH shows +7% and EXPO shows +31% (L 72, M=H 90,
5 analysts). Colour depends only on the sign (`medUp >= 0 ? emerald : red`). 34 rows have a median
upside under 5%, and 32 rows have low == high (a single target), yet they render with the same
range strip as a 40-analyst name. Fix: (a) a grey "LOW UPSIDE" pill below a declared threshold,
e.g. a median under +10% or under one 21-session MoveScore; (b) a "1 target" pill when low == high
or n < 2, instead of drawing a range that does not exist. (EXPO note: the receipt says +31% to median.
That does not match the owner's reading, so check his source before deciding that EXPO is a
data error.)

**F4. MEDIUM-HIGH: the insider window is labelled 180 days but covers about 18.** `insiders.window_days = 180`
and the Detail panel prints "last 180 days". The column header tooltip says the same. But
`table_covers_from_utc = 2026-09-18`. Only 18 to 19 days of Form 4 exist. The research note on SOC
says "insiders sold at 3x today's price". Its row shows "no open-market Form 4 ... since
2026-09-18", which is accurate, but the "n/a" beside it reads as "no insider selling". The RGEN CEO
sale IS shown correctly: 3 sells, $3.44M, all under 10b5-1, with filing links. Fix: print
`min(180, days since coverage start)` as the window, and show "coverage starts 2026-09-18" in
the cell rather than only in the hover text.

**F5. MEDIUM-HIGH: "why the engine picked it" cites evidence written after the pick.**
`load_cards()` takes the NEWEST card per ticker across every day folder. Books frozen on 2026-09-25
quote 2026-09-27 cards: 23 of 23 rows in `human_ai_thematic_v2`, 24 of 28 in v1 and 9 of 11 in
`probe_equal`. The page calls this column "why the engine picked it". A card the engine could
not have read at freeze time is "what we think now", not "why picked". Separately, the filler
reason "fundamentals proxy percentile 0.37" is appended to any row with fewer than 3 reasons.
A 0.37 percentile is below the median, so it argues AGAINST the pick, and no service used it to
pick. "ROI hypothesis score -0.0% (rank 53)" is shown as a reason for RGEN. Fix: pick the
newest card with `day <= list.asof` for "why picked", and show a later card under a separate
"since the pick" heading. Drop the fundamentals filler unless the list was ranked on it.

**F6. MEDIUM-HIGH: production will 404. The receipt is not in git, and the builder is pinned to one date.**
`git status` shows `?? backend/data/optimus/opportunities/`. The 5.1 MB receipt is untracked, and
the Railway image builds from git, so `/api/opportunities/latest` will return 404 on the public
site that the CORS fix just opened. `roi_list_v3.json` does not exist either, so the ROI list
came from re-parsing Markdown (the `source` field says so honestly). The JSON hook never ran.
`STOCK_LISTS_ASOF = "2026-09-27"` is a module literal: the next stock list will never be picked up,
and no staleness gate exists. This is the `funnel_night10.json` pattern from CLAUDE.md, rebuilt:
a static file, no scheduled caller, no age check. Fix: commit the receipt (or a trimmed one) or build it
on deploy. Derive the as-of from the newest `stock_lists/<day>/`. Add
`OPPORTUNITIES_STALE_DAYS` with a red banner on the page, like `FUNNEL_STALE_DAYS`.

**F7. MEDIUM: the page never shows the dates behind targets and prices.** 924 of 947 rows compare
a 2026-09-29 target snapshot with a 2026-10-05 close. That is a modest gap, but `analyst.observed_utc`
is in the receipt and never rendered (grep `observed_utc` in page.tsx: 0 hits). The price date
appears only in a hover title. The analyst count comes from yfinance on 2026-09-27 and the L/M/H
from the snapshot of 2026-09-29: two sources, two dates, one cell. Fix: one muted line under the
strip, e.g. "targets 09-29 (snapshot, n from yfinance 09-27) · close 10-05". Hover text does not
work on a phone.

**F8. MEDIUM: Direction and revisions are "as of today", but nothing on the page says so.**
`ctx["asof"] = today` (2026-10-06). The revision pull stopped on 2026-09-29, so the "last 90 days"
window has a silent 7-day hole at its end. The lists were frozen on 09-25 to 09-27. For a "current
view" this is acceptable, but if anyone grades a list by its Direction column, that grade leaks
information from after the freeze. Fix: show "revisions through 2026-09-29" and keep the freeze date
beside the list title.

**F9. MEDIUM: MoveScore is one click from ranking a long list.** The default sort is file order (rank
for ROI, weight for books), which is correct. But "MoveScore" is a sortable header on every list.
Only the contest sheet carries the banner, so sorting the ROI list by MoveScore gives the owner
a magnitude ranking with no warning. Fix: on lists where `magnitude_ranking` is false, make
MoveScore non-sortable, or show the same amber banner while the table is sorted by it.

**F10. MEDIUM: the site fallback can quietly send a developer to production.** `resolveApiBase` sends
any value that is not an absolute http(s) URL to `PUBLIC_API_FALLBACK`. A developer's
`NEXT_PUBLIC_API_URL=localhost:8000` (no scheme) or `/api` would hit the PRODUCTION backend, with
only one `console.error`. The desktop path is safe: `next.config.ts` forces
`NEXT_PUBLIC_AEGIS_DESKTOP_BUILD=1` and blanks the URL, and `desktop` wins first. (Note:
`frontend/.env.local` already points dev at production, which predates this build.) Fix: fall
back to production only when `NODE_ENV === "production"`; otherwise fall back to localhost. Add a
unit test of `resolveApiBase` covering the placeholder, scheme-less, empty and desktop cases.

**F11. LOW: CORS change is narrow; the test checks the list, not the behaviour.** One exact
origin is appended, with no regex or wildcard, so `allow_credentials=True` widens nothing else.
The origin is hard-coded in `main.py` rather than in `config.py` (house rule). The test asserts list
membership rather than the `Access-Control-Allow-Origin` header returned for a preflight from that origin.

**F12. LOW: performance.** Every request re-parses the 5.1 MB receipt (`load_latest`, no cache).
Selecting `analyst_upside_v3` ships 3.4 MB of JSON to the browser. Cache the parsed blob keyed
on the file name, and page or trim the 700-row screen (news[] and catalysts[] dominate).

**F13. LOW: CRL is never explained.** 16 rows mention "CRL" in their falsifier (BBIO, AGIO, ...)
and there is no glossary or tooltip (grep `CRL|complete response` in the page: 0 hits). The owner
asked exactly this. Fix: a three-entry glossary in the legend: CRL = FDA Complete Response
Letter (rejection pending fixes), PDUFA = FDA decision date, BLA/NDA = the application itself.

**F14. LOW: foreign names are LLM strings with clutter in them.** For example
"Advantest Corporation (TSE Prime: 6857 / 6857.T), Tokyo, JPY listing currency" and
"Robert Half Inc. (RHI)". The source is the DeepSeek card, which the field states honestly.
Strip the parentheticals for display. Foreign rows have no sector, only the book theme.

**What passed (with evidence):** 947 of 947 rows have a source on every price, analyst block and
news item. The 31 upsides from fewer than 2 analysts all carry the "thin coverage" flag, so
none is unflagged. No `missing_because` gaps were found on the audited fields. The contest
banner is visible text, not hover-only. Book weights are the frozen `books.jsonl` positions, each
with a `book_id`, and they sum to 0.97-1.00 with declared cash. Excluded names (QUBT, KYTX, SOC,
NOVT, SLDP) are SHOWN, marked EXCLUDED, with the research-note veto text. RGEN's CEO 10b5-1 sales
appear with filing links. `tsc` is clean and the tests are green.

## The three things I would have done instead

1. **Lead with a "since the pick" column.** Each list was frozen on a known date. Show the return
   since freeze against SPY over the same sessions, and the ROI list's own 21-session check date
   (2026-10-26). An investor's first question is "is this working", and the page cannot answer it.
2. **One lane taxonomy driven by the owner's three words: coverage, binary, runway.** Not one
   catch-all badge triggered by sigma. Build the owner's 10 named tickers into a golden test that
   asserts each one's badge, so a regression shows up as a red suite and not as an owner complaint.
3. **Test the builder, not the reader.** Use a 20-row fixture taken from the real receipt (pinned and
   committed) and assert the behaviour: no card dated after `list.asof` in why-picked, an
   insider window no longer than the coverage, Direction never UP when the median upside is below 0, and
   the regex catching BLA and CRL. The reader is 200 lines of glue; the builder is where the
   errors in F1-F5 live.

## Investor's question: five minutes before the US open

Only partly. It is clearly better than the PDF: you can sort, links open the source, insider
filings are one click away, and you can see why a field is empty. But nothing on the page asks
for a decision today. No column says what changed since yesterday or since the freeze, and the
two signal-looking columns (Direction, High-Risk) contradict the rows they sit in (F1, F2). As it stands
I would use it as a reference lookup, not as a pre-open screen.

- **Add:** (1) *Return since freeze vs SPY* (sessions counted); (2) *Event in the next 21
  sessions*: date, kind, and the MoveScore beside it, so magnitude sits next to a reason for magnitude.
- **Delete:** (1) *Coverage*. It repeats "N analysts" already printed in the price cell, and
  short interest and Congress trades belong in the detail panel. (2) *Direction* as built. Replace it
  with an "Analyst stance" pill inside the price cell until a model actually forecasts direction.

## Score: 63 / 100

| Part | Score |
|---|---|
| Provenance and refusal discipline | 23 / 25 |
| Labels a reader acts on (F1-F5) | 10 / 25 |
| Deployability and freshness (F6, F10) | 12 / 20 |
| Tests (the builder is untested) | 9 / 15 |
| Usefulness before the open | 9 / 15 |

The total is held down by the labels. The data underneath is sound.
