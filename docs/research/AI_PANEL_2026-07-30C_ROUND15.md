# AI panel round 15 — adjudication + updated roadmap (2026-07-30)

**Inputs:** five reviews (Consensus, DeepSeek, GPT, Gemini, Perplexity) answering
`PANEL_PROMPT_ROUND15.md` — the prompt built to break round 14's anchoring by
disclosing our own errors up front and demanding falsifiable predictions.
**Method:** every claimed error verified against the ledger before crediting.
**Nothing registered. Freeze holds. Cumulative candidates 162.**

---

## 0. Did the new prompt work?

Yes, and it produced one result the program could not have generated internally.

| | Round 14 | Round 15 |
|---|---|---|
| New un-registered ideas | 1 | 3 (all with resolvable DOIs) |
| Verified errors found in our documents | 1 (which we had told them) | **3 real defects + 1 scope error, all newly found** |
| Falsifiable numeric predictions | 0 | 5 |
| Fabricated citations | ~30 | **0** |

The anti-anchoring worked. Disclosing our own error made reviewers hunt rather
than agree, and the citation rule eliminated fabrication entirely — the reviewer
that fabricated ~30 sources in round 14 produced zero this round.

---

## 1. Claimed errors — verified one by one

### ✅ REAL defect 1: row #9 omitted its window (Gemini)
Gemini claimed the briefing's momentum row misapplied SPY's COVID drawdown
(−33.7%) to the 2004-2018 window, where SPY's maxDD is −55.2%.

**Their conclusion is wrong; the defect they pointed at is real.** TRIAL-MOM-
BACKTEST #13 ran on **2017-01→2026-06** on the 50,462-name delisting-aware panel
— *not* the CRSP explore window — so −33.7% is correct for its window and the
two SPY figures are not comparable. But **the briefing never stated the window**,
so a careful reader was led straight into the error. Fixed: the row now names
its window and explicitly warns the two SPY drawdowns are not comparable.

### ✅ REAL defect 2: unlabelled t-statistics (Gemini)
Gemini read gp-small's "IC t 4.29 → t 1.24" as an IC collapse and inferred the
gain was benchmark exposure. **The 1.24 is a *net* t, not an IC t** — IC actually
went 4.29 → 4.35, essentially unchanged. Reviewer error, caused by our unlabelled
column. Fixed: both t-statistics are now named.

The irony worth recording: **their substantive conclusion was right by accident.**
The trial doc already says +6.8 of the +9.4 headline is benchmark composition.
They reached the correct mechanism from a misread of the wrong number.

### ✅ REAL scope error 3: the LLM closure was over-broad (DeepSeek)
DeepSeek argued NEG_RESULTS §19 closes *LLM-as-trader* (timing/allocation) and
does not close *LLM-as-feature-extractor* (an LLM producing typed inputs a
deterministic engine consumes).

**Correct, and the house already relies on the distinction.** EVENT-INTEL has an
LLM classify enums only, with the deterministic engine computing everything —
that is feature extraction, it is live in production, and the standing rule
("the LLM narrates, the deterministic engine computes") permits it by
construction. §19's receipts do not reach it. Briefing corrected: a
feature-extraction proposal is admissible and needs its own control arm, not a
rebuttal of §19. **Second consecutive round DeepSeek has caught a scope
violation — that is a genuine specialty.**

### ⚠️ PARTIAL: candidate-count discrepancy (Gemini)
"162 in §1 vs 160 in §22" is a timing artifact, not an error — INSTR-SMALL-SHELF
*was* candidate 160 and RESID-MOM added 2 after it. Clarified in-place.

### ❌ REFUTED: "the cost-killed claim hides a small-cap decomposition" (Perplexity)
The decomposition exists and is published: §22's zero-cost-bound column shows
`rec_mom` clears both legs at literally zero cost (net t 2.64, IC t 3.32) and
dies at realistic cost. That *is* the cost-vs-information decomposition the
reviewer asked for.

---

## 2. The prediction experiment — and the finding it produced

Five reviewers, five falsifiable predictions. **Zero are runnable on current
data.** Full ledger with intervals and confidences:
`docs/research/PANEL_PREDICTION_LEDGER.md`.

| Reviewer | Signal | Data blocker |
|---|---|---|
| Consensus | earnings-call FinBERT tone | no transcript corpus; historical text PIT-barred |
| DeepSeek | OptionMetrics realized-minus-implied vol | `optionm` entitlement unverified |
| GPT | option-implied disagreement (skew dispersion) | same |
| Gemini | 5-day industry-neutral reversal | panel is monthly; needs `crsp.dsf` |
| Perplexity | 0DTE put/call skew, explore 2004-2018 | self-invalidating — it says in its own answer 0DTE didn't exist pre-2020 |

**This is the round's most important output, and it is not an idea.** Five
adversarial reviewers, given the full graveyard and asked to name one thing this
program could test, named five things it cannot. The idea shelf is not empty —
**the data shelf is.** The binding constraint has moved from hypothesis
generation to data acquisition, and that reorders the roadmap (§5).

Gemini's prediction earns partial directional credit now: it predicted a
negative-to-flat net t for reversal and named turnover as the cause; the banked
monthly `st_reversal` is net t −2.58/−2.61 at 0.67 turnover. Its IC call
(+4.5 to +6.8) is far above the monthly analogue (0.29–1.22), but the specs
differ on horizon, so it is recorded as *directionally corroborated, not scored*
until daily data lands.

---

## 3. New leads with resolvable citations — three, all from Consensus

The only reviewer that has never produced an unresolvable citation supplied
three post-2024 results the program did not have:

1. **Kirk (2025), "Abnormal Institutional Ownership and Expected Returns,"
   *J. Accounting, Auditing & Finance* 41:524-546, DOI 10.1177/0148558x251319189.**
   2.29M firm-months 1984-2022; **76 bps next-month high-minus-low spread** from
   *abnormal* institutional ownership — actual IO residualised on firm
   characteristics. **This is a different construction from `best_ideas`** (a
   top-3 manager count), so our batch-3b rejection does not reach it. This is the
   best new lead of the round. Adjudicated in §4.
2. **Voleti, Malladi & Sohoni (2025), *Management Science* 71:7929-7947, DOI
   10.1287/mnsc.2023.02221.** Operations-management content in earnings calls
   predicts abnormal returns 1-3 months out, from call text alone.
3. **Ying (2024), *J. Financial Economics*, DOI 10.1016/j.jfineco.2024.103852.**
   Gradual information diffusion across commonly-owned firms — a spillover class
   distinct from the industry/customer/analyst links we closed.

Also supplied and independently verified this session:
**SEC Reg NMS amendments adopted 2024-09-18** — half-penny ticks for the most
liquid NMS stocks and reduced access-fee caps, **compliance date the first
business day of November 2025**, i.e. already in force. Plus T+1 settlement
(2024-05-28) and the accelerated Schedule 13D/13G deadlines (effective
2024-02-05: initial 13D now 5 business days, amendments 2 business days).

**What that means for us, stated conservatively:** the historical KO cost model
describes 2004-2024, not the current regime; liquid-name costs are now *lower*
than the backtest assumed. This does not change a single conclusion — the
empty cost-killed cohort already established costs were never the executioner —
but it does mean **the forward lanes trade in a cheaper regime than the
graveyard was judged in**, and any future forward-vs-backtest comparison must
say so.

---

## 4. Our own adjudication of the best new lead — the receipt no reviewer had

Kirk's abnormal IO is *institutional ownership residualised on firm
characteristics*. **The program produced a directly analogous receipt yesterday.**

INSTR-RESID-MOM residualised momentum against a factor model. The decomposition
run showed the fitted (tilt) leg alone carried t(IC) 2.80 of total momentum's
2.84, while the residual carried 0.58: **the information WAS the loading, and
residualising removed it.**

That is a real prior against Kirk-style constructions — with an honest limit.
Momentum-residualisation strips *factor-return* exposure; IO-residualisation
strips *characteristic* correlation. Those are different operations, and the
receipt raises the prior against without closing the question. Kirk's own
reported effect is large (76 bps/mo), and CZ-CALIB says large published effects
decay hardest here (rank corr −0.544).

**Feasibility, checked:** `tr13f_ownership` gives `inst_shares` and `n_inst` by
cusip and quarter, 1980→present, on disk. But **`shrout` is absent from both
CRSP monthly files** (`crsp_msf`, `crsp_msf_ext` carry permno/date/ret/prc/vol/
exchcd/delisting only). Without shares outstanding there is no ownership
*fraction*, only a share count. Compustat `csho` is on disk and would work as a
stale annual denominator with a disclosed defect.

**Verdict: admissible, queued, NOT registered. Declared prior before any run:
weak-negative** — the residualisation receipt, the CZ-CALIB fame-decay, and the
fact that every 13F-family variant we have tested (best_ideas, breadth_chg,
inst_persist both directions, own_dur_t10) produced real IC and a dead net book.
It becomes a clean test after one WRDS column.

---

## 5. Updated roadmap — the reordering this round forces

Round 14 put the OptionMetrics entitlement test first. **That is now wrong.** The
prediction ledger shows the constraint is data breadth, and one WRDS session
unblocks far more than one entitlement check does.

### P0 — one attended WRDS session (Murat; needs a Duo tap)
The single highest-leverage hour available to this project. In one session pull:

| Item | Unblocks |
|---|---|
| `crsp.dsf` — daily returns, full universe | **THREE closed-at-monthly families** (PEAD §14, 8-K §20, FDA §16) plus the queued 13D/13G candidate, plus Gemini's R15-4 prediction becomes scoreable |
| `crsp.msf.shrout` — one column | A clean Kirk-style abnormal-IO test (§4) with no stale-denominator defect |
| `SELECT * FROM optionm.opprcd2015 LIMIT 10` | Settles the single-stock options branch — 578 catalogued tables, alive or dead, in one query |

All three in one Duo tap. Until this happens, **the research arm cannot test
anything any reviewer has proposed in two rounds.**

### P1 — the paper (unchanged, and now better armed)
"The Empty Shelf" gains three exhibits from this week: the small-cap shelf
extension (§22), the flow-vs-level finding (§24), and — new — **the panel
experiment itself.** Five adversarial frontier models, given a complete
graveyard and asked for one testable idea, produced zero testable on the
available data. That is a publishable statement about the state of retail-
accessible equity research, and no other paper has it.

### P2 — product levers that need no alpha (unchanged, still the largest ROI)
Risk-shaping, concentration control, cost discipline, behaviour. The mirror lane
at −20.1% vs SPY −1.1% over 52 days is the live argument for all four.

### P3 — queued candidates, in declared priority order
1. Kirk-style abnormal IO (after `shrout`) — prior weak-negative, §4
2. 13D/13G activist events (after `crsp.dsf`) — the only un-registered idea from round 14
3. Cohen-Polk-Silli **weight-tilt** 13F variant — distinct from the rejected count proxy
4. Earnings-call text (Voleti 2025) — blocked on a transcript corpus we do not have and cannot cheaply buy
5. Meta-labeling as a sizing layer — still untested, still weak prior

### What did NOT change
The freeze, the cumulative count, any lane, any config hash, any verdict.

---

## 6. Where the panel landed on the central question

P(the search is effectively over), five independent estimates:
**68%, 72%, 72%, 82%, 88% — median 72%, mean 76.4%.**

Every reviewer put it above 2:1 and none went above 90%. The residual
probability mass is concentrated in exactly one place, and all five agree on
where: **release-timed and option-implied information at daily-or-finer
resolution** — which is precisely what P0 unblocks and nothing else does.

The honest caveat, again: five models reading one document we wrote is a
correlated sample. But this round the anchoring was actively attacked, three of
them found real defects in our documents, and they still converged. That is
worth more than round 14's agreement.
