# Teacher Library — ownership-forms ingestion (Forms 3/4/5)

**Order 5** of `docs/HANDOFF_OPUS5_2026-08-15.md`. Built and proven on real
EDGAR data 2026-08-15. **Production cycle is NOT yet verified** — see §5.

## 1. Why a new path, and not the existing Form 4 fetcher

`insider_form4.parse_form4_open_market_buys` does exactly what its name says:
transaction code `P`, acquisitions only, one ticker at a time. That is right for
a buy-signal feature on a stock page and **structurally wrong for a Teacher
Library**, in two ways that both point the same direction:

**It cannot see losers.** R6 is explicit: *losers are studied with the same
machinery as winners — otherwise this is reverse-engineered hagiography.* Ask
"do insider trades predict returns" of a corpus containing only purchases and
the sample cannot disagree. Measured on 25 real Form 4s from 2026-08-13: **60
transactions, of which 20 sells and 2 buys.** The old parser would have kept 2
rows out of 60.

**Its universe is our universe.** Looping over 150 tickers we already track
yields insider activity only at companies we already found interesting, and any
cross-sectional claim inherits that selection invisibly. The SEC daily index is
the agency's own list of everything filed, so coverage has a denominator.

## 2. What is parsed now

`backend/services/ownership_forms.py` — pure, offline, 26 tests.

- **Every transaction code**, acquisitions and dispositions, with the code and
  its meaning preserved. An unknown code stays `unknown:X` rather than folding
  into "other", so a future SEC addition is visibly unhandled.
- **`is_discretionary_market_trade`** — only `P` and `S`. Grants, tax
  withholding and option exercises are compensation mechanics, not opinions;
  mapping code `A` to BUY is how "insiders are buying" charts get built out of
  payroll.
- **Derivative and non-derivative tables.** An option exercise and a same-day
  sale are two rows that mean one thing and are only visible together.
- **Form 3 holdings.** Not transactions — the opening balance every later delta
  is measured against. Without them an actor's first appearance looks like their
  first trade.
- **Officer / director / 10% owner, and the officer title.** R6 asks "CEO vs CFO
  vs director"; unanswerable unless these travel on the row. Tri-state: a filing
  that does not say is `None`, never `False`.
- **Rule 10b5-1, tri-state.** Explicit element (post-2023), else a footnote
  mention, else **UNKNOWN**. Returning `False` for "no element" would relabel
  every pre-2023 planned sale as discretionary — manufacturing precisely the
  finding a 10b5-1 study exists to test. On 2026-08-13: 222 true, 0 explicit
  false, **1,345 unknown**, and the unknowns carry a flag so a study can exclude
  rather than silently count them as one side.

## 3. The source: SEC daily index

`backend/services/sec_daily_index.py`.

**Point-in-time by construction.** `form.YYYYMMDD.idx` for a day is published
after that day closes and lists what became public that day. A collector walking
forward one day at a time cannot see a filing before the world did. That is a
property of the file, not a rule we impose and hope to keep.

**`NOT_YET_PUBLISHED` is a real state.** S3 answers a missing key with **403
AccessDenied, not 404**, so "today's index isn't posted yet" and "we have been
blocked" arrive identically — and the retry logic then backs off into a
timeout. Measured 2026-08-14 15:00 UTC: latest published was 2026-08-13, and
asking for 2026-08-14 produced 403 → ReadTimeout, which the caller would have
recorded as a source failure. `fetch_index` now checks the directory listing
first.

**No silent backfills.** `collect_day` refuses anything older than yesterday
without `allow_historical=True`, which stamps the rows as Gym material rather
than forward evidence — the same discipline COPY-LAB already enforces at the
lane, applied at the source.

## 4. Two defects found by running it for real

**The date format.** The live file uses `YYYYMMDD` with no separators. The
first fixture invented `YYYY-MM-DD`, the parser was written to match the
invention, and the whole path reported a Thursday of 1,098 insider filings as
`OK_EMPTY`, *"index published but held no ownership forms"*. Green tests, zero
rows, a plausible status. **A fixture that agrees with the parser and not with
the source proves only that they agree.** Both spellings are now accepted and
both are in the fixtures.

**Joint filings.** A Form 4 filed jointly appears once per reporting entity:
2026-08-13 held **1,098 index rows covering only 512 distinct accessions**, and
one filing (Chime Financial with ten DST Global funds) appeared **eleven times**.
Two consequences, both fixed:

- We fetched the same document up to 11×, doubling the run to 28 minutes and
  reporting "1,098 attempted" for 512 documents — coverage describing work
  rather than data. Now deduplicated by accession before fetching: 512 fetches,
  0 parse errors (down from 4 — the errors were timeouts on redundant requests).
- `findtext` returns the **first** match, so the parser read one reporting owner
  and dropped the rest. Joint filings *are* the cluster case, so the loss was
  concentrated exactly where it mattered most. All owners are parsed now; the
  event is still emitted **once** (emitting per owner would multiply the share
  count and turn one disposal into an eleven-insider "cluster" that never
  happened) and carries `joint_filing_lead_filer_of_N`.

## 5. What one real cycle produced — and what is still unproven

`python -m scripts.collect_ownership_day --day 2026-08-13`

| | |
|---|---:|
| index rows | 1,098 |
| joint-filing rows collapsed | 586 |
| distinct documents | 512 |
| attempted / coverage | 512 / **1.000** |
| parse errors | **0** |
| events in ledger | **1,567** |
| SELL / BUY / other | **516 / 87 / 964** |
| distinct actors / tickers | 482 / 294 |
| Form 3 / 4 / 4-A | 108 / 1,436 / 19 |
| officer / director / 10% | 974 / 717 / 228 |

Re-running is fully idempotent (1,563 submitted, 1,563 recognised as
duplicates, 0 written).

**Scheduled** as `pi_ownership_collect`, daily 06:00 ET — safely after EDGAR
posts the prior day's index — writing a dated receipt per run. A run that writes
nothing logs a WARNING with the counts, because the house failure mode is a
collector that runs green and produces nothing forever, and this project has
already shipped one: *the insider collector passed twelve tests while 403-ing on
100% of production fetches.*

**Not yet true, and must not be claimed:**

- **The production cycle has not run.** Everything above is a LOCAL cycle
  against live EDGAR. Railway's egress is a different network from this laptop's,
  and the 403 history above is exactly why "it works locally" is not evidence.
  The first scheduled prod run must be verified by its receipt, not assumed.
- **Day one lacks one flag.** The 1,567 rows were written by the pre-fix parser,
  so joint filings among them are attributed to the lead filer **without**
  `joint_filing_lead_filer_of_N`. Share counts and attribution are correct; only
  the disclosure flag is missing, and re-collection cannot add it because the
  event ids match and dedupe correctly. It applies from the next run onward.
- **COPY-LAB still cannot accrue from this.** Wiring these events into
  `CORPORATE_INSIDER_CLUSTER` eligibility is the next step, not this one.
  `ACTIVIST_13D` stays blocked until 13D ingestion exists.

## Matched controls exist BEFORE any winner is interpreted (T3, 2026-08-15)

`backend/services/teacher_library/matched_controls.py`, 21 tests.

The tempting first result from a Teacher Library is a story — *a CEO bought
after a 40% drawdown and the stock doubled*. That sentence contains no
comparison, so it cannot be wrong, so it cannot be evidence. A control built
after such a story is found is chosen, however honestly, by someone who already
knows which control lets the story survive. So the engine is written first and
its covariates are declared before an event is scored:

`sector` (matched **exactly** — a nearby sector is not a sector), `log_market_cap`,
`beta`, `momentum_12m`, `realised_vol_60d`, `drawdown_pct`, `log_dollar_volume`,
`days_to_next_earnings`. **`valuation` is deliberately absent**: unreliable
across financials, REITs and loss-makers, and a covariate missing for a third of
candidates silently restricts the pool to the two-thirds where it exists.

Four arms, all run together so the kind one cannot be chosen afterwards:

| arm | what it removes | what survives means |
|---|---|---|
| `matched_security` | sector, size, momentum, vol, drawdown, liquidity | not the market |
| `actor_shuffle` | *who* acted | not the identity |
| `date_shuffle` | *when* they acted | not the timing |
| `sign_flip` | buys vs sells | not long-equity drift |

Design points that are load-bearing rather than decorative:

- **Controls come from the same date.** A control measured over a different
  window compares against a different market, and the market moves further than
  any insider signal in this sample.
- **Balance is measured, not claimed.** Every match reports the standardised
  mean difference per covariate; an unbalanced set is marked *uninterpretable*,
  because "matched" carries authority the numbers have to earn.
- **A candidate missing a covariate is not a close match on it.** Skipping the
  term would preferentially select candidates with missing data.
- **Clustered events are not independent ones.** Five insiders filing on one
  issuer in one week are one event; `n_event_clusters` shrinks the effective
  sample, and not doing so is the easiest way to manufacture significance here,
  because clusters are exactly where the interesting stories live.
- **Too few controls is UNPOWERED, not a null**, and the summary distinguishes
  *"we cannot evaluate this yet"* from *"we evaluated it and found nothing"*.
- **A shuffle placebo requires a seeded rng** and refuses without one: an
  irreproducible placebo is a number, not a control.

## ACTOR SURPRISE is data-blocked, measured 2026-08-15

The ordered next step (T1) is `P(action | actor history, issuer state, market
state)` — *how unusual is this action for THIS actor*. A CEO who buys every
quarter is a different signal from one who sold or held for eight years and then
buys after a 45% drawdown, and that distinction is the whole point.

It needs actor **history**. Measured on the corpus as it stands:

| | |
|---|---:|
| events | 1,589 |
| resolved actors | 485 |
| actors with exactly **1** event | **234** |
| with 2 | 87 |
| with 3 | 43 |
| with ≥4 | 121 |
| transaction months represented | one (2026-08 holds 1,147 of them) |

The median actor has **one observation**. `P(action | actor history)` estimated
on one observation is not a weak estimate, it is a restatement of the action.
Building the scorer on this corpus would produce a number for every actor and
mean nothing for almost all of them — and it would look like a working feature.

**What IS computable now**, without actor history, and could be built first:
insider role (officer / director / 10%), independent-insider clusters, opposite
actions within one issuer, 10b5-1 status, and event proximity.

**What unblocks the rest** is a per-actor backfill of prior Form 4s from EDGAR.
That is a baseline, not a track record, and it is PIT-safe (filings carry
`filed_at`) — but it is **not authorized** and must not be confused with a
COPY-LAB historical fill, which stays forbidden. Roughly 12 months of history
per actor would move the median from 1 observation to something estimable; that
estimate has not been made and should be before the fetch is designed.
