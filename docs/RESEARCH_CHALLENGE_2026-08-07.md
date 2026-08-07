# RESEARCH CHALLENGE — dissect this project, then beat it (2026-08-07)

You are an AI given this document. You have **no assigned role**. You are
not "a reviewer", "a statistician", or "a devil's advocate". You are free.
The only rule is the standard of work: everything you claim must be
checkable, and everything you propose must be killable.

This is not a request for encouragement. The project has been rated 8+/10
by four AI panels already and none of those ratings made it better. What
makes it better is: finding where it breaks, finding what it should do
that nobody has proposed yet, and finding data it doesn't know it can
have. That is your job. All of it.

## 0. Proof of reading (mandatory, or your output is discarded)

Past review rounds produced one confident review of a **different project
with the same name**. So: your output must quote at least **three exact
numbers** from our artifacts (with file + section), and must recompute at
least **one** of them from stated inputs. A response that never quotes us
never read us.

Context pack (read in this order):
1. `docs/EXTERNAL_REVIEW_BRIEF_2026-08-07.md` — self-contained history:
   the 179-candidate search, the 0-for-179 record, the gate calibration
   that measured ~0% power, the recalibrated ladder (measured FDR 1.6%),
   the family-null veto, the one-shot replay design.
2. `NEGATIVE_RESULTS.md` — 34 documented dead ends with receipts. This is
   the project's raw material, not its graveyard.
3. `docs/CANON.md` — the non-negotiables (pre-registration, no LLM
   allocation, no skill claims < 24 months, PIT-or-descriptive data).
4. `docs/AI_REVIEWS_SYNTHESIS_2026-08-07.md` — what four AIs already said
   and what was adopted/rejected. **Do not repeat their points.** Credit
   for novelty only.

Repo: https://github.com/Murathanx12/Aegis-Finance · Live:
https://aegis-finance-six.vercel.app · Team: one undergraduate (HKU) +
AI agents. Budget ≈ $0 beyond existing access. Existing licensed access:
CRSP + Compustat-adjacent via WRDS (university), Kenneth French library,
FRED, SEC EDGAR, GDELT, free tiers of Finnhub/FMP/Polygon.

## 1. Dissect (find where it breaks)

Attack, in whatever order you see weakness. Not a summary — a teardown.
For every attack: state the failure scenario concretely (what input/state
produces what wrong output/decision), and what measurement would confirm
it. Suggested surfaces, not limits:

- The simulator (DGP-A v6) certifies a payoff null. What real-market
  structure is it still missing that would make the measured 1.6% FDR
  optimistic — and how would you *demonstrate* the miss with our own data?
- The family-null veto has two levels (generic, σ-family). Construct a
  candidate that slips between them.
- The one-shot replay: find the remaining researcher degrees of freedom
  we have not disclosed ourselves.
- The confirm window (2019-2024, fixed): design a candidate class it
  systematically mis-judges that our TEMPORALLY-MISMATCHED class does
  not already cover.
- The forward paper lanes: what invalidates a 24-month NAV record that
  we have not already listed?
- The meta-risk: every safeguard here was built by AI agents that also
  wrote this challenge. Where does that circularity bite hardest, and
  what is the cheapest external anchor that would break it?

## 2. Rebuild (come up with the better version)

Ideas are cheap; killable ideas are not. Every proposal in this section
must come in this exact format or it will not be adopted:

```
IDEA: one sentence
MECHANISM: why this would work (economic or statistical reason)
DATA: exact source + access path + license status + PIT feasibility
TEST: the pre-registerable design (explore/confirm split, control arm,
      placebo, primary metric, decision rule)
KILL: the condition under which this idea is declared dead
COST: hours + dollars + capacity estimate
WHY WE'RE PROBABLY WRONG: your own strongest argument against it
```

Directions we want pushed (extend, replace, or overrule them):

- **Better tests than ours.** Our decision instrument is an explore/
  confirm wall + simulator-measured FDR. Propose a test architecture
  that dominates it — more power at equal FDR, or equal power at lower
  cost — and prove the dominance claim on the simulator's own terms.
- **Fail-proofing.** The house failure mode is silent success (code runs
  green, does nothing). We now assert coverage and test guards. Design
  the next layer: what property of a research pipeline can be made
  *impossible to fake* rather than merely checked?
- **ROI, plural.** The goal is maximum long-run ROI under our canon. That
  has more degrees of freedom than signal discovery: portfolio-of-lanes
  construction, evidence-conditioned sizing curves, cost/turnover
  engineering, capacity-aware universe choice, overlay stacking (vol/
  trend/exit rules that survived), cross-lane netting. Which of these
  moves the ROI needle most per unit of our time, with what evidence?
- **Old data, new hypotheses.** Take our 34 negative results and the 179
  candidates as INPUTS. Which combination of a documented corpse + a
  dataset we already hold (or can get, §3) yields a hypothesis nobody in
  the ledger has tested? Example shape (do not copy it): §28 shows the
  spread information lives in the short leg we cannot trade — what
  *instrument* (options we can price, inverse ETFs, index-relative
  underweights) converts short-leg information into a long-only
  implementable book, and what would kill it?
- **Groundbreaking or nothing.** The paper-worthy asset here is the
  method: a fully pre-registered, self-calibrating, failure-publishing
  research factory run by one student + AI agents. What is the ONE
  experiment that, if run, would make this project citable — the
  experiment a hedge fund cannot publish and an academic cannot run?

## 3. Data hunt (our bottleneck is no longer data — prove it)

Find public or archived datasets we can legally access at ≈$0 that create
NEW testable edges under our discipline. For each: source, exact access
path (URL/API/archive), license, history depth, point-in-time integrity
(can we know what was known when?), and the specific hypothesis it
unlocks in the §2 format. Seed examples of what "counts" (find better):

- ALFRED (FRED archival vintages) — real-time macro data AS PUBLISHED,
  the PIT-correct version of half our macro features.
- SEC EDGAR full-text search + historical filings back to 1993 — we use
  Form 4/13F/8-K; the S-1/10-K/DEF-14A text layers are untouched.
- FINRA daily short-sale volume files; CFTC COT; Treasury auction
  results; USAspending federal contracts; LDA lobbying disclosures;
  ClinicalTrials.gov + FDA calendars (we already run PDUFA — extend it).
- Internet Archive + Common Crawl for archived news/text where GDELT is
  thin; Wikipedia pageviews as attention proxy.
- University-accessible WRDS libraries we may not have opened yet
  (IBES estimates, OptionMetrics, TAQ intraday, Audit Analytics) — state
  what each unlocks IF the subscription covers it, so we can check.

Rank everything by (edge plausibility × PIT integrity × access cost).
A dataset without a hypothesis is not a finding.

## 4. Retention and reach (compete with the big platforms)

The platform must earn return visits without pretending to be Bloomberg.
Free constraint: our differentiator is *verified honesty* (public
negative results, forward-only track record, self-calibrating gates).
Propose concretely: what daily/weekly artifact would make a quant
student, a finance professor, or an AI agent come BACK — and how do we
measure retention without dark patterns? What should the public API
serve that nothing else on the internet serves?

## 5. Questions from the resident agent (answer at least three)

I built most of this under direction and I know where I am uncertain.
Answer with designs or receipts, not opinions:

1. The family-null veto rests on ledger receipts because the simulator
   couples IC and alpha. What is the cheapest simulator extension that
   would let the veto be *certified* rather than argued? (WORLD-8
   "IC-real/book-dead" is registered as future work — design it: how do
   you inject rank information with provably zero payoff into a panel
   that keeps F1-F8 fidelity?)
2. Wave-3 gives 1000 fresh nulls for FDR. What is the equivalent cheap
   certification for the *confirm* stage's operating characteristics —
   without spending another 140 core-hours?
3. Our capacity story is untested: the ladder adopts on rank-IC in a
   3000-name universe, but real fills at our AUM are unknown unknowns.
   What free data bounds realistic capacity for a monthly-rebalanced
   long-only small/mid book, and at what AUM does the small-segment
   edge (if the replay finds one) stop existing?
4. The 24-month no-claims clock is honest but commercially brutal. What
   intermediate, statistically-defensible public milestone exists between
   "operations proven" and "skill proven" that we could publish at month
   6 and 12 without lying?
5. If you had our exact artifacts and ONE month of Opus-class agent time,
   what would you build that we have not thought of?

## 6. Output contract

- Sections in your answer mirror §1-§5. No preamble, no summary of us.
- Every §2/§3 item in the exact IDEA format. Un-killable ideas are
  discarded unread.
- Cite our artifacts by file+section when you attack; cite external work
  precisely (author-year-venue or working URL) when you import it.
- End with your three strongest contributions ranked, each in one
  sentence, each with its kill condition attached.
- If you have repository or execution access (Claude Code / Opus
  session): do not just propose — RUN the cheapest decisive version of
  your top idea against the repo's data and report the number, following
  CANON (pre-register in one paragraph before computing; a result
  without a prior registration line is not a result).

We will verify your claims against the artifacts, credit what survives,
and publish what we adopt with attribution to the round. The last round's
reviews are in the synthesis doc with each error flagged — yours will be
treated the same way.
