# NIGHT-10 — silent-fragility audit of tonight's changes

Scope: `recommendation.py`, `capital_frontier.py`, `portfolio_factory.py`,
`llm_research.py`, `insider_trading.py`, `opportunity_funnel.py` (stage 1 and
stage 3), `mirror_challenge.py`, `investment_committee.py`.

**3 findings, all fixed now. 2 of the 3 were the house failure mode: a plausible
output where the truth was "this did not run".**

---

## F1 — the gate could return CLEAN because its own check crashed · FIX NOW

`backend/services/recommendation.py:618` (before the fix)

```python
try:
    checks.append(rank_invariance(candidates, sig.signal_id, registry=reg))
except registry_mod.RegistryError:
    continue                      # <- silently skipped
```

`assert_registry_discipline` is the one control whose entire job is to **refuse
to publish** a BUY ranking that a closed signal is steering. If the invariance
check for a closed signal raised, the check was dropped and the gate returned
`{"status": "CLEAN"}` — a green checkmark over a verification that never ran.
The Investment Committee page calls this function first precisely so a broken
ranking cannot print; that guarantee was conditional on the checker not
erroring.

**Fixed:** any exception is caught, logged at ERROR, recorded, and **raises**
`RankLeadershipError` with the message "A check that did not run is not a check
that passed." Signals genuinely exempt (no adapter, so no path to the ranking at
all) are listed separately in `exempt_no_adapter` rather than passed over.

Pinned by `test_gate_refuses_when_an_invariance_check_cannot_run` and
`test_gate_records_signals_exempt_for_having_no_adapter`.

## F2 — a total price failure produced a $0 NAV · FIX NOW

`scripts/mirror_challenge.py:128` (before the fix)

`_prices()` returns `{"error": ...}` on a fetch failure. The caller treated that
as an empty price map, so `marked` was empty, `nav` was `0`, and the run printed

```
book: 12 names, marked NAV $0
```

then wrote a JSON file full of zero weights and a QUBT fork worth $0. This is
the fake-NAV lesson exactly: **a fabricated number is worse than a refusal,
because a refusal is obviously not an answer and $0.00 is not obviously not an
answer.**

**Fixed:** the script now `SystemExit`s with the fetch error when no price
returns, and separately when prices return but NAV is still zero (bad share
counts). Nothing is written in either case.

## F3 — ledger spend could be understated in silence · FIX NOW (minor)

`backend/services/llm_research.py:357`

`spent_usd()` logged a warning on an unreadable ledger line, but
`ledger_summary()` — the function the handoff quotes — silently `continue`d,
so a corrupted ledger would report a lower spend with no signal. Budget
enforcement reads `spent_usd`, so the *cap* was never at risk; the *report* was.

**Fixed:** unreadable lines are counted, logged at WARNING, and surfaced as
`unreadable_ledger_lines` / `spend_is_lower_bound` in the summary. The dotenv
load failure at line 121 now logs instead of `pass`.

---

## Checks run, and what passed

| # | check | result |
|---|---|---|
| 1 | swallowed exceptions | **3 findings above.** All other `except` blocks in the new code either re-raise, return an explicit `(None, reason)` pair, or log at WARNING+ with context. `capital_frontier.py` and `investment_committee.py` contain **no** exception handlers — they raise. |
| 2 | runs-but-fetches-nothing | **This was the night's main product bug and is fixed** — see below. The funnel's `_insider` and `_fundamentals` both return `(value, reason)` and never a bare `None`. `stage1` raises `FunnelError` rather than returning an empty candidate list. |
| 3 | status row + canary | **GAP, backlogged.** The new subsystems (recommendation gate, funnel insider leg, capital frontier) write no persisted status row and have no `/api/health/full` canary. If the insider leg went dark tomorrow, the IC page would print `ABSENT — <reason>` per name, which is visible in the artefact but **not on the health surface**. |
| 4 | rate limits + volume | Insider fetches go through the existing Finnhub client. Stage 3 now makes **2** per-ticker calls instead of 1 (fundamentals + insider), and the hard `budget` cap was already counting calls — it was raised to 120 to match, so the cap still binds. No new SEC/EDGAR path was added. |
| 5 | hangs | All new external calls carry timeouts: LLM 180s, prices via the existing batch fetcher, insider via the existing client. No new non-slow test touches the network. |
| 6 | degraded ≠ fabricated | **F2 above.** Also verified: `portfolio_factory` **refuses** rather than filling a book from too few names; Kelly **refuses** rather than substituting a ranking score for an expected return; `in_universe` denies on unknown cap rather than assuming a band. |
| 7 | cache masking | The funnel was run cold three times tonight (full 5,324-name universe fetch each time) and produced consistent stage counts. The IC page reads only the funnel artefact. |
| 8 | contract drift at load | The signal registry validates on load (pre-existing). `config.SIGNAL_UNIVERSE_BANDS` is now **complete** for every universe string in the registry, so a signal blocked by the size gate is blocked deliberately and never by a gap in the table. |

---

## The three product bugs this audit's discipline caught earlier tonight

These were found while building, not in this pass, but they are the same class
and belong in the record:

1. **The insider signal was dead on arrival.** The fetcher read
   `transactionType`, which the Finnhub API returns as `null` on 100% of rows.
   Every transaction arrived uncoded, the open-market filter discarded all of
   it, and the score returned a confident `0.0` — "No open-market insider
   purchases" — for **every ticker in the universe**. Twelve tests passed
   throughout. Fixed by reading `transactionCode`; "no purchases" and "cannot
   classify" are now different return values, and the PIT collector records
   UNSCOREABLE instead of writing a fabricated zero into a store later research
   reads as fact.

2. **Market cap in the wrong currency.** Finnhub reports
   `marketCapitalization` in the company's **reporting currency**; the funnel
   multiplied by 1e6 and called it USD. IBN was overstated **95×** (INR), TSM
   **28×** (a $61 trillion cap), FMX **6×**. Market cap decides the cap band,
   which decides which signals are licensed to score the name. Non-USD profiles
   are now recorded as UNKNOWN rather than converted with a guessed rate.

3. **Ties printed as a ranking.** Thirty-plus names shared one score and were
   printed in a confident order that was really list order.

## What was NOT covered

* **No live prod verification.** Nothing was deployed tonight, so
  `verify-prod-after-deploy` does not apply — but it means the insider fix is
  verified locally only. The prod Finnhub tier may behave differently, and the
  standing note that the insider collector once 403-ed on 100% of prod fetches
  while passing 12 tests is exactly the reason to check it live before trusting
  it there.
* **No status rows or health canaries were added** (check 3). Backlogged.
* **The `Aegis module` research scripts were not audited** — `heresy_lab.py`,
  `run_analyst_ident_1.py`, `audit_analyst_power2.py`. They are offline
  research runners writing to `runs/`, not services, and each fails loud on a
  missing frame. They have no tests.
* **`recommendation.py`'s `_get` returns `None` on a coercion failure** without
  distinguishing "field absent" from "field present but unparseable". Both
  surface as `available: False` with the adapter's missing-reason, which
  attributes an unparseable value to the wrong cause. Low severity; backlogged.
