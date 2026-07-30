# Panel prediction ledger — scoreable forecasts from external AI reviewers

Round 15 introduced a rule: every reviewer must commit to **one falsifiable
numeric prediction** before anything is run, with a stated confidence. Those
predictions are recorded here verbatim and scored when (if) the corresponding
run happens. This is the same treatment the program gives its own hypotheses —
pre-registration, then scoring — applied to the panel itself.

**Why this exists.** Rounds 13 and 14 showed that panel advice is easy to
produce and impossible to weight. A reviewer who is confidently wrong reads
exactly like one who is confidently right. Over enough rounds this ledger turns
reviewer credibility into a measurement instead of an impression.

**Scoring rule (frozen 2026-07-30).** A prediction is scored HIT if the realized
statistic falls inside the stated interval, MISS if outside, UNRUNNABLE if the
data required does not exist. UNRUNNABLE predictions are **not** counted against
the reviewer — but they are counted, separately, as a measure of how well the
reviewer understood what the program can actually execute.

---

## Round 15 (2026-07-30) — five predictions, **zero currently runnable**

| # | Reviewer | Signal predicted | Predicted net t | Predicted rank-IC t | Conf. | Data status |
|---|---|---|---|---|---|---|
| R15-1 | Consensus | Earnings-call FinBERT tone / OM-content, large-mid, event-timed, explore 2004-2018 | 1.0 – 2.1 | 2.2 – 3.3 | 58% | ❌ **UNRUNNABLE** — no earnings-call transcript corpus on disk; PIT-barred for historical text |
| R15-2 | DeepSeek | OptionMetrics realized-minus-implied vol spread, single-stock, large-mid, explore | 0.4 – 1.0 | 1.0 – 2.0 | 65% | ❌ **UNRUNNABLE** — `optionm` read entitlement unverified |
| R15-3 | GPT | Option-implied disagreement (skew / term-structure dispersion), traded through stocks | 0.8 – 1.5 | 1.5 – 2.4 | 42% | ❌ **UNRUNNABLE** — same blocker |
| R15-4 | Gemini | `rev_5d` — 5-day industry-neutral short-term reversal, T+1 entry, deciles | −1.20 – +0.40 | +4.50 – +6.80 | 85% | ❌ **UNRUNNABLE at the stated spec** — the factory panel is MONTHLY; a 5-day holding period needs `crsp.dsf`. See note below |
| R15-5 | Perplexity | 0DTE SPX put/call skew, 5-day hold, explore 2004-2018 | 1.2 – 1.8 | 1.5 – 2.5 | 65% | ❌ **UNRUNNABLE, and self-invalidating** — the reviewer states in its own answer that 0DTE volume was negligible before ~2020, i.e. the prediction is for a signal that does not exist in the window it names |

### The finding this table produced

**Five independent reviewers, each asked for one falsifiable prediction, produced
five predictions that this program cannot currently run.** Not because the
predictions are bad — R15-2, R15-3 and R15-4 are well-specified and would be
genuinely informative — but because every one of them requires data the program
does not hold: option surfaces, earnings-call transcripts, or daily returns.

That is the strongest available evidence for a conclusion the program had only
inferred: **the binding constraint is no longer hypothesis generation. It is data
acquisition.** Five adversarial reviewers, given the full graveyard and asked to
name something testable, could not name one thing testable on the current data
layer. The idea shelf is not empty; the *data* shelf is.

### Partial credit available now — R15-4

Gemini's prediction is the only one with a monthly-resolution cousin already
banked. The factory's `st_reversal` (monthly, not 5-day, not industry-neutral)
scored, explore 2004-2018 at flat 25 bps:

| | net t | rank-IC t | turnover 1-way |
|---|---|---|---|
| small | −2.58 | 1.22 | 0.667 |
| largemid | −2.61 | 0.29 | 0.674 |

The **direction** of Gemini's net-t call is right and confidently so (it predicted
a negative-to-flat net t and named turnover as the reason). Its **rank-IC call of
+4.50 to +6.80 is far above the monthly analogue's 0.29–1.22** — but the specs
differ on horizon and industry-neutralisation, so this is recorded as
*directionally corroborated, not scored*. It becomes scoreable the day
`crsp.dsf` lands.

---

## Reviewer reliability record (cumulative, rounds 13-15)

Not a score of usefulness — a score of **whether claims about this project turned
out to be true.**

| Reviewer | Verified correct claims | Verified false claims | Fabrications |
|---|---|---|---|
| GPT | Round 14: correctly noted the analog-engine null was scoped to a representation, not to analogs generally (the trial record agrees) | none recorded | none |
| Gemini | R14: residual-momentum estimation-noise objection — specific, testable, and **refuted by the run**, but the 60-month arm partly supported it. R15: correctly flagged 3 real documentation defects in the briefing | R14 round 2B: fabricated a base-rate table. R15: misread §9's window and misread an IC t as a net t (both caused by briefing defects, both wrong as stated) | one (round 2B) |
| DeepSeek | R14: correctly caught that the Dew-Becker & Giglio closure is scoped to *index* options. R15: correctly caught that the FINSABER closure is scoped to LLM-as-trader, not LLM-as-feature-extractor | R13: asserted the EDGAR parser was dead (it had been fixed and prod-verified twice); quoted insider alpha 2-5× the current literature | none |
| Consensus | R14: recommended Bowles et al. *Anomaly Time* — already implemented. R15: supplied three resolvable, genuinely new post-2024 citations (Kirk 2025, Voleti 2025, Ying 2024) | none recorded | none — the only reviewer that has never made an unresolvable citation |
| Perplexity | R15: no false claims about the project | R14: ~30 citations to a public GitHub repo that is not this project; a 7.7× internal self-contradiction on a headline statistic | **~30 (round 14)** |

**Reading:** Consensus is the most reliable on literature and has never
fabricated. Gemini produces the sharpest testable objections and the most
unforced errors — high variance, worth reading closely, never worth trusting
unverified. DeepSeek is best at scope violations, which is a genuinely useful
specialty. Perplexity's round-14 fabrication is disqualifying for factual claims
until it produces a clean round.
