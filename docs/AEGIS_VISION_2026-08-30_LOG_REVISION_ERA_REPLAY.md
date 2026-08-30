# VISION LOG REVISION — 2026-08-30 — TWO LLMs, THE NEWS FUNNEL, AND THE ERA REPLAY

**TIER 0 addendum** to `AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`.
Murat said this on Sunday 30 Aug, spoken, after reading Opus's session-4 report.
§1 is his intent, cleaned only for transcription. §2 is the validation he asked
for ("see if it is possible"). §3 is the improved version. Plain language on
purpose — he asked for that too.

---

## 1. What Murat said (his words, lightly cleaned)

**Two independent LLMs.** One prepares the backtest. The other implements it.
They do not talk to each other. Then we look at the results.

**The paper accounts.** On the new accounts the LLM's job is to digest the news.
All of the news comes through a funnel and passes through filters. It picks:
today's winners · next month's winners · the upcoming dates · what we should be
worried about · what we should do. It should focus on those subjects and decide
the way a human decides — keep up, hold it in memory. It turns emotions, news
and numbers into numerical data for the engine, and the engine is what
maximises profit and loss.

**The complaint.** We should be working on how to maximise profits. I understand
we need to falsify claims and make the engine safe, but we are not making any
money. All six paper accounts are losing. The engine is not a decision-making
engine. That has to be fixed before Monday's open — there are more than 24
hours left.

**The novel part is the backtest.** Take one large company, say Micron. The LLM
gets all the earnings and all the news and summarises it while trying its best
to leave out anything that identifies the company: "when the quarter came, this
happened; this company works in the semiconductor industry; here is the trend
of that industry; the news about this company shows this; analyst consensus is
very high; this is what it does differently and why it matters." We don't name
the competitors either. It can also be a small company — an offshore driller
with public backlash, regulation, a bank cutting its funding, unpaid bills, a
war. The engine and the LLM can both fetch everything that is available, and
the LLM makes decisions — not daily: "this is what we think for six months, for
a week, for a month." We set the decision times and how it may edit the
portfolio based on performance. Run many backtests and see **which time
interval is best, independent of the situation** — one run over last year, one
over 2010, one over 2016 — so the trend switches from AI to electric cars to
something else.

**Like giving a kid an exam.** "Company one, company two, the overall news" —
then the narrow past news: "this company did this, this, this." That is how we
test how our system would have worked in the past, not just the next six
months. It is a bulk revision of the material into testable material; if the
local model can do it we avoid API cost, if not, use an API — I don't mind.

**Keys we have:** NVIDIA, DeepSeek, OpenAI, Featherless — good credits on all.

---

## 2. Is it possible? — YES, with three things that must be true

**2a. The two-LLM split is possible today and cheap.** LLM-A (the *designer*)
writes the test as a file: universe rule, dates, decision cadence, what the
decider may see, the null, the cost rate, the objective. LLM-B (the *decider*)
only ever sees the anonymised bundle and returns numbers. Neither sees a price
or an outcome. Code — not an LLM — joins the numbers to prices and grades. This
is exactly the "compiler from text to features" contract Opus wrote in
`REPLY_TO_FABLE_2026-08-30_OPUS.md` §1, extended from single items to a
portfolio over time. Nothing new has to be invented; `scripts/blind_tournament.py`
already has the blinding, the canary and the seal.

**2b. The data exists for three eras, not for every year.**

| era | company news | filings | prices | note |
|---|---|---|---|---|
| 2025-06 → today | our corpus (80k rows, 91% headline-only) | EDGAR | Alpaca | what T1/T12 use |
| 2015 → 2025 | **Alpaca news API (Benzinga) goes back to 2015** — not yet pulled | EDGAR | Alpaca / CRSP to 2024 | the "2016 era" |
| 2001 → 2015 | none from us; **8-K exhibit 99.1 press releases + 10-K/10-Q text from EDGAR** | EDGAR | CRSP (farm, 1993-2024) | the "2010 era" — company voice only, no press |

So "2010, 2016, last year" is three different data shapes. Report each era
separately; never pool them.

**2c. The exam can be cheated, and we must measure how much.** An LLM shown
"the AI boom, a data-centre memory shortage, a war with Iran" knows the year
without the name, and knows what happened next. That is memorisation, not
reading. T1 measured it by asking the model to identify the company (0/120 —
the blind held). The era replay needs the same canary **for the year**: ask
the decider "what year is this and which company?"; report the identification
rate beside the P&L. If it names the year, the era is not blind and the result
is reported as **NOT BLIND**, not as edge. The pre-2023 eras are where every
model knows the ending, so this is exactly where the check matters most.

**2d. The local model is not worth it.** The bulk step is 80k items →
anonymised summaries. gpt-5-nano with `reasoning_effort="minimal"` measured
$0.03 per 1,000 items (Opus, 30 Aug), so the whole corpus is ~$2.40 and runs in
under two hours on 24 workers. The 8 GB laptop GPU runs a 7-9B model at a few
items a minute and blocks the machine. Name-stripping itself is regex + the
alias table and costs $0. Keep the local model off.

---

## 3. The improved version (what Opus builds)

The idea is right. Four changes make it survive our own reviewers.

**3a. Anonymise the WHOLE bundle once, then re-use it.** Encode every item to a
fixed record — `{era_month, sector, size_bucket, event_type, is_new_fact,
subject, expectation_gap, tone, summary_without_names}` — with the ticker kept
in a *sealed side table* that only the grader may read. The decider gets
"Company 7"; the grader joins Company 7 → MU. One encoding feeds T12 (relevance
counts), T13 (era replay) and the live funnel. Never re-encode per test.

**3b. The decider is a portfolio manager with a diary, not an oracle.** At
each decision date it receives: the bundle for the window, its own previous
diary entry, and its previous weights. It returns weights (sum ≤ 1, long-only
first), a horizon, and a one-line reason per name. The diary is Murat's "keep
it in the mind, the memory" — and it is a variable: run with and without the
diary. If the diary helps, memory carries information; if it hurts, the model
is anchoring on its own old story (disposition effect in silicon — a T11 bias
cell we can measure on the LLM itself).

**3c. Cadence is the experiment; cost is the referee.** Decision cadence ∈
{1w, 1m, 3m, 6m}, crossed with era ∈ {2025-26, 2016-19, 2010-13}. Every
rebalance pays the cost rate the farm already refuses to omit. The reported
number is **terminal wealth vs the same-era equal-weight basket of the same
anonymised names** (the "better than what?"), not raw return. A cadence that
wins in all three eras is a finding; one that wins in one era is a regime.

**3d. Three nulls, built in:**
1. **Shuffled companies** — same decisions, the bundles re-assigned to the
   wrong names. Kills "the model just likes the era."
2. **Shuffled dates within the era** — the calendar null.
3. **Same-day paired** — each chosen name vs a non-chosen name in the same
   bundle on the same day (the T3 lesson: 60% of the shock was the day).

**3e. What this buys on the live books.** The same encoder runs on today's
news before the open, so the funnel output ("today's winners / next month's /
dates / worries") is *the same records* the backtest was graded on. That is
the missing bridge between "the LLM read the news" and "the engine had a
number it was allowed to act on."

---

## 4. Why the books are not deciding (the Monday part)

The sealed pre-open book derives `CLAIMING` from the confidence intervals of
the features panel. The panel's features have IC ≈ 0 on 152 names, so the book
will **never claim** — by construction. That is a measurement system, not a
decision system, and Murat's complaint is exactly right.

The fix is not to loosen a guard. It is to add a **second generator** that is
allowed to claim under `PRODUCT_EXPERIMENT`: a declared human heuristic
(Murat's rule — target/price ≥ 1.5, rating ≥ 4.1 where readable, a dated
catalyst inside the horizon, already down from the 60-day high), which claims
`direction = up` with a stated size, and is graded like every other claim.
Intuition generates, data adjudicates — but only if the intuition is allowed to
speak. Details and the sizing arithmetic are in the terminal brief
`docs/NEXT_SESSION_2026-08-30b_OPUS.md`.

---

## 5. REVISION 2 (Murat, 30 Aug, after reading §2c) — THE FANTASY TRANSPOSITION

**Murat:** *Let's change everything then. Rather than hiding the year and the
industry, create a new futuristic situation and wait for the model to find the
connections. The year is made up (2050, or 1980), the company works in a
made-up industry that matters to that time, the news is a made-up scenario
that carries the same narrative. See if the LLM can turn that kind of context
into usable data for the engine. Too many guardrails — the engine just says
"I don't know, and this is why." It should say "I am X confident this might
happen, with this risk and this profit," and choose the best of its choices.*

### 5a. Why this is better than the year-canary

The canary only DETECTS memorisation. Transposition REMOVES the thing being
memorised: there is no 2016 to remember if the story is set in 2050 in the
orbital-cooling industry. What survives the rewrite is the *shape* of the
situation — a demand shock, a supply constraint, a bank pulling funding, a
regulator, a war, consensus that is very high, a company that does one thing
differently. If the decider can turn that shape into a good number, it is
reading, not remembering. That is the cleanest test of Murat's claim that
exists.

### 5b. How it must be built (three rules, or it leaks)

1. **The rewriter is point-in-time too.** LLM-A rewrites each window seeing
   ONLY that window's items — never a later item, never a price. Otherwise the
   rewriter, which knows how Micron ended, writes the ending into the tone.
2. **One mapping per era, frozen and sealed.** Semiconductors → "orbital
   cooling", Micron → "Company 7", 2016 → "2051", JPMorgan → "the Meridian
   bank", Iran → "the Strait conflict". The map is a file, hashed, and only the
   grader may open it. The same real entity always gets the same fantasy name
   inside an era, so the decider can follow a company across windows.
3. **Magnitudes are preserved, names are not.** "+40% consensus upside",
   "revenue −18%", "third guidance cut in a year", "rating 4.6/5" go through
   untouched. The numbers are the information; the nouns are the leak.

Two controls run beside it, always:
- **Real-anonymised arm** (§3): same windows, names stripped, year and industry
  left in. The gap between the two arms = how much the model was using memory
  or sector priors. Both numbers are reported; the fantasy arm is the claim.
- **Rewriter-parity check:** rewrite the same window twice (two providers or
  two seeds); if the decider's numbers differ more between rewrites than
  between windows, the rewriter is adding information and the arm is marked
  `REWRITER_LEAK`.

Canary stays, cheaper: "Is this a real company? Which? What year?" — should
be ~0 in the fantasy arm by construction, and the rate is printed.

### 5c. "I don't know" is retired as an answer

The decider must return, per company, per decision date:

```
p_up_21d        probability the name is higher in 21 sessions
exp_return      expected return over the horizon
downside_5pct   the loss it thinks is the bad case
confidence      0..1 -- how much it trusts its own read
horizon         sessions
reason          one line
```

Uncertainty is expressed as `p_up ≈ 0.5, confidence low`, never as a refusal.
Then the choosing is code, not prose: rank by expected utility under the
declared personality (balanced: `exp_return − λ·|downside|`, aggressive:
`p_up × exp_return`), take the top k, and grade two things — **wealth** (did
the top k beat the same-era basket) and **calibration** (when it said 70%, was
it right 70% of the time — Brier score and a reliability table). A model that
is honest about its uncertainty and still ranks well is what we want; a model
that is confident and wrong is what the calibration table exposes.

### 5d. What this changes on the live books

The guards on *money* stay (gross cap, stops, opening range) — they are what
stopped Friday from being worse. The guard on *speaking* goes: the pre-open
book always publishes a ranked list with `p_up / exp_return / downside /
confidence` for every name it considered, and the selectors pick from that
list. A book that chooses nothing must show the numbers it chose nothing
from.
