# DESIGN — move corpus collection to Railway (written 2026-09-05, NOT applied)

**Measured tonight:** 332,065 rows / 218.2 MiB across 189 local file(s).

## The defect this removes
The seal authority runs on Railway; the corpus runs on a laptop. A seal taken
while the laptop is off is a seal taken without news, filings or catalyst dates
— which on 2026-09-03 produced an empty hack4 book that looked like a decision.
Absence of an input read as an opinion. That is the failure being closed.

## The shape
One Railway **cron service** in the existing project, sharing the seal
authority's volume:

- image: the terminal repo `Dockerfile` (already built)
- command: `python -m scripts.corpus_refresh --all`
- schedule: `10 21 * * 1-5` UTC (17:10 ET, after the close, before the seal)
- volume: the authority's `/app/state`, so the seal reads the same path it
  reads today and NO code changes
- variables: the collector keys only (`AAT_FINNHUB_API_KEY`, `AAT_FRED_API_KEY`);
  **no broker keys** — a collector that cannot authenticate to a venue cannot
  place an order by accident

## Cost
One more service on the same project. The measured comparator is the existing
warm loop at ~$7/month; a cron that runs once a day for a few minutes is well
under that. Bandwidth is the daily delta, not the 218.2 MiB (the initial copy is
one upload).

## The check that proves it is working
Add to `scripts/fleet_health.py`: **`corpus rows on the authority >= N`**, where
N is yesterday's count minus a tolerance. A collector that returns 200 with an
empty body is the house failure mode (`silent-fragility-audit`), so the health
check must assert on ROWS THAT ARRIVED, never on the job's exit code.

## What is NOT in this design
Moving the corpus does not make it correct. Only 7.7% of corpus news is a new
dated fact (T12, closed negative), so this is an availability fix, not an alpha
fix, and it should be judged on "did the authority seal with news present",
nothing more.

## The decision Murat makes
Create the service, or keep collection on the laptop and accept that a seal
taken with the laptop off is news-blind. No session flips this.
