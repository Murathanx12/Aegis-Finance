# Panel prompt — round 15 (paste this verbatim to each model, with the briefing attached)

> Give each model `docs/research/EXTERNAL_BRIEFING_2026-07-30.md` **and** this
> prompt. Run them separately, don't show them each other's answers.

---

You are reviewing a pre-registered quantitative research program (briefing
attached). **This is not a request for approval, a summary, or a verdict on work
already done. I want new information and better questions.**

## Read this first — it changes how you should treat the briefing

In the previous round, four models reviewed this same document. Here is what
happened, because it should calibrate how much you trust it:

1. **The briefing contained an error.** It stated that a 13F "best-ideas" signal
   was untested. It had in fact been tested and rejected (small-cap rank IC
   t = 2.70, net −5.7 bps/month, t = −0.53). **All four models independently made
   "run the 13F best-ideas test" their top recommendation — because the document
   told them it was open.** They inherited the error instead of catching it.
2. **The one criticism that produced value was specific and testable.** One model
   argued a null result came from 36-month beta-estimation noise rather than
   information loss. That was run as a decomposition. It was wrong (the
   factor-tilt component alone carried t(IC) 2.80 of the total 2.84), but a
   secondary arm partly supported it and was published as a concession. It made
   the finding stronger.
3. **One model fabricated its sources** — roughly thirty citations to a public
   GitHub repository that does not contain this project, with numbers taken from
   the prompt and re-attributed to it. It also self-contradicted by a factor of
   7.7× on a headline statistic inside a single answer.
4. **Almost everything else was already in the ledger with receipts.** Four
   independent reviews produced exactly one un-registered idea.

**So: the briefing is written confidently, and it is wrong in places. Do not
treat it as ground truth. Where it makes a claim you can check, check it. A
demonstrated error in that document is worth more to me than agreement with it.**

## What I actually want

Answer these five. Depth on two or three beats thin coverage of all five.

**1. What question should this program be asking that it is not?**
Not "which signal should it test next" — what *framing* is wrong or missing.
The program currently asks "does signal X predict returns, net of costs,
out-of-sample?" If that is the wrong question, say what the right one is and
what would have to be true for your reframing to be worth its cost.

**2. What has changed since roughly mid-2024 that this program would not know?**
This is where you have an advantage over me and I have almost none. I want:
new empirical results that overturn or sharpen something in the briefing;
market-structure changes (retail options volume, 0DTE, T+1 settlement, PDT
rules, fractional shares, direct-indexing costs, SEC disclosure rule changes);
data sources that became cheap, free, or newly available; and anything that
makes a previously-blocked test feasible. **Concrete and dated, not thematic.**

**3. One falsifiable prediction, stated as a number, before anything is run.**
Pick any measurement this program could make and commit to what it will show.
Format: *"If you run X on the 2004-2018 explore window with honest costs, the
long-only top-decile net t-statistic will be between A and B, and the rank-IC
t-statistic between C and D."* State your confidence as a percentage.
**Your predictions will be scored against the runs and published with your name
attached, across rounds.** A wrong prediction that was precise is worth more
than a vague one that cannot be scored — say "I don't know" rather than hedging
into unfalsifiability.

**4. The strongest argument AGAINST your own best idea.**
Every proposal here costs a multiple-testing slot in a program whose measured
zero-skill ceiling is t ≈ 3.6–4.0. So: name your best idea, then argue the case
for *not* running it as well as you can. Include the kill condition — what
result would make you abandon it — and your honest prior probability that it
clears the bar. If your prior is below 20%, say so; that is useful and it will
not be held against you.

**5. What is the correct answer to this question:**
*Given a measured self-deception ceiling of t ≈ 3.6–4.0, a best-achievable
library result of t = 2.94, an empty cost-killed cohort, and 23 recorded
negative results — is there any information class reachable by a ~$100k US
retail account that has not been exhausted, or is the correct conclusion that
the search is over and the remaining levers are allocation, risk-shaping, cost,
tax and behaviour?*
**Give a probability that the search is effectively over**, and say what single
piece of evidence would most change your number in either direction. "The search
is over" is a fully acceptable answer and I am not looking for encouragement.

## Hard rules

- **Every factual claim needs a citation that resolves** — DOI, arXiv ID, SSRN
  abstract ID, or a working URL. If you cannot produce one, write *"unverified,
  from memory"* next to the claim. That label costs you nothing. A fabricated
  citation discredits everything else you write, and a prior round is on record.
- **Do not cite this project's own repository.** It is private. Anything you
  "find" there came from this prompt.
- **Numbers must carry their source and sample period.** An effect size without
  a window is not usable.
- **Distinguish untested from refuted.** If the briefing says something is
  closed, check whether the closure covers the specific variant you are
  proposing — several closures are deliberately scoped narrowly, and a variant
  outside the scope is a legitimate proposal.
- **Do not propose anything from the DO-NOT-RE-PROPOSE list without rebutting
  its receipt by name.**
- Length is not a virtue. A single well-sourced, falsifiable claim beats ten
  paragraphs of architecture.

## Output format

```
1. THE MISSING QUESTION
2. WHAT CHANGED SINCE 2024        (dated, cited)
3. MY PREDICTION                  (numeric, with confidence %)
4. THE CASE AGAINST MY BEST IDEA  (with kill condition + prior)
5. P(search is over) = __%        (+ what would move it)
6. ERRORS I FOUND IN THE BRIEFING (or: "none found", which is also an answer)
```

## What happens next

Your answers go into an adjudication document alongside the other three models'.
Every checkable claim is verified against the project ledger or settled by a run.
Predictions are scored. Fabrications are logged by name. The adjudication is
committed to the repository and forms a running reliability record across
rounds — the same treatment the program applies to its own hypotheses.
