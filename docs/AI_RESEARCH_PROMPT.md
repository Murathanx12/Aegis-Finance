# RESEARCH BRIEF — Aegis Finance External Review & Idea Generation

*Paste this prompt together with `AEGIS_FINANCE_DOSSIER_2026-08-02.md`. That document is the complete state of the project: timeline, every experiment (179 candidates, 31 negative results), every bug found, the testing infrastructure, and the owner's investment thesis.*

---

## Who you are

You are an independent quantitative research consultant with **no stake in this project being right**. Your value comes from what you find that we missed — a flaw, a paper, a dataset, a repo, an idea. You have been hired precisely because you were NOT in the room. Treat every claim in the dossier as a claim, not a fact.

You have **full freedom**: any methodology, any source, any angle of attack, any length. Go wild. The only currency here is *specificity* — a named paper, a linked repo, a computable test, a falsifiable prediction. Vague advice ("consider transaction costs") is worthless; we've read the textbooks.

## The situation in one paragraph

A solo builder (HKU student, strong engineering discipline) built a market-intelligence platform and a research pipeline: 179 strategy candidates screened over explore(2004-2018)/confirm(2019-2024) splits, pre-registered trials, placebo controls, a negative-results ledger with 31 entries. Search phase closed 2026-08-02. Surviving candidates: **gp-small** (gross-profitability in small caps), **fusion**, **TSMOM-XA** (time-series momentum cross-asset) — a fourth "survivor" (insider) turned out to be a data collector writing constant zeros, discovered only by a late audit. Ten paper-trading lanes run forward since 2026-06-08. The goal: **beat the S&P 500 on real money**, via strategy mixing and regime-based switching, exploiting LLM-read news/social signals, insider/hedge-fund/politician flows, and the owner's "social bias" thesis (below). The owner is worried the results are faulty because of "how we use data, how we test, the environment we created" — the dossier's audit sections (Parts V–VI) confirm several of those worries were justified.

## Your five jobs (do all five; weight them however evidence pulls you)

### 1. VALIDATION — attack the results
Read Parts II–VI of the dossier as a hostile referee.
- Is the multiple-testing arithmetic right? (Deflated Sharpe Ratio at N=179, Z(179)=2.729, the claim that a noise best-of-179 hits Sharpe ≈0.71 on 15 years.) Recompute anything you can. If a number is wrong, show the correction.
- Are the survivors *real*, or exactly what surviving a 179-candidate screen by luck looks like? What test would distinguish those two worlds? Design it concretely.
- The placebo-gate logic (§29–§31, the F1 correction): is seed-level t vs pooled t the right resolution? Is there a third reading we missed?
- Find leaks we haven't found. The dossier documents: FRED reference-date vs release-date (~56 features), alphabetical tie-break fabrication, constant-collector zeros, tautological assertions. Assume there are more. Where would YOU look first, given the codebase layout described?
- The 37-day paper-lane record vs SPY: the dossier says no conclusion is possible (SE ≈ ±2.14 on Sharpe). Confirm or refute that framing. What's the minimum forward window before ANY claim is meaningful?

### 2. METHODOLOGY REVIEW — attack the process
- Critique the explore/confirm split, the pre-registration protocol, the placebo-gate design, the 24-month no-skill-claims rule. What would a top journal referee or a fund's risk committee reject, and what would they steal?
- The registry counts 18 trials while the true count is 179 (documented defect). Beyond fixing the counter — what OTHER process claims in the dossier are "described but not executed"? Hunt for the gap between stated discipline and machine-enforced discipline.
- Is anything **over**-disciplined? Are we killing true signals with controls that have more power against truth than against noise? (E.g., does a random-date placebo gate have a known false-kill rate?)
- Propose the *minimum* protocol changes with the *maximum* epistemic payoff. Rank them.

### 3. SOURCES — bring receipts we don't have
For every claim you make, and every idea you propose, bring:
- **Papers**: exact titles, authors, years. Prefer post-2020 work we're less likely to know. Replication studies and negative results count double (we run a negative-results ledger; feed it).
- **Git repositories**: named repos with URLs — factor libraries, backtesting engines, PIT-data tooling, LLM-finance pipelines, network-analysis codebases. For each: what specifically to take from it (a file, a technique, a test), not just "look at this." Examples of the caliber we mean: Chen-Zimmermann's `openassetpricing` / CrossSection repo (we already use the SignalDoc snapshot), `alphalens`/`zipline` lineage, LOPS/`mlfinlab` (we have it), `qlib`, anything doing point-in-time BoardEx/CRSP linkage properly in public.
- **Datasets**: what's accessible to a WRDS subscriber (we have CRSP, Compustat, CCM, BoardEx North America — full and uncapped as of 2026-08-03, including the 5M-row company network file and 17M-row director master — IBES, and possibly RavenPack-trial + Thomson TFN 13F entitlements) plus free sources (SEC EDGAR, Form 4, 13F, GDELT, FRED). What high-value dataset are we NOT using that we're already paying for?
- **Methodologies**: named techniques with their canonical reference (e.g., combinatorial purged CV, Romano-Wolf stepdown, SPA/MCS tests, conformal methods for regime uncertainty). For each: the exact decision in our pipeline it would change.

### 4. IDEA GENERATION — the owner's thesis and beyond
The owner's core thesis, verbatim priorities: social biases matter more than numbers; profitable-but-unfashionable companies are systematically undervalued because they're not mainstream; perpetually-covered names (NVDA/TSLA class) are structurally overvalued — ride the trend in, exit at peak attention; company networks matter (boards, founders, political stance, closeness to ruling party, even ethnic composition of leadership); get in early on trends, use LLMs to read news/X/journals as signals; exploit insider, hedge-fund, and politician trades.
- **Steelman it**: what does the academic and practitioner literature actually support? (We know: Fang-Peress media coverage, Hong-Kacperczyk sin stocks, Cohen-Frazzini-Malloy networks, Cooper et al. political contributions, Scherbina neglected stocks, attention-cycle papers.) What's the strongest evidence FOR each leg, and the honest effect size after costs?
- **Attack it**: which legs are already-arbitraged, uninvestable at retail scale, or proxies for known factors (size, illiquidity, low-analyst-coverage)? Where would the thesis have lost money in the last decade?
- **Extend it**: give us ideas we haven't had. Anything goes — alternative data, structural/behavioral effects, market microstructure, LLM-native signals, graph methods on the BoardEx network (we now have the full 5M-edge NA network + 17M director-role records, point-in-time linkable to CRSP), political/lobbying data, supply-chain graphs, earnings-call linguistics, Form 4 cluster detection improvements. For each idea: the data needed, the null hypothesis, the placebo/control design, expected capacity, and why it might still be alive in 2026.
- **Regime switching**: the goal is mixing strategies and switching by market phase. Known evidence is discouraging (HMM switchers underperform buy-and-hold net; 384 years to detect a 0.10 Sharpe improvement). Is there a version that works — regime-conditional *sizing* rather than switching, filtered vs smoothed states, vol-targeting hybrids? Bring the best evidence either way.
- **Risk appetite**: owner is willing to lower confidence thresholds and take much riskier bets to maximize ROI, and questions whether Sharpe is even the right objective. Give a rigorous treatment: geometric growth (Kelly and fractional Kelly), drawdown-constrained objectives, why a 19-year-old's human capital changes the answer, where the line between "aggressive" and "innumerate" actually is.

### 5. ROADMAP — what would YOU do next
End with a concrete, ordered 90-day plan as if this were your project: what to build, what to test, what to kill, what to read — each item with its blocking dependency and its kill criterion. Assume one talented builder, WRDS access, ~$20 of LLM budget/month (DeepSeek), free-tier everything else, and the discipline infrastructure already described.

## Ground rules (from the project's own canon — hold us to them)

1. **Cite or don't claim.** Every empirical statement gets a source or a computation.
2. **State your prior before your result.** If you designed a test, say what you expected before running it.
3. **Separate three registers explicitly**: VERIFIED (you checked), REPORTED (a source says), SPECULATION (your idea). Mislabeling these is the one way to fail this assignment.
4. **Negative findings are deliverables.** "This thesis leg is dead, here's why, stop spending on it" is a top-tier outcome.
5. **The LLM narrates; the engine computes.** Any proposed LLM signal must have a numeric, auditable extraction path — no vibes-as-features.
6. **Point-in-time or it didn't happen.** Every proposed dataset/signal must state its publication lag and how you'd enforce PIT alignment. (BoardEx's `"Curr"` sentinel and FRED reference-dates already burned us.)
7. **Costs, capacity, and the short leg.** Every long-short idea must say what survives long-only at retail scale (§28 taught us 99.9% of one spread lived in the short leg).

## Output format

Free-form, but end with:
- **TOP 10 ACTIONS** — ranked, one line each, each starting with a verb.
- **TOP 5 SOURCES** — the papers/repos/datasets you most want us to actually open, with one sentence on what each changes.
- **THE ONE THING** — if we can only do one thing you said, which, and why.

Length: as long as the content deserves. Depth beats coverage. If you spent all your effort on one section and it's genuinely excellent, that's a better outcome than five shallow sections.
