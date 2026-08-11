# Silent-fragility audit — NIGHT-12's six new modules

**2026-08-11.** Audited: `conviction_sheets`, `conviction_prices`,
`conviction_replay`, `counterfactual_replay`, `belief_state`,
`optimus_specialists`, `exposure_controller`.

The house failure mode is **no output wearing a green checkmark**, and this
session produced a textbook instance before the audit even started: APLT and
SLNO were dropped from the replay with nothing but a WARNING, which moved the
headline by ten points. Everything below is the same class.

---

## Findings

### FIXED NOW — silent-wrong

**F1. Unparsed sheet rows vanished at DEBUG level.**
`conviction_sheets.py` logged an unreadable holding row at `logger.debug` and
continued. DEBUG is invisible by default, so a partial parse — say 10 of 13
holdings — would produce a smaller basket, a different mean, and a clean run.
Now WARNING, collected onto `Sheet.unparsed`, and reported in the load summary.
*Verified: both sheets parse with 0 unparsed.*

**F2. A missing sheet silently shrank the universe.**
`all_tickers()` caught `FileNotFoundError` and warned. That would have shrunk
the price fetch, which would have dropped names from one side of the selection
comparison — the exact failure the module exists to prevent. The catch is
removed; a missing sheet now fails loudly.

**F3. `basket()` excluded names with only a log line.**
The APLT bug generalised: any name without a price is dropped and the mean is
computed over whatever is left. `GroupReturn` now carries `excluded`, and
`require_all=True` raises. The three verdict-deciding baskets in the runner use
it. *Verified: the replay still runs and still reports 13 / 48.*

**F4. Forecasts that can never resolve were counted as "pending".**
`belief_state.resolve_one` returned `None` for a ticker absent from the price
frame — indistinguishable from "the window has not closed". A permanently dark
forecast would have hidden inside a growing backlog forever. `resolve_all` now
separates `pending_not_yet_due` from `OVERDUE_AND_UNRESOLVED`, warns, and
returns a `health` field.

### FIXED NOW — degraded-state visibility

**F5. The exposure controller was silently full-risk during warmup.**
Before 200 days of history, `classify()` emitted `risk_on` with exposure 1.0 —
a real state presented as a neutral one. A short price history therefore
disabled the control invisibly. Warmup days are now labelled
`warmup_full_risk`, counted, and warned about.

**F6. The prediction ledger had no status row or canary.**
It is precisely the subsystem that fails by *not growing*: an empty append is
indistinguishable from a night with nothing to say. Added `ledger_health()` —
DEGRADED on an empty ledger, on more than 7 quiet days, or on any overdue
record. Three tests pin it, including that **silence must not read as ok**.
Wired into **`/api/health/full`** as `prediction_ledger`, so the canary is
observed rather than merely callable — the crash-overlay template, which went
dark for weeks precisely because a status row existed nowhere.

---

## Checks run and passed without change

**Degraded ≠ fabricated.** The two reconstructed price series are the only
invented data in the session and they are quarantined: `synthetic_names()`
excludes them from every path statistic and from up/down capture, because two
known points and no path between them cannot produce an MFE without inventing
the shape of the move. The APLT CVR is marked at **zero** rather than a guess,
and the replay reports its headline both with and without both names.

**Contract drift at load boundaries.** `load_prices()` asserts that every name
resolves and that every recorded corporate action leaves **both an entry and a
payout** — the invariant that would have caught the original defect. The leg
decomposition **aborts** if the legs stop summing to the spread they partition.

**Refusals over coercion.** `make_prediction` refuses percent thresholds,
unfrozen horizons, non-probabilities and unbenchmarked comparisons rather than
repairing them. The specialist parser refuses forecasts with no counter-thesis,
recommendation language, or tickers outside the snapshot — and records every
refusal on the batch rather than dropping it.

**Hangs and network.** The only external call is the DeepSeek client, in a
script, never in a test. No test in `test_conviction_replay.py` or
`test_belief_state.py` touches the network; both read committed artefacts.

**Cache masking.** The price panel is a committed CSV and `load_prices` raises
if it is absent, so a cold run fails loudly rather than passing on whatever
happens to be cached.

---

## Verified live

Deploy `84287c5`, CI green, commit flipped, checked on the running service:

```
"prediction_ledger": {"status": "ok", "n_records": 87, "n_void": 6,
                      "n_resolved": 0, "n_overdue": 0,
                      "distinct_specialists": 5, "distinct_models": 1}
```

The CONTENT was read, not the status code — 87 records across 5 specialists with
6 voided is the ledger as written, so the canary is reporting the real
subsystem and not a default. `scheduler.nav.all_fresh` true, 4 jobs, FRED 23/23,
yfinance 23/23.

One warning present and **not** attributable to this change: `trends_sentiment`
got a 429 from Google Trends and is cooling down for 6h. It discloses itself as
unavailable rather than writing a value, which is the correct behaviour. Noted,
not ignored.

---

## NOT covered

* **Rate limits and prod volume.** No SEC/EDGAR path was touched; the DeepSeek
  client inherits the existing breaker and daily cap in `llm_analyzer`, which
  was **not** re-audited.
* The ~70 legacy swallowed-exception sites repo-wide (BACKLOG H5). Nothing in
  this session added to them.
