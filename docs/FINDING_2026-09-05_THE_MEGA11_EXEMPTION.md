# FINDING — a guard scoped "outside the mega-11" left the only path that traded

**Date:** 2026-09-05. **Licence:** RESEARCH_CLAIM standard for the negative
(it is a refutation with a re-measurement); the strategy claim it refutes was
`PRODUCT_EXPERIMENT`.
**Origin:** asked "why was hack1 shorting PANW?" — a question raised only because
a *different* defect (the entry pass having no deadline gate) made the trades
visible. The answer to the question asked is benign. The answer to the question
it opened is not.
**Related:** `FINDING_2026-08-26_PEAD_ADVERSARIAL.md` (the battery whose fix this
document says was mis-scoped) · `PROPOSAL_2026-09-05_DECISION_TIMING_NOT_POLLING.md`
· `VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md` §6 (the exit-machinery findings).

---

## 0. THE ONE-LINE VERSION

A 2026-08-26 adversarial battery found that `post_event_drift` **measures** its
edge as excess over β·QQQ in **log** returns and **trades** it unhedged in
**simple** returns. The fix — `WIDE_UNHEDGED_SHORT_ENABLED = False` plus a
registered guard — was scoped, in the finding's own words, to *"outside the
mega-11."* **The mega-11 is the only path that has ever placed one of these
shorts.** Re-measured in the receipt's own window, the headline **t 2.82 becomes
t 1.45** in the currency the position is paid in, and the cell PANW landed in is
**negative**.

## 1. WHAT WAS ASKED, AND WHY THE ANSWER IS "NO"

**Is `post_event_drift` shorting positive events — a sign inversion?** No.

PANW filed an 8-K Item 2.02 after the close on **2026-09-01**. The first
reflecting close, 2026-09-02, moved **−9.74%** (362.06 → 328.45). Post-earnings
drift is a *continuation* effect, so a short on a −9.74% print is exactly what
the brain is designed to do. The sign traces end to end with no negation:

- `alpha/brains/event_move.py:114` — `event["move"] = math.log(closes[i]/closes[i-1])`
- `alpha/brains/post_event_drift.py:265-266` —
  `sign = 1.0 if r0 > 0 else -1.0; centre = sign * base_centre`

The brain's own emitted rationale, reproduced read-only:

> *PANW printed amc on 2026-09-01; the first reflecting close 2026-09-02 moved
> −9.74% — over-extended (>8.2%, t 1.26). 2 session(s) elapsed … worth −0.41%
> excess over beta\*QQQ*

**Verdict: DIRECTIONALLY CORRECT.** Read that rationale again, though. It says
`excess over beta*QQQ` — and the position was `short_shares`, unhedged.

Provenance is established from the venue rather than from prose: all five PANW
`client_order_id`s reverse under `sha256(decision_id)[:32]` to `post_event_drift`
decision ids (e.g. `aat-cad2f7a661c0370bb0c7117b75f32d52` →
`20260903T1401:post_event_drift:PANW`), and Railway's log independently carries
`"instrument": "short_shares"`. This mattered because **every fleet decision row
lives only on the Railway volume** — the local `state/decisions.jsonl` holds 32
hack1 and 42 hack2 rows and they are all 2026-08-28 laptop dry-runs with **no
PANW decision at all**.

## 2. THE ACTUAL FINDING: THE EXEMPTION

`FINDING_2026-08-26_PEAD_ADVERSARIAL.md:8` scopes its work to *"outside the
mega-11."* `alpha/guards.py:96` registers `wide_down_pair_only` — *"unhedged
short +0.04% simple, nothing"* — and `WIDE_UNHEDGED_SHORT_ENABLED = False`
disarms the wide universe. Both defects the battery found apply verbatim to the
mega-11 path, which was never amended: `scripts/source_pead_horizon.py:122`
computes the `ARRIVAL` constants as *"per-day excess over beta\*QQQ, signed into
the day-0 direction"*, and the mega-11 quotes them while expressing
`short_shares`.

Re-measurement in the receipt's own window (2024-03-21 .. 2026-08-05,
`|day-0| ≥ 3.5%`, day+1 open → +3 close, Alpaca `adjustment=all`):

| cell | n | EXCESS vs β·QQQ (**quoted**) | RAW SIMPLE (**traded**) | PAIR vs IWM |
|---|---|---|---|---|
| ALL | 80 | +1.352% t **2.71** | +0.976% t **1.45** | +1.213% t 2.00 |
| UP mid | 13 | +1.276% t 1.12 | −0.829% t −0.45 | −0.406% t −0.28 |
| UP big (>8.2%) | 20 | +2.624% t 1.86 | **+3.698% t 2.29** | +3.632% t 2.37 |
| DOWN mid | 28 | +1.255% t 1.99 | +1.111% t 1.60 | +1.315% t 1.79 |
| **DOWN big (>8.2%) ← PANW** | **19** | **+0.210% t 0.24** | **−0.852% t −0.59** | **−0.379% t −0.31** |

Three claims, each standing on its own row of that table:

1. **The headline t 2.82 is t 1.45 in the currency the position is paid in.** The
   same collapse the battery found in the wide universe, one population up.
2. **PANW's print landed in the single worst of the four cells** — negative on the
   raw measure *and* on the pair measure. The brain halves conviction above 8.2%
   (`conviction = 0.6 * ...`) but does not refuse, and the −0.72%/−0.41% it
   quoted came from a **pooled two-sided** `ARRIVAL` constant, not from that cell.
3. **On raw simple returns the mega-11's edge lives in `UP big`** (+3.698%,
   t 2.29) — the *opposite* of the module docstring's *"the DOWN side is the
   stronger half"*, and the one cell where conviction is halved.

Extending to 2024-01..2026-08 (n = 52 DOWN) gives the same picture: raw unhedged
**+0.03% t 0.05** overall, `big` **−1.40% t −1.01**.

**What this does and does not close.** It closes *this implementation* — an
unhedged short expressed from a hedged, log-return measurement, sized from a
pooled constant, on the strategy's worst cell. It does **not** close post-event
drift. Two things in the same table look worth testing properly: the `UP big`
cell on raw simple returns, and the pair-vs-IWM expression that keeps the
measurement and the trade in the same currency.

## 3. WHAT IT COST, AND WHY THE SIGNAL WAS NEVER THE BINDING TERM

Five shorts, two SAFE-tier books, **−$725.35** total.

| # | decision_id | entered ET | side | fill | exit | P&L |
|---|---|---|---|---|---|---|
| 1 | `20260903T1401:…:PANW` (hack1) | 09-03 10:03:44 | sell 48 | 328.9010 | buy-**stop** 338.79375 | **−$474.85** |
| 2 | `20260904T1400:…` (hack1) | 09-04 10:18:39 | sell 37 | 334.91 | mkt buy 330.41 | +$166.50 |
| 3 | `20260904T1501:…` (hack1) | 11:42:54 (sent 11:01:32) | sell 51 | 331.8388 | mkt buy 331.84 | −$0.06 |
| 4 | `20260903T1402:…:PANW` (hack2) | 09-03 10:03:42 | sell 75 | 328.1576 | mkt buy 333.49 | **−$399.93** |
| 5 | `20260904T1503:…` (hack2) | 11:03:39 | sell 74 | 331.4101 | mkt buy 331.64 | −$17.01 |

**All five carried `expected_edge_usd` of $92–128 against a 3% stop worth
$700+ — roughly 1:8 against.** That ratio is computable at seal time from
numbers the book already holds, and it makes every one of these trades
negative-EV *before any question about the signal*. A book that prints its
expected edge in dollars and its stop in dollars and does not compare them is
missing a one-line guard, and the guard needs no research to justify.

### 3a. The −$475 was the stop, not the thesis

`STOP_FRACTION_BY_PROFILE["conservative"] = 0.03` put a buy-stop at
328.90 × 1.03 = **338.77** against the brain's own forecast 2-session sd of
**5.75%** (4.07%/day × √2) and a claimed centre of −0.72%. **The barrier sat
0.52σ away.** PANW's 5-minute bars show a spike to **338.91 at 09:40–09:45 ET**
that touched it and reversed to 334 within ten minutes. Held to that session's
close (333.29) the mark was **−$210.68** — the stop made the realised loss
**2.25× worse than the thesis's own horizon**.

`alpha/engine/equity.py`'s own comment reads *"a stop inside the noise is a fee,
not a stop"* — and the file then keeps 3% for the SAFE profiles. This is the same
constant already indicted twice: it pre-empts the correctly-profiled venue stop
(8% for hack3, 6% for hack4), and it is *also* the sizing charge, so the per-name
worst case is understated ~2.5× in the opposite direction.

### 3b. The −$400 came with a defect that happened to be lucky

hack2's protective stop (338.00, `aat-stop-922d3abb94e5c3f6eba8960d`) was
**cancelled at 2026-09-04T13:32:05Z and no replacement was ever placed**; the
position was closed by a `close_position` DELETE **76 minutes** later. The
sequence is structural: `exits.manage` calls `protect.ensure` at the *top* of the
pass on a stale `positions` snapshot, and only later runs `cancel_for` →
`close_position` (`alpha/exits.py:513, 561-586`). The code reasons carefully
about *cancel fails ⇒ do not close* and says **nothing** about *close fails ⇒
re-place the stop we just cancelled*. A one-sided guard leaves a naked short for
a full cadence.

Honest accounting, because it cuts the other way: that naked window **contained**
the 338.91 spike. Had the stop survived it would have filled at ≈338.00 for
**−$738.18**. **The bug saved $338.25.** It is still a defect — a naked unbounded
short for 76 minutes is not a risk anyone authorised — and the fact that it paid
this once is exactly why it would otherwise never be found.

### 3c. Losses #3 and #5 are the deadline asymmetry, already fixed

Entries kept firing after `LIQUIDATE_BY_ET` (10:45) because the exit pass was
gated on the deadline and the entry pass was not. #5 lived **five seconds**; #3
was round-tripped for the spread. Fixed in terminal commit `fd0c75b` (local,
unpushed) and disarmed at the variable layer on all six roles.

## 4. AND THE FRAME UNDERNEATH: `tier` IS DECLARATIVE ONLY

A SAFE-tier account could open an unbounded short **by omission, not by design**.

- `Mandate.tier` is read nowhere outside `alpha/fleet.py`'s own tuple-building and
  table-printing, plus `scripts/fleet.py:33,220`. The only enforcement in the
  repo is `tests_smoke_fleet.py:47` — *"safe roles never run a gated profile."*
- `alpha/engine/equity.py:150` admits `short_shares` for any book whose
  `structure_kinds` is empty, which is hack1's and hack2's setting. `shares()`
  refuses only if the venue says the name is not shortable.
- No refusal class, no admission check and no guard is keyed to tier **or to
  side**.
- The structure self-labels `"theoretical_max_loss": "UNBOUNDED (short share, no
  ceiling)"` while booking `max_loss = spot × 0.05`. The label and the number
  disagree, and the number is what sizes the position.

One related mismatch, worth a line: hack1's declared question is about
*"SPY/QQQ/IWM shares + one ATM index call"*, and its `fixed_symbols` are
`("SPY","QQQ","IWM","NVDA","AVGO","PANW")` — three single-name earnings printers
inside what is described as an index anchor.

## 5. WHAT IS STILL ARMED

`Mandate.manage_only=True` is declared on **hack1 only**. **hack2 is also
`tier="SAFE"`, also `brains=("post_event_drift",)`, and runs
`universe="window"`** — so it can originate this same short on any name whose
8-K clears the mega-11 filter. It is held back today only by the Railway
variable layer (`--manage-only` in `AAT_LOOP_ARGS`, `AAT_ENTRY_STYLE` absent),
which is deliberate and instantly reversible — but the *mandate* does not say it.

## 6. WHAT SHOULD CHANGE (proposed; none of it applied)

Ordered by ratio of harm prevented to work required:

1. **Compare the edge to the stop at seal time.** Refuse (typed) when
   `expected_edge_usd < k × stop_loss_usd`. Every one of these five trades fails
   at any sane `k`. No research needed; both numbers are already in the book.
2. **Amend the mega-11 with the 2026-08-26 fix** it was scoped out of: an
   unhedged short may not be expressed from a hedged measurement. Either hedge
   it (pair vs IWM, which measures +1.213% t 2.00 overall) or re-measure the
   constants raw and simple — and if raw, the DOWN-big cell refuses.
3. **Make `tier` binding.** A guard keyed to tier *and side*, so a SAFE book
   cannot open an unbounded short. Reconcile
   `theoretical_max_loss: UNBOUNDED` with `max_loss = spot × 0.05` — a structure
   whose label and number disagree should refuse to size.
4. **Re-place the stop when a close fails.** `exits.manage` must not leave a
   position naked between a cancel and a failed close; the guard is one-sided and
   the naked window is a full cadence.
5. **Profile the 3% stop, and widen it past the forecast noise.** The file
   already says a stop inside the noise is a fee. A 0.52σ barrier on a 2-session
   thesis is not risk control.
6. **Declare `manage_only` on hack2** so the mandate matches the variable.

## 7. CLAIMS FOR FABLE TO ATTACK

| claim | receipt / evidence | what would kill it |
|---|---|---|
| The mega-11's edge is t 1.45, not t 2.82, in raw simple returns | re-measurement §2, receipt window 2024-03-21..2026-08-05, n=80 | a costed, hedged expression that keeps the measurement and the trade in one currency and still clears a family-corrected bar |
| The DOWN-big cell (PANW's) is negative unhedged | §2 row 5, n=19, −0.852% t −0.59 | n=19 is thin — a longer window, or a pooled test across mega-caps, that returns it to positive |
| The edge, if any, is in UP-big not DOWN | §2 row 3, +3.698% t 2.29 vs the docstring's claim | multiplicity: this is the best of four cells looked at, and the family correction is not computed |
| The 3% stop caused the −$475, not the thesis | 0.52σ barrier vs 5.75% 2-session sd; held-to-close mark −$210.68 | showing the 09-04 spike was information rather than noise |
| A SAFE tier cannot prevent an unbounded short | `tier` unread outside fleet.py; `equity.py:150` | a guard I failed to find |

## 8. WHAT COULD NOT BE DETERMINED

**Why hack2's stop was cancelled at 13:32:05Z on 09-04.** Two candidate paths —
`exits.manage`'s cancel-then-failed-close, or `protect.ensure`'s RECONCILE
cancel-and-replace where the re-place was refused — and they cannot be separated
from outside the volume. Railway log retention for `aat-loop-hack2` reaches back
only to 2026-09-04T15:32:53Z, and `railway ssh` fails with *"Host key
verification failed."*

**The artefact that settles it:** the `exit` row with
`_written_utc ≈ 2026-09-04T13:32:05Z` in `/app/state/decisions.jsonl` on the
`aat-loop-hack2` volume. Its `action` (`close_failed` vs absent) and
`refusal_reason` name the branch. Reachable by accepting the Railway host key
once, then
`railway ssh --service aat-loop-hack2 "grep PANW /app/state/decisions.jsonl"`.

This is the third time in two days that a question was unanswerable because the
fleet's decision rows exist only on the Railway volume while the laptop holds
dry-runs. That is not a logging problem, it is the missing half of the learning
loop, and it is B3.
