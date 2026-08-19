# HANDOFF — 2026-08-20 morning (overnight session, Murat asleep)

## THIRD WAVE — THE NIGHT'S ACTUAL HEADLINE (came after the second)

**OUT-OF-ERA-CONFIRM-1: the program's first out-of-era CONFIRMATION.**
The 1990–2012 era was pulled fresh (6,988 eligible names, 1,463
delistings — 3× the modern rate), the protocol frozen while the pull
was in flight, §64 audits written before verdicts. Result:
**streak_up5 CONFIRMED** — a stock up ≥5 straight days lags its
matched twin by −0.37%/21d (p≈0.0000, clears MDE and the 0.25% bar,
Holm m=4). Same sign as the generating era, LARGER out of era. The
other three cells: all same-signed as declared (4/4; P=1/16),
up7 misses its MDE by 0.03%. Second Holm-surviving effect of the
program; candidate negative rule STREAK-AVOID-RULE-1 (defer entries
after streaks) queued for registration. Receipts in `lane_factory/`.
Substrate bonus: the early era (1990–2012 universe + 33M daily rows +
1.4M finratio rows) is now permanent local infrastructure.

## SECOND WAVE (post-21:00 "mega test" order)

Three independent, pre-declared tests converged on ONE lesson:
**short-horizon winner-chasing is an ANTI-signal net of costs.**

1. **MEGA-SWEEP-1** (84 books, grammar frozen pre-run at m=84, 0
   errors): the ONLY BH-FDR survivor is NEGATIVE — concentrated
   rank-weighted 3-month-momentum books lost **−26%/yr vs the plain
   equal-weight baseline** (p 0.0005, maxDD −92%); the whole mom_63
   family fills the worst cells. Positive leans (value_bm + winner-
   exempt, +6–12%/yr) do NOT survive the charge — leads only. Receipt
   `lane_factory/mega_sweep_1_screen_2026-08-19.json`.
2. **Factor-momentum registered screens**: chasing LAST MONTH's factor
   winners = **−2.1/−2.6%/yr net, p≈0.001, survives BH-FDR** — the
   quantified case for the no-bandit rule. 12-month formation +1.2%/yr
   ns (consistent with the primary's NOT_ESTABLISHED).
3. **Streak registered screens**: every cell negative-leaning (up5
   −0.15%/21d p 0.066 at 78,762 events; up10, down7 ns) — no
   survivors, same direction as the primary's reversal lean.

4. **UNIVERSE-SURVIVAL-STRESS-1 (SCREEN)**: the tournament ordering did
   NOT fully survive the PIT universe (229,571 stock-months, 4,298
   names). Returns: ALL arms negative (ridge WORST at −0.047 — the
   linear model inherits the era's anti-momentum hardest). Vol:
   **LGBM 0.747 beats ridge 0.680** — a flip vs the 182-name result;
   breadth gives nonlinearity room on risk. Receipt
   `net_tournament/universe_survival_stress_2026-08-19.json`.

Candidate registrations queued (screen survivors ⇒ registrations,
never promotions): **FACTOR-REVERSAL-AVOID-1** (avoiding recently-hot
factors/stocks as a NEGATIVE rule), **VALUE-EXEMPT-BOOK-1** (the
value+winner-exempt lead, fresh formulation + mean-masked §64), and
**RISK-HEAD-AT-SCALE-1** (confirm LGBM>ridge on vol at universe scale —
feeds the G2 risk-sized lane's v2 model choice).

Final gate after everything: **5,090 passed / 0 failures.**

## NEW INFORMATION ACQUIRED overnight (first wave)

1. **FACTOR-MOMENTUM-1 RESOLVED: NOT_ESTABLISHED.** On the JKP set (153
   US long-short factors, 1926–2025, sha-pinned, free-with-citation),
   monthly reallocation toward trailing-12-1 winners earned
   **+0.94%/yr net** vs holding all factors — positive sign, below the
   1.71%/yr MDE at 73 twelve-month blocks. Costs (20bp effective
   one-way per factor notional) consumed ~2/3 of the published gross
   effect. STATIC_NONINFERIOR was NOT_ANSWERABLE_AT_N by pre-run
   declaration. Slow-turnover descendant declared PRE-peek in the
   results section.
2. **STREAK-EVIDENCE-1 RESOLVED: NOT_ESTABLISHED, reversal lean.**
   Murat's coin parable as a trial: after ≥7 consecutive up-closes,
   eligible names ran **−0.25% per 21d behind** momentum/vol-matched
   same-date controls (CI [−0.42%, +0.05%]) vs MDE 0.41% — the
   biased-coin (persistence) reading has the WRONG SIGN on this panel;
   the lean matches short-term reversal/lottery literature. 19,726
   matched events; drop accounting on the receipt (biggest bucket:
   11,283 streaks outside the PIT-eligible universe — small-cap
   streaks are a different, unasked question).
3. **LANE-FACTORY-SIM-1 engine is REAL**: daily books over the pulled
   CRSP panel, delistings charged (known-answer world: −95% delisting
   hits the book), costs, winner-exemption logic; 6 planted-world tests
   green. Engine lesson worth keeping: deferred trims are LUMPIER, not
   smaller — turnover can RISE under exemption in trending worlds.
4. **G2 sweep (SIMULATION, SCREEN)**: inverse-vol vs equal =
   **+5.2%/yr with maxDD −0.48 vs −0.64** (at the edge of monthly MDE);
   winner-exemption dilutes to noise at book level (±0.9%/yr) but
   improves vol/DD/costs in both weightings and fired 283 times. §60
   scope finding: monthly rebalance trims are far gentler than the
   convexity trial's surgical exits — transports weaken with dilution.
5. **G2 lane preregs DRAFTED** (`PREREG_LANES_G2_2026-09-08.md`):
   pair A (risk-sized) gets a READABLE primary (realized-vol diff,
   §59 clock); pair B (winner-hold) honestly declares its return
   question unanswerable at 2-lane n — primary is behavior receipts.
   **Murat signs in the 09-08 window.**

## Standing state

- Suite: full fast gate run at night's end (see last commit for count).
- Nights: N3 `ok` (585 records, third clean night). Clean-clock firing
  #1 TONIGHT 17:00 (schtask, empty-stdin fix live, `--require-rehearsal`
  baseline current at the post-provenance-fix rehearsal). Quiesce heavy
  local work by 16:15.
- Receipt provenance now captured at RUN START (N3's wrong-commit stamp
  fixed); `git_dirty` excludes self-written night outputs, disclosed.
- Pooling + arming decisions recorded pre-read
  (`DECISION_IIF1_POOLING_AND_ARMING_2026-08-19.md`).
- **FRIDAY 08-21: first 396 resolutions land** — mechanics only, read
  gate holds.

## Morning queue (machine)

1. **EXPECTATION-BACKFILL resume** — FMP quota reset at 08:00 HKT;
   small batches, quota shared with prod.
2. OptionMetrics surface pull (`wrds_training_pull optionm`), then iid,
   then 13F (functions written, resumable).
3. UNIVERSE-SURVIVAL-STRESS-1: rebuild NET features on the PIT panel.
4. Streak SCREEN grid (registered, unpeeked) + CRSP full-history
   descendant design.
5. Factor-momentum slow-turnover descendant prereg (declared pre-peek).
6. NAV stamp fix P-day-2026-08-19a ships attended AFTER tonight's
   firing (lane-integrity-check both sides).

## For Murat (two minutes)

- Read the two overnight verdicts above — both doors stay open, neither
  licenses a trade; the honest headline is "reallocation and streaks
  don't clear costs at detectable size on these panels."
- G2 preregs await your read/signature before 2026-09-08.
- WRDS access offer: current entitlements covered everything tonight;
  the wishlist if HKU can add: SEC filings text (wrdssec), CIQ Key
  Developments, insiders. None block the current queue.

## FOURTH WAVE (post-22:30 "dont wait" order)

- **FACTOR-CHASE-FOREIGN-1: CHASING_HARMFUL_CONFIRMED** — US parent
  barred; pooled jpn/gbr/deu/fra/can = −2.43%/yr net (p 0.0002),
  negative in ALL FIVE countries. Six markets agree: never reallocate
  toward last-month strategy winners. Third registered effect, second
  out-of-sample confirmation.
- **STREAK-AVOID-RULE-1 (SCREEN, m=4): no survivors — the rule barely
  BINDS at monthly cadence** (48–158 blocked buys per decade). The
  confirmed event-level reversal belongs to the ENTRY-TIMING layer
  (daily buy decisions), not monthly allocation. G3 lane transport
  killed cheaply; candidate redirected: STREAK-ENTRY-TIMING-1 (defer
  actual purchase execution after streaks — an execution-layer rule
  for whenever real execution exists).
- RISK-HEAD-AT-SCALE-1 (LGBM vs ridge vol ordering, 1994–2012,
  prereg frozen pre-computation) running at handoff-write time.
- **RISK-HEAD-AT-SCALE-1 RESOLVED: LGBM_WINS** — early-era walk-forward
  (226 dates): LGBM−ridge vol ΔIC +0.0315 (MDE 0.0042, bar 0.01).
  Ordering holds in BOTH eras ⇒ **G2 risk lane v2 model = LGBM**
  (drafted into the G2 prereg pre-signature). SCREEN gem: early-era
  RETURN ICs are POSITIVE for all arms (+0.012..+0.017) vs all-negative
  2017–24 — the price-only return signal is ERA-DEPENDENT; a
  regime-conditional return question is a NEW registration candidate
  (REGIME-CONDITIONAL-RETURN-1), not a revival.
- **FACTOR-MOMENTUM-SLOW-1 RESOLVED: NOT_ESTABLISHED** — annual
  re-formation cut turnover 10x yet pooled 6 markets = +0.38%/yr
  (p 0.48); all six positive but tiny. The family is CLOSED: fast
  chasing harmful (confirmed), slow tilting noise; no further variants
  without a new mechanism (declared).
- **VALUE-EXEMPT combined-evidence note (meta-analytic, both eras
  already seen):** inverse-variance combination of the two cell reads
  gives ~+4.2%/yr, p~0.14 — a persistent positive lean that still does
  not establish. The honest path remains the G2 lane pair + more
  simulated grammar around value+exemption, not a re-read.
- Overnight pulls in flight at handoff time: OptionMetrics 30d
  surfaces (per-year), TAQ intraday indicators, 13F holdings.
- Candidate design for the day session: REGIME-CONDITIONAL-RETURN-1
  (return ICs flipped sign between eras; conditioning must use
  OBSERVABLE trailing proxies only — design carefully, the ex-post
  regime label is the classic trap).
