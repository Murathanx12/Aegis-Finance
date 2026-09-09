# REVIEW 2026-09-09 — Fable 5.1 on the night of 09-08/09: what the backtests got wrong, and how the method changes

**For Murat, then the Opus day-run builder.** Receipts: `backend/data/optimus/night_factory_2026-09-08/`;
the night's own write-up is `ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md` §§8-9;
the mandate this answers is §10 of the same file.

## 0. Scoreboard

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE on any book.** The night produced one live candidate (N1 `H5|all`, an event-level learner, +32%/yr t 2.9 after its control) that is not a claim and not a book yet, and it closed three things that looked like results: the reaction long leg, the bottom-decile exit rule, and G1's 548× development-window search (9.7× vs 4.9× on the sealed window at β 1.13, drawdown past its own budget). |
| LLM spend | $0.00 paid. Local Qwen wrote 4,669 anonymised counterfactual documents (DeepSeek-equivalent $2.18). |
| Paper accounts | hack3 8, hack6 12, hack5 1 positions at 02:06Z on 09-09; hack1 (human), hack2 (evidence gate), hack4 (zero-name seal) empty. Murat's "no movement" is right for those three; the other three moved. |
| New this morning | RW1, randomised-window backtests (§3). Protocol changes (§2). Six-book plan, the app, the day run (roadmap §10). |

## 1. What was wrong with the backtests (six defects, in order of consequence)

1. **Cells were graded against zero while their own control was on the page.** D1
   printed its placebo (same names, same book, same costs, dates shifted +40
   sessions) at −14.9%/yr and used it only as a veto. Read against that control, the
   long leg was the best cell (+10.7 pp) and the bottom decile's t −4.7 was mostly
   the construction (−4.0%/yr, t −0.79 after the control). My 09-08 evening
   conclusions were inverted by the same night's D3. A matched control is a
   baseline to subtract, never a flag to check.
2. **Era robustness was a sign count.** "Same sign in every era" stamped
   PRODUCT_PROMISING on a cell going 28.7 → 17.3 → 2.1 %/yr. D4 replaced it with a
   decay regression (21.19%/yr, t 2.74). The reaction long-short is real, Holm-clean,
   placebo-flat, and **dead in 2016-2024 above the $10m/day floor** (12/12 positive
   late-window corners at floor $0 → 0/12 at $10m). The surviving effect is
   microstructure below the tradability floor.
3. **A gate that could not go green.** G2's first read refused all 235 evaluations
   on a hard-coded `months < 150` floor written for the 202-month development window
   (the sealed window is 107 months) and still wrote `READ_ONCE: true`. Nothing
   leaked; the second run is the genuine read. Floors now travel with the window.
4. **One development window, one holdout.** G1 optimised 40,680 genomes against a
   single 1999-2015 number and the "best" was 548× on that window. That is the exam,
   learned. The sealed read: 9.69× vs the market's 4.86×, β 1.13, drawdown −42%
   against a declared 35% budget, β-matched t median 0.86 (t > 2 in 1 of 35). The
   fitness never enforced its own drawdown budget; it only penalised it.
5. **Archive rows counted as independent.** "35/35 above the random p95" were 30
   unique genomes sharing ancestry. Sign counts over relatives are not evidence.
6. **Costs as one number; borrow as none.** Every book ran at 25 bps a side; every
   short leg ran at zero borrow. D4's cost curve showed the long leg's economics
   turn on the floor and the rate; H5's +44%/yr rides a 5-session short leg with no
   borrow line at all.

Two smaller ones: R4's event deciles were formed within the calendar month (a
rank look-ahead; the PIT rank halves the spread), and N1's cache key did not name
the tape (a smoke run would have made the night skip its grid).

## 2. What changes in the method (adopted in roadmap §10.2)

- **Random windows are the product ruler's instrument.** Not one split: hundreds of
  seeded windows of 6-72 months anywhere in the tape, each graded β-first, and a
  strategy is judged by its β-matched win rate as an EXCESS over random genomes on
  the same windows, per start era and per length. The question "when does it beat
  the S&P and what was it holding" is answered by a table, not by a terminal wealth.
- **Every event cell carries `vs_control`;** the runner refuses a product stamp without it.
- **Era decay is a regression, not a sign count.**
- **Drawdown budgets are hard refusals in any search fitness.**
- **Archives de-duplicate by ancestry before any count.**
- **Costs are a curve (5/10/25 bps × liquidity floors) and shorts carry borrow.**
- **The fleet is graded as regret monthly** against the other five books and SPY.
- **The holdout is read once by a named job whose floors derive from the window.**

## 3. RW1 — the randomised windows (run this morning)

`RW1_random_windows_run01.json`, per-window table `RW1_windows.parquet`. 240 seeded
windows (6 to 72 months, 39/35/34/36/28/31/37 by length) anywhere in 1999-2024;
six strategies × two constructions × a five-genome random null on the SAME
windows; 5,280 gradings in 8.3 minutes, none refused. A "win" is a positive
β-matched excess over the VW market on that window at 25 bps a side; the number
that matters is the win rate MINUS the null's win rate on the same windows.

**The null itself wins 28-33% of windows β-matched** (the constructions drag),
and every strategy's excess over it lives in **one era**:

| strategy \| construction | median β | excess win over null: 1999-07 / 2008-15 / 2016-24 | win rate 2016-24 (null 0.35 arena, 0.29 broad) |
|---|---|---|---|
| G1 genome (already holdout-read) \| arena k50 vw | 1.24 | **+0.53** / +0.02 / +0.04 | 0.39 |
| G1 genome \| broad k100 ew hold400 floor $3m | 1.32 | +0.31 / +0.08 / **+0.19** | 0.49 |
| ensemble (mom + rev + upside) \| arena | 1.40 | +0.45 / +0.02 / −0.05 | 0.30 |
| ensemble \| broad | 1.40 | +0.07 / −0.01 / **+0.19** | 0.49 |
| revisions 4w \| broad | 1.10 | +0.37 / −0.04 / −0.09 | 0.20 |
| revisions 4w \| arena | 0.87 | +0.29 / +0.07 / −0.15 | 0.20 |
| human-heuristic proxy \| arena | 1.20 | +0.17 / +0.16 / **−0.22** | 0.13 |
| momentum 12-1 \| arena | 1.51 | −0.00 / +0.07 / +0.03 | 0.37 |
| target upside \| either | 1.87-1.95 | ≤ +0.01 / ≤ +0.02 / −0.16 to −0.19 | 0.13-0.16 |

Reading:

1. **"When it beats the S&P" is 1999-2007.** Every selector's edge over random
   genomes on the same windows is +0.3 to +0.5 in windows starting 1999-2007 and
   within ±0.08 of zero after 2008, except two broad-construction cells at +0.19 in
   2016-2024 — both the same object (the momentum + revisions + upside blend held in
   a wide band), winning 49% of late windows against the null's 29%, at β 1.3-1.4.
   That is the one live, if modest, product-ruler signal in the table, and it is a
   *construction* result again: the same blend through the top-50 VW arena book is
   −0.05 in the same era.
2. **"What it was focusing on" does not separate wins from losses.** The books hold
   the same thing when they win and when they lose: 35-42% Manufacturing, 17-20%
   Services, 80-90% small caps, one sector above 40% of the book in about half the
   windows. The wins are the era, not the holdings — which is exactly the "picks up
   all the noise from 2000" concern, now measured: a straight 1999-2024 backtest of
   any of these is dominated by windows that start before 2008.
3. **Length helps only through the era.** Win rates rise from ~0.41 at 6 months to
   ~0.65 at 48-60 months for the best cells, because long windows drawn at random
   are more likely to overlap 1999-2007.
4. **Down-market windows flatter every book** (0.84-0.89 win rates on the 38 windows
   where the market fell): a β estimated on a short falling window is unstable and
   the β-matched line credits small-cap EW books in rebounds. Down-window wins are
   discounted in the protocol (§2) by requiring the excess in *every* start era.
5. **The human-heuristic proxy** (upside × consensus revision − disagreement + a
   drawdown tilt, the shape of `murat_rule`) is the only cell positive in 2008-2015
   (+0.16) and it is the worst in 2016-2024 (−0.22). Murat's heuristic had a decade,
   and the decade ended around 2016.

What RW1 does not say: nothing here is a holdout, the G1 genome was read on the
sealed window yesterday, and 240 windows overlap heavily (a 72-month window shares
months with dozens of others), so the era columns are the honest unit, not the
window counts. RW2 (the day run) applies the same windows to the event-clock books.


## 4. What the night's one candidate needs before anyone calls it anything

`N1 H5|all`: event-level learner, 5-session hold, long-short +44.5%/yr t 4.3,
placebo-trained control t −0.45, learner-minus-control +32.2%/yr t 2.9, holdout
+28.3%/yr t 1.4, no era decay, control fires in 0/13 seeds. Found after the
pre-specified primary (H21) failed; 39 of 156 configs clear t 2 uncorrected;
drawdown −78% at 46% vol; no borrow cost. It goes to `pre-register-trial` with a
borrow line, a drawdown budget it can meet, the RW2 random-window read, and a
capacity number at the $10m floor. Not a seal.

## 5. Where the methodology goes overall (Murat's "see what we did, our approach was, how it needs to change")

What we did for five months: measure one forecast on one long window, apply the
claim ruler, conclude "noise", move on. What the last two nights showed: the
construction, the control and the window carried more of every number than the
signal did. So the approach changes from *"does this factor clear Holm on
1999-2024?"* to *"on which windows, holding what, against which control, at which
cost, does this book beat a β-matched market — and does the same object win on
windows it has never seen?"* The night factory is now that instrument: jobs are
cheap (D1 ran in 41 s; 5,280 window gradings in ~7 minutes), every job writes a
typed row, and the LLM is local and free, so the loop can run every night and
learn from its own leaderboard. The desktop app (roadmap §10.7) is the button on
top of it.
