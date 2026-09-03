# Forensics — the 2026-09-03 DEGRADED episode

**Deploy investigated:** `6c52680` (Railway, `selfless-courage` / Aegis-Finance — the
website backend; it places no orders)
**Observed:** 2026-09-03 ~05:30 UTC, `/api/health/full` = `DEGRADED`
**Method:** read-only against prod, except one authorised data repair (§F2)
**Receipt:** `backend/data/optimus/tracker_backtest/health_forensics_20260903.json`

---

## Is trading or account state involved?

**No.** Explicitly, and this is the first line because it is the first question.

- No lane strategy, weight, position, or order was changed.
- No order was submitted or cancelled. `execution_ledger` is still `ABSENT` — no
  external order has ever been submitted from this repo's deploy.
- The single write to prod was a **NAV catch-up mark** through the existing
  allowlisted `run_job` endpoint (§F2), which appended one row per lane for a
  session that had already closed. Lane-integrity check passed before and after.
- Railway config was not touched. Nothing was pushed. The deploy freeze holds.

The one fault that *touches* account state is the Alpaca 401 (§F3), and its
effect is that the mirror could not **read** positions — it placed nothing.

---

## Scoreboard

| # | Reported | Verdict | Repaired |
|---|---|---|---|
| F1 | 15 forecasts past due and unresolved | **False positive** — measurement artefact | code, `2908a06` |
| F2 | NAV not fresh | **Real, structural, chronic** | data (prod) + code, `9b6cca8` |
| F3 | Alpaca 401 | **Real** — keys revoked at Alpaca | attended only |
| F4 | WHY-MOVED crashed | **Real** — but after all work completed | code, `7932c6d` |
| F5 | ARENA scan source absent | **Real, long-standing** | proposal only |

Two of the five degraded signals were the monitoring being wrong rather than the
system being wrong. That is itself the most important finding here: **F1 and F2
were both green-looking receipts sitting over the fault they existed to catch.**

---

## F1 — "15 forecasts past due and unresolved"

### Root-cause tree

```
DEGRADED: live_forward, 15 past due and unresolved
└── were the 15 actually unresolvable?                          NO
    ├── missing price?           ruled out — `unpriceable` empty in all 15 receipts
    ├── delisted / dark symbol?  ruled out — same
    ├── quarantine refusal?      ruled out — those are the other 25, counted separately
    ├── ledger persistence?      ruled out — /data/optimus/predictions.jsonl, status ok
    └── resolver never ran?      ruled out — 15 receipts, every one reports
                                            n_overdue_actionable: 0
└── ROOT CAUSE: the canary and the resolver run on different clocks
    ├── ledger_health:  overdue  ⇔  today >= resolves_after
    ├── resolve_due:    due      ⇔  today >= resolves_after      ← same predicate
    └── pi_ledger_resolve fires 16:30 ET = 20:30 UTC
        ⇒ a record maturing on D is "past due and unresolved" from 00:00 UTC on D
          until 20:30 UTC on D — 20.5 of every 24 hours on which anything matures
```

### The proof is arithmetic, and it is exact

The ledger did not change between the resolver's last run and the health read:

| | resolver receipt 2026-09-02T23:32Z | health 2026-09-03T05:30Z |
|---|---|---|
| `n_records` | 237 | 237 |
| `n_resolved` | 42 | 42 |
| `n_void` | 6 | 6 |
| `last_written` | 2026-09-02 | 2026-09-02 |
| `n_overdue` | **25** | **40** |
| `n_overdue_actionable` | **0** | **15** |

Same file, same provenance hash (`43cfd12e16…`). The only variable that moved is
`date.today()`. `40 − 25 = 15`, so **the 15 are precisely the records whose
`resolves_after` is `2026-09-03`** — they had not been overdue at any moment
before 00:00 UTC that morning.

### The exact forecast IDs

**They are not obtainable read-only, and that is itself a defect.** The health
row named the 25 **quarantined** prediction_ids and gave the actionable ones as a
bare integer — backwards, since the actionable ones are the only ones anyone can
act on. Recovering *which* records were meant required differencing two receipts,
as above.

Fixed in `2908a06`: `ledger_health` now emits `overdue_actionable` with
`prediction_id`, `ticker`, `specialist`, `made_at`, `resolves_after` (capped by
`LEDGER_HEALTH_MAX_NAMED_OVERDUE`). The ids become readable on the next deploy.

Their provenance is nonetheless known: 23 records entered the ledger between
20:34 and 21:32 UTC on 09-02 (214 → 237), written by the nightly WHY-MOVED pass
at 21:16:32 (§F4). The `why_moved:*` specialists write 1- and 5-day horizons —
`live_forward` currently holds 60 pending at horizon 1 and 47 at horizon 5 — so a
cohort maturing the next calendar day is the expected shape.

### Why this matters more than the count

The resolver has **never once** left an actionable record ungraded, across every
receipt back to 2026-08-14, including the night of 2026-09-01 when it cleared 42
in a single pass. A canary that is red for most of the day is alarm fatigue with
extra steps — an argument `belief_state.py` already makes, verbatim, for the
quarantine split of 2026-08-17. The same defect had recurred one screen up.

**Fix:** the fault predicate is now strictly greater — overdue once a *whole* day
has passed, by which point the 16:30 slot and all three catch-up retries have
fired. `resolve_due` deliberately keeps `>=`; the resolver should still grade on
the maturity day. This cannot mask a real stall for more than a day: the genuine
2026-08-27 → 09-01 gap, where 42 forecasts went ungraded for days, still degrades.

### Secondary finding, not repaired

`/api/optimus/calibration` reports the same file as `n_overdue_actionable: 40,
n_overdue_quarantined: 0`, because `calibration_report` calls `ledger_health`
without `quarantined_hashes`. **Two health surfaces disagree on one file.**

---

## F2 — NAV not fresh

### Root-cause tree

```
nav.all_fresh = false; all 10 lanes at 2026-09-01, expected 2026-09-02
└── did the MTM job run?                                    YES — 4 times on 09-02
    └── did it fail?                                        NO — every receipt:
                                                            "marked, n_marked 10, n_failed 0"
        └── so what did it write?                           the 2026-09-01 row. Again.
            └── mark_lane_to_market stamps the row with the BAR DATE
                (P-day-2026-08-19a: "NAV_t means close_t by construction")
                └── bar date comes from _get_latest_bar_date
                    └── end = datetime.now().strftime("%Y-%m-%d")
                        └── ROOT CAUSE: yfinance's `end` is EXCLUSIVE
                            ⇒ the newest bar obtainable is ALWAYS yesterday's
                            ⇒ the close mark can never see the close it is marking
```

The change that introduced bar-date stamping was written to stop NAV lagging one
session. The exclusive-end bound made it lag one session — the precise outcome it
set out to prevent.

### The duty cycle

`_expected_nav_date` rolls to today at 17:00 ET, while the mark writes D−1. So
`nav.all_fresh` could only ever be true between the 16:30 mark and 17:00 ET —
**about thirty minutes a day.** This was never an incident; it was the steady
state, which is why "nav not fresh" reads as chronic.

### Why nothing caught it

`mark_lane_to_market` returned a float for all ten lanes, so the receipt reported
success. The receipt **prints** `expected_nav_date` and never compares the written
row against it. A receipt that carries the expected value and does not check it
cannot detect the fault it exists to detect.

### The repair (authorised data repair, prod)

`POST /api/optimus/run_job/pi_hourly_mtm` — the existing allowlisted, idempotent
job, the one documented for slept-through days.

| | before | after |
|---|---|---|
| lanes at 2026-09-02 | 0 / 10 | **10 / 10** |
| `nav.all_fresh` | false | **true** |
| degraded reason "nav not fresh" | present | **gone** |

**This doubles as the proof.** Running the *unmodified* job one calendar day
later produced the 2026-09-02 bar. Same code, same lanes, one day of clock — the
fetch window was the only variable.

### Lane integrity check (before and after) — PASS

- lane YAMLs byte-stable, 0 modified; lane set identical (10)
- exactly one row appended per lane, `2026-09-02`; **0 removed, 0 historical rows
  mutated, 0 new `config_version` segments**
- registry: `cumulative_trials` 18 → 18, all 18 trial rows identical; the only
  delta is `effective_independent_trials.n_obs` 21 → 22 — the observation just added
- all ten lanes visible on `/api/pi/track-record`

### Deploying the code fix needs one attended step

Post-fix the 16:30 mark writes D instead of D−1. If D−1 has not already been
marked it is **skipped permanently** — a hole in the track record. Trigger
`pi_hourly_mtm` on the **current** code first, then deploy. That has already been
done for 2026-09-02 by this pass.

---

## F3 — Alpaca 401 (attended; nothing repairable here)

### Root-cause tree

```
401 Unauthorized on /v2/positions, from 2026-09-02T20:33:49Z
├── env vars absent on Railway?     NO — health reports credentials "present"
├── wrong env var names?            NO — lane:mirror uses ALPACA_API_KEY_ID /
│                                        ALPACA_API_SECRET_KEY, as configured
├── malformed values?               NO — 26-char PK… id, 44-char secret, both pairs
└── ROOT CAUSE: the credentials are REVOKED at Alpaca
    └── and the local .env copies are the SAME keys, and are ALSO 401
```

Probed read-only (`GET /v2/account`, no orders): **both** the lane pair and the
arena pair return `401 unauthorized` from this machine.

`.env.bak.2026-08-27` carries identical prefixes and lengths — so nothing rotated
locally; the keys worked until 2026-09-02 ~20:33 UTC and were revoked or reset at
Alpaca's end.

> **The obvious fix is wrong.** Copying the local keys onto Railway will not work —
> they are dead too. New paper keys must be generated in the Alpaca dashboard.

**Procedure for the post-judging queue:**
1. Alpaca dashboard → paper account → regenerate API key pair (do this for the
   arena account too; both are dead).
2. `railway variables --service <svc> --set ALPACA_API_KEY_ID=… --set ALPACA_API_SECRET_KEY=…`
   (and the `ALPACA_ARENA_*` pair), then redeploy the service.
3. Update local `.env` to match.
4. Verify with `GET /v2/account` before trusting the mirror.

**Health-surface defect:** `paper_broker` reports `status: ok`,
`credentials: "present"`, `credential_error: null` for both targets while every
call 401s. **Presence is checked; authentication never is.**

---

## F4 — Nightly WHY-MOVED crash

### Root-cause tree

```
"Nightly WHY-MOVED failed: 'str' object has no attribute 'get'" @ 21:16:32Z
└── where?  scheduler.py:1314
            rejected = sum(len(l.get("rejections") or [])
                           for l in (result.get("lenses") or []))
    └── run_why_moved returns  out["lenses"] = by_lens   ← a DICT keyed by lens name
        └── iterating it bare yields the KEYS — strings
            └── ROOT CAUSE: str.get → AttributeError
```

Reproduced offline with the exact error string and frame before fixing.

### The job had already done all of its work

| evidence | value |
|---|---|
| 21:15 pass duration | **92.041 s** |
| ledger records before → after | 214 → **237** (23 minted) |
| ledger `last_record_at` | **2026-09-02T21:16:32Z** — the same second as the error |
| catch-up slots 22:15 / 23:15 | 0.043 s / 1.081 s — correctly no-opped |

It attributed the day, ran the lenses, minted 23 forecasts, wrote them to the
volume — and then died formatting its own summary line. **Nothing was lost but the
summary**, including the `minted == 0` "NOTHING GRADEABLE WAS WRITTEN" warning,
which cannot fire from a line that raises before reaching it.

The 2026-08-31 run also took 92.5 s — the same shape, crashed the same way, unnoticed.

### Two failures of the safety net

- **The receipt recorded `status: "ran", exception: null`** — the crash was
  swallowed by the job's own `try/except`, so `@receipted()` never saw it. A green
  receipt over a crashed job.
- **Nine tests cover this job and none saw the real shape.** Every fake returned
  `"lenses": []`, while `test_why_moved.py` had been asserting
  `out["lenses"]["options_vol"]` on the producer side the whole time. The two
  suites disagreed about the contract and both were green.

### A second route to the same error, fixed with it

`why_moved._extract_json` is annotated `-> dict` but is `json.loads`, which
returns a `str` for a JSON string literal and a `list` for an array. Those parse
*cleanly*, so they bypass the `JSONDecodeError` guard and reach
`parse_hypotheses`' `raw.get(...)` — and that call site is **outside** the guard,
so the exception escapes the lens, the orchestrator and the job. Double-encoded
JSON is a known DeepSeek `json_object` failure mode, so this is reachable rather
than hypothetical. The annotation is now enforced, routing it into the branch that
already exists for a model that produced no object: a counted rejection.

**Same class, unaudited:** `llm_swarm._extract_json` and
`optimus_specialists._extract_json` carry the identical `-> dict` annotation over
a bare `json.loads`.

---

## F5 — ARENA scan source absent (proposal only)

### Root-cause tree

```
"no scan source at /data/optimus/crsp_pit/crsp_pit_monthly_v1.parquet"
└── reader: arena/discovery.py:179-213, path = OPTIMUS_LEDGER_DIR/crsp_pit/…
└── producer: scripts/crsp_pit_universe_pull.py:117
    └── writes to backend/data/optimus/crsp_pit/ — INSIDE THE REPO
        └── .gitignore:63 excludes *.parquet
            └── ROOT CAUSE: no deploy has ever carried it, and there is no
                volume-seeding script for it. It has never been on the volume.
```

**Consequence.** `scan_universe` returns `[]` and **caches the empty list for the
process lifetime**, and the scan is deliberately excluded from the
`priced_fraction` denominator, so no guard can fire. `engine.py:442` states the
stakes: *"the scan is the only route by which a name the watchlist never contained
can reach a book."* Prod DISCOVERY has been core-universe-only for its whole life,
logging one warning per process start. The empty result is *pinned as intended
behaviour* by `test_arena_brain.py::test_scan_universe_absent_source_is_loud_and_empty`.

**Cheapest ship:** the file already exists locally, complete and correct —
`backend/data/optimus/crsp_pit/crsp_pit_monthly_v1.parquet`, 13.4 MB, 545,478
rows, built 2026-08-19. Upload it to the Railway volume at
`/data/optimus/crsp_pit/`. No rebuild, no WRDS pull, no code change. **A restart is
required** afterwards, because the empty scan is cached per process.

**Rejected alternative:** converting the local
`wrds/crsp_monthly_panel_2013_2024.json`. It has no `ticker` column at all (keyed
on `permno`, and that mapping is time-varying), no `eligible` flag, and its
dollar-volume column is a *median daily* figure from `crsp.dsf` rather than the
monthly `crsp.msf` quantity — with a 100× unit convention between them. The reader
requires `["date", "ticker", "dollar_vol", "eligible"]`.

---

## Commits (local only — nothing pushed)

| sha | fault | tests added | red on parent |
|---|---|---|---|
| `7932c6d` | F4 — lenses dict iterated as a list, + the `_extract_json` twin | 2 | yes, with the exact prod error string |
| `9b6cca8` | F2 — exclusive-end fetch window | 3 | yes; the e2e test reproduces the one-session lag |
| `2908a06` | F1 — overdue predicate, + naming actionable overdue records | 2 | yes |

| suite | result |
|---|---|
| baseline, before any change | 6074 passed, 14 skipped, **0 failed** (383 s) |
| after all four commits | **6113 passed, 14 skipped, 0 failed** (608 s) |

`.env` was never moved; `AEGIS_IGNORE_DOTENV=1` throughout.

One intermediate run showed a single failure in
`test_learner_states.py::test_the_planted_structure_is_recovered_and_beats_its_own_shuffle`.
It is **not attributable to this pass**: another local process was rewriting
`learner/evaluate.py` (+270 lines) while pytest imported it — eleven concurrent
python processes were active in the repo — and `learner/` is touched by none of
these commits. It passes in isolation and in the final full run.

Worth noting how it was nearly missed: that run reported `exited with code 0`
despite the failure, because the command was piped to `tail`, which eats the exit
code. The text caught it; the status would not have.

---

## Remaining attended

1. **F3** — generate new Alpaca paper keys (both accounts) and set them on
   Railway. The local copies are dead, so there is nothing to copy.
2. **F5** — upload the 13.4 MB parquet to the volume, then restart.
3. **F2 deploy ordering** — trigger `pi_hourly_mtm` on the current code before
   deploying `9b6cca8`, or the transition day is skipped permanently.
4. **F1 secondary** — `calibration_report` calls `ledger_health` without
   `quarantined_hashes`; two surfaces disagree on one file.
5. **F4 same-class** — audit `llm_swarm._extract_json` and
   `optimus_specialists._extract_json`.
6. `paper_broker` health checks credential presence, never authentication.
7. The MTM receipt prints `expected_nav_date` and never compares against it.

---

## The lesson worth keeping

Three of these five faults were **green receipts over broken work**: the MTM
receipt reporting "marked 10, failed 0" while writing yesterday's date; the
WHY-MOVED receipt reporting `exception: null` over a crash; the paper-broker row
reporting `credentials: present` over a revoked key. In each case the receipt held
the value that would have exposed the fault and never compared anything to it.

**A receipt that carries the expected value without checking it is a receipt that
cannot fail.** That is the house failure mode wearing a hard hat — and it is worth
more than the individual bugs.
