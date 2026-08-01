# AI panel round 16 — adjudication + roadmap v2 (2026-08-01)

**Inputs:** five responses (GPT, Gemini, DeepSeek, Perplexity, Consensus) to the
P0-harvest results + Murat's own strategy questions (bull-phase lag, hedge-fund
methods, holders/13F, leverage, options). **Method:** every recommendation
checked against the trial ledger before crediting; every claimed number treated
as unverified unless independently confirmable.

**Registered this round: TRIAL-ABIO-KIRK (candidates 164-166), module commit
`66add9e`, frozen before any run code.** Cumulative candidates **166**.
Nothing else registered. No lane touched. Freeze otherwise holds.

---

## 0. Murat's questions, answered from our own ledger first

### "We win when SPY drops but can't keep up in bull phases — fix it"

Measured before theorising (GPT's one genuinely right process call this round).
Upside/downside capture vs SPY, live lanes, 2026-06-09 → 07-31 (37 daily obs,
18 up / 19 down days — **descriptive, far too short for skill claims**):

| lane | total % | up-capture | down-capture | bull β | bear β |
|---|---|---|---|---|---|
| conservative-atr | +2.30 | 0.09 | **−0.16** | 0.15 | 0.02 |
| aggressive | +1.24 | −0.05 | −0.16 | 0.03 | −0.13 |
| balanced | +0.57 | −0.04 | −0.10 | 0.00 | −0.10 |
| conservative | +0.14 | −0.08 | −0.12 | 0.03 | −0.04 |
| tsmom-overlay | +0.10 | 0.01 | −0.05 | — | — |
| tsmom-6040-control | +0.11 | −0.10 | −0.25 | — | — |
| smallmid-quality | −2.80 | −0.88 | 0.13 | — | — |
| balanced-ew-control | −3.20 | −0.05 | 0.24 | −0.15 | 0.16 |
| conviction | −11.77 | 0.25 | **1.44** | −0.32 | 0.87 |
| mirror | −24.11 | **−0.98** | **1.58** | 1.07 | 1.05 |

(SPY over the window: up-days +15.1% cumulative, down-days −11.9%, total +1.3%.)

**Two different problems, and the panel's shared diagnosis fits neither:**

1. **The rules lanes don't lag because a trailing-vol filter misses V-recoveries**
   (Gemini/DeepSeek's theory). Their bull β is 0.00-0.15 — they are low-beta
   **by mandate** (40-60% bonds/gold/cash). They are doing exactly what their
   frozen configs say. Making them "keep up" means changing the mandate, which
   is an allocation-timing bet — and the wall has killed that family three
   times (JM, JM2, COND-VT; NEG_RESULTS §15/§18/§21).
2. **Mirror and conviction have the worst possible shape:** mirror captures
   −98% of up-days (it *loses* money when SPY rises) and 158% of down-days;
   conviction captures 25% up / 144% down. That is **concentration + expensive
   growth beta**, not timing. The fix is the P2 product lever that has been on
   the roadmap since round 10 — concentration caps, position limits, cost
   discipline — not a new signal.

### "How do hedge funds do it — should we copy holders/insiders/politicians?"

What the reviewers describe as hedge-fund method — many weak signals, risk
budgeting, exposure control, no single magic factor — **is what the program
already runs forward:** multi-factor composite (T8), insider IC (T9 + CMP
clock to 2027), congress IC (T11), revisions (T10), TSMOM-XA. Nothing new to
register there; the clocks need time, not ideas. "BlackRock/Vanguard hold it"
is the passive-indexing trap (Gemini is right); the testable version — *active
abnormal* accumulation — is exactly TRIAL-ABIO-KIRK, registered this round.

### "Leverage?"

No — and now with a measured reason, not a vibe. Leverage scales whatever
convexity you already have; mirror/conviction currently have **negative**
convexity, so leverage would amplify the worst property of the book.
Vol-managed leverage overlays (Perplexity's LRS, DeepSeek's regime rule) are
the **closed** family: §21's confirm window showed the overlay taking SPY's
entire 2020 drawdown to four decimal places while giving up 2.6pp CAGR.
Leverage becomes discussable only after something survives confirm + forward.

### "Options?"

All five reviewers, independently: **options as data first, options as trades
never (for now).** That is also our queue. Covered calls (DeepSeek's #2) are a
real income mechanism but the "2-5% monthly premium" figure is wrong by
roughly an order of magnitude for OTM calls on liquid large-caps (realistic:
0.5-2%/mo gross, before the capped-upside cost, which in a bull market is
exactly when it binds — it *worsens* bull-phase capture, the problem it was
proposed to fix). Parked as a possible future lane experiment, not a research
trial; it would need options paper-trading infra we don't have.

---

## 1. Recommendation adjudication — all five reviewers

| Recommendation | Reviewer(s) | Verdict |
|---|---|---|
| Option-implied signals as inputs, not option trading | ALL FIVE | ✅ **ADOPTED** — matches house queue #1; P0b pull script ready (`scripts/fetch_wrds_optionm.py`); constructs registered after data lands, as a pre-declared cohort |
| O/S option-to-stock volume ratio (Johnson-So 2012) | Gemini, Perplexity | ✅ queued into the option cohort (opprcd daily volume aggregates are in the P0b pull) |
| RIV-spread, moment score (Alexiou-Rompolis 2021), residual skew (Wu-Tian 2023), term slope (Kim 2020, Vasquez 2017) | Consensus, Perplexity | ✅ queued into the option cohort — with the §23 receipt carried as a declared prior against the *residual*-skew arm specifically |
| Kirk-style abnormal IO | Gemini, Consensus | ✅ **REGISTERED this round** (TRIAL-ABIO-KIRK, 164-166) |
| Daily event harness (PEAD/8-K/13D-13G), control-armed | Perplexity, Consensus, GPT | ✅ queued P2 — build assigned to the Opus session; each event family still needs its own registration (§20 is the receipt for skipping the control arm) |
| Regime-switching / HMM allocation rule | DeepSeek | ❌ **CLOSED FAMILY** — §15 (regime rotation), §18 (JM2), §21 (COND-VT). Their cited HMM papers have no held-out 2020-class fast crash; ours did, three times, and it killed the family each time |
| Vol-targeting / vol-managed leverage overlay (200-SMA + target vol) | Perplexity, DeepSeek | ❌ **CLOSED** (§21, incl. the unconditional arm) — the trend half is already live as the TSMOM-XA lane pair, day 5, first rebalance ~Aug 3. The forward test exists; adding a backtest registration would be re-testing a closed family |
| Congressional copycat (Tuberville etc.) | DeepSeek | ⚠️ already running forward (T11 congress-IC since 07-11). The quoted returns (+259%, +520% all-time) come from promotional trackers, are survivorship-selected on the best names ex post, and are **not credited as evidence**. No new registration — the forward clock is the honest test |
| Covered calls on conviction | DeepSeek | ⚠️ parked (see §0 — premium figure implausible, worsens the stated problem) |
| Information-propagation DAG / PIFI (which source leads which) | GPT | ⚠️ genuinely novel framing, admissible as an *instrument* — but it needs the option + daily-event layers first. Queued P4 behind the data it would consume. INSTR-ANOMALY-TIME (EAD timing upgrade) is the existing receipt that timing structure exists |
| "Measure capture ratios before changing anything" | GPT | ✅ **DONE this round** (§0 exhibit) |
| 13F restatement caveat (Cao et al. MS 2026) | Consensus | ✅ folded into TRIAL-ABIO-KIRK's disclosed limitations |
| Options as portfolio hedge (puts/collars) | GPT, Consensus | ⚠️ legitimate, out of scope until options data + an options-capable lane exist; revisit after the option cohort reads out |

## 2. Reviewer reliability — round 16 entries

- **Perplexity: fabrication relapse.** Cited `github.com/AegisFinance/aegis`
  again (the non-project repo from round 14) as a source for *our own* numbers.
  Also: its RIV-spread prediction interval is **numerically identical** to
  DeepSeek's R15-2 (net t 0.4-1.0, IC t 1.0-2.0, 65%) — which was published in
  our briefing. Recorded as an **echo of our own ledger**, not an independent
  prediction. Its unverifiable Pelosi/congress return figures are not credited.
- **DeepSeek:** recommendation #1 (regime switching) walked into a family its
  own round-15 review had access to as closed (§21 was in the briefing).
  First clear scope *miss* after two rounds of scope catches. The congress
  numbers (Tuberville +259%) are promotional-tracker artifacts, uncredited.
- **Gemini:** the "trailing-vol window misses V-bottoms" mechanism is real —
  it is literally §21's measured failure mode — but misapplied to lanes that
  are low-beta by mandate. Half credit: right mechanism, wrong patient. Its
  O/S proposal came with a spec question rather than a numeric prediction, so
  nothing scoreable was offered.
- **GPT:** best process discipline this round (measure capture first, options
  as data, A/B/C options triage). The PIFI/DAG idea is the round's only new
  framing. No falsifiable prediction offered.
- **Consensus:** again the only reviewer whose citations all resolve; queue
  ordering matches ours almost exactly; the 13F-restatement caveat and the
  Wu-Tian residual-skew lead are both genuinely useful. Still the benchmark.

## 3. Roadmap v2 (supersedes round-15 §5)

- **P0b — one attended WRDS session (Murat, one Duo tap):**
  `.venv\Scripts\python -m scripts.fetch_wrds_optionm` in the module, on HKU
  VPN. Lands: secid↔permno links, month-end vol surface 2002-2024 (30/91-day,
  25/50-delta), daily per-name option volume/OI aggregates. ~15-40 min,
  checkpointed, resume-safe.
- **P1 — TRIAL-ABIO-KIRK run** (registered, frozen `66add9e`): next Opus
  session, data already on disk.
- **P2 — daily event harness build** (crsp.dsf on disk): harness first, then
  a control-armed 13D/13G registration. Opus session.
- **P3 — option-implied cohort registration** (after P0b lands): one
  pre-declared cohort — ATM IV level / RIV-spread / 25Δ put-call skew /
  term slope / O/S / put-call volume ratio — registered together with per-arm
  candidates counted, mirroring INSTR-SMALL-SHELF, so the family cannot be
  garden-of-forking-paths'd one arm at a time.
- **P4 — product levers for the actual measured problem:** mirror/conviction
  concentration caps and drawdown-aware sizing (the §0 exhibit is the
  argument). These are lane-mandate changes → attended, Murat's call, via
  `seed-a-lane` discipline if new lanes.
- **Paper-1:** add the §0 capture exhibit to the forward-record section;
  wording per §25 (zero-cost-bound lead).
- **Unchanged:** freeze, lanes, hashes; TSMOM-XA first rebalance ~Aug 3;
  PDUFA scoring ~late Aug; quarterly panel refresh ~Oct.

## 4. What this round was worth

The panel converged with the house queue on the one big thing (options as
data), supplied two usable literature caveats (13F restatements, residual-skew
receipts), and one new framing worth keeping (information-propagation DAG).
Its unanimous *diagnosis* of the bull-phase problem was wrong in a way five
minutes with our own NAV data could show — which is the recurring lesson of
this panel series: **external reviewers are a literature instrument, not a
diagnosis instrument.** They have never seen the book; they pattern-match to
the median quant blog. The house measures first.
