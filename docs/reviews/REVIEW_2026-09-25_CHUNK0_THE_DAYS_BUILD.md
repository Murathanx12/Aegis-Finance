# REVIEW 2026-09-25, chunk 0: the day's build, reviewed as money

**Reviewer:** Opus (read-only, investor seat). **Loop:** `ROADMAP_2026-09-25_CHUNKS_AND_THE_REVIEW_LOOP.md` §1.
**Read:** CLAUDE.md, the roadmap, the evening handoff, the GPT review, BOOK v0/v1, the v2 draft, 81 cards + DIGEST,
`books.jsonl` (112 rows: 23 books + 89 controls), leaderboard, autopsy, reputation, revision-flow sweep,
`forecasts/day_2026-09-25.json`, RESEARCH_QUEUE (BANKED), `git log --stat -8`. I did not touch the sim or any data.

**Short version.** Today built the ability to grade decisions later. It did not move expected terminal wealth.
Three findings in today's receipts matter more than anything the handoff put in its headline:
1. **The investigator's reputation weight is volatility skill, not direction skill.** On `return_sign` h=5 its
   most bullish bin (stated p 0.664, n 107) went up **35.5%** of the time, with mean return **−1.42%**
   (`reputation_2026-09-25.json` → `calibration.h5`). Chunk 2 is about to feed this arm into `E[r]`.
2. **VRT is the largest position in both v1 and v2 (12%).** Our own engine has it at mom_63 −30%, vol_63 74%,
   net raises −4 of 5 firms, three target cuts on 07-30, and consensus upside of +2.4% (`thesis_cards/.../VRT.json`).
   RESEARCH_QUEUE Q-5 already recorded that VRT fails the triangulation.
3. **The grading layer marks foreign names in local currency, unadjusted for dividends, against URTH**
   (`global_prices.py:26`, "no FX leg"; leaderboard `wls_caveat`). URTH has no Taiwan or Korea in it, and
   `comp_asia_supply_chain` is about 75% Taiwan, Korea and Japan.

---

## 1. Did today move expected terminal wealth, or the ability to grade a decision?

| artefact | EV moved? | grading moved? | why (receipt) |
|---|---|---|---|
| `u_forecast` | no | **yes, but aimed at the wrong names** | 118 rows for $0.146 of a $2.00 cap (`day_2026-09-25.json`). The 60-name cap chose which names got a forecast. **20 of the 60 slots went to `revision_flow_v0_random_twin`'s control names** (ACAD, ARES, … WVE). The cap then cut MRK, ASML, VRTX, COGT, NVDA, MP, CCJ and the whole Asia book. MRK and ASML each sit in **15 of 23** books. The books we will grade have no name-level forecast under them. |
| `u_review` | no | **not yet** | No `review/` directory exists at the time of this review, so no label has been written or graded. The patience rule ("a >2σ day is WATCH") has never fired. Quoting the move in sigma is the right design. |
| 23 frozen books + controls | no (nothing trades; PC-PAPER is idle) | **yes, weakly** | Frozen before outcomes, hashed, with twins. That is real. But mean pairwise **weight overlap is 0.25**, and each personal/competition pair of the same strategy overlaps **0.37–0.80** (pharma pair 0.80). 112 distinct names, all drawn from one `evidence_pack.json`. The leaderboard will mostly rank sector tilts (§2.3). |
| thesis cards (81) | **not yet** | **no** | The best object made today ($3.07, 0 drift). But (a) **no card verdict is written as a forecast row**: `thesis_card.py` reads `predictions` and never writes one, so the 81 verdicts cannot be graded. That breaks the loop's first rule. (b) The cards did not govern the v2 book. v2 added AVGO, CLS and BE, **which have no card**, and left out 9 of the 20 "supports" cards (000660.KS, 6857.T, 8035.T, 010120.KS, 012450.KS, ENR.DE, LDO.MI, ARGX, LLY). (c) **Every non-US card has empty engine fields** (mom, vol, revisions), so their verdicts rest on the LLM alone. |
| reputation | no | **yes, with a defect** | The machinery is right: held out, shrunk, floored. Its evidence base is thin. **12,793 of 17,484 graded rows come from one day (08-12)**, and all of them from 08-11..08-27. `k_prior` is unidentified. The arm weight mixes `abs_move_exceeds` (a volatility question) with `return_sign` (a direction question). See §2.1. |
| revision-flow sweep | no | yes | This is the right procedure: by year, leave-one-year-out (LOO), worst cell. Result: +0.32%/hold vs SPY at k=20, **+0.04% at k=50**, LOO-worst **+0.02%** once 2020 is dropped. What is left is one lucky year plus a concentration effect. It is a sector book rather than an edge: `revision_flow_v0` is **13 of 20 software/internet names**, and its random twin is drawn from all 1,624 names, not matched on sector. |
| decision autopsy | no | **partly** | 225 rows, 6 days, 1-day horizon only, benchmark SPY, no cost. PROBE averaged −0.36% and REFUSED −0.54%. **The only informative number is the +0.18% gap between them.** Both levels are "small/mid shortlist vs cap-weighted SPY in a mega-cap week", which is a size effect, not a verdict. It does flag a category error worth fixing: META, NVDA, NFLX and LLY were marked `NEGATIVE_EV / EDGE_BELOW_BAR` **because the insider signal was absent**. No signal is not the same as negative EV. |

**Verdict:** RESULT IMPROVEMENT: NONE (the handoff says the same, honestly). GRADING IMPROVEMENT: real but mis-aimed.
The name cap, the currency handling and the missing card-to-row link each cost more grading power than
they save.

---

## 2. You are wrong: five places

### 2.1 Wiring the "calibrated investigator" into E[r] (chunk 2) before splitting its skill by observable
**What was decided.** The roadmap's chunk 2 puts `w_i·(calibrated investigator p→return)` into `E[r]`, with
weights from `forecast_reputation`. The investigator currently gets weight 0.42 (D_all) on a skill of +6.0%.
**Why that is wrong.** That skill is earned on `abs_move_exceeds`, where discrimination is clean: stated
0.58 → realised 0.48 at h=1, and it rises monotonically. On `return_sign` h=5 the realised up-rate is flat to
inverted across stated p (0.43→0.40, 0.50→0.42, 0.55→0.41, 0.59→0.39, **0.66→0.355**). The two highest bins
have the worst mean returns (−0.73%, −1.42%). This is a **volatility forecaster**, and chunk 2 would use it as
a direction signal.
**What I would do.** Report reputation per `(arm, observable)`. Send `abs_move_exceeds` skill to **sizing and
risk**: position size proportional to 1/forecast σ, and to the tournament (§5 idea A). Start the
`return_sign` component at w=0 until its held-out discrimination is above 0 on at least 6 date blocks.
**What would settle it.** Re-run `forecast_reputation` split by observable. If `return_sign` discrimination
is ≤ 0 with n ≥ 1,500, the investigator has no place in the return term.

### 2.2 The v2 book: VRT at 12%, three uncarded names from an unreceipted review, and 8 positions too small to matter
- **VRT 12% (the largest weight) goes against our own data.** mom_63 −30%, net raises −4 of 5 firms, three
  target cuts on 07-30 (RBC 418→337, Citi 414→358, KeyBanc 360→325), consensus upside +2.4%, vol 74%.
  RESEARCH_QUEUE Q-5 already recorded "VRT does not fire; EMEA organic −14.8%; inventory 2×". The book's
  thesis also cites a "$2.6B Utility Innovations deal", while the card's 8-K says **~$1.45B UIG**.
  VRT at 12% × 74% vol is the book's largest risk contribution, sitting on its weakest evidence.
- **AVGO, CLS and BE entered on a GPT review whose facts "carry no receipts of ours"** (its own provenance
  note). None of the three has a thesis card. Meanwhile 9 "supports" cards stayed out. That swaps human
  judgement for another model's judgement, which is not the human side the design intended.
- **The binary sleeve is too small to win and too big to ignore.** BBIO, PRAX, RGEN and IONQ at 1% each, plus
  LEU, CCJ and AGIO at 2%, make 10% of capital that cannot move a 126-day grade (a +50% move on 1% adds
  0.5%), plus a CRL tail. Our own receipt (CRL −33%/5d vs approval +2–8%) puts break-even approval
  probability at **p ≈ 0.87**. No book computed it.
- **DKNG at 3%** has a neutral card, a flat handle, 17 firms with −2 net, and v0 excluded it on evidence.
  It is there because Murat holds 150 shares. That is holding bias, and it contaminates the "human edits"
  attribution. **Grade Murat's actual holdings as their own book** (`murat_actual`) and keep the thematic
  book free of it.
**What I would do.** Cap VRT at 4% or drop it. Put the freed ~20% into the supports cards the book left out
(SK Hynix, Advantest, LS Electric), each with its card's falsifier. Hold binaries at ≥4% or not at all.
**What would settle it.** v2 against v2-minus-VRT at 21 and 63 sessions (a free twin: re-weight the frozen
book in the grader).

### 2.3 Freezing 23 books and 89 controls at once: this produces less learning than it appears to
It looks like 23 experiments. It is closer to 4: AI semis/power, pharma PDUFA, software revision flow, and
European defence. All 23 books read one `evidence_pack.json` through one model. MRK and ASML appear in
15/23, TSM in 14, GEV and VRTX in 13. `comp_small_cap_catalyst` holds MRK, ASML, TSM and VRTX (about 21%
in mega/large caps), so its name does not describe it. The **random_same_band** control draws from the whole
liquidity band (JPM, KO and BKNG stand in for pharma and semis). A software or semis rally will therefore
show up as "skill" in every book that tilts that way.
**What I would do.** Make the **name** the unit of learning: one forecast and one E[r] per name. Treat a book
as a weighting of graded names, and cut to about 5 books picked to be orthogonal on purpose. Make the
random control **sector-and-band matched**.
**What would settle it.** At 21 sessions, regress each book's daily net return on SMH, XBI, IGV and EUAD
(or ITA). If median R² > 0.85, the leaderboard is a factor ranking, and the other 18 books added no
information.

### 2.4 The ten competition books cannot win a tournament and measure the wrong index
Murat's objective is **+50%, grand prize** (roadmap chunk 5). The ten `comp_*` books hold **13–26 names at a
5.4–9.8% max**, with ≤2% cash. Their LLM strategy text says outright "spread so no single print decides the
book". Rough numbers: with 23 names, 5-week single-name σ around 10%, and pairwise ρ around 0.4, book σ is
about 7%, and tracking error vs a world index is perhaps 5%. **+50% relative is then a 7σ+ event.** To give
+50% a 1% chance you need about 21% tracking error over the window: 5–6 names at 15–20% (the challenge
allows 20%), low mutual correlation, and dated right-skewed events inside Oct 12–Nov 13. Tournament theory
agrees: winner-take-all rewards variance (Chevalier & Ellison 1997; Lichtendahl et al. 2013).
The grading is also wrong on three counts:
- **URTH is developed-market only.** WLS includes EM and small caps, and the Asia book is about 75% EM/Japan.
- **Local-currency returns with no FX leg** are compared with a USD benchmark.
- **Unadjusted closes.** 8035.T goes ex-dividend ¥384 on 09-29, 7011.T on 09-29, and 6857.T has its record
  date 09-30. That is inside the first grading week, so a dividend will print as a loss.

**What I would do.** Use **VT** (FTSE Global All Cap, including EM and small) as the proxy. Convert every
foreign bar to USD. Use total-return closes. Build the `grand_prize` books as described in §5A.
**What would settle it.** Grade URTH, VT and ACWI against each other for 5 weeks. If VT–URTH is more than 1%,
the proxy choice decides rank. Also record the FX component for each foreign book.

### 2.5 The forecast caps were in the wrong place, and the autopsy used the wrong benchmark
- `FORECAST_DAILY_CAP_USD=2.0` used 7% of itself. `FORECAST_MAX_NAMES_PER_DAY=60` was the cap that bound, and
  it was filled in file order, so random-twin names came before the books' core names. Forecasting all ~125
  names would cost about **$0.30/day**. Remove the name cap, keep the dollar cap, and order the universe by
  **Σ weight across frozen books**.
- The autopsy compares a small/mid shortlist with SPY at h=1. Its benchmark should be the **same-universe
  equal-weight** return (the rule backtest already computes `mean_vs_covered_ew`), reported beside SPY, with
  n counted in **date blocks** (6 today, not 225).
- The reputation **floor at 0** is correct, but the reason is wrong. The personas' discrimination is ≈0
  (−0.002 to −0.03; biotech −0.058 on n=82). Their −20% to −70% skill is calibration gap (0.14–0.31), not
  anti-signal, so inverting them would recover almost nothing. MEMORY's "negative discrimination =
  anti-signal" overstates it. The floor stays, and the note should be corrected.

---

## 3. Guardrails that cost money

| guard | blocked a bad decision this month? | what it blocks that is good | receipt |
|---|---|---|---|
| **`FORECAST_MAX_NAMES_PER_DAY = 60`** (`config`, `u_forecast`) | none: spend was $0.146 against a $2 cap | name-level forecasts for the 64 cut names, including the 15-book names MRK, ASML, VRTX, COGT and NVDA | `day_2026-09-25.json` → `universe.cut` |
| **Competition factory constraints `max_weight 0.1`, `min_names 8`**, plus a prompt that rewards "no single print decides" | none: no book has been graded | the only book shape that can reach +50%. The challenge allows 20% | `books.jsonl` comp_* constraints; max weights 5.4–9.8% |
| **Execution lease: only `u_plan`'s ranker may place PC-PAPER orders** | none: the ranker is refused, so nothing trades | measuring fills and slippage for the book shapes we will actually run in the challenge. $1M of paper sits idle while 23 books are graded on virtual fills | handoff scoreboard: "PC-PAPER $1,000,000, connected, idle" |

**Under-used guard: the CRL-asymmetry receipt.** It exists (CRL −13.7%/day, −33%/5d; approval +2–8%) and is
cited to justify sizing binaries small. Nobody applied its logical consequence, which is a
**break-even approval probability (~0.87)** that each PDUFA position must clear, using a per-drug prior
(priority review, AdCom vote, prior CRL). CAPR (AdCom 9-3 against, date already extended) fails that test on
its face, yet it sits in 5 books. Turn the receipt into a gate: *no binary without a stated P(approve) > the
break-even*. A second, cheaper gap: `wls_membership_checked: false` is on every competition book, and
nothing reads it.

---

## 4. The one thing to delete

**Stop generating the `competition` kind as currently prompted, and take the ten `comp_*` books off the
competition section of the leaderboard.** Their ledger rows stay (no mutation of frozen history); relabel them
`rehearsal_wrong_objective`. Three reasons:
- They answer "does a diversified LLM book beat URTH over 5 weeks?", which nobody asked.
- They overlap their personal twins by 0.37–0.80.
- Their grade will be read in October as evidence about the competition engine, and it is not.

The five `grand_prize` books in chunk 5 replace them. Until those exist, the competition leaderboard should be
empty rather than misleading.

---

## 5. Three new ideas (not on the roadmap) and three things to read

**A. Use the skill we actually have (volatility) for the objective that rewards it (the tournament).**
The investigator forecasts |move| with real discrimination (§2.1). A grand-prize book wants high
idiosyncratic variance with a right skew inside Oct 12–Nov 13. So: rank WLS-eligible names by the
investigator's `abs_move_exceeds` probability for in-window catalysts × the sign of the thesis card × low
correlation to the other picks, and hold the top 5–6 at 15–20%.
*Separation from factor beta:* grade realised |move| / implied move (from the chain we already read) for the
chosen names against beta-matched names. A factor tilt does not predict idiosyncratic |move| beyond
implied.
*Cost:* about $0.30/day in forecasts plus one options pull. Two builder-days.

**B. Split revision flow into LEAD raises and CHASE raises.**
`net_raises` counts target raises, and analysts raise targets after a stock goes up. That is probably why flow
"improves" the momentum arm only slightly. Classify each raise by the stock's return over the 10 sessions
before it: *chase* is a raise after more than +1σ, *lead* is a raise when the stock is flat or down. Test
whether only lead raises carry forward return. Da & Schaumburg (2011) found target information works
**within industry** even where the raw level fails, which matches our §17 finding.
*Separation from factor beta:* residualise on mom_21, mom_63 and industry. A lead raise is orthogonal to
prior return by construction.
*Cost:* $0, the 393,369 rows are on disk. Half a day.

**C. Catalyst run-up, exit before the event.**
The window Oct 12–Nov 13 is Q3 earnings season, and our own receipt says approvals "are largely priced in by
the pre-date run-up". Hold names from T−10 to T−1 before a dated print or PDUFA and **exit before the
event**. That collects the earnings-announcement premium (Frazzini & Lamont 2007; Barber et al. 2013) and the
PDUFA run-up without the CRL tail.
*Separation from factor beta:* compare the same names' returns in [T−10, T−1] with their own non-event
10-day windows, and with sector-matched names that have no event.
*Cost:* $0 historically. The catalyst YAML (31 primary-tagged rows) and 81 cards already hold the dates, and
earnings dates for the 2,993 names are in the bars history. One day.

**Read next (Sonnet):**
1. **Lichtendahl, Grushka-Cockayne & Pfeifer (2013), "The Wisdom of Competitive Crowds", *Operations Research*
   61(6).** Also **Chevalier & Ellison (1997), *JPE*.** Optimal play in winner-take-all contests is to
   exaggerate and add variance. This is the theory behind chunk 5's book shape. Ask Sonnet to turn it into a
   rule: the number of names and weights that maximise P(top 1%) given the entrant count.
2. **Barber, De George, Lehavy & Trueman (2013), "The earnings announcement premium around the globe",
   *JFE*.** Also **Frazzini & Lamont (2007).** Idea C, including the non-US evidence, which matters because
   half our cards are Asian and European.
3. **Da & Schaumburg (2011), "Relative valuation and analyst target price forecasts", *J. Financial
   Markets*.** Also **Brav & Lehavy (2003), *JF*.** Why target *level* can be perverse while *within-industry*
   target information and revision *events* carry return. These map directly onto §17 and Q-10.

---

## 6. My own book: $1M, six months, long only, from the 81 cards

Rules I hold myself to:
- Only "supports" cards.
- No binary PDUFAs, because none has a stated P above 0.87.
- No name our own revision or momentum data contradicts. That excludes VRT and MU: MU has 0 net of 8 firms
  and a Sep 30 print that is the event, and I take HBM through the share leader instead.
- Accept FX: 60% of the book is not in USD, **so the machine must add the FX leg before it grades me**.

Worst case (protocol item 4): 10 names, gross 100%, no stops (§62). The AI-capex/power sleeve (000660,
6857, GEV, ENR, 010120, NVT) is **62%**. A −35% sleeve drawdown (VRT has already done −30% in 63 sessions)
costs **−$220k**, and a full-book −35% costs −$350k.

| # | ticker | w | why | falsifier (from the card) |
|---|---|---:|---|---|
| 1 | 000660.KS SK Hynix | 14% | HBM share leader. Earnings react most sharply to the memory state change. Card: supports | 3Q26 on 10-27 shows HBM/DRAM ASP down QoQ, or operating profit < KRW 60.54T |
| 2 | GEV | 12% | Power is the binding constraint. Net raises +8 of 9 firms. Card: supports | reservations not converting to signed orders by the 10-28 print |
| 3 | 6857.T Advantest | 10% | Test capacity gates HBM/AI output. A picks-and-shovels play on #1 with different customers | FQ2 on 10-28: gross margin below Q1 and guidance not raised |
| 4 | HOOD | 10% | Net raises +13 of 15, mom_63 +17%. Event contracts are where the betting trend actually lives (AGA handle flat) | state/federal action forcing event contracts under gambling licensing |
| 5 | ARGX | 10% | Net raises +17 of 14 firms, a commercial compounder, with a dated 10-22 print. Not a binary | Q3 product-sales growth < 40% y/y on 10-22, or the EMPASSION MMN readout fails |
| 6 | ENR.DE Siemens Energy | 9% | Grid and turbines outside the US crowd. Guided 14–16% | FY26 on 11-11: comparable revenue growth < 14% or Gamesa back to a loss |
| 7 | 010120.KS LS Electric | 9% | Korean grid equipment. The GEV thesis at a different price and with different buyers | Q3 on 10-28: order intake below the KRW 6.0tn run-rate or operating margin < 11.3% |
| 8 | 012450.KS Hanwha Aerospace | 9% | Defence exports at 35–39% margins. Low correlation to the AI sleeve | Q3 ground-systems operating margin < 10%, or the Poland K9 EC3 award slips past 12-31 |
| 9 | LDO.MI Leonardo | 9% | European defence with a dated 11-05 print. Pairs with #8 across regions | 9M on 11-05: free operating cash flow still negative and no FY guidance raise |
| 10 | NVT | 8% | Electrical content per data-center MW. Net raises +6 of 5 | Maverick fails to close by 11-20 (or extends to Feb 2027) |

**Not held, on purpose:**
- VRT: our own data (§2.2).
- MU: 0 net raises, and the Sep 30 print is a coin flip.
- TSM and LLY: mega-cap sensors. I read them rather than own them.
- Every PDUFA binary: break-even p ≈ 0.87, and none was stated.
- DKNG and QUBT: the cards are neutral and against/high.

**Freeze this as `reviewer_opus_2026-09-25` with the same four twins**, so the loop grades its reviewer too.
If this book loses to its own `sector_etf` twin (SMH/GRID/ITA) at 126 sessions, the reviewer's stock picking
added nothing, and the next reviewer should be told so in its first line.
