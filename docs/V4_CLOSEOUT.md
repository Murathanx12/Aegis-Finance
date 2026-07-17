# V4 Closeout — 2026-07-17

V4 ("a quant desk for the average person", opened 2026-07-16) is **build-complete**.
This is the adversarial audit: what shipped, what's proven, what we still lack,
and the next session's marching orders.

## What V4 shipped

### 2026-07-16 (session 1)
| What | Commit | Live-verified |
|---|---|---|
| Screener NameError + numpy-serialization fix (2 days dead) | `f935df1`, `71c05ba` | ✅ |
| Railway cost levers (FinBERT unload, off-hours warm, MALLOC_ARENA_MAX, close-only MTM) | `f935df1` | ✅ close-mark ran 16:30–19:30 ET 07-16, all 7 lanes stamped; **RAM delta needs Murat's dashboard glance** |
| Wall Street View (targets, ratings, firm actions) | `f935df1` | ✅ |
| TRIAL-FORECAST-LEDGER pre-registered (#11), weekly collector wired | `51ebec3` | ✅ accruing, matures 2027-07-16 |
| Brain findings ledger → lab prompts | `3643a88` | ✅ |
| Collector honesty (GDELT stale-serve, Trends cooldown) + model-vs-firms card + next_runs | `39f6ed6` | ✅ |
| Alpaca paper mirror (third-party NAV) | `1803d95` | ⏳ BUILT + deployed, **unseeded — blocked on Murat's env keys** |
| EODHD phase-1 acceptance (16/20 PASS) | `39f6ed6` | ⏳ phase 2 blocked on Murat's subscription |

### 2026-07-17 (session 2 — this one)
| What | Commit | Live-verified |
|---|---|---|
| **P0 (unplanned):** Congress-IC collector died on FMP 402 (daily quota burned by fallback traffic before the 16:30 ET check) + the error log **leaked the FMP API key**. Fix: `APIKeys.redact()` choke-point, 402→explicit quota error, new 07:30 ET `pi_congress_collect` job (fresh quota; 16:30 stays as same-day retry; 5-day throttle dedups) | `9e49d72` | ✅ 4 jobs live incl. `pi_congress_collect`, zero new-code warnings; first morning collect fires 07:30 ET 07-17 |
| Chunk 1: quantstats lane tearsheets + BCa bootstrap CIs (`/api/pi/lane/{id}/stats-ci` + `/tearsheet`; "Sharpe X [95% CI lo, hi]" on the track-record page) | `afe62ec` | ✅ live: balanced Sharpe −0.51 [95% CI −6.80, +5.32] at 28 obs (honestly wide); tearsheet HTML + banner render |
| Chunk 2: casual/advanced switch (casual DEFAULT, legacy key migrated) + driver.js first-run tour (6 marks, never forced) | `32c8daf` | ✅ Vercel deployed; **tour still needs a human eyeball** |
| Chunk 3: screener preset chips (analyst upside ≥15%, dividend safety, momentum leaders — rules stated inline) | `4671268` | ✅ Vercel deployed (client-side filters; backend payload unchanged) |
| Chunk 4: FRED economic calendar card (Actual / trend-proxy forecast / Previous + stars; proxy disclosed as not-consensus) | `6c3782c` | ✅ live: real FRED prints, claims beat +2.8% vs trend, note present |
| Chunk 5: bull/bear two-sided card (LLM argues both sides of the COMPUTED signal; advice language rejected fail-closed; status=unavailable over fabrication) | `4ded5bb` | ✅ live: AAPL returned grounded BULL/BEAR prose, zero advice language, bear case correctly attacks the signal's own 52% confidence |
| Compare-round 2: 4 fact-checked research verdicts → F-016..F-020 | `bfbf1ca` | n/a |

Ten deploys yesterday, eight commits today, every one CI-gated. Tests: fast
suite 2905 passed + 21 failures that turned out to be LOCAL-ENV gaps (`ta`,
`lifelines`, `lppls` not installed on the dev machine — installed, all 21 now
pass; CI was green throughout), PI suite green, 24 new tests today, all offline.

### Compare-round 2 verdicts (details in `docs/KNOWLEDGE/findings.jsonl`)
- **F-017 robo onboarding** (Wealthfront/Betterment/SEC 2017-02): absorb
  conservative-component weighting, risk-vs-horizon contradiction flag,
  Betterment's exact P10/P50/P90 band sentences, probability-of-target + the
  three levers. Never the binary On-Track badge.
- **F-018 factor-lens tools**: PV and testfol.io both paywalled, both silent on
  survivorship — **the free PV-grade factor-lens niche is empty.** Absorb
  loadings-with-t-stats, factor-return contribution column. Publish T7 loudly.
- **F-019 uncertainty display** (Metaculus/CHI/Kitces): baseline reference lines
  on every chart, "too early" as a first-class display state, frequency framing,
  probability+severity, no 1%-precision. The researched playbook for our
  track-record page.
- **F-020 aggregation**: REJECTED (per-user server-side secrets ⇒ accounts+DB).
  CSV import via Ghostfolio's client-side pattern if ever wanted (~1 day).

## The forward record (day 39)

7 lanes, all fresh through 2026-07-16, zero touched today (lane YAMLs
byte-stable across all 8 commits, registry still 11 trials, no spurious
segments). Mirror +1.99%, aggressive +0.14%, conservative-atr −0.01%,
conservative −0.42%, EW-control −0.50%, balanced −0.63%, conviction −5.79%.
The conviction gap is the most interesting number on the board and it is
**noise at n=39 days** — no reads before the pre-registered windows.

## What we LACK (the adversarial part)

**Validation**
1. **Still zero trustworthy backtests.** Everything absolute-alpha remains
   forward-only until the survivorship-free panel lands (EODHD blocked on a
   $19.99 subscription — cheapest unblock in the whole program). TRIAL-NN-1
   stays gated; the NN/GKX question is unanswerable until then.
2. **The crash overlay is dark on every lane** (`model_not_deployed` since
   June) and the successor plan is HELD. We ship crash probabilities to the
   dashboard from the composite/conformal path while the lane overlay has no
   model. Defensible (F-006: honest dark beats skill-less numbers) but it is
   a hole in the product's central promise.
3. **New CIs are iid-bootstrap for Sharpe/Sortino.** Daily returns
   autocorrelate; BCa on iid resamples **understates** interval width. maxDD
   got the block bootstrap; Sharpe/Sortino should too eventually. The
   direction of the error is at least conservative-in-spirit (intervals are
   already huge at n=21) but it's not the final method.
4. **Tearsheets/CIs read the full NAV series across config segments.** No lane
   has segment boundaries yet, so it's correct today — but the first versioned
   rule change would silently blend two strategies into one Sharpe. Needs a
   segment-aware guard before any config v2 ships.
5. **The F-019 playbook is researched, not applied.** Our track-record page
   still shows raw NAV without baseline overlays; no calibration scaffolding,
   no frequency framing, probabilities still displayed at 1% precision in
   places. We now know better than we display.

**Product**
6. The first-run tour and casual-default flip are **untested by any human**.
   Casual default changes what existing visitors see (fewer nav items,
   simplified copy) — deliberate, but Murat should click through before
   publicizing.
7. The two-sided card adds an LLM call per uncached ticker view (150/day cap
   shared with news/brief). Heavy screener browsing could exhaust the cap by
   afternoon — the card degrades to absent (by design), but nobody is
   measuring how often.
8. The empty factor-lens niche (F-018) is identified and unbuilt. That's the
   single clearest product differentiator available and it's ~presentation
   work on data we already compute.

**Data**
9. **FMP's 250/day free quota is one shared scarce resource** consumed by an
   unbounded set of callers (fallback provider, comps, ESG, congress). The
   morning slot protects one consumer. Any new FMP caller can re-create the
   402 class silently. Needs a per-day budget ledger like the LLM spend guard.
10. GDELT 429s every ~25 min around the clock. Stale-serve keeps the product
    honest, but ~40 warnings/day of known noise buries real warnings in the
    50-slot health buffer (the Congress 402 nearly scrolled out). Demote
    successful-stale-serve retries to INFO, or rate-limit the warning itself.
11. yfinance "Invalid Crumb" 401 storms recur intermittently. The shared-fetch
    layer absorbs them, but they burn FMP fallback quota (see #9) — the two
    failure modes compound.
12. **Leaked keys:** the FMP key reached Railway logs (this incident); Alpaca +
    EODHD keys passed through chat on 07-16. All three need rotation — listed
    in Murat's checklist below.

**Trust**
13. The Alpaca third-party NAV attestation — the strongest trust artifact we
    designed — is built and dormant behind two env vars. Every day unseeded is
    a day the mirror lane's record stays self-attested.
14. `conviction` at −5.79% vs `mirror` +1.99% will be the first thing a
    skeptical visitor screenshots. Nothing on the page yet says "n=39 days,
    pre-registered decision 2027, this gap is noise" — the F-019 "too early"
    state would say exactly that.

## What needs to be done (ordered)

**Murat (5-minute checklist, unchanged + one addition):**
1. Railway → Variables: `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`,
   `EODHD_API_TOKEN`; one boot with `AEGIS_SEED_ALPACA_MIRROR=1`, verify, unset.
2. EODHD All World ($19.99/mo) when ready → phase 2 runs same day.
3. **Rotate the FMP key** (it's in Railway logs) and the Alpaca/EODHD keys
   (they passed through chat). Update Railway vars.
4. Glance at Railway Metrics → Memory (close-only MTM + levers should show
   the 4.2 GB plateau down).
5. Click through the new tour + casual mode once on the live site.

**Next build arc (V5 candidates, in leverage order):**
1. **EODHD phase 2 → loader → survivorship audit rerun → PIT delisted panel →
   draft TRIAL-NN-1 pre-registration** (do NOT run it) — unblocks the entire
   validation program.
2. **Apply F-019 to the track-record page**: SPY+control baselines on the NAV
   chart, "too early to read" framing with pre-registered decision dates on
   every trial surface, frequency phrasing, 5pp probability rounding.
3. **Factor-lens presentation** (F-018): loadings with t-stats/p-values/R²,
   rolling loadings, factor-return contribution column — on the existing
   FF5+MOM engine.
4. **FMP daily-budget ledger** (the LLM spend-guard pattern, applied to FMP)
   + GDELT warning demotion (#9, #10).
5. **Builder absorbs** (F-017): contradiction flag, band sentences,
   probability-of-target + three levers.
6. Segment-aware guard in `lane_return_series` (#4).

## Next-session kickoff prompt

```
/go

V4 is closed (docs/V4_CLOSEOUT.md is the audit). This session opens V5:
validation unlock + trust surfaces. Work in this order:

PHASE 0 — verify (30 min):
- aegis_verified_state: deploy should be at/past bfbf1ca; confirm the 07:30 ET
  pi_congress_collect actually COLLECTED on 2026-07-17+ (log line or PIT rows —
  a registered job is not a fired job), NAV all_fresh, no new warning classes.
- Live-verify the V4 surfaces that deployed after close-out:
  /api/pi/lane/balanced/stats-ci (CIs present, insufficient_history honest),
  /api/pi/lane/balanced/tearsheet (HTML + banner), /api/analytics/economic-calendar,
  /api/stock/AAPL/two-sided (ok or disclosed-unavailable). Cache-busted.
- Check my checklist state: Alpaca seed (registry annotation), EODHD token,
  FMP key rotated. If Alpaca seeded: verify orders + alpaca:equity PIT row,
  remind me to unset the flag. If EODHD set: run
  python -m engine.research.eodhd_acceptance --phase 2 (bar >=16/20).

PHASE 1 — compare & absorb FIRST: 3-5 NEW projects/firms. Do NOT redo:
Vibe-Trading, qlib, RD-Agent, FinGPT, ML4T, alphalens, OpenBB, gs-quant,
quantstats, skfolio, vectorbt, PyBroker, FinRL, TradingAgents, FinMem, FinCon,
Betterment, Wealthfront, Portfolio Visualizer, testfol.io, Metaculus,
Ghostfolio, SnapTrade, Plaid. Angles worth hunting: fintech onboarding tours
that actually convert (docs/analytics evidence), open-source Sharadar/EODHD
loaders worth borrowing, how quant shops present factor tearsheets publicly
(AQR/RA), retail options-education UX. Fact-check before citing; fold into
findings.jsonl + the roadmap in the same commit.

PHASE 2 — build, in order, each with tests + CI green + live verify:
1. If EODHD phase 2 passed: eodhd_loader (engine/research ONLY, offline
   validation only) + survivorship audit rerun + PIT delisted-inclusive panel
   schema + DRAFT TRIAL-NN-1 pre-registration for my review (do not run).
2. F-019 playbook on the track-record page: benchmark+control baselines,
   "too early" first-class state with pre-registered decision dates,
   frequency framing, 5pp rounding. The conviction -5.8% needs its honest
   n=39 caption.
3. Factor-lens presentation (F-018): t-stats/p-values/R2 + rolling loadings
   + factor-return contribution on the existing FF5+MOM output.
4. FMP daily-budget ledger (LLM spend-guard pattern) + demote GDELT
   stale-serve retry warnings to INFO.
5. Builder absorbs (F-017): contradiction flag + Betterment band sentences +
   probability-of-target with the three levers.

PHASE 3 — close-out (mandatory, 45 min): full fast+PI suites;
lane-integrity-check if anything touched the lane path; audit V5 work;
write docs/V5_CLOSEOUT.md (same adversarial pattern: what's next, what we
LACK across validation/product/data/trust, next kickoff prompt); update memory.

Discipline unchanged: six forward clocks is the CAP; pre-register before
anything accrues; no LLM near a trade path; EODHD offline-only; read
docs/KNOWLEDGE/findings.jsonl (now 20 findings) before proposing hypotheses;
every deploy CI-gated + live-verified on the changed surface.
```
