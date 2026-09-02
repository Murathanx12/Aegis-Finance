# RED-TEAM AUDIT — the money path, 2026-09-02

**Scope.** `aegis-alpha-terminal` execution engine, attacked rather than reviewed:
sizing arithmetic, the sealed-weight chain, gate ordering, stops and exits, the
2026-09-04 liquidation, PIT integrity of the seal, ledger/receipt tearing, and
config drift. Every finding carries a concrete input → wrong outcome → dollar
shape.

**Evidence tags.**
- **CONFIRMED-REPRODUCED** — I ran it (`AAT_TEST_MODE=1`, sockets blocked, no
  orders, no state writes) and the output is quoted.
- **CONFIRMED-IN-SOURCE** — the code path is complete and unambiguous end to end
  (including greps whose emptiness is itself the proof); nothing venue-side is
  assumed.
- **PLAUSIBLE** — code-read only, and the failure needs a timing or an input I
  could not establish here.

`alpha/runner.py`, `scripts/prediction_book.py` and `scripts/decision_writeback.py`
were read at `git show HEAD:<path>` (a4fffc3) because other agents are editing
them; their line numbers are HEAD line numbers. Everything else is from disk.

**Already-known, deliberately NOT re-reported:** corpus/tracker producer split ·
ratio<1.5 band hole · mdm_floor −$846k · ungraded-counted-as-wins · VISN sign
contradiction · 2 torn ledger lines · broken ledger hash chain since 25 Aug ·
wash-trade 403 on same-symbol resting stops · `ET_OFFSET` fixed −4h (DST) ·
attention-watchlist out-of-window gate.

## SEVERITY COUNT

| Severity | Count | Findings |
|---|---|---|
| CRITICAL | 2 | R1, R2 |
| HIGH | 5 | R3, R4, R5, R6, R7 |
| MEDIUM | 8 | R8 – R15 |
| LOW | 5 | R16 – R20 |

**20 findings.** 7 reproduced by running, 10 confirmed in source, 3 plausible.

**The one-line summary:** the engine's *declared* risk controls — the widened
stop, the sealed-weight ceiling, the ADV participation cap, the same-session
re-entry guard — are, in four separate places, guards that cannot fire; and the
two dated things that have never run live (the 09-04 liquidation and tonight's
staggered top-up) both contain a loop that trades against itself.

---

# CRITICAL

## R1 — On judging day the book is bought back every 30 minutes after the 10:45 ET liquidation

**CONFIRMED-REPRODUCED** (guard reachability and the clock arithmetic; the venue
leg has never run).

**Where.**
- `alpha/exits.py:114-121` `deadline_liquidation_due`; `alpha/exits.py:348-355`
  the liquidation verdict (`urgency="immediate"`, outranks everything).
- `scripts/agent_loop.py:354-367` — the entry block. **There is no deadline test
  on the entry side anywhere in the repo.**
- `scripts/run_pass.py:339-350` — the only time-based refusal is `horizon <= 0`,
  and it can never fire: `alpha/engine/structures.py:90-99` floors `_days` at 0.05.
- `alpha/runner.py:71-86` — `DEADLINE` is loaded and used **only** to validate an
  `--expiry` *date* (`check_expiry_against_deadline`), never a wall clock.
- `alpha/protect.py:93-107` `stopped_today` — matches only orders whose
  `client_order_id` starts with `aat-stop-`. `client.close_position` is not one.
- `alpha/refuted.py:227` — the refuted-route check bites `LONG_VOL` kinds only, so
  shares pass.

**The scenario.** 2026-09-04, `AAT_LOOP_EXPIRY=2026-09-04`, six live loops.

| ET | what happens |
|---|---|
| 09:20 | `scripts.open_auction` sends hack4's whole sealed book and hack6's half as `market/opg` |
| 09:30 | the auction print fills them |
| 10:01 / 10:31 | ordinary entry passes complete hack3 and top up hack6 |
| **10:45** | `exits.manage` returns `close`/`immediate` for **every** position: each protective stop is cancelled, each position closed at market |
| **11:01** | entry pass. Book flat; `held`, `in_flight` and `stopped_today` all empty (a `close_position` is not an `aat-stop-` fill); the sealed names are still in `portfolios[<role>]`. **It re-buys the entire sealed book.** |
| 11:05 | `exits.manage`: the deadline is still due → liquidates again |
| 11:31 … 15:31 | repeat, ~9 more times |

Reproduced:

```
UTC 15:00 (ET 11:00)  sessions_to 2026-09-04 = 0.769  -> run_pass horizon<=0 guard fires? False
UTC 19:00 (ET 15:00)  sessions_to 2026-09-04 = 0.154  -> run_pass horizon<=0 guard fires? False
deadline due at ET 15:00 on 09-04: True
```

**Dollar shape.** Gross at the seal: hack3 83%, hack4 50%, hack6 ~90%. A round
trip on the sealed small-cap class (RZLV/NB/LAES/ABAT/ALMU) is 30–100 bp and the
exit leg is a **market** order. Nine cycles × ~0.7 gross × ~0.5% ≈ **−3% of equity
per book, spent on the one session that is judged** — which is also exactly where
the `daybreak` latch sits (`alpha/daybreak.py:64`), so the engine's declared
worst single-day loss gets delivered by churn with no thesis being wrong. Plus
~40 spurious ledger rows per name and a stop placed and cancelled every cycle.

Second-order: whether the account is *flat at the 11:00 judging cut* now depends
on where the 30-minute entry cadence lands against the 5-minute exit cadence. On
the schedule above it is flat; a slow entry pass (killed only at 600 s) can put an
unliquidated book across 11:00.

**Minimal fix (do not apply).** In `runner.run_pass`, before the per-symbol loop,
call `exits.deadline_liquidation_due(config.COMPETITION["deadline_utc"])`; when
true refuse every forecast with class `risk` ("past the judging-day liquidation;
the book only gets smaller from here"). Belt: gate the entry block in
`scripts/agent_loop.py:354` on the same predicate. Test: `run_pass` submits 0 at
`now = 2026-09-04 11:01 ET`.

---

## R2 — A restart or a late seal makes the "pre-open" book read the current session's in-progress bar — changing SELECTION, under the hash

**CONFIRMED-IN-SOURCE.**

**Where.**
- `scripts/tracker.py:457` and `:646` — `client.stock_bars_multi(syms,
  start="2025-06-01", timeframe="1Day")`. **No `end`.** `alpha/broker/alpaca.py:69`
  strips `None` params, so no upper bound reaches the vendor.
- `scripts/seal_authority.py:108-115` `maintainer` — wakes every `interval`
  seconds and calls `ensure_today()` **whenever `_book_path(day)` is None**. There
  is no check of the ET clock against the open. `ensure_today` (`:70-106`) then
  runs `--refresh` → `--backfill-prices` → `--seal`.
- `alpha/tracker.py:389-415` `price_stats` — `close = closes[-1]` (`:396`),
  `high_60d = max(highs[-60:])` (`:399`), `ret_12m` (`:411`), and
  `realised_vol_20d`'s final term is `log(closes[-1]/closes[-2])` (`:412-415`).
  There is **no bar-date assertion in either direction**.
- Contrast, in this same repo: `alpha/sources/features.py:507-521` `_bars_upto` +
  `price_context` filter to `<= day` and then **refuse** if the last bar is not
  exactly `day` — "a stale last bar would report yesterday's context under today's
  date." The discipline exists; it was not applied to the path that trades.

**The scenario.** The seal-authority container is redeployed, or crashed
overnight and restarts, at **10:15 ET on day D**. No book exists for D, so the
whole chain runs mid-session. The unbounded fetch returns D's in-progress daily
bar. `close` becomes D's 10:15 print. Then, on the same row:
`upside = mean_target/close − 1` (`alpha/tracker.py:376`),
`drawdown_60d = close/high_60d − 1` (`:383`) with `high_60d` including D's
high-so-far, and `realised_vol_20d` inflated by a partial-day return.

Those are `murat_rule`'s clause (a) and clause (e) inputs, so **the selection
changes, not merely the numbers**: a name is chosen *because it fell today*, and
then sized on today's move (`downside_5pct` → `alpha/brains/tracker_portfolio.py:180`
`sd = |downside_5pct|/1.645` → the sizer). The book is then written with
`sealed_at_utc`, hashed, and a `portfolios_note` asserting it was decided before
the open. `entry_open.verified_book` re-hashes it and it validates. Every integrity
check is green and the artifact is a same-day momentum read wearing a pre-open
receipt.

`--backfill-prices` makes this worse independently of the restart: its own
docstring (`scripts/tracker.py:621-634`) promises it touches only price columns
and never rewrites observations — but it rewrites `close` / `high_60d` /
`ret_12m` / `realised_vol_20d` (`:663-668`) while leaving `observed_at` untouched.
Run intraday, it retroactively restamps a captured day's prices with mid-session
values under the original capture stamp.

**Also verified, same family, three smaller leaks:**

- **The seal declares an instant and bounds nothing by it.**
  `scripts/prediction_book.py` (HEAD) `build()` computes `seal_utc` and passes it
  to `_build_from_tracker`, which uses it **only** to write `sealed_at_utc`. The
  corpus branch does the right thing one function away
  (`crows = [r for r in corpus.read(...) if r["observed_at"] <= seal_utc]`); the
  tracker branch has no equivalent. The `pit` block it writes instead is
  `{"tracker_observed_at": <day string>}` — a date, not an instant — beside a note
  asserting an ordering that nothing checks.
- **`--seal --day D` silently ignores `D`.** `scripts/prediction_book.py:1042`
  calls `build(source=args.universe)` without `args.day`; `build` derives the day
  from the wall clock and `_build_from_tracker` calls `tracker_rows()` with no
  argument, which falls through to `latest_day()` — the newest file on disk,
  whatever day it is. `scripts/seal_authority.py:99` passes `--day day` believing
  it pins the vintage. It does not.
- **A live network read inside the seal, after the declared instant.**
  `scripts/prediction_book.py` HEAD `_ratings_for` (`:258-281`) calls
  `finnhub.recommendation_trends` in a `time.sleep(1.1)` loop from
  `rule_predictions` (`:293`), i.e. after `seal_utc` was frozen, and merges the
  result onto the row unstamped (`:298`). Rating revisions published between
  `sealed_at_utc` and the fetch enter a book that claims to predate them.

**Dollar shape.** Not a fee — a selection error. The whole `PRODUCT_EXPERIMENT`
licence rests on "no information acted on before it was public", and this is its
mirror: information acted on that was not knowable at the declared time. Every
forward grade of the tracker artery computed on a day the container restarted
late is unusable, and nothing on the artifact says which days those are.

**Minimal fix.** Pass `end=<the session before the seal day>` to both
`stock_bars_multi` calls in `scripts/tracker.py`; assert in `price_stats` that
`bars[-1]["t"][:10] < seal_day` and refuse otherwise, in the voice
`features.price_context` already uses. Gate `seal_authority.maintainer` on
`mins_to_open > 0` — an unsealed day past the bell should print
`SEAL AUTHORITY DECLINED: the open has passed` and leave the book absent, which
`tracker_portfolio` already fails closed on. Make `--seal --day` actually reach
`tracker_rows`.

---

# HIGH

## R3 — The widened venue stop can never fire: `exits` closes every share at a hardcoded 3%

**CONFIRMED-REPRODUCED.**

**Where.** `alpha/engine/equity.py:231-232` — `stop_hit(plpc)` compares against the
module constant `STOP_FRACTION = 0.03`, **not** `stop_fraction(profile)`
(`equity.py:75-79`). Called at `alpha/exits.py:176` (shares) and `:282` (pairs).
The *resting* stop is placed at `equity.stop_fraction()` via
`alpha/protect.py:208-210` → `:138-154`.

```
conservative   venue stop 3% (px 4.85)  manage-pass exit fires at 3.00%  -> binds
aggressive     venue stop 3% (px 4.85)  manage-pass exit fires at 3.00%  -> binds
maximum        venue stop 6% (px 4.70)  manage-pass exit fires at 3.00%  -> NEVER BINDS
basket         venue stop 8% (px 4.60)  manage-pass exit fires at 3.00%  -> NEVER BINDS
convex         venue stop 8% (px 4.60)  manage-pass exit fires at 3.00%  -> NEVER BINDS
```

**The scenario.** hack3 runs `basket` and hack4 runs `maximum`
(`alpha/fleet.py:76-110`) — both live, both shares-only tracker books. hack3 holds
LAES at 8.3%. LAES trades −3.1% intraday, about half a daily sigma on a 100%-vol
name. The manage pass runs every 5 minutes and `_evaluate_shares` closes it at
market. The 8% stop the 28 Aug post-mortem installed — explicitly because "a stop
inside the noise is a fee, not a stop" (`equity.py:66-72`) — never gets to be the
binding constraint. `STOP_FRACTION_BY_PROFILE` reaches the venue and reaches
nothing else.

Same shape on the upside: `equity.target_hit` (`:235-236`, `PROFIT_TARGET = 0.025`)
sells a sealed 21-session thesis at +2.5% on every profile, with no profile term.

Note the knock-on: `alpha/protect.py:295-302` justifies swallowing a refused stop
placement on the grounds that "that position is ALREADY past its stop, so
`exits.evaluate` closes it on this same pass". That is true only *because* of this
bug. Fixing the stop width without touching that comment leaves a position
unprotected for a cycle.

**Dollar shape.** This reproduces the measured 28 Aug event — nine names stopped
inside eleven minutes, −$6.9k realised on each of two books, index +0.1% — with
the fix installed and inert. Compounded by R4, which re-buys each shaken name.

**Minimal fix.** `stop_hit(plpc, profile=None)` / `target_hit(plpc, profile=None)`
reading `STOP_FRACTION_BY_PROFILE`; thread the role's profile through
`exits.evaluate` → `_evaluate_shares`. Suite check: for every profile in
`PROFILES`, the manage-pass trigger and `protect`'s placed stop agree.

---

## R4 — Any exit performed by `exits.manage` is invisible to the same-session re-entry guard

**CONFIRMED-IN-SOURCE** (the venue leg is PLAUSIBLE).

**Where.** `alpha/runner.py:1112-1130` is the only re-entry guard, and it reads
`alpha/protect.py:93-107`:

```python
if is_ours(order) and order.get("status") == "filled":
```

`is_ours` is `client_order_id.startswith("aat-stop-")` (`protect.py:84-85`).
`client.close_position(symbol)` (`alpha/exits.py:578`) is a venue-side market
DELETE with an auto-generated id — not ours, never seen. `status == "filled"` also
excludes a `partially_filled` stop.

**The scenario.** 10:05 ET, hack4. `exits.manage` closes ABAT at −3.05% — which,
after R3, is now the *normal* way a `maximum`/`basket` book exits, not an edge
case. 10:31 ET entry pass: ABAT is in the sealed book, the book is flat in it,
`stopped_today` is empty, so it is re-bought at the full sealed 10% weight ~3%
below the first entry. 10:40 it prints −3% from *that* entry and is closed again.
Up to 12 cycles per session per name.

The refusal text the guard prints — "a protective stop closed this name earlier
today; no same-session re-entry — tomorrow is a new decision" — describes a policy
the engine does not implement for the two books that need it most.

**Dollar shape.** hack4, one name at 10% weight, three churn cycles = −0.9% of
equity in one name in one day before spread; five sealed names doing it together
reaches the −3% `daybreak` latch.

**Minimal fix.** Make `stopped_today` the union of (a) `filled` **and**
`partially_filled` `aat-stop-` orders and (b) the account's own ledger rows with
`action == "closed"` in today's ET session (`alpha/exits.py:597` already writes
them). Rename it `exited_today`.

---

## R5 — `topup_headroom` is a martingale: it measures the remainder at MARKET value, so a losing position re-opens headroom every 30 minutes

**CONFIRMED-REPRODUCED.** New tonight (`a4fffc3`); live on hack6 at tomorrow's
open (`alpha/fleet.py:118-121`, `env={"AAT_ENTRY_STYLE": "staggered"}`).

**Where.** `alpha/entry_open.py:265-307`, consumed at `alpha/runner.py:1099-1110`
and `:1131-1140`:

```python
room = full - held_usd.get(sym, 0.0) / float(equity)
if room >= MIN_TOPUP_FRACTION_OF_SEALED * full and room > 0:
```

`held_usd` is `abs(market_value)` (`:291-296`). The docstring (`:277-280`) asserts:
*"Once the top-up fills, the headroom is ~0 and the name is refused again by this
same arithmetic — so this cannot become the 30-minute re-buy loop the original
guard was written to stop."* **That is false.** Market value falls when the
position loses, and the headroom re-opens by exactly the loss.

Reproduced, sealed weight 6% on $100k equity:

```
A  auction leg on (600 sh @ $5.00, mv $3,000)     -> room 3.00%   (correct: the other half)
B  protective stop PARTIALLY filled, 240 sh left  -> room 4.80%   (80% of the sealed weight)
C  full position, name gapped down 40% overnight  -> room 2.40%   (buys more of a -40% name)
```

**Two distinct failures.**

1. **Add to losers, never to winners.** A name that falls 15% after the top-up
   re-opens 0.9% of headroom, above the 0.6% floor
   (`MIN_TOPUP_FRACTION_OF_SEALED × full`), and the next 30-minute entry pass buys
   it. A winner's room goes negative and is never touched. Every 30 minutes, all
   session, on every losing name — a martingale bolted onto a book whose mandate
   says the sealed weight is a *reduce-only* ceiling.
2. **It defeats the stop guard.** `alpha/runner.py:1118` reads
   `if symbol in stopped and symbol not in held:`. A **partially** filled stop
   leaves the symbol still in `held`, so that branch does not fire and the top-up
   branch on the next line does — buying back **4.8% of equity, 80% of the sealed
   weight, into the name whose protective stop is mid-fill, in the same session**.
   `protect.stopped_today`'s `status == "filled"` filter makes it doubly invisible.

**Dollar shape.** hack6 is k=15 × 6% ≈ 90% gross. On a −10% day across five sealed
names the top-up adds ~0.6% of equity per name per pass; eight passes is up to
+4.8% of *additional* gross bought into falling names, on a book whose declared
stop-based worst case is −2.70%. Only the `daybreak` latch bounds it.

**Minimal fix.** Compute the remainder from what was bought, not from what it is
now worth: read the auction receipt (`entry_open.receipt_path`, or the `submitted`
ledger rows for `opg_decision_id(day, sym)`) and cap the top-up at
`(1 − auction_fraction) × sealed`, once per day. Separately, move the
`stopped_today` test above the top-up branch and drop its `and symbol not in held`
clause.

---

## R6 — A torn resealed book makes the runner silently trade the *seed* book, with every hash check green

**CONFIRMED-IN-SOURCE.**

**Where.** `alpha/brains/tracker_portfolio.py:89-97`:

```python
for base in (BOOKS, SEED_BOOKS):
    cands = sorted(base.glob(f"{day}.json")) + sorted(base.glob(f"{day}.resealed_*.json"))
    if not cands:
        continue
    try:
        return json.loads(cands[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue          # <- continues the OUTER loop, to SEED_BOOKS
```

On a parse failure it does **not** fall back to the valid `<day>.json` sitting
beside the torn one — it abandons the whole `BOOKS` directory and returns the
`docs/seed/predictions/` copy, which is whatever was last `--publish`ed and
committed.

**The scenario.** `state/predictions/<day>.resealed_HHMMSS.json` is truncated —
by a kill during the non-atomic `write_text` at `scripts/prediction_book.py:931`,
or by R7's fixed-tmp-name race in `prediction_book_sync`. `_book_for` returns the
seed book. `sealed_holdings` succeeds, `entry_open.verified_book` re-hashes *that*
payload and it validates, `open_auction` logs a sha and a name list, and the
account trades a superseded book while every integrity check reports green.

This is the one failure in this audit that does not announce itself in any log
line. It also defeats a deliberate policy: `scripts/seal_authority.py:78-82`
explicitly declines to alias a reseal over the original ("no retroactive reseals
is the default") — and the brain's own glob takes the newest file regardless, so a
mid-session reseal *does* silently switch the runner's book on the next pass.

**Minimal fix.** Try the candidates newest-first *within* a directory before
moving to the next, and refuse outright rather than falling back across
directories when a candidate for the requested day exists but will not parse.

---

## R7 — A killed `candidates` / `window_universe` write silently stops the entry pass for six hours

**CONFIRMED-IN-SOURCE.**

**Where.**
- `scripts/candidates.py:110` — `path.write_text(json.dumps(report, ...))` onto
  `state/candidates/<utc-date>.json`, non-atomic. On-disk sizes are 13–20 KB
  (`state/candidates/2026-08-28.json` = 20,193 B).
- `scripts/agent_loop.py:301-304` runs it every 6 h with a **900 s kill**.
- `scripts/run_pass.py:296-302` — `files = sorted(glob("*.json"))`, then
  `json.loads(files[-1].read_text())` with **no `try/except`**.
- Identical shape: `scripts/window_universe.py:276` writes
  `state/window_universe.json` (40 KB) non-atomically; `scripts/run_pass.py:283-288`
  checks `src.exists()`, passes, then `json.loads` unguarded. Readers in
  `discovery_autopsy.py:73`, `dislocation_scan.py:48`, `premarket_digest.py:83` are
  equally unguarded; only `news_backfill.py:84` protects itself.
- `os.replace` appears exactly three times repo-wide (`escalation.py:99`,
  `liveness.py:162`, `prediction_book_sync.py:86`). Everything else on the money
  path writes straight onto the final name.

**The scenario.** `scripts.candidates` runs long on vendor calls and is SIGKILLed
at 900 s mid-`write_text`. `state/candidates/<today>.json` is left truncated. The
next entry cycle takes `files[-1]` — which is *today's broken file*, not
yesterday's good one — and `run_pass` dies with `JSONDecodeError`, rc≠0. `_run`
counts and logs it, and **the entry pass places nothing** until `candidates`
regenerates six hours later. That is exactly the "a refusing pass reads exactly
like a quiet market" failure `agent_loop._run`'s own docstring is written about,
arriving through a file rather than through a flag.

**Dollar shape.** A whole session of a sealed book unexpressed, on a five-session
competition. Silent to everything except a non-zero rc.

**Minimal fix.** tmp + `os.replace` for both writers (with a **pid-unique** tmp
name — see R14), and `try/except (OSError, ValueError)` at every reader with a
fall-back to the previous file and a loud line naming the corrupt one.

---

# MEDIUM

## R8 — `clamp_to_sealed` compares a RISK fraction to a NOTIONAL weight, so it can never bind

**CONFIRMED-REPRODUCED.**

`alpha/brains/tracker_portfolio.py:250-272`, called from `alpha/runner.py:463-487`
on the value produced at `alpha/engine/sizing.py:412-434`:

```python
risk = w * (structure.max_loss / structure.entry_cost)      # sizing.py:427
```

For a share, `max_loss = spot × stress_charge` and `entry_cost = ask ≈ spot`, so
`risk ≈ 0.05 × w`. `clamp_to_sealed` then tests `0.05w <= w`:

```
sealed_notional = 10%  ->  sizing risk_fraction = 0.499%
clamp_to_sealed        ->  0.499%  |  "within the sealed 10.0%"
CLAMP BINDS? False
```

To bind, the stress charge would have to exceed **100% of spot**.

The delivered notional is currently correct only because `runner.contracts_for`
(`:918-930`) divides by the same `max_loss` that `sizing` multiplied by — the two
errors cancel. The guard meant to catch a divergence is measuring in the wrong
unit and will report "within the sealed w" for any divergence short of a 100%
charge. Three changes silently un-cap the weight with the guard still green:
making `stress_charge` profile-aware (the R3 fix), changing `entry_cost` to the
mid or the last trade, or admitting a kind whose `max_loss` is not proportional
to spot. The 08-31 artery's headline protection — "the book's weight is a ceiling,
not a suggestion" (`tracker_portfolio.py:224-237`) — is presently decorative.

Related: `SHARE_KINDS` (`:243`) includes `short_shares`, but `sizing.size`'s sealed
branch refuses any structure with `entry_cost <= 0` (`sizing.py:420`) and
`short_shares` carries `entry_cost = -bid` (`equity.py:193`). A sealed short is
silently un-expressible — fail-closed, but the two modules disagree about what is
legal.

**Minimal fix.** Clamp on notional: compute `n` first, assert
`n × spot <= sealed × equity`, reduce `n` if not. Or convert the ceiling into the
same unit (`sealed_risk = sealed × max_loss / entry_cost`). Test: a
`risk_fraction` set to `2 × sealed` is actually cut.

## R9 — `units_cap` is the one link in the sizing chain that ignores the `risk_profile` argument

**CONFIRMED-REPRODUCED.**

`alpha/runner.py:918-930` calls `equity_mod.units_cap(spot, equity)` with **no
profile** → `notional_cap(None)` (`equity.py:144-148`) →
`os.getenv("AAT_RISK_PROFILE", "")`. Everything around it honours the argument:
`sizing.profile(risk_profile)` (`runner.py:1387`), `sizing.gross_cap(risk_profile)`
(`:1395`), `admission.admit(...)`.

`scripts/run_pass.py`'s own docstring line 5 documents
`python -m scripts.run_pass --role exp1 --profile maximum --live`. `--role` is
pushed into `os.environ` at the entry point (`:239`); `--profile` is not.
Reproduced with the env unset:

```
--profile basket   AAT_RISK_PROFILE UNSET: units=4990  $24,950 = 25% of equity;  mandate cap = 10%
--profile convex   AAT_RISK_PROFILE UNSET: units=4990  $24,950 = 25% of equity;  mandate cap = 10%
with env set to basket:                    units=1996  $ 9,980 = 10%             (correct)
```

**Dollar shape.** 2.5× the mandated per-name notional; a k=10 basket book becomes
a 4-name 25%-each book before the (correctly-profiled) gross cap stops it. At the
basket 8% stop the per-name worst case is −$2,000 instead of −$800 — concentration
wearing a basket's name, which is exactly what `MAX_NOTIONAL_BY_PROFILE`'s comment
(`equity.py:136-139`) exists to prevent.

The Railway fleet is **not** affected — `alpha/fleet.py:216-233` puts
`--profile <p>` into `AAT_LOOP_ARGS` *and* `AAT_RISK_PROFILE` into the service
env; verified per role for hack3/4/5/6. This is an attended-run and
future-caller defect.

Same family, same file: `protect.ensure`'s default `stop_fraction`
(`protect.py:208-210`) is env-only, and `equity.stress_charge` (`:125-129`)
hardcodes `STOP_FRACTION` — so a `basket` book's sizing charge is computed at a 3%
stop while its stop rests at 8%.

**Minimal fix.** `contracts_for(..., profile=None)` threaded from `_execute`; or
set `os.environ["AAT_RISK_PROFILE"] = args.profile` in `scripts/run_pass.py`
beside the existing `--role` mutation, with the same "the flag is authoritative"
comment.

## R10 — `universe.execution_authority` has no caller on any order path

**CONFIRMED-IN-SOURCE** (the grep's emptiness is the proof).

`alpha/universe.py:90-118`. Repo-wide:

```
alpha/universe.py:66,80      prose
alpha/universe.py:90         the definition
scripts/fleet_health.py:14   prose
scripts/tracker.py:45,338    prose
tests_smoke_universe.py      x4   <- the only callers
```

Nothing between `sealed_holdings` and `client.submit` consults it. Every size
bound in `runner._execute` and `admission.admit` is a fraction of **our** equity
(notional, gross, driver, event-node); **no bound anywhere is a fraction of the
NAME's liquidity.** `MAX_ADV_PARTICIPATION = 0.01` (`universe.py:87`) is enforced
by nobody.

**Scenario.** A sealed name with $400k/day median dollar volume takes hack4's 10%
= $10,000 = 2.5% of ADV, 2.5× the declared ceiling. Alpaca paper fills it at the
quote, so the ledger records an impact-free fill, the counterfactual grades
against it, and the competition P&L rests on a fill that could not be repeated
with real capital. The declared UNKNOWN semantics ("an absent dollar volume is not
a dollar volume of zero", `:94-98`) are correct and unreached. Same shape as the
recorded S30 finding, one layer down.

**Minimal fix.** Call it in `_execute` beside the gross check using the sealed
row's `median_dollar_volume`; refuse on `tier == "UNKNOWN"`, cut `n` to
`max_usd / spot` on `OBSERVE_ONLY`. Enrol it in `scripts/reachability.py` so it
cannot go orphan again.

## R11 — The tracker day file is named in UTC and its freshness guard is read in ET, so it reads one session fresher than it is

**CONFIRMED-IN-SOURCE.**

`scripts/tracker.py:95` `_day()` returns the **UTC** date;
`alpha/exits.py:94` `session_day()` returns the **ET** date. `alpha/tracker.py:290`
`freshness(day, asof=...)` compares the file's day label against an ET `asof` in
sessions, limit `MAX_TRACKER_AGE_SESSIONS = 2` (`:264`).

Between 20:00 and 24:00 ET the UTC date has already rolled, so an evening refresh
writes **tomorrow's filename over today's closes**.

**Scenario.** The refresh last succeeded Monday 20:30 ET and wrote
`2026-09-01.jsonl` (Tuesday UTC) holding Monday's closes. Thursday's seal computes
age = 2 sessions, hits the limit exactly, and **passes** — on prices three
sessions stale. This is precisely the failure the guard's own comment
(`alpha/tracker.py:245-252`) says it exists to prevent: "a refresh that dies on
Sunday and again on Monday produces a Tuesday seal priced on Friday's closes."

**Minimal fix.** `_day()` should be `exits.session_day()`. One definition of the
trading day, next to the offset it depends on — the rule `session_day`'s own
docstring already states.

## R12 — `observed_at` is stamped at the run's start, not at capture

**CONFIRMED-IN-SOURCE.**

`scripts/tracker.py:463` computes `now = datetime.now(timezone.utc).isoformat()`
**once, before the per-symbol loop**, and `:516` writes `"observed_at": now` on
every row. With `FINNHUB_SLEEP_S = 0.4` (`:86`) + `YF_SLEEP_S = 0.15` (`:90`) plus
two HTTP round-trips per name over ~3,000 names, a run spans hours.

**Scenario.** The chain starts 06:00 ET. The consensus target for the name at
position 2,400 is actually read at 09:55 ET — after the open, after that name's
revision hit the tape — and is written with `observed_at: 06:00`. Any reseal,
replay, or `company_state` vintage that filters on `observed_at`
(`alpha/company_state.py:137` copies the stamp verbatim) concludes the value was
knowable pre-open. It was not. `alpha/tracker.py:38-45` states the contract this
line breaks: "we stamp `observed_at` ourselves at capture and the value may be
used strictly AFTER that stamp."

**Minimal fix.** Move the `now` computation inside the loop.

## R13 — `decision_writeback` grades from the decision-day CLOSE, and freezes an immature horizon append-only

**CONFIRMED-IN-SOURCE.** Two defects in one file (HEAD).

*(a) Wrong basis.* `grade_rows` (HEAD `:113`ff) sets `basis = series[i0][1]` where
`i0 = idx[day]` — the **close of the decision day**. The decision was made
pre-open and the order placed at or near the open, so every horizon measures
close-to-close from a price stamped ~6.5 hours after the decision.

> A sealed name gaps +12% at the open on day D — which is where an
> analyst-target signal's edge lives — and drifts −1% into the close. Basing on
> D's close makes the +12% invisible at every horizon, and the book grades as
> flat-to-negative on its best day.

Meanwhile `scripts/prediction_book.py` `_sessions_after` (HEAD `:485-498`) grades
the *same* decisions **from the open of the session after `day`**, matching the
falsifier text printed on every prediction row. Two graders, two conventions, no
reconciliation, and one of them contradicts the book's own written falsifier.

*(b) An immature horizon is frozen as a result.* `_closes` (HEAD `:181`) calls
`client.stock_bars(sym, start=start_day, timeframe="1Day")` — **no `end`**.
`grade_rows` guards only on index (`if j >= len(series): break`), so an
in-progress bar counts as a matured session. `append_missing` (HEAD `:153-167`) is
keyed on `(type, day, book, symbol, horizon_sessions)` and, by its own docstring,
"an existing row is never rewritten, even if the new assembly differs."

> `--grade` runs at 11:00 ET on the session completing the h=5 horizon.
> `j = i0+5 < len(series)`, a `grade` row is written with `graded_close` = the
> 11:00 print, and the append-only key **permanently blocks** the correct
> post-close value. The h=5 result is a mid-session quote, forever, and nothing
> on the row says so.

**Minimal fix.** Base on the session-after open, matching `_sessions_after`. Pass
`end` to `_closes` and refuse to write a grade whose terminal bar is the current
session. Make `append_missing` upgrade a row whose `graded_close` came from an
incomplete bar.

## R14 — `alpha/ledger.py:_Lock` steals a stale lock and then unlinks unconditionally, reopening the 25-Aug multi-writer window

**CONFIRMED-IN-SOURCE.**

`__enter__` (`:166-168`) steals any lock whose mtime is >30 s old; `__exit__`
(`:175-179`) unlinks `self.lock` **without checking whether it is still its own**.
The pid *is* written into the lock at `:160` and **never read back** — the
information needed to make `__exit__` safe is on disk and unused.

Interleaving, three writers on `state/decisions.jsonl` (17.8 MB):

- `t=0` **A** (`scripts.counterfactual`, marking a batch) creates the lock and
  stalls inside the critical section. >30 s is not hypothetical: the comment at
  `ledger.py:108-110` records exactly this — two loops recording ~5,000 marks each
  "held the lock past its timeout (26 Aug 04:00 HK)".
- `t=31` **B** (`scripts.manage`) sees the lock is stale, **unlinks A's lock**,
  creates its own, enters. A is still inside. Mutual exclusion is already gone.
- `t=33` **A** exits and unlinks the same path — **deleting B's lock**, which B
  does not know.
- `t=34` **C** (`scripts.run_pass`) finds no lock, `O_EXCL` succeeds immediately,
  enters. **B and C are both in the critical section with no lock at all.** Both
  compute the same `_prev`; the second row's `_prev` is stale (a chain break), or,
  if either row exceeds the buffer — `Decision.tournament_state` is an open dict —
  the two writes splice mid-JSON, which is the "decisions partly LOST rather than
  merely unverifiable" damage `scan_chain` describes at `:214-216`.
- Whichever of B or C exits first unlinks the other's lock, so the corruption is
  self-sustaining across subsequent writers.

Two supporting defects: `:169-170`'s `except OSError: continue` skips **both** the
120 s deadline test and the `time.sleep(0.05)`, so a rapidly created/deleted lock
produces an unthrottled spin that can never raise the `TimeoutError` it
advertises; and the mtime is never refreshed while held, so `STALE_S = 30` is a
hard cap on how long any legitimate writer may hold it.

*(This is offered as a distinct root-cause mechanism, not as a re-report of the
known chain break. Do not repair the existing chain — repairing a tamper-evident
chain is the tampering.)*

**Minimal fix.** Write the pid, read it back in `__exit__`, and unlink only when
it matches. Refresh the mtime on a heartbeat while held. Restore the sleep and
the deadline on the `OSError` path.

## R15 — The pre-open auction window can be starved by ungated steps earlier in the same cycle

**PLAUSIBLE** (timing-dependent; step runtimes not measured here).

`scripts/agent_loop.py:249-346` cycle order: sync → clock → manage (open only) →
autopsy (closed, 16–20 ET) → `window_universe` (every 6 h, 900 s kill, **ungated
on the clock**) → `candidates` (every 6 h, 900 s kill, **ungated**) → council
(gated on `mins_to_open > 60`) → **the auction block**. The auction window is
`[T−45, T−10]` minutes (`alpha/entry_open.py:73, 81`).

**Scenario.** `candidates` fires at T−22 and takes 14 minutes. The auction block
is reached at T−8, `should_run` returns *"8.0 min to the open is outside the
pre-open window [10, 45]"*, and hack4 and hack6 silently enter at 10:01 like the
control. The tournament's arms become uncomparable for that day — the exact
failure `entry_open`'s own docstring (`:26-29`) says a tournament cannot survive.
It is also invisible: the no-pass line is `log.debug` (`agent_loop.py:342`) and
the loop runs at INFO (`:189`).

**Minimal fix.** Gate `window_universe` and `candidates` on `mins_to_open > 60`
as `council` already is. Raise the missed-window line to `log.warning` when a
style is set, and write a `"missed_window"` receipt so `entry_timing_grade` counts
the days each arm actually ran.

---

# LOW

## R16 — `deadline_liquidation_due` compares a UTC date to an ET date

**CONFIRMED-REPRODUCED.** `alpha/exits.py:114-121`:

```python
if current.date() < (deadline + ET_OFFSET).date():   # UTC date vs ET date
```

```
UTC 09-04 00:05 -> ET 09-03 20:05  liquidate_due=True   <-- a full evening early
UTC 09-04 03:59 -> ET 09-03 23:59  liquidate_due=True
UTC 09-04 04:01 -> ET 09-04 00:01  liquidate_due=False
UTC 09-04 14:44 -> ET 09-04 10:44  liquidate_due=False  (correct)
UTC 09-04 14:46 -> ET 09-04 10:46  liquidate_due=True   (correct)
```

True for every instant from **20:00 ET on 09-03** to **00:00 ET on 09-04**. It
fires on the right day only because this deadline's ET and UTC dates coincide; a
deadline at `02:00Z` would fire a day **late**.

Not merely cosmetic: an attended `python -m scripts.manage --live` on the evening
of 09-03 — a plausible pre-judging check — enters the deadline branch for every
position, and `exits.manage` cancels the protective stop *before* attempting the
close (`:566-576`). With the market shut the close fails, the error is recorded,
and the loop moves on **without re-placing the stop**, leaving the estate
unprotected overnight into judging day.

**Fix.** `(current + ET_OFFSET).date() < (deadline + ET_OFFSET).date()`; and
`exits.manage` should re-place a stop it cancelled when the close fails.

## R17 — The entry-timing receipt is written AFTER the orders are live, under the tightest timeout, and the grader rewrites it non-atomically

**CONFIRMED-IN-SOURCE.** `scripts/open_auction.py` order of operations: claim the
marker (`:245`) → `run_pass` submits (`:250`) → `write_receipt` →
`p.write_text(...)` (`:120`). `scripts.open_auction` carries the **300 s** kill
(`agent_loop.py:70`), the tightest in the table, on the step doing broker
round-trips.

Killed mid-`write_text`: the receipt is truncated, the marker already exists so
`should_run` returns `already ran today` (`entry_open.py:143-144`) and nothing
regenerates it. That evening `scripts/entry_timing_grade.py:80` sees
`receipt_path.exists() == True` (so it does *not* report `NO RECEIPT`), then
`json.loads` at `:83` raises — uncaught, since `main`'s `except BrokerRefusal`
(`:176`) does not catch `JSONDecodeError`. The whole grade run dies, and the
`client_order_id`s recorded only in that receipt are the sole link between the
sealed book and the venue fills. The tournament number for a day of **real
orders** becomes unrecoverable. `entry_timing_grade.py:87` and `:154` then rewrite
the same file non-atomically, so the grader can destroy the artifact it is
grading.

**Fix.** tmp + `os.replace` with a pid-unique tmp name, and write a minimal
receipt (day, role, style, decision ids) *before* `run_pass`, enriching it after.

## R18 — Swallowed writes that make a failed persist look successful

**CONFIRMED-IN-SOURCE.** Three instances, ranked:

- `alpha/exits.py:479-489` `_arbiter_record_due` — `marker.write_text(...)` inside
  `except OSError: pass`, then `return True` regardless. On a full or read-only
  `state/`, the 30-minute rate limit silently degrades to **every exit pass (5
  minutes)**, flooding the decision ledger with arbiter verdicts — while
  `ledger.record` is simultaneously the thing most likely to be failing.
- `alpha/alpha_budget.py:216-221` — `_append` swallows `OSError`; `alpha_budget`
  (`:207-208`) returns the `Verdict` either way, and `summary()` (`:224`) derives
  wealth entirely from the rows on disk. A silently dropped append **restores
  wealth that was actually spent**.
- `alpha/spend.py:103-107` — `record()` swallows `OSError` and returns `None`;
  `llm_post` (`:119`) returns the data unconditionally. `state/llm_spend.jsonl`
  (1.78 MB) is the only record of what the money bought, and `summary()` (`:128`)
  parses it unguarded, so one torn line makes the whole spend report unreadable.

## R19 — Symbol case is handled inconsistently inside the one-position-per-symbol predicate

**PLAUSIBLE.** `alpha/runner.py:1131`:

```python
if symbol in held and symbol.upper() in topup and symbol not in in_flight:
```

`held` (`:334-345`), `in_flight` (`:347-378`) and `stopped` are keyed by the
**venue's** symbols (always upper); `topup` is keyed `.upper()` — the line itself
concedes `symbol` may not be. `Forecast` (`alpha/brains/base.py:35-80`) does not
normalise: `__post_init__` checks only `sd > 0`. `scripts/run_pass.py:270-330`
dedupes the universe by exact string.

A lowercase symbol from any brain or a hand-typed `--universe` makes
`symbol in held` False, the `already_held` guard never fires, and a second
position opens in a name the book already holds — the per-name notional cap does
not save it, because `units_cap` is computed fresh per order and knows nothing
about the existing position. Today's tracker books are clean only because
`tracker_portfolio.forecast` uppercases at `:158`.

**Fix.** `object.__setattr__(self, "symbol", self.symbol.upper())` in
`Forecast.__post_init__`; `.upper()` the universe before dedup.

## R20 — Three smaller ones, stated for the record

- **A duplicate symbol in a sealed portfolio silently collapses.**
  `alpha/brains/tracker_portfolio.py:153` builds `{h["symbol"]: h for h in ...}`;
  two rows for one symbol keep the last. `n_selected` and the seal's
  `worst_case(n=...)` receipt (`alpha/tracker.py:1246-1269`) still count both, so
  the book trades less than the receipt declares. PLAUSIBLE (depends on whether
  the sealer can emit a duplicate — that file is being edited concurrently).
  Refuse rather than collapse, in the voice of `ranking_is_degenerate` (`:138`).
- **A rejected order permanently consumes gross headroom for the rest of the
  pass.** `alpha/runner.py:1421-1428` increments `gross["committed"]` before the
  POST; the `BrokerRefusal` branch (`:1472-1478`) never rolls it back, and the
  `dry_run` branch increments real gross for an order never sent. Conservative in
  direction, but "the number the cap binds on" and "what the book carries" diverge
  silently inside a pass. CONFIRMED-IN-SOURCE.
- **`scripts/analyst_panel.py:185` opens its day file with `"w"`, contradicting
  its own comment.** The comment at `:177-181` says "WRITE AS WE GO… a panel row is
  worth having whether or not the run finished"; `path.open("w")` truncates to
  zero at open, so a retry after a kill destroys every row the first run captured
  before writing a byte. CONFIRMED-IN-SOURCE.

---

# WHAT I ATTACKED AND FOUND CLEAN

Recorded so the next auditor does not re-spend the time.

- **Division by zero and negative prices.** Guarded everywhere on the order path:
  `equity.shares:174`, `sizing.size:420`, `contracts_for:920`, `units_cap:226`,
  `topup_headroom:282`, `protect.stop_price_for:131`, `gap_allowance:105`,
  `implied_probability_beyond:322`, `tracker_portfolio.forecast:181`. This is the
  best-defended axis in the engine.
- **The half-weight rounding to zero shares.** It cannot silently round: a
  staggered 3%-of-equity leg on $100k needs a $3,000+ ask to reach zero units, and
  `_execute` refuses with class `capital` and a named reason (`runner.py:1412-1420`)
  rather than rounding up; `build_order` also raises on `contracts < 1` (`:846`).
  Fail-closed both ways.
- **Decimal-string quantities from the venue.** `topup_headroom` and
  `gross_notional_by_symbol` both coerce (`float(pos.get("qty") or 0.0)`,
  `abs(float(mv))`). `protect.build_stop:143` truncates a fractional qty by <1
  share — noted, immaterial for an integer-qty shares-only book.
- **`opg` replay / double-submit.** `opg_decision_id` is deterministic in
  (day, symbol) (`entry_open.py:192-202`), the marker is claimed with `O_EXCL`
  before any order is built (`:164-182`, `open_auction.py:243-247`), and the venue's
  duplicate-client-id rejection is the backstop rather than the plan. Correct as
  designed.
- **`already_held` in the auction pass.** `entry_style is not None` makes `topup`
  an empty dict (`runner.py:1103`), so the pre-open pass cannot double a position
  held from yesterday.
- **The opening-range BYPASSED stamp.** Written onto the decision row's economics
  *before* the gate is skipped (`runner.py:1330-1345`); `in_opening_range` takes an
  injectable clock and excludes weekends (`:276-299`). Clean.
- **`AAT_LOOP_ARGS` carrying `--profile`.** I expected drift (the Dockerfile CMD
  does not name `--profile`); `alpha/fleet.py:220-233` strips only
  `--brains`/`--shadow` and passes `--profile` through, verified per role.
  **Not** a defect — recorded so it is not re-suspected.
- **Sealed-weight bounds.** `0 < w <= 0.25` is enforced and refuses a corrupt
  artifact (`sizing.py:412-419`).
- **`alpha/counterfactual.py`.** `mark()` prices forward from `now` against live
  quotes; `Mark.graded` (`:133`) counts `mark_source == "chain"` only, so
  `unmarkable` and `null` worlds are excluded from win rates. No pre-decision
  price is used and no immature world is counted.
- **`alpha/sources/features.py` and `alpha/analyst_targets.py`.** Correct
  instant-vs-day bounds throughout, including the deliberate two-clock split in
  `daily_features` (`:550`). The PIT discipline the tracker path lacks (R2) is
  fully present here.
- **Per-service volumes.** `scripts/fleet.py:110` mounts `/app/state` per service,
  so the six Railway roles do **not** share state. The multi-writer surface is the
  dev host running two roles from one checkout, and an overlapping redeploy.

# STILL OPEN — NOT AUDITED

`alpha/fills.py`; `alpha/book.py`'s residual-short charge; `alpha/admission.py`'s
greeks and `n_risk` branches; `alpha/arbiter.py`'s override authority over a
deadline verdict; and the options structures (`payoff.py`, `structures.py`,
`spreads.py`) — hack5 is the only options book and it fell outside the
shares-first priority order.
