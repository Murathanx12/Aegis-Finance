# Edge measurement: prior-art and methodology map (cloud session, 2026-10-07)

> **This is not a patentability or freedom-to-operate opinion.** It is an engineer's map of
> where each part of the AEGIS measurement system already exists in statistics, in the
> investment industry and in the patent record. Its purpose is that anyone who later needs
> counsel starts from verified sources. The labels say how close the nearest prior art I found
> is; they are not legal conclusions. "No hit" means my search found nothing, not that
> nothing exists. Patent statuses are Google Patents' own labels, read on 2026-10-07. Google
> calls them "an assumption and not a legal conclusion". None was checked on USPTO Patent Center.

**RESULT IMPROVEMENT: NONE.** This is a research note. No code was changed.

**Session constraints.** This session had no Exa MCP and no Optimus MCP. The CLAUDE.md
session-start calls were therefore not run (`session_briefing`, `aegis_verified_state`,
`brain_query`, `aegis_postmortems`), and the brain may already hold a note on this topic that
this one has not seen. Web pages were read with WebFetch and found with WebSearch.
Bibliographic records come from the Crossref REST API. Patents come from Google Patents'
`xhr/result` and `xhr/query` endpoints. The normal `patents.google.com/patent/<n>` HTML page
returned Google's 503 "automated queries" page to both curl and WebFetch all session.

---

## 0. Three most important conclusions (for the PR)

1. **Each of the seven components already exists elsewhere, and most of that prior art is
   decades old.** Of the 30 rows in the risk map (§3), 15 are `COMMON / OLD` and 11 are
   `KNOWN BUT DIFFERENT`. The main precedents:

   | AEGIS component | Precedent |
   |---|---|
   | Leave-one-source-out | The data-denial Observing System Experiments of numerical weather prediction ([ECMWF, Bormann et al. 2019](https://www.ecmwf.int/sites/default/files/elibrary/2019/18859-global-observing-system-experiments-ecmwf-assimilation-system.pdf)); LOCO ([Lei et al. 2018](https://doi.org/10.1080/01621459.2017.1307116)) |
   | Contribution after neutralisation | [Numerai MMC](https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc) and [TC](https://forum.numer.ai/t/true-contribution-details/5128) |
   | Signed per-decision-type regret | Perold's implementation shortfall, including the opportunity cost of unexecuted trades ([1988](https://doi.org/10.3905/jpm.1988.409150)); Brinson-Hood-Beebower ([1986](https://doi.org/10.2469/faj.v42.n4.39)); Cabot's per-action counterfactual portfolios (buy, sell, add/trim; [FactSet 2022](https://insight.factset.com/quantifying-portfolio-managers-skills-for-a-more-vibrant-active-equities-industry), in use since about 2006); Inalytics' initiation, scale-up, close and scale-down decisions scored against benchmark weight ([public in 2009](https://thehedgefundjournal.com/identifying-manager-skill/)) |
   | Per-source reputation | StarMine's analyst-accuracy weighting ([US6510419B1](https://patents.google.com/patent/US6510419B1/en), priority 1998, expired 2019); Bühlmann credibility ([1967](https://doi.org/10.1017/S0515036100008989)); the extremized logit pool ([Satopää et al. 2014](https://doi.org/10.1016/j.ijforecast.2013.09.009)) |
   | Sequential evidence | Wald ([1945](https://doi.org/10.1214/aoms/1177731118)), through [Howard et al. 2021](https://arxiv.org/abs/1810.08240) and [Ramdas et al. 2023](https://arxiv.org/abs/2210.01948) |

2. **The patents that matter are in commercial decision analytics, not in machine learning.
   None of the 58 patents AEGIS docs already cite touches measurement.** Two active US patents
   sit next to the regret ledger:
   - **[US7756769B2](https://patents.google.com/patent/US7756769B2/en)** (Cabot, now FactSet;
     anticipated expiry 2028-01-13). It claims hypothetical portfolios whose actions are
     modulated so that holding periods become more uniform.
   - **[US12032652B1](https://patents.google.com/patent/US12032652B1/en)** (Inalytics;
     anticipated expiry 2043-04-03). It claims a simulated portfolio weighted to a
     benchmark-neutral position, with the weights computed by GPU-parallel matrix calculation.
     Its dependent claims split selection, initial sizing and change in sizing.

   AEGIS's current alternatives are frozen per decision, before the outcome is known. That is
   built differently from both patents. Two things AEGIS has not built would sit right next to
   these claims: a portfolio-level book with a common holding period, and a neutral-weight
   simulated book that separates selection from sizing. Either should go to counsel before it
   is built. Numerai's [US11704593B1](https://patents.google.com/patent/US11704593B1/en)
   (to 2038) is narrow: it claims stake ranking, logloss thresholds and smart-contract payouts.

3. **The only candidate for something AEGIS-specific is a narrow implementation detail:
   leave-one-source-out gated on a replay check, with typed refusals.**
   - A counterfactual "plan without source s" is written only if the plan, replayed from its
     own frozen inputs, reproduces the live targets to within 1e-9.
   - The declared mapping from sources to model components must pass a check against the
     decision layer's own component registry.
   - The source must not have fed an upstream stage that is not re-run, or a downstream gate
     whose effect on the counterfactual book is not modelled.
   - Otherwise the row is written as `NOT_SEPARABLE` with its reason. A source the plan
     provably does not read is `IDENTICAL_NOT_READ`, with contribution zero by construction.

   I found no prior art that claims this refusal discipline. That is the result of a limited
   search, not a finding of novelty. The code has been on `origin/main` of a public repository
   since commit `951719f9` (authored 2026-10-07 03:22 +08:00). What that means for any filing
   is a question for counsel.

## Generic vs potentially distinctive (summary)

- **Generic (`COMMON / OLD`):**
  - the Opportunity Score composite;
  - keeping direction separate from magnitude;
  - leave-one-out (LOO) and ablation contribution;
  - exact linear SHAP;
  - the marginal-versus-LOO comparison with its interaction term;
  - MMC-style neutralised contribution;
  - credibility-shrunk reputation weights clipped at a floor;
  - the extremized logit pool;
  - firm→sector→global shrinkage and sleeping experts;
  - e-values and confidence sequences;
  - hash-sealed append-only logs and event-sourced id chains;
  - the contextual bandit;
  - co-coverage graph propagation.
- **Known but different.** The concept exists and AEGIS implements a variant:
  - signed per-decision regrets against alternatives frozen before the outcome (Cabot and
    Inalytics instead analyse holdings after the fact);
  - reason-coded abstention cohorts scaled to the strategy's own gross cap;
  - selection regret against the next-ranked name;
  - the news "add one in" tilt at earned trust;
  - the analyst reputation weight labelled `NOT_PERSISTENT_OOS`;
  - one e-value per date block (design only);
  - the matched-null regret triple.
- **Potentially distinctive implementation detail:** leave-one-source-out gated on a replay
  check, with typed separability refusals (one row; §4).
- **Needs counsel.** None of these is built:
  - a portfolio-level book with equalised holding periods (Cabot, to 2028-01-13);
  - a benchmark-neutral simulated portfolio that splits selection, initial sizing and change
    in sizing (Inalytics, to 2043-04-03);
  - payouts to external contributors ranked by stake and accuracy (Numerai, to 2038-03-27).
- **A structural point the prior art makes clear.** AEGIS is small enough to be a price-taker,
  so the outcome of the trade it did not make is observable: the price series exists whether
  or not AEGIS bought. Abstention and alternative regrets are therefore full-information
  bookkeeping, not off-policy estimation. Compare credit "reject inference"
  ([Hand & Henley 1993](https://doi.org/10.1093/imaman/5.1.45)), propensity-based outcomes of
  untaken lending decisions ([FICO US8682762B2](https://patents.google.com/patent/US8682762B2/en)),
  and logged-bandit evaluation ([Dudík et al. 2011](https://arxiv.org/abs/1103.4601)).
  The method risk sits in the cost and impact model and in the choice of counterfactual size,
  not in the estimator. That is where review effort belongs.

---

## 1. What AEGIS means by each component (as of the 2026-10-07 working tree)

**1. Opportunity Score / Edge Vector.** This is mostly a design.

- The roadmap adopts "Edge Vector fields" as vocabulary from an outside guide ("ChatGPT's ten
  phases"). It refuses to build the "ten-field Edge Vector" before a consumer exists, and says
  the Opportunity Explorer shows "D/M/Q/F/X from services that already run"
  (`docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md:112-117`).
- No Edge Vector object exists in code. The letters Q and X are not defined anywhere in the
  tree; D/M/Q/F/X appears only at roadmap line 116.
- What exists:
  - Direction is kept separate from magnitude. `move_score` is magnitude and "`direction` is a
    SEPARATE field ... never derived from sigma"; a list sorted by magnitude is labelled
    "MAGNITUDE RANKING: not a long list" (`backend/services/opportunities.py:22-25`).
  - MoveScore is σ63·√21·√(2/π) (`docs/research_notes/2026-10-06/opportunity_explorer_2026-10-06.md:45`).
  - Freshness is `last_update_age_days`, computed at serve time
    (`backend/services/opportunities.py:206-214`).
  - The Explorer rows also carry analyst stance and a reputation label
    (`scripts/opportunities_build.py:1012`).
- The only "opportunity score" in code is an older fixed-weight composite: signal 0.35,
  Sharpe 0.25, risk-reward 0.25, confidence 0.15
  (`backend/services/signal_analytics.py:290-345`). It sorts the screener
  (`backend/routers/stock.py:404-406`).

**2. Unique / marginal decision contribution (MDC).** The regret ledger computes, per session,
`mdc_<source> = utility(plan_full) − utility(plan without source)`. It also computes
`mdc_news_tilt = utility(plan + SHADOW_NEWS_v0 tilt) − utility(plan)`
(`backend/services/regret_ledger.py:32, 412-436`). Each number carries `n_sessions` and the
label `TRUST_AT_63 (n/63)` until 63 sessions have been graded
(`regret_ledger.py:64, 549-571`). The roadmap logs this as the owner's "MMC / MDC" ask, built in
modified form: "capture now, trust at 63 sessions" (roadmap line 131).

Two related tools already exist:
- an exact linear-SHAP split of `E[r]` into components
  (`backend/services/expected_return.py:11-13, 336`);
- a two-direction marginal-versus-leave-one-out decomposition that prints the interaction and
  refuses to give one number when the two disagree (`backend/services/lane_autopsy.py:20-45, 325`).

Status: plumbing only. No graded MDC exists yet. The first h5 grades come 2026-10-13 at the
earliest (`docs/research_notes/2026-10-06/decision_story_and_regret_2026-10-06.md`).

**3. Leave-one-source-out counterfactual decisions.** The plan is replayed (`replan`) from its
own frozen scoring inputs with one source removed. The sources are news, analyst,
price_momentum, regime and llm (`backend/services/decision_story.py:78`, with source →
component map at `:82-91`). Four checks control whether a number is written:

- **Replay check.** `replay_check` (`:329-338`) requires the replay to reproduce the live
  pre-gate targets within 1e-9. If it does not, every leave-one-out row is `NOT_SEPARABLE`.
- **Mapping check.** `mapping_check` (`:196-205`) refuses a source map that has drifted from
  `expected_return.COMPONENTS` or from `NOT_READ_BY_DESIGN`.
- **Separability.** `funnel_separable` (`:207-224`) marks a name `NOT_SEPARABLE` for a source
  when the candidate funnel, which is not re-run, ranked or filtered on that source. Names whose
  EXPLOIT weights were scaled by the order gate are also refused, because the gate's effect on
  the counterfactual book is not modelled (`:606-611`).
- **Unread sources.** A source the plan does not read is `IDENTICAL_NOT_READ` (`:584-590`).

The loop that writes these rows is at `:759-776`. When component weights are renormalised under
reputation weighting, the result is flagged as an approximation (`er_names_minus`, `:227-273`).

**4. Abstention regret.** The roadmap refuses to "punish not deciding". Its reason: "a learner
rewarded for acting will act on noise". Instead every HOLD/REFUSE freezes a BUY counterfactual
and is graded against it (roadmap line 91; `decision_story.py:1-14, 107`).

- **Grading** (`regret_ledger.py:195-197`). For a picked-but-blocked name the abstention regret
  is `plan_full − actual`. For a shortlisted name not taken, or a ranker-pool name, it is
  `buy_default − actual`. Resizing a held line is not counted as an abstention.
- **Cohorts.** Abstentions are graded as cohort books (`picked_blocked`, `shortlist_not_taken`,
  `ranker_pool`, `held_resize`, `acted`). Each book is scaled to `PROBE_GROSS_CAP` and reported
  as net excess over SPY and over a same-liquidity-band equal-weight control, by session, with
  t and MDE. The books are never summed into one dollar line (`regret_ledger.py:22-25, 283, 474-492`).
- **Why it looks like this.** The first version priced a 102%-gross, 51-name book that could
  never have been held (`docs/reviews/REVIEW_2026-10-06_C11_DECISION_STORY_REGRET.md`, F2).

**5. Signed direction / sizing / timing / selection / exit regret.**

- **Definition.** Every regret is `outcome(alternative) − outcome(actual)` between two
  alternatives frozen at decision time (`regret_ledger.py:65-67, 154-200`). There is no `max`
  over alternatives.
- **The alternatives:**
  - direction: `no_trade`;
  - sizing: `buy_default`;
  - timing: the traded delta entered at the next open versus the reference entry, same exit;
  - exit: `hold` or `exit_now`;
  - selection: one row per (session, selector), the taken book against the next-ranked name
    not taken, each at its own cost band (`:452-472`).
- **Why there is no `max`.** The original sizing regret was a best-of-two, which read
  +5.6 bps on 100% of zero-drift draws (review F1). Every regret type is now pinned mean-zero
  under a martingale null by `backend/tests/test_decision_story_and_regret.py:277`.
- **Costs.** Zero cost is refused (`pnl`, `:86-93`).
- **Older siblings:**
  - `backend/services/research_gym/regret.py:1-45` reports regret as a triple: against the
    ex-post best (labelled an upper bound), against a fixed default, and as excess over a
    state-and-action-matched null. It refuses a null computed under different assumptions.
  - `backend/services/arena/regret.py:1-30` is a reader that joins REJECT rows to chosen legs.

**6. Conditional source / model reputation.**

- **Forecaster arms** (`backend/services/forecast_reputation.py:1-46`):
  - weights come from held-out Brier skill per arm;
  - the shrink is `s_shr = n/(n+k)·skill`; then `w = clip(s_shr, floor, 1)^γ`, normalised (`:265-281`);
  - the pool is `sigmoid(κ Σ w logit p)` (`:292-310`);
  - `k`, `γ` and `κ` are tuned by leave-one-quarter-out (or leave-one-day-out).
- **E[r] layer** (`expected_return.py:30-46, 336-350`):
  - it uses the same recipe for component weights;
  - asleep components drop out and the rest renormalise ("sleeping experts");
  - the reputation blend is used only when its out-of-sample advantage over equal weights is
    positive and survives dropping any one year.
- **Analyst reputation** (`backend/services/analyst_reputation.py:1-55`):
  - shrinkage runs firm → sector → global, and the weight is clipped to [0.5, 1.5];
  - the receipt prints a Kish effective sample size;
  - claims are admitted point-in-time;
  - the split-half persistence test (`:421-470`) failed (Spearman −0.31), so the weight
    carries the label `REPUTATION_WEIGHT: NOT_PERSISTENT_OOS`.
- **What "conditional" means today:** sector only. The horizon level is degenerate ("every
  target on disk is 12-month"). Regime-conditional weights are not built. A contextual bandit
  over source weights waits for 63 regret sessions (roadmap line 303).

**7. Sequential evidence.** Design only. The roadmap settles on "sequential evidence for
display, 24-month floor for claims" (lines 152, 201-202). The design is in
`docs/research_notes/2026-09-21/research_sequential_evidence_and_bandits.md` §1:
- an e-process per hypothesis, with one e-value per date block (not per row);
- a confidence sequence;
- e-BH for multiplicity;
- a gate of at least 200 scored rows.

`backend/services/` contains no e-value or confidence-sequence code; a grep found none. What
runs today is fixed-n t and MDE over date blocks (`regret_ledger._stat`, `:494-506`) plus the
`TRUST_AT_63` labels.

**Substrate: the Decision Story.** One id chain per candidate per session
(`decision_story.py:16-40`):

    event_ids → evidence_ids → forecast_ids → decision_id → order_or_abstention_id → outcome_ids → attribution_ids

- Only decision and abstention ids are minted. Outcome and attribution ids are deterministic
  from the decision id and the horizon (`:174-194`).
- Rows are monthly JSONL, append-only, and each row carries a sha256 seal (`:120-123`).
- Alternatives read no bar after `asof` (`cut_bars`, `:396`) and carry no wall-clock stamp.
- The point-in-time property is tested by mutating post-`asof` bars
  (`test_decision_story_and_regret.py:158`).

---

## 2. Prior art in four buckets

### 2a. Standard / statistical prior art

| Topic | Prior art (verified) | Relevance to AEGIS |
|---|---|---|
| Proper scoring | [Brier 1950](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2), Mon. Wea. Rev. 78(1):1-3; [Murphy 1973](https://doi.org/10.1175/1520-0450(1973)012%3C0595:ANVPOT%3E2.0.CO;2), J. Appl. Meteor. 12:595-600 (reliability/resolution/uncertainty partition; generalised by [Pohle 2020](https://arxiv.org/abs/2005.01835)); [Gneiting & Raftery 2007](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf), JASA 102(477):359-378. They trace propriety to "Brier (1950) and Good (1952)" and the word "proper" to Winkler and Murphy (1968). | The held-out Brier skill per arm in `forecast_reputation` is this, unchanged. |
| Comparing two forecasts | [Diebold & Mariano 1995](https://doi.org/10.1080/07350015.1995.10524599); [Harvey, Leybourne & Newbold 1998](https://doi.org/10.1080/07350015.1998.10524759) (forecast encompassing); [Giacomini & White 2006](https://doi.org/10.1111/j.1468-0262.2006.00718.x) (*conditional* predictive ability) | A signed loss differential against one pre-declared comparator is the shape of every AEGIS regret. Encompassing asks whether a forecast adds information beyond another, which is MDC's question in forecast space. Giacomini-White is the statistical form of "conditional reputation". |
| Direction vs magnitude | [Pesaran & Timmermann 1992](https://doi.org/10.1080/07350015.1992.10509922) (directional accuracy test); [Christoffersen & Diebold 2006](https://doi.org/10.1287/mnsc.1060.0520) (direction-of-change predictability arising from volatility dynamics) | Supports the Explorer's separate D and M columns. It also warns that direction "skill" can be volatility in disguise. |
| Shapley / SHAP | Shapley 1953, *Contributions to the Theory of Games* II, pp. 307-317 (formula and axioms via [Wikipedia](https://en.wikipedia.org/wiki/Shapley_value); RAND original 403); [Lundberg & Lee 2017](https://arxiv.org/abs/1705.07874) | `expected_return`'s linear SHAP is the textbook exact case. |
| LOO vs Shapley | [Ghorbani & Zou 2019, Data Shapley](https://arxiv.org/abs/1904.02868): Shapley is "more powerful than the popular leave-one-out" | **A method warning for MDC.** With two redundant sources, LOO gives each roughly zero. MDC by LOO will understate correlated sources (analyst revisions vs momentum). `lane_autopsy`'s two-direction print is the cheap fix and could be reused for MDC. |
| LOCO | [Lei et al. 2018](https://doi.org/10.1080/01621459.2017.1307116), JASA 113(523):1094-1111. The fitted model is refit without covariate j and the excess prediction error is measured ([PDF](https://www.stat.cmu.edu/~ryantibs/papers/conformal.pdf)). | Model-free LOO importance with inference. MDC is LOCO in decision-utility space. |
| First-in vs last-in | [Grömping 2007](https://doi.org/10.1198/000313007X188252) (relative importance) | Same two bounds as `lane_autopsy` MARGINAL / LEAVE-ONE-OUT. |
| Online learning, regret | [Cesa-Bianchi & Lugosi 2006](https://www.cambridge.org/core/books/prediction-learning-and-games/A05C9F6ABC752FAB8954C885D0065C8F); [Littlestone & Warmuth 1994](https://doi.org/10.1006/inco.1994.1009); [Freund & Schapire 1997](https://doi.org/10.1006/jcss.1997.1504); [Blum & Mansour 2007](https://www.jmlr.org/papers/v8/blum07a.html) (external vs swap regret); [Cover 1991](https://doi.org/10.1111/j.1467-9965.1991.tb00002.x) (universal portfolios; record only) | Textbook regret is against the best action *in hindsight*, the biased form AEGIS removed in review F1. Swap regret (replace action i by j) is the closer analogue of AEGIS's pairwise rows. |
| Sleeping / specialist experts | [Freund, Schapire, Singer & Warmuth 1997](https://doi.org/10.1145/258533.258616), STOC '97 (record only) | `expected_return.blend` renormalises over awake components, the same rule. |
| Bandits and counterfactual evaluation | [Auer, Cesa-Bianchi & Fischer 2002](https://doi.org/10.1023/A:1013689704352) (UCB1; record only); [Auer et al. 2002](https://doi.org/10.1137/S0097539701398375) (EXP3; record only); [Li et al. 2010](https://arxiv.org/abs/1003.0146) (LinUCB plus unbiased offline replay on logged random traffic); [Dudík, Langford & Li 2011](https://arxiv.org/abs/1103.4601) (doubly robust); [Swaminathan & Joachims 2015](https://arxiv.org/abs/1502.02362) (CRM/POEM); [Bottou et al. 2013](https://arxiv.org/abs/1209.2355) (causal inference to "predict the consequences of changes to the system") | Needed when untaken actions' rewards are unobserved. AEGIS's are observed, see §0. The deferred contextual bandit over source weights is off the shelf. |
| Max-over-alternatives bias | [White 2000, Reality Check](https://doi.org/10.1111/1468-0262.00152) (record only) | `research_gym/regret.py` G1 ("half the headline was the denominator") is this result found again in-house. |
| Abstention as an option | [Chow 1970](https://doi.org/10.1109/TIT.1970.1054406) (reject option; record only); [El-Yaniv & Wiener 2010](https://www.jmlr.org/papers/v11/el-yaniv10a.html) (risk-coverage); [Yang, Jin & Tan 2024](https://arxiv.org/abs/2402.15127) (bandits with an abstention arm: fixed-regret and fixed-reward settings); [Hand & Henley 1993](https://doi.org/10.1093/imaman/5.1.45) (reject inference; record only) | Abstention is priced in all four. In reject inference the rejected outcome is unobservable; in AEGIS it is observable. |
| Regret (other meaning) | [Loomes & Sugden 1982](https://doi.org/10.2307/2232669) (record only) | Behavioural "regret theory" puts regret into utility. AEGIS's regret is an outcome difference. Keep the two meanings apart in public text. |
| Forecast combination | [Bates & Granger 1969](https://doi.org/10.1057/jors.1969.103) (record only); [Elliott & Timmermann 2005](https://doi.org/10.1111/j.1468-2354.2005.00361.x) (regime-switching weights; record only); [Jacobs, Jordan, Nowlan & Hinton 1991](https://doi.org/10.1162/neco.1991.3.1.79) (mixture of experts; record only) | Accuracy-weighted and context-gated combination are old. |
| Credibility shrinkage | [Bühlmann 1967](https://doi.org/10.1017/S0515036100008989), ASTIN Bull. 4(3):199-207: premium = Z·individual + (1−Z)·collective, with Z = 1/(1+σ²/(v²m)) = m/(m+k) ([Wikipedia](https://en.wikipedia.org/wiki/B%C3%BChlmann_model)) | `n/(n+k)` in `forecast_reputation` and the K-constants in `analyst_reputation` are credibility weights. |
| Extremized aggregation | [Satopää, Baron, Foster, Mellers, Tetlock & Ungar 2014](https://doi.org/10.1016/j.ijforecast.2013.09.009), IJF 30(2):344-356. [Satopää, Pemantle & Ungar](https://economics.sas.upenn.edu/sites/default/files/filevault/event_papers/Satopaa_ungar.pdf) describe it as "a logistic regression model to derive an aggregator that extremizes". [Baron et al. 2014](https://doi.org/10.1287/deca.2014.0293) | `pool = sigmoid(κ Σ w logit p)` is this aggregator. AEGIS lets κ < 1 (un-extremize) because its arms were found over-confident. |
| Sequential and anytime-valid inference | [Wald 1945](https://doi.org/10.1214/aoms/1177731118) (record only); [Howard, Ramdas, McAuliffe & Sekhon 2021](https://arxiv.org/abs/1810.08240), Ann. Stat. 49(2); [Ramdas, Grünwald, Vovk & Shafer 2023](https://arxiv.org/abs/2210.01948), Stat. Sci. 38(4); [Vovk & Wang 2021](https://arxiv.org/abs/1912.06116), Ann. Stat. 49(3); [Grünwald, de Heide & Koolen](https://arxiv.org/abs/1906.07801), JRSS-B 86(5), 2024; [Waudby-Smith & Ramdas](https://arxiv.org/abs/2010.09686) (betting CS for bounded means); [Wang & Ramdas](https://arxiv.org/abs/2009.02824) (e-BH, FDR under arbitrary dependence); [Johari, Pekelis & Walsh](https://arxiv.org/abs/1512.04922), Oper. Res. 70(3), 2022 (always-valid p-values, deployed in a commercial A/B platform) | All of AEGIS's sequential-evidence design comes from these. |
| Provenance and event sourcing | [Fowler 2005](https://martinfowler.com/eaaDev/EventSourcing.html) (rebuild, temporal query, replay); [W3C PROV-DM 2013](https://www.w3.org/TR/prov-dm/) (Entity/Activity/Agent; wasGeneratedBy, used, wasDerivedFrom, ...); [Singh, Cobbe & Norval, "Decision Provenance"](https://arxiv.org/abs/1804.05741) (IEEE Access 9); [Haber & Stornetta 1991](https://doi.org/10.1007/BF00196791) (hash-chained timestamps; record only); [RFC 6962](https://datatracker.ietf.org/doc/html/rfc6962) (Certificate Transparency Merkle log), obsoleted by [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162) | The Decision Story's id chain, append-only rows and seals. CT adds Merkle consistency proofs, which AEGIS does not have. |
| Data denial / observation impact | [Bormann, Lawrence & Farnan 2019](https://www.ecmwf.int/sites/default/files/elibrary/2019/18859-global-observing-system-experiments-ecmwf-assimilation-system.pdf), ECMWF Tech. Memo: "the forecast impact of withholding selected observations from the assimilation system compared to using the full observing system"; [Langland & Baker 2004](https://doi.org/10.3402/tellusa.v56i3.14413) (adjoint-based observation impact; record only) | **The closest old analogue of leave-one-source-out:** withhold one observing system, re-run the whole pipeline, score the forecast difference. The adjoint method is to data denial what Numerai's gradient TC is to leave-one-out. |
| Knowledge graphs and event propagation | [Cohen & Frazzini 2008](https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns), JF 63(4):1977-2011; [Ali & Hirshleifer 2020](https://doi.org/10.1016/j.jfineco.2019.10.007), JFE 136(3):649-675 (shared analyst coverage unifies momentum spillovers; record only); [Feng et al. 2019](https://arxiv.org/abs/1809.09441), ACM TOIS (temporal relational ranking over stock relations); [Ding et al. 2014](https://aclanthology.org/D14-1148/), EMNLP (structured events; metadata only) | `graph_propagation.py` (co-coverage peer return) is the Ali-Hirshleifer mechanism. The deferred world graph is a temporal relational model. |

### 2b. Financial-industry analogues

| Practice | What it does (verified source) | AEGIS counterpart and difference |
|---|---|---|
| **Implementation shortfall** ([Perold 1988](https://doi.org/10.3905/jpm.1988.409150)) | "Return/profits on a paper portfolio – Return/profits on actual portfolio"; paper trades at benchmark (decision) prices. Includes "opportunity costs (the penalty associated with not completing intended trades)" ([Hasbrouck lecture notes](https://pages.stern.nyu.edu/~jhasbrou/Teaching/POST%202015%20Fall/classNotes/STPPTradingCosts.pdf); history in [Quantitative Brokers 2018](https://www.quantitativebrokers.com/blog/a-brief-history-of-implementation-shortfall)) | `plan_full − actual` for picked-but-blocked names is Perold's paper-versus-real gap. Timing regret is IS delay cost. AEGIS extends the "paper portfolio" to names the plan never selected. |
| **Brinson attribution** ([BHB 1986](https://doi.org/10.2469/faj.v42.n4.39)) | Active return = allocation + selection + interaction, which "sum exactly" ([Wikipedia](https://en.wikipedia.org/wiki/Performance_attribution)) | `lane_autopsy` already cites "the Brinson interaction error". The regret types are a per-decision, ex-ante cousin. |
| **Cabot Research / FactSet** | Buy, sell and sizing skill: "each type of action (buy, sell, add/trim) is assessed individually using a counterfactual portfolio"; "available for 16 years" as of May 2022 ([FactSet Insight](https://insight.factset.com/quantifying-portfolio-managers-skills-for-a-more-vibrant-active-equities-industry)). Patent [US7756769B2](https://patents.google.com/patent/US7756769B2/en). | The direct commercial analogue of signed sizing and exit regret. Cabot builds hypothetical portfolios **after the fact** from holdings. AEGIS freezes **per-decision** alternatives **before** the outcome and charges a cost model. |
| **Inalytics** | Decisions classed as initiation, scale up, closing and scale down, judged against benchmark weight in five buckets; average hit rate 49.6%, win/loss 102% ([Di Mascio & Savage, Hedge Fund Journal, Sept 2009](https://thehedgefundjournal.com/identifying-manager-skill/)). Patent [US12032652B1](https://patents.google.com/patent/US12032652B1/en) (2023 priority). | Decision-type attribution has been public since at least 2009. The 2023 patent claims a specific neutral-weight simulation computed on a GPU. |
| **Institutional sell decisions** | [Akepanidtaworn, Di Mascio, Imas & Schmidt 2023](https://doi.org/10.1111/jofi.13271), JF 78(6). Per [Marginal Revolution](https://marginalrevolution.com/marginalrevolution/2019/01/selling-fast-buying-slow-bias.html), they used 783 portfolios and 4.4M trades, and found managers "would have done better had [they] chosen what to sell randomly". | An exit regret against a random-sell counterfactual, published. Odean's bought-vs-sold comparison ([1999](https://doi.org/10.1257/aer.89.5.1279); [1998](https://doi.org/10.1111/0022-1082.00072); records only) is the retail ancestor. |
| **Alpha capture** (Marshall Wace, from 2001) | Ideas arrive with "a rationale, timeframe and conviction level", which lets investors "quantify and monitor the performance of different ideas" ([Wikipedia](https://en.wikipedia.org/wiki/Alpha_capture_system)) | Per-source reputation for idea contributors, tracked whether or not the idea was executed. That is the industry form of abstention grading combined with source reputation. |
| **StarMine SmartEstimates** (LSEG) | "weights forecasts by analyst accuracy and estimate recency", excluding "stale, clustered and outlier estimates" ([LSEG](https://www.lseg.com/en/data-analytics/financial-data/analytics/quantitative-analytics/starmine-smartestimates)). Patent family [US6510419B1](https://patents.google.com/patent/US6510419B1/en) (1998, expired). | `analyst_reputation`'s firm weights and the Explorer's freshness. StarMine weights **EPS** estimates. AEGIS weights **target-price** claims, and [Bradshaw, Brown & Huang 2013](https://ideas.repec.org/a/spr/reaccs/v18y2013i4d10.1007_s11142-012-9216-5.html) find "statistically significant but economically weak evidence" of persistence for target prices. That fits AEGIS's own `NOT_PERSISTENT_OOS` result. |
| **Numerai MMC / TC / FNC** | MMC is "the covariance of a model with the target, after its predictions have been neutralized to the Meta Model" ([docs](https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc); MMC staking from 2024-01-02). TC is "the gradient of portfolio returns with respect to users' stakes" through a differentiable optimizer (cvxpylayers), with 100 rounds of 50% stake dropout. The same post says it solved "limitations of earlier leave-one-out approaches" ([forum, 2022-03-22](https://forum.numer.ai/t/true-contribution-details/5128)). FNC neutralises predictions to features ([docs](https://docs.numer.ai/numerai-tournament/scoring/feature-neutral-correlation)). | MMC works in prediction space and TC in portfolio space by gradient. AEGIS's MDC works in decision space by leave-one-out through a non-differentiable rule-based plan, which is the approach Numerai moved away from. AEGIS should not call MDC "MMC". |
| **Alpha decomposition vs a risk model** | [Karels & Sun (MSCI), 2013](https://www.msci.com/documents/10199/c6e5e3f7-cd44-4322-aeb5-331e20e2afb7) split alpha into a part spanned by risk factors and a residual orthogonal part; IC and the fundamental law ([Grinold 1989](https://doi.org/10.3905/jpm.1989.409211), record only). [US7890408B2](https://patents.google.com/patent/US7890408B2/en) (MSCI, expired) orthogonalises risk factors to custom "process" factors. | The industry form of "unique contribution = residual after neutralisation". |
| **Transaction cost analysis** | Pre-trade cost models, e.g. [US8229834B2](https://patents.google.com/patent/US8229834B2/en) (ITG, expired) | AEGIS's liquidity-band round-trip cost and its zero-cost refusal are ordinary TCA hygiene. |

### 2c. Patent prior art

> Not a freedom-to-operate opinion. Statuses are Google's labels. "Expired - Fee Related"
> means the patent lapsed for non-payment before the anticipated date shown. The expiry column
> is Google's "Anticipated expiration" event.

**(i) The 58 patents already named in AEGIS docs, every one fetched.** Sources:
`docs/research_notes/2026-09-11/ideas_round2/angle2_patents.md`,
`docs/research_notes/2026-09-11/research_patents_data.md`,
`docs/research_notes/2026-09-11/research_nn.md`. Note that `grep -rni patent docs/ | head -50`
shows none of these numbers; they sit further down the grep output.

Result: **none of the 58 claims attribution, regret, abstention, reputation or sequential
testing.** I scanned each abstract and claim 1 for attribution, regret, counterfactual,
reputation, track record, forecaster, analyst, leave-one, abstention, missed, opportunity cost,
contribution and accuracy. Only three incidental hits came back:
- [US10255523B2](https://patents.google.com/patent/US10255523B2/en): vehicle "attributes".
- [US8296211B2](https://patents.google.com/patent/US8296211B2/en) (Bdellium, expired): a
  user-weighted scoring of standardised performance measures. This is old prior art for any
  composite "Opportunity Score".
- [US20070288342A1](https://patents.google.com/patent/US20070288342A1/en) (abandoned):
  "opportunity cost" of failing to cross in a dark pool.

**Status corrections against the 2026-09-11 notes** (outside this task's scope, but material):
- [US7792719B2](https://patents.google.com/patent/US7792719B2/en) (Research Affiliates,
  priority 2004-02-04) is listed **Active, anticipated expiry 2027-02-07**. The 09-11 note §12
  said "YES for this patent and for anything claiming 2002-2004 priority".
- [US8533098B2](https://patents.google.com/patent/US8533098B2/en) (Sutton) is
  **Expired - Fee Related**. The 09-11 note had "Likely ACTIVE ... STATUS UNVERIFIED".
- [US7698197B1](https://patents.google.com/patent/US7698197B1/en) (IPOX) is **Active to
  2028-01-31**.

| Patent | Title (Google) | Original assignee | Priority | Google status | Anticipated expiry |
|---|---|---|---|---|---|
| [US10255523B2](https://patents.google.com/patent/US10255523B2/en) | Moving vehicle detection and analysis using low resolution re… | Orbital Insight Inc | 2015-11-16 | Active | 2036-11-14 |
| [US10373254B2](https://patents.google.com/patent/US10373254B2/en) | System and method for providing income payments to an investor | New York Life Insurance Co | 2011-03-10 | Active | 2031-03-10 |
| [US10387958B2](https://patents.google.com/patent/US10387958B2/en) | Self-directed style box portfolio allocation selection appara… | FMR LLC | 2015-06-11 | Active | 2037-01-01 |
| [US10452978B2](https://patents.google.com/patent/US10452978B2/en) | Attention-based sequence transduction neural networks | Google LLC | 2017-05-23 | Active | 2038-05-23 |
| [US10453139B2](https://patents.google.com/patent/US10453139B2/en) | Apparatus, method and system for designing and trading macroe… | Goldman Sachs and Co LLC | 2004-04-16 | Active | 2027-08-17 |
| [US10839316B2](https://patents.google.com/patent/US10839316B2/en) | Systems and methods for learning and predicting time-series d… | Goldman Sachs and Co LLC | 2016-08-08 | Active | 2038-03-03 |
| [US11100587B2](https://patents.google.com/patent/US11100587B2/en) | Systems and methods for dynamic fund allocation in goals-base… | Franklin Advisers Inc | 2019-01-25 | Active | 2040-01-22 |
| [US11195232B2](https://patents.google.com/patent/US11195232B2/en) | Methods and apparatus employing hierarchical conditional valu… | Axioma Inc | 2016-05-09 | Active | 2036-09-29 |
| [US11257161B2](https://patents.google.com/patent/US11257161B2/en) | Methods and systems for predicting market behavior based on n… | Refinitiv US Organization LLC | 2011-11-30 | Active | 2031-11-30 |
| [US11353833B2](https://patents.google.com/patent/US11353833B2/en) | Systems and methods for learning and predicting time-series d… | Goldman Sachs and Co LLC | 2016-08-08 | Active | 2040-11-15 |
| [US20030225658A1](https://patents.google.com/patent/US20030225658A1/en) | Buy-write indexes | Chicago Board Options Exchange Inc | 2002-06-03 | Abandoned | — |
| [US20050262010A1](https://patents.google.com/patent/US20050262010A1/en) | Systems and methods for converting closed-end funds to active… | American Stock Exchange LLC | 2004-05-21 | Abandoned | — |
| [US20060100949A1](https://patents.google.com/patent/US20060100949A1/en) | Financial indexes and instruments based thereon | Individual (Robert Whaley) | 2003-01-10 | Abandoned | — |
| [US20060271452A1](https://patents.google.com/patent/US20060271452A1/en) | System and method for relative-volatility linked portfolio ad… | Individual (Panayotis Sparaggis) | 2005-05-25 | Abandoned | — |
| [US20070288342A1](https://patents.google.com/patent/US20070288342A1/en) | Method and system for algorithmic crossing to minimize risk-a… | Individual (Leon Maclin) | 2006-05-13 | Abandoned | — |
| [US20080183638A1](https://patents.google.com/patent/US20080183638A1/en) | Method and system for multiple portfolio optimization | ITG Software Solutions Inc | 2003-02-20 | Abandoned | — |
| [US20080288386A1](https://patents.google.com/patent/US20080288386A1/en) | Method of Systematic Trend-Following | Aspect Capital Ltd | 2005-10-21 | Abandoned | — |
| [US20090018969A1](https://patents.google.com/patent/US20090018969A1/en) | Systems and methods for providing investment strategies | Individual (Ian Ayres) | 2007-06-07 | Abandoned | — |
| [US20090271230A1](https://patents.google.com/patent/US20090271230A1/en) | Method and system for solving stochastic linear programs with… | Individual (Pu Huang) | 2008-04-28 | Granted (grant's own status not read) | 2029-07-09 |
| [US20100005032A1](https://patents.google.com/patent/US20100005032A1/en) | Buy-write indexes | Individual (Robert E. Whaley) | 2002-06-03 | Abandoned | — |
| [US20100070427A1](https://patents.google.com/patent/US20100070427A1/en) | Dynamic indexing | Palantir Technologies Inc | 2008-09-15 | Abandoned | — |
| [US20100076904A1](https://patents.google.com/patent/US20100076904A1/en) | Apparatus and methods for facts based trading | Bank of America Corp | 2008-09-24 | Granted (grant's own status not read) | 2030-08-21 |
| [US20110178958A1](https://patents.google.com/patent/US20110178958A1/en) | System and Method for Analyzing Data Associated with Statisti… | Credit Suisse Securities USA LLC | 2006-10-30 | Granted (as US8688558B2, below) | 2028-06-18 |
| [US20130046677A1](https://patents.google.com/patent/US20130046677A1/en) | Financial products based on a serialized index | IntercontinentalExchange Inc | 2012-10-22 | Granted (grant's own status not read) | 2032-10-22 |
| [US20140188762A1](https://patents.google.com/patent/US20140188762A1/en) | Method and system for multiple portfolio optimization | ITG Software Solutions Inc | 2003-02-20 | Abandoned | — |
| [US20140244474A1](https://patents.google.com/patent/US20140244474A1/en) | Automated trading system and methodology for realtime identif… | Individual (Remington John Sutton) | 2007-11-06 | Abandoned | — |
| [US20150206244A1](https://patents.google.com/patent/US20150206244A1/en) | Systems and methods for portfolio construction, indexing and… | Movengineering Srl | 2014-01-17 | Abandoned | — |
| [US20190066208A1](https://patents.google.com/patent/US20190066208A1/en) | System and method for dynamic implementation of exchange trad… | JPMorgan Chase Bank NA | 2017-08-24 | Granted (grant's own status not read) | 2038-09-20 |
| [US20260111964A1](https://patents.google.com/patent/US20260111964A1/en) | Method and system for training and fine-tuning large language… | JPMorgan Chase Bank NA | 2024-10-21 | Pending | — |
| [US5101353A](https://patents.google.com/patent/US5101353A/en) | Automated system for providing liquidity to securities markets | Lattice Investments Inc | 1989-05-31 | Expired - Fee Related | 2009-05-31 |
| [US5148365A](https://patents.google.com/patent/US5148365A/en) | Scenario optimization | Individual (Ron S. Dembo) | 1989-08-15 | Expired - Lifetime | 2009-09-15 |
| [US5799287A](https://patents.google.com/patent/US5799287A/en) | Method and apparatus for optimal portfolio replication | Individual (Ron S. Dembo) | 1994-05-24 | Expired - Lifetime | 2014-05-24 |
| [US6687681B1](https://patents.google.com/patent/US6687681B1/en) | Method and apparatus for tax efficient investment management | Marshall and Ilsley Corp | 1999-05-28 | Expired - Fee Related | 2019-05-28 |
| [US7031937B2](https://patents.google.com/patent/US7031937B2/en) | Method and apparatus for tax efficient investment management | Marshall and Ilsley Corp | 1999-05-28 | Expired - Lifetime | 2021-02-20 |
| [US7117175B2](https://patents.google.com/patent/US7117175B2/en) | Method and apparatus for managing a virtual mutual fund | Research Affiliates LLC | 2002-04-10 | Expired - Lifetime | 2023-07-10 |
| [US7337137B2](https://patents.google.com/patent/US7337137B2/en) | Investment portfolio optimization system, method and computer… | ITG Inc | 2003-02-20 | Expired - Lifetime | 2024-04-07 |
| [US7587347B2](https://patents.google.com/patent/US7587347B2/en) | Computer implemented and/or assisted methods and systems for… | Citadel Investment Group LLC | 2004-10-19 | Active | 2028-02-13 |
| [US7587352B2](https://patents.google.com/patent/US7587352B2/en) | Method and apparatus for managing a virtual portfolio of inve… | Research Affiliates LLC | 2002-04-10 | Expired - Lifetime | 2023-03-08 |
| [US7620577B2](https://patents.google.com/patent/US7620577B2/en) | Non-capitalization weighted indexing system, method and compu… | Research Affiliates LLC | 2002-06-03 | Expired - Lifetime | 2023-11-02 |
| [US7698197B1](https://patents.google.com/patent/US7698197B1/en) | Index of initial public offerings (IPOX) and IPOX derivatives | IPOX Schuster LLC | 2003-12-17 | Active | 2028-01-31 |
| [US7747502B2](https://patents.google.com/patent/US7747502B2/en) | Using accounting data based indexing to create a portfolio of… | Research Affiliates LLC | 2002-06-03 | Ceased | 2024-01-18 |
| [US7792719B2](https://patents.google.com/patent/US7792719B2/en) | Valuation indifferent non-capitalization weighted index and p… | Research Affiliates LLC | 2004-02-04 | Active | 2027-02-07 |
| [US7853510B2](https://patents.google.com/patent/US7853510B2/en) | Method and system for multiple portfolio optimization | ITG Software Solutions Inc | 2003-02-20 | Expired - Fee Related | 2025-03-10 |
| [US7873530B2](https://patents.google.com/patent/US7873530B2/en) | Method and system for solving stochastic linear programs with… | International Business Machines C… | 2008-04-28 | Expired - Fee Related | 2029-07-09 |
| [US7949590B2](https://patents.google.com/patent/US7949590B2/en) | Apparatus, method and system for designing and trading macroe… | Goldman Sachs and Co LLC | 2004-04-16 | Active | 2029-04-25 |
| [US8005740B2](https://patents.google.com/patent/US8005740B2/en) | Using accounting data based indexing to create a portfolio of… | Research Affiliates LLC | 2002-06-03 | Ceased | 2023-12-18 |
| [US8296211B2](https://patents.google.com/patent/US8296211B2/en) | Method of analyzing investments using standardized performanc… | Bdellium Inc | 2002-01-25 | Expired - Lifetime | 2023-05-07 |
| [US8374951B2](https://patents.google.com/patent/US8374951B2/en) | System, method, and computer program product for managing a v… | Research Affiliates LLC | 2002-04-10 | Expired - Fee Related | 2023-04-10 |
| [US8533098B2](https://patents.google.com/patent/US8533098B2/en) | Automated trading system and methodology for realtime identif… | Individual (Remington John Sutton) | 2007-11-06 | Expired - Fee Related | 2031-05-04 |
| [US8635141B2](https://patents.google.com/patent/US8635141B2/en) | Method and system for multiple portfolio optimization | ITG Software Solutions Inc | 2003-02-20 | Expired - Fee Related | 2023-08-14 |
| [US8688550B1](https://patents.google.com/patent/US8688550B1/en) | Method and apparatus for leveraged tax efficient investment m… | BMO Financial Corp | 1999-05-28 | Expired - Fee Related | 2021-09-06 |
| [US8688558B2](https://patents.google.com/patent/US8688558B2/en) | System and method for analyzing data associated with statisti… | Credit Suisse Securities USA LLC | 2006-10-30 | Expired - Fee Related | 2028-06-18 |
| [US8719148B2](https://patents.google.com/patent/US8719148B2/en) | Model-based selection of trade execution strategies | Goldman Sachs and Co LLC | 2005-11-30 | Expired - Lifetime | 2025-11-30 |
| [US8768810B2](https://patents.google.com/patent/US8768810B2/en) | Dynamic asset allocation using stochastic dynamic programming | Individual (Gerd Infanger) | 2006-05-19 | Expired - Fee Related | 2032-05-16 |
| [US8856056B2](https://patents.google.com/patent/US8856056B2/en) | Sentiment calculus for a method and system using social media… | ISENTIUM LLC | 2011-03-22 | Expired - Fee Related | 2033-01-17 |
| [US9070165B2](https://patents.google.com/patent/US9070165B2/en) | Method of matching hedge funds and investors and apparatus th… | Individual (Lisa Vioni) | 2005-05-23 | Expired - Lifetime | 2026-05-23 |
| [US9208502B2](https://patents.google.com/patent/US9208502B2/en) | Sentiment analysis | IPC Systems Inc | 2011-01-20 | Active | 2032-07-11 |
| [WO2006127541A2](https://patents.google.com/patent/WO2006127541A2/en) | System and method for relative-volatility linked portfolio ad… | Individual (Panayotis T. Sparaggi… | 2005-05-25 | Ceased | 2007-11-25 |

**(ii) New patents found for the three named mechanisms and their neighbours.** Each was fetched
and its claim 1 read (claims 1-31 for Cabot and 1-19 for Inalytics).

| Patent | Assignee (original → current) | Priority | Status / anticipated expiry | Nearest AEGIS piece | Claim-level read-out |
|---|---|---|---|---|---|
| [US7756769B2](https://patents.google.com/patent/US7756769B2/en) "Portfolio-performance assessment" | Cabot Research LLC → Cabot Investment Technology Inc | 2006-09-01 | **Active**, 2028-01-13 | exit / hold and sizing regret | Independent claims 1, 14 and 27: identify actions in an actual portfolio, then build a hypothetical portfolio from those positions with the actions modulated so the spread of holding periods around their average is smaller than in the actual portfolio; compare performance. Claim 9 adds a common target holding period: delay sales of young positions and eliminate positions older than the target. |
| [US12032652B1](https://patents.google.com/patent/US12032652B1/en) "Attribution analysis" | Inalytics Ltd | 2023-04-03 | **Active**, 2043-04-03 | sizing / selection regret | Independent claims 1, 18 and 19: a simulated set of states weighted to a **neutral position** with respect to a reference set, with the weights computed by **matrix calculation in parallel on a GPU**. Dependent claims 2-17: totals for selected and non-selected states, build intervals, and benefit matrices for initial sizing and change in sizing. |
| [US7644011B2](https://patents.google.com/patent/US7644011B2/en) "…determining investment manager skill" | Individual | 2005-01-26 | Expired - Fee Related | matched-null regret | Standardises manager returns against distributions of randomly drawn portfolios from the mandate universe: a random-portfolio null. |
| [US7890408B2](https://patents.google.com/patent/US7890408B2/en) "Attributing performance, risk … to custom factors" | Morgan Stanley Capital International → MSCI | 2007-10-11 | Expired - Fee Related | MMC-style neutralisation | Residual factors from orthogonalising risk factors to custom process factors; attribution to custom, residual and idiosyncratic parts. |
| [US8533081B2](https://patents.google.com/patent/US8533081B2/en) "Dynamic value added attribution" | Research Affiliates | 2007-10-23 | Active, 2031-08-21 | none built | Splits allocation and variance measures into static and dynamic parts across periods. AEGIS has no static/dynamic allocation split; keep it that way or ask counsel. |
| [US7249079B1](https://patents.google.com/patent/US7249079B1/en), [US7249082B2](https://patents.google.com/patent/US7249082B2/en) | Vestek → Refinitiv | 2000-07-11 | Expired - Lifetime | linking 5/21/63 effects | Links single-period attribution effects over many periods and distributes the residual. |
| [US11205231B2](https://patents.google.com/patent/US11205231B2/en) | Axioma | 2014-10-02 | Expired - Fee Related | — | Attribution hierarchy for composite instruments. |
| [US6510419B1](https://patents.google.com/patent/US6510419B1/en), [US6983257B2](https://patents.google.com/patent/US6983257B2/en), [US7603308B2](https://patents.google.com/patent/US7603308B2/en) | StarMine → Refinitiv | 1998-04-24 | Expired (2019 / 2020 / 2021) | analyst and source reputation | US6510419B1 claim 1: "a composite prediction based on a plurality of analysts' current predictions and historical data concerning analysts' past predictions", with "individual weighting factors for individual analysts based at least in part on the historical data". **Expired, and prior art against anyone else.** |
| [US20040133497A1](https://patents.google.com/patent/US20040133497A1/en) "Performance-weighted consensus" | Individual | 2002-12-18 | Abandoned (published 2004) | source reputation | Claim 1: "rank sources of financial advice ... based upon the relative past performance of the sources". |
| [US8364580B2](https://patents.google.com/patent/US8364580B2/en) | Goldman Sachs | 2002-11-14 | Expired - Fee Related | conditional source weighting | A consensus that excludes estimates from entities with a banking relationship to the issuer. |
| [US11704593B1](https://patents.google.com/patent/US11704593B1/en) | Numerai Inc | 2017-03-27 | **Active**, 2038-03-27 | per-source payout | Claim 1: rank data-source nodes by stake; score each estimate's accuracy against a second data set; assign token augmentation from a smart-contract feedback resource when logloss beats thresholds. |
| [US8682762B2](https://patents.google.com/patent/US8682762B2/en) "…outcomes associated with decision alternatives" | Fair Isaac | 2009-12-01 | Active, 2032-08-30 | abstention / alternatives | Propensity-score (Rubin) estimates of outcomes under lending-decision alternatives. Needed in credit because the untaken outcome is unobserved; AEGIS reads it from prices. |
| [US11373109B2](https://patents.google.com/patent/US11373109B2/en) | Fair Isaac | 2019-07-02 | Active, 2040-01-31 | lineage / attribution | Finds the past transactions that most move a current score. That attributes a score to input events, not a trade to its sources. |
| [US20180182037A1](https://patents.google.com/patent/US20180182037A1/en) | Individual → AQR Capital Management | 2014-03-28 | Abandoned | source selection | Selects crowdsourced forecasting algorithms from test-trial parameters (the abstract mentions controlling for backtest overfitting). |
| [US20250384341A1](https://patents.google.com/patent/US20250384341A1/en) | Strong Force TX Portfolio 2018 | 2022-10-28 | Pending | source reliability gating | Claim 1 as published: a reliability score per new datum from source features; include the datum in the **training set** above a threshold and exclude it if likely malicious. Pending, so the claims may change. |
| [CN116308809A](https://patents.google.com/patent/CN116308809A/en) | Dalian Univ. of Technology | 2023-02-27 | Pending | analyst reputation | A deep model predicting the quality of an analyst's view from event-domain features. A learned quality score, not a track-record weight. |
| [US11323388B1](https://patents.google.com/patent/US11323388B1/en) | Triangle IP | 2017-01-27 | Active, 2038-01-29 | multi-source weighting | A gap-filling composite signal from tagged, latency-aligned sources. Not attribution. |
| [US10585778B2](https://patents.google.com/patent/US10585778B2/en), [US10901872B2](https://patents.google.com/patent/US10901872B2/en) | Optimizely → Optimizely North America | 2015-09-23 | Active, 2035-09-23 | sequential evidence | Continuous monitoring of web-content variation tests, with a **reset policy** to keep the results valid. |
| [US8433645B1](https://patents.google.com/patent/US8433645B1/en), [US8229834B2](https://patents.google.com/patent/US8229834B2/en) | Alpha Vision → Portware; ITG → Virtu ITG | 2010 / 2002 | Expired - Fee Related | cost model | Choice of execution algorithm, cost components, and pre-trade cost estimation. |
| [US8224866B2](https://patents.google.com/patent/US8224866B2/en) | IBM | 2008-06-13 | Expired - Fee Related | none | Surfaced by a search on "rejected ideas". It is generic idea tracking, not investment-idea performance. |

**Not verified** (Google returned 503 after retries; leads only, not read):
- US8433638B2 (E*Trade, "investment performance data to investors");
- US20220129765A1 (Optimizely, "A/B testing using sequential hypothesis");
- CN121581250A (2025 application). Its search snippet mentions a counterfactual inference
  layer computing marginal contribution in portfolio investment. **Read this one first if
  this map is ever extended**: it is the only hit that names counterfactual marginal
  contribution in portfolio decisions.

**Searches run** on patents.google.com `xhr/query`, 2026-10-07; full-text unless a CPC is shown:

| Query | Results |
|---|---|
| (a1) leave-one-out / ablation / data denial × trading, contribution, source | 48,151 hits, all off-topic noise |
| (a2) counterfactual × trading/investment decision × source × attribution | 12 hits, mostly 2025-26 CN applications |
| (a3) "marginal contribution" × removing/excluding × trading | 617 hits, noise |
| (b1) counterfactual/LOO × attribution × signal, CPC G06Q40 | 120 hits; FICO, IBM |
| (b2) regret / missed opportunity / opportunity cost × hypothetical / not traded × decision, CPC G06Q40 | 113 hits; execution and auction patents, no regret ledger |
| (b3) paper/shadow/hypothetical portfolio × unexecuted/rejected × recommendation, CPC G06Q40 | 90 hits; none tracks the performance of declined decisions |
| (c1) analyst/forecaster accuracy × weighting × sector/horizon × consensus, CPC G06Q40 | 20,539 hits, noise at the top |
| (c2) crowdsourced forecasts × stake × contribution | Numerai US11704593B1 |
| (d1) always-valid / confidence sequence / e-value × experiment | Optimizely |
| (d2) assignee Optimizely × sequential | 9 hits |
| (e1) hash chain / Merkle / append-only × investment decision × audit, CPC G06Q40 | 4 hits; Qomplx / Fractal "decision platform", nothing specific |

Patents were also found through web search (site:patents.google.com) for counterfactual
attribution of manager skill and for analyst-weighted consensus. The full-text queries are
noisy, and I did not run a classification-only (CPC-browsing) pass or a non-English pass.

### 2d. What could still be AEGIS-specific engineering

Most of what makes the AEGIS system good is careful engineering on known methods, not new
methods. Specifically:

- **Alternatives frozen before the outcome**, not reconstructed afterwards. Prior art for the
  pieces: Perold's paper portfolio at decision prices, decision-time logging for counterfactual
  analysis ([Bottou et al. 2013](https://www.jmlr.org/papers/v14/bottou13a.html)), and hash
  commitment.
- **Every regret a signed pairwise difference that is mean zero under the null**, enforced by a
  test. Prior art: Diebold-Mariano, swap regret, White.
- **Abstentions split by why the plan did not trade**, each cohort graded as an admissible book
  (scaled to the gross cap) against SPY and a same-band control. Prior art: Perold for gated
  names, Brinson and Cabot for selection, and matched controls.
- **Honesty labels**: `TRUST_AT_63`, `NOT_PERSISTENT_OOS`, the approximation flag when weights
  are renormalised, and refusal to sum cohorts. This is governance, not method.
- **Leave-one-source-out gated on a replay check, with typed refusals.** This is the one item
  I could not match to prior art (§4).

---

## 3. Risk map

One label per row: `COMMON / OLD` · `KNOWN BUT DIFFERENT` ·
`POTENTIALLY DISTINCTIVE IMPLEMENTATION DETAIL` · `NEEDS COUNSEL`.

| # | Component / sub-mechanism (AEGIS file) | Label | Closest prior art | Why |
|---|---|---|---|---|
| 1 | Opportunity Score as a fixed-weight composite (`signal_analytics.py:290`); Edge Vector as a ten-field object (design only, roadmap 112-117) | COMMON / OLD | [US8296211B2 Bdellium (expired)](https://patents.google.com/patent/US8296211B2/en); [Piotroski 2000](https://doi.org/10.2307/2672906) (record only); [Grinold 1989](https://doi.org/10.3905/jpm.1989.409211) (record only) | A weighted sum of normalised metrics is decades old. No Edge Vector field list exists to evaluate, and Q and X are undefined in the tree. |
| 2 | Edge fields that exist: direction separate from magnitude, MoveScore σ63·√21·√(2/π), freshness age (`opportunities.py:22-25, 206-214`) | COMMON / OLD | [Christoffersen & Diebold 2006](https://doi.org/10.1287/mnsc.1060.0520); [Pesaran & Timmermann 1992](https://doi.org/10.1080/07350015.1992.10509922); [StarMine SmartEstimates](https://www.lseg.com/en/data-analytics/financial-data/analytics/quantitative-analytics/starmine-smartestimates) | Splitting direction from volatility is standard; √(2/π)σ is the mean absolute value of a normal; recency weighting is StarMine's published practice. |
| 3 | MDC = utility(plan) − utility(plan without source), per session, labelled `TRUST_AT_63` (`regret_ledger.py:412-436, 549-571`) | COMMON / OLD | [ECMWF OSEs](https://www.ecmwf.int/sites/default/files/elibrary/2019/18859-global-observing-system-experiments-ecmwf-assimilation-system.pdf); [Lei et al. 2018 (LOCO)](https://doi.org/10.1080/01621459.2017.1307116); [Numerai TC post](https://forum.numer.ai/t/true-contribution-details/5128) | Withhold one input stream, re-run the pipeline, score the difference: that is data denial. Numerai describes LOO as the approach TC replaced. Method caveat: LOO understates redundant sources ([Data Shapley](https://arxiv.org/abs/1904.02868)). |
| 4 | MMC-style neutralised contribution (discussed in the owner review, not built) | COMMON / OLD | [Numerai MMC](https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc); [Karels & Sun 2013](https://www.msci.com/documents/10199/c6e5e3f7-cd44-4322-aeb5-331e20e2afb7); [US7890408B2 (expired)](https://patents.google.com/patent/US7890408B2/en) | Orthogonalising against the ensemble or the risk model is published and was patented, now expired. |
| 5 | Exact linear-SHAP split of E[r] (`expected_return.py:11-13, 336`) | COMMON / OLD | [Lundberg & Lee 2017](https://arxiv.org/abs/1705.07874); Shapley 1953 ([summary](https://en.wikipedia.org/wiki/Shapley_value)) | φ_c = w_c(x_c − baseline_c) is the exact Shapley value of a linear model. |
| 6 | Marginal (add one) vs leave-one-out (remove last), interaction printed, no single number when they disagree (`lane_autopsy.py:20-45, 325`) | COMMON / OLD | [Grömping 2007](https://doi.org/10.1198/000313007X188252) (record only); [BHB 1986](https://doi.org/10.2469/faj.v42.n4.39) | First-in and last-in are the two bounds of relative importance; the residual is Brinson's interaction term. |
| 7 | **Leave-one-source-out gated on a replay check, with typed refusals** (`decision_story.py:196-224, 329-338, 556-612, 759-776`) | POTENTIALLY DISTINCTIVE IMPLEMENTATION DETAIL | Nearest: [Fowler 2005 (replay)](https://martinfowler.com/eaaDev/EventSourcing.html); [ECMWF OSEs](https://www.ecmwf.int/sites/default/files/elibrary/2019/18859-global-observing-system-experiments-ecmwf-assimilation-system.pdf); [Numerai TC](https://forum.numer.ai/t/true-contribution-details/5128) | Replay and data denial are old. I found nothing that gates each counterfactual on replay fidelity and emits typed `NOT_SEPARABLE` / `IDENTICAL_NOT_READ` results from a checked source map. Narrow mechanism in §4. |
| 8 | News "add one in" tilt at the contract's earned trust and at full trust (`plan_plus_shadow_news`, `decision_story.py:650-661`; `regret_ledger.py:32`) | KNOWN BUT DIFFERENT | [Numerai MMC](https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc); [ECMWF OSEs](https://www.ecmwf.int/sites/default/files/elibrary/2019/18859-global-observing-system-experiments-ecmwf-assimilation-system.pdf) | Asking what an unused input would add is the forward half of ablation. Scaling the tilt by trust from a frozen contract row is AEGIS's variant. |
| 9 | Alternative menu frozen before the outcome: input cut at `asof`, no wall-clock, per-row sha256, per-decision aggregate seal, deterministic outcome ids (`decision_story.py:120, 174-194, 396, 714-778`) | KNOWN BUT DIFFERENT | [Perold 1988](https://doi.org/10.3905/jpm.1988.409150) via [Hasbrouck](https://pages.stern.nyu.edu/~jhasbrou/Teaching/POST%202015%20Fall/classNotes/STPPTradingCosts.pdf); [Bottou et al. 2013](https://arxiv.org/abs/1209.2355); [Haber & Stornetta 1991](https://doi.org/10.1007/BF00196791) | Freezing the comparator set before outcomes removes hindsight choice. The pieces (decision-time paper portfolio, logging for counterfactual analysis, hash commitment) are each old. Cabot and Inalytics reconstruct after the fact, which is the difference. |
| 10 | Every regret is a signed outcome(alt) − outcome(actual), no `max`; mean zero under a martingale null, pinned by test (`regret_ledger.py:154-200`; test `:277`) | KNOWN BUT DIFFERENT | [Diebold & Mariano 1995](https://doi.org/10.1080/07350015.1995.10524599); [Blum & Mansour 2007](https://www.jmlr.org/papers/v8/blum07a.html); [White 2000](https://doi.org/10.1111/1468-0262.00152) | A signed loss differential against one pre-declared comparator is standard. White formalised the max-over-menu bias that review F1 found again. |
| 11 | Direction regret (`no_trade − actual`) and sizing regret (`buy_default − actual`) | KNOWN BUT DIFFERENT | [Cabot / FactSet](https://insight.factset.com/quantifying-portfolio-managers-skills-for-a-more-vibrant-active-equities-industry); [Inalytics 2009](https://thehedgefundjournal.com/identifying-manager-skill/) | Buy and sizing skill against counterfactual portfolios has been sold since about 2006. AEGIS works per decision, before the outcome, and net of a liquidity-band cost model. |
| 12 | Timing regret: traded delta entered at the next open vs the reference entry, same exit | COMMON / OLD | [Perold 1988](https://doi.org/10.3905/jpm.1988.409150); [Hasbrouck notes](https://pages.stern.nyu.edu/~jhasbrou/Teaching/POST%202015%20Fall/classNotes/STPPTradingCosts.pdf) | This is IS delay cost on a paper trade. |
| 13 | Exit regret: `hold` vs `exit_now` per held line at 5/21/63 sessions | KNOWN BUT DIFFERENT | [Akepanidtaworn et al. 2023](https://doi.org/10.1111/jofi.13271) (via [MR](https://marginalrevolution.com/marginalrevolution/2019/01/selling-fast-buying-slow-bias.html)); Cabot "Sell Skill" | Sell decisions against a counterfactual (random sell, or hold) are published. AEGIS's version is per line and fixed before the outcome. |
| 14 | *(Not built)* portfolio-level hypothetical book with equalised holding periods / a common target holding period | NEEDS COUNSEL | [US7756769B2 (Cabot), Active to 2028-01-13](https://patents.google.com/patent/US7756769B2/en) | Claims 1, 14, 27 and 9 read directly on this construction. |
| 15 | *(Not built)* benchmark-neutral simulated portfolio splitting selection / initial sizing / change in sizing (especially computed with GPU matrix calculation) | NEEDS COUNSEL | [US12032652B1 (Inalytics), Active to 2043-04-03](https://patents.google.com/patent/US12032652B1/en) | The independent claims cover neutral-weight simulated states; dependent claims 11-17 cover the selection and sizing split. |
| 16 | Selection regret: taken book vs next-ranked name not taken, one row per (session, selector), each at its own cost band (`regret_ledger.py:452-472`) | KNOWN BUT DIFFERENT | [Odean 1999](https://doi.org/10.1257/aer.89.5.1279) (record only); [Blum & Mansour 2007](https://www.jmlr.org/papers/v8/blum07a.html) | Comparing what was bought with what was passed over is classic. The "next-ranked" rule fixes the comparator before the outcome. |
| 17 | Abstention regret: HOLD/REFUSE graded against a frozen BUY counterfactual (`decision_story.py:1-14`; `regret_ledger.py:195-197`) | KNOWN BUT DIFFERENT | [Perold 1988](https://doi.org/10.3905/jpm.1988.409150) (opportunity cost); [El-Yaniv & Wiener 2010](https://www.jmlr.org/papers/v11/el-yaniv10a.html); [Yang et al. 2024](https://arxiv.org/abs/2402.15127); [alpha capture](https://en.wikipedia.org/wiki/Alpha_capture_system); [FICO US8682762B2](https://patents.google.com/patent/US8682762B2/en) | Execution, machine learning and bandits all price not acting. AEGIS differs because a price-taker observes the untaken outcome, so no estimator is needed. |
| 18 | Abstentions split by reason (picked_blocked, shortlist_not_taken, ranker_pool, held_resize), each scaled to `PROBE_GROSS_CAP`, net of SPY and of a same-band control, never summed (`regret_ledger.py:22-25, 474-492`) | KNOWN BUT DIFFERENT | [Perold 1988](https://doi.org/10.3905/jpm.1988.409150) for blocked names; [BHB 1986](https://doi.org/10.2469/faj.v42.n4.39) for selection | Each piece is standard. The mapping from cohort to counterfactual weight, and the scaling to the admissible cap, are sound AEGIS choices that nobody I found claims. |
| 19 | Arm reputation: held-out Brier skill, `n/(n+k)` shrink, floor 0, γ, normalised; sleeping-experts renormalisation; reputation blend only if out-of-sample better than equal weights (`forecast_reputation.py:1-46, 265-281`; `expected_return.py:30-46`) | COMMON / OLD | [Brier 1950](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2) (record only); [Bühlmann 1967](https://en.wikipedia.org/wiki/B%C3%BChlmann_model); [Bates & Granger 1969](https://doi.org/10.1057/jors.1969.103) (record only); [Freund et al. 1997](https://doi.org/10.1145/258533.258616) (record only); [StarMine US6510419B1 (expired)](https://patents.google.com/patent/US6510419B1/en) | Accuracy-weighted combination with credibility shrinkage is old. StarMine's 1998 claim covers analyst weights from historical accuracy, and has expired. |
| 20 | Logit pool `sigmoid(κ Σ w logit p)`, κ tuned in both directions (`forecast_reputation.py:292-310`) | COMMON / OLD | [Satopää et al. 2014](https://doi.org/10.1016/j.ijforecast.2013.09.009); [Baron et al. 2014](https://doi.org/10.1287/deca.2014.0293) | This is the Good Judgment Project's logit aggregator with an extremizing exponent. |
| 21 | Conditional analyst reputation: firm → sector → global shrinkage, weight in [0.5, 1.5], Kish n_eff (`analyst_reputation.py:1-55`) | COMMON / OLD | [Bühlmann 1967](https://doi.org/10.1017/S0515036100008989); [Giacomini & White 2006](https://doi.org/10.1111/j.1468-0262.2006.00718.x) (record only); [Jacobs et al. 1991](https://doi.org/10.1162/neco.1991.3.1.79) (record only); [US20040133497A1 (abandoned, published 2004)](https://patents.google.com/patent/US20040133497A1/en) | Hierarchical credibility and context-conditional weighting are old. Ranking advice sources by past performance was published in 2004. |
| 22 | Persistence gate and `REPUTATION_WEIGHT: NOT_PERSISTENT_OOS` label (`analyst_reputation.py:421-470`) | KNOWN BUT DIFFERENT | [Bradshaw, Brown & Huang 2013](https://ideas.repec.org/a/spr/reaccs/v18y2013i4d10.1007_s11142-012-9216-5.html) | AEGIS's own negative agrees with their weak target-price persistence. Publishing the failed weight as labelled plumbing is governance, not method. |
| 23 | *(Not built)* payouts to external forecasters ranked by stake and accuracy thresholds | NEEDS COUNSEL | [US11704593B1 (Numerai), Active to 2038-03-27](https://patents.google.com/patent/US11704593B1/en) | Only matters if AEGIS ever pays outside contributors. The claims are specific: stakes, logloss thresholds, smart-contract tokens. |
| 24 | Contextual bandit over source / policy weights (deferred until 63 regret sessions; roadmap line 303) | COMMON / OLD | [Li et al. 2010](https://arxiv.org/abs/1003.0146); [Auer et al. 2002](https://doi.org/10.1023/A:1013689704352) (record only); [Dudík et al. 2011](https://arxiv.org/abs/1103.4601) | Off the shelf. The AEGIS-specific trap, a raw-P&L reward, is already written down in `docs/research_notes/2026-10-06/borrow_from_outside_2026-10-06.md:36`. |
| 25 | Matched-null regret triple, refusing a null whose universe, cost or menu hash differs (`research_gym/regret.py:1-45`) | KNOWN BUT DIFFERENT | [White 2000](https://doi.org/10.1111/1468-0262.00152) (record only); [US7644011B2 (random-portfolio null, expired)](https://patents.google.com/patent/US7644011B2/en) | Best-of-menu bias and random-portfolio nulls are known. The refusal on a mismatched hash is hygiene. |
| 26 | Sequential evidence: e-process per hypothesis, confidence sequence, e-BH (design only) | COMMON / OLD | [Howard et al. 2021](https://arxiv.org/abs/1810.08240); [Ramdas et al. 2023](https://arxiv.org/abs/2210.01948); [Vovk & Wang 2021](https://arxiv.org/abs/1912.06116); [Wang & Ramdas](https://arxiv.org/abs/2009.02824); [Johari et al. 2022](https://arxiv.org/abs/1512.04922); Optimizely [US10585778B2](https://patents.google.com/patent/US10585778B2/en) (reset policy for web tests, a different construction) | Published methods with reference implementations. Nothing is built yet. |
| 27 | One e-value per non-overlapping date block for overlapping-horizon rows; at least 200 scored rows before computing (design only) | KNOWN BUT DIFFERENT | [Waudby-Smith & Ramdas](https://arxiv.org/abs/2010.09686); [Howard et al. 2021](https://arxiv.org/abs/1810.08240) | The martingale tolerates dependence, but overlapping rows inflate effective n. Collapsing to blocks is standard finance practice, applied here to e-processes. |
| 28 | Decision Story id chain with abstention ids as first-class nodes (`decision_story.py:16-27, 174-194`) | COMMON / OLD | [W3C PROV-DM](https://www.w3.org/TR/prov-dm/); [Singh et al.](https://arxiv.org/abs/1804.05741); [Fowler 2005](https://martinfowler.com/eaaDev/EventSourcing.html) | Provenance from inputs to decision to action is standard. A "no action" node is just another activity. |
| 29 | Append-only monthly JSONL, per-row sha256 seals, order links appended rather than rewritten (`decision_story.py:29-35, 120-123`) | COMMON / OLD | [Haber & Stornetta 1991](https://doi.org/10.1007/BF00196791) (record only); [RFC 6962](https://datatracker.ietf.org/doc/html/rfc6962) / [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162) | Hash-committed append-only logs. CT adds Merkle consistency proofs, which AEGIS lacks. |
| 30 | Co-coverage peer-return propagation (`graph_propagation.py:1-40`) | COMMON / OLD | [Ali & Hirshleifer 2020](https://doi.org/10.1016/j.jfineco.2019.10.007) (record only); [Cohen & Frazzini 2008](https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns); [Feng et al. 2019](https://arxiv.org/abs/1809.09441) | Shared-analyst-coverage spillover is a published anomaly; the module calls itself "the plainest version". |

Tally: 15 `COMMON / OLD`, 11 `KNOWN BUT DIFFERENT`, 1 `POTENTIALLY DISTINCTIVE IMPLEMENTATION
DETAIL`, 3 `NEEDS COUNSEL`. All three NEEDS COUNSEL rows describe things AEGIS has **not**
built.

---

## 4. The one potentially distinctive implementation detail, stated narrowly

**Mechanism: leave-one-source-out (LOSO) counterfactual decisions gated on a replay check,
with typed refusals.** The claim, if there is one, is the refusal discipline below, not
"attributing trades to sources".

1. **Replay before counterfactual.** Re-run the deterministic decision function from the
   decision's own frozen scoring inputs. Require the result to reproduce the live pre-gate
   target weights for every name to |Δw| ≤ 1e-9 (`replay_check`, `decision_story.py:329-338`).
   On mismatch, *every* LOSO row of that decision cycle becomes `NOT_SEPARABLE`, carrying the
   count of differing weights. The receipt prints `replay MISMATCH`, and a test pins it
   (`test_a_drifted_replay_is_a_red_line_not_a_silent_mismatch`, test file `:567`).
2. **A source map checked against the decision layer's own registry.** A declared table maps
   each source to the decision function's components (`SOURCE_COMPONENTS`, `:82-91`).
   `mapping_check` (`:196-205`) derives its test from the decision layer's own declarations,
   `expected_return.COMPONENTS` and `NOT_READ_BY_DESIGN`. It refuses when the map names
   components that no longer exist.
3. **Per-name separability.** A name is `NOT_SEPARABLE` for source s in three cases:
   - (a) an upstream stage that is not re-executed (the candidate funnel) ranked or filtered
     on s, judged by matching the funnel's recorded `evidence_basis` (`funnel_separable`,
     `:207-224`);
   - (b) a downstream risk gate bound, and its behaviour on the counterfactual book is not
     modelled (`gate_bound_names`, `:606-611`);
   - (c) the source's components carry mixed content (LLM catalyst names).
4. **Provably unread means zero, by declaration.** When the decision function's own
   `NOT_READ_BY_DESIGN` table shows s is not read, and no upstream stage used it, the row is
   `IDENTICAL_NOT_READ`: contribution zero by construction (`:584-590`). The question "what
   would s add?" goes to a separate frozen add-one-in alternative (`plan_plus_shadow_news`).
5. **Approximations are labelled.** Renormalising weights over the remaining components is
   exact under equal weights. It is flagged as an approximation under reputation weights
   (`er_names_minus`, `:227-273`).

**Why it might matter.** It turns "contribution of source s" from a number that is always
produced into a typed result with machine-readable refusal reasons. Data-denial OSEs, LOCO,
SHAP and Numerai's TC all assume the pipeline can be re-run, or differentiated, end to end;
none of the sources I read addresses partial re-execution.

**What weakens it.**
- Replay determinism checks ("golden master" or differential tests) are routine in software
  engineering. I did not search the software-testing or MLOps literature.
- To someone combining event sourcing with ablation, it may look like an obvious thing to try.
- The code has been public on `origin/main` since commit `951719f9`
  (`git log --diff-filter=A` dates `decision_story.py` to 2026-10-07 03:22 +08:00).
  Git does not record when it was pushed.

What to do about any of this is a question for counsel, not for an engineer. The dated commits
and `docs/reviews/REVIEW_2026-10-06_C11_DECISION_STORY_REGRET.md` are the record of when it was
built.

**What I do *not* list as distinctive.** These are each plausibly useful, and each has the
prior art named in §3:
- frozen alternatives (rows 9-10);
- reason-coded abstention cohorts (row 18);
- the news tilt at earned trust (row 8);
- the date-block e-values (row 27).

---

## 5. Method notes the prior art implies (for the builders, not for counsel)

1. **LOO understates redundant sources** ([Data Shapley](https://arxiv.org/abs/1904.02868)).
   Analyst revisions and momentum are correlated, so `mdc_analyst` and `mdc_price_momentum`
   will each read low. Print the marginal (add-one) number beside the LOO number for MDC, as
   `lane_autopsy` already does. Treat a large gap between them as the interaction, not as a
   contribution.
2. **Full information holds only while AEGIS is a price-taker.** The BUY counterfactual of an
   illiquid name has no market impact in the ledger. The liquidity-band cost and the same-band
   control are the only defences. If any book's size grows, the impact model becomes the
   measurement.
3. **StarMine's persistence result does not transfer.** StarMine reports persistence for EPS
   estimates. Bradshaw-Brown-Huang find only "economically weak" persistence for target prices,
   which is AEGIS's input. AEGIS's own −0.31 split-half result is consistent with that.
   Reputation on targets should stay labelled as plumbing until a forward test says otherwise.
4. **`TRUST_AT_63` is a fixed-n rule.** The e-process design in the 2026-09-21 note would let
   the display update every session without a penalty for looking. Methods and reference
   implementations exist ([Waudby-Smith & Ramdas](https://arxiv.org/abs/2010.09686) for bounded
   net returns).
5. **Do not call MDC "MMC".** In Numerai's vocabulary MMC is a prediction-space residual
   covariance. AEGIS's number is a decision-space LOO utility difference, which is closer to a
   data-denial experiment than to Numerai's MMC.

---

## 6. Sources (all fetched 2026-10-07)

**Notation.** `[page]` means content was read (WebFetch, or a PDF read via pdftotext).
`[crossref]` means only the bibliographic record was verified, at
`https://api.crossref.org/works/<DOI>`; content claims attached to these come from memory and
are kept generic. `[patent]` means the record was read through
`https://patents.google.com/xhr/result?id=patent/<n>/en`.

**Web pages and PDFs [page]**
1. https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc
2. https://docs.numer.ai/numerai-tournament/scoring/true-contribution-tc. It served the MMC
   content; no TC section was present. Used item 4 instead.
3. https://docs.numer.ai/numerai-tournament/scoring/feature-neutral-correlation
4. https://forum.numer.ai/t/true-contribution-details/5128 (mdo, 2022-03-22)
5. https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf
6. https://repository.library.noaa.gov/view/noaa/33800/noaa_33800_DS1.pdf. This turned out to
   be a 1988 NWS technical attachment (McNulty) that cites Brier 1950, not Brier itself.
7. https://www.wpc.ncep.noaa.gov/research/amsver/tsld018.htm (full Brier 1950 and Murphy 1973 citations)
8. https://arxiv.org/abs/2005.01835
9. https://arxiv.org/abs/1705.07874
10. https://arxiv.org/abs/1604.04173 and https://www.stat.cmu.edu/~ryantibs/papers/conformal.pdf
11. https://arxiv.org/abs/1904.02868
12. https://en.wikipedia.org/wiki/Shapley_value
13. https://arxiv.org/abs/1103.4601
14. https://arxiv.org/abs/1502.02362
15. https://arxiv.org/abs/1003.0146
16. https://www.cambridge.org/core/books/prediction-learning-and-games/A05C9F6ABC752FAB8954C885D0065C8F
17. https://www.jmlr.org/papers/v8/blum07a.html
18. https://arxiv.org/abs/1810.08240
19. https://arxiv.org/abs/2210.01948
20. https://arxiv.org/abs/1912.06116
21. https://arxiv.org/abs/1906.07801
22. https://arxiv.org/abs/2010.09686
23. https://arxiv.org/abs/2009.02824
24. https://arxiv.org/abs/1512.04922
25. https://martinfowler.com/eaaDev/EventSourcing.html
26. https://www.w3.org/TR/prov-dm/
27. https://datatracker.ietf.org/doc/html/rfc6962
28. https://www.rfc-editor.org/rfc/rfc9162
29. https://arxiv.org/abs/1804.05741
30. https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns
31. https://arxiv.org/abs/1809.09441
32. https://aclanthology.org/D14-1148/ (metadata only; the abstract was not on the page)
33. https://insight.factset.com/quantifying-portfolio-managers-skills-for-a-more-vibrant-active-equities-industry
34. https://pages.stern.nyu.edu/~jhasbrou/Teaching/POST%202015%20Fall/classNotes/STPPTradingCosts.pdf
35. https://www.quantitativebrokers.com/blog/a-brief-history-of-implementation-shortfall
36. https://www.lseg.com/en/data-analytics/financial-data/analytics/quantitative-analytics/starmine-smartestimates
37. https://ideas.repec.org/a/spr/reaccs/v18y2013i4d10.1007_s11142-012-9216-5.html
38. https://www.ecmwf.int/sites/default/files/elibrary/2019/18859-global-observing-system-experiments-ecmwf-assimilation-system.pdf
39. https://en.wikipedia.org/wiki/Alpha_capture_system
40. https://marginalrevolution.com/marginalrevolution/2019/01/selling-fast-buying-slow-bias.html
41. https://en.wikipedia.org/wiki/Performance_attribution
42. https://www.jmlr.org/papers/v11/el-yaniv10a.html
43. https://arxiv.org/abs/2402.15127
44. https://www.msci.com/documents/10199/c6e5e3f7-cd44-4322-aeb5-331e20e2afb7 (Karels & Sun, a chapter in *Rethinking Valuation and Pricing Models*, Elsevier 2013)
45. https://en.wikipedia.org/wiki/B%C3%BChlmann_model
46. https://economics.sas.upenn.edu/sites/default/files/filevault/event_papers/Satopaa_ungar.pdf
47. https://arxiv.org/abs/2607.28446 (CoLAS, 2026). The abstract shows no leave-one-modality-out attribution.
48. https://arxiv.org/abs/2608.06909 (agent trajectory attribution, 2026). Component-level LOO perturbation on agent trajectories, security-oriented.
49. https://arxiv.org/abs/1209.2355 and https://www.jmlr.org/papers/v14/bottou13a.html
50. https://thehedgefundjournal.com/identifying-manager-skill/ (Di Mascio & Savage, Sept 2009)

**Crossref records [crossref]** (DOIs; each resolved at api.crossref.org):

| DOI | Reference |
|---|---|
| 10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2 | Brier 1950 |
| 10.1175/1520-0450(1973)012<0595:ANVPOT>2.0.CO;2 | Murphy 1973 |
| 10.1198/016214506000001437 | Gneiting & Raftery 2007 |
| 10.1080/01621459.2017.1307116 | Lei et al. 2018 |
| 10.1023/A:1013689704352 | Auer, Cesa-Bianchi & Fischer 2002 |
| 10.1137/S0097539701398375 | Auer et al. 2002 |
| 10.1214/20-AOS1991 | Howard et al. 2021 |
| 10.1214/23-STS894 | Ramdas et al. 2023 |
| 10.1093/jrsssb/qkae011 | Grünwald, de Heide & Koolen 2024 |
| 10.1287/opre.2021.2135 | Johari et al. 2022 |
| 10.1214/aoms/1177731118 | Wald 1945 |
| 10.1007/BF00196791 | Haber & Stornetta 1991 |
| 10.1111/j.1540-6261.2008.01379.x | Cohen & Frazzini 2008 |
| 10.1016/j.jfineco.2019.10.007 | Ali & Hirshleifer 2020 |
| 10.2469/faj.v42.n4.39 | Brinson, Hood & Beebower 1986 |
| 10.3905/jpm.1988.409150 | Perold 1988 |
| 10.3905/jpm.1989.409211 | Grinold 1989 |
| 10.1007/s11142-012-9216-5 | Bradshaw, Brown & Huang 2013 |
| 10.1057/jors.1969.103 | Bates & Granger 1969 |
| 10.1017/S0515036100008989 | Bühlmann 1967 |
| 10.1016/j.ijforecast.2013.09.009 | Satopää et al. 2014 |
| 10.1287/deca.2014.0293 | Baron et al. 2014 |
| 10.1145/258533.258616 | Freund, Schapire, Singer & Warmuth 1997 |
| 10.1006/jcss.1997.1504 | Freund & Schapire 1997 |
| 10.1006/inco.1994.1009 | Littlestone & Warmuth 1994 |
| 10.1111/j.1467-9965.1991.tb00002.x | Cover 1991 |
| 10.1109/TIT.1970.1054406 | Chow 1970 |
| 10.3402/tellusa.v56i3.14413 | Langland & Baker 2004 |
| 10.2307/2232669 | Loomes & Sugden 1982 |
| 10.1257/aer.89.5.1279 | Odean 1999 |
| 10.1111/0022-1082.00072 | Odean 1998 |
| 10.1111/jofi.13271 | Akepanidtaworn et al. 2023 |
| 10.1080/07350015.1998.10524759 | Harvey, Leybourne & Newbold 1998 |
| 10.1080/07350015.1995.10524599 | Diebold & Mariano 1995 |
| 10.1111/j.1468-0262.2006.00718.x | Giacomini & White 2006 |
| 10.1080/07350015.1992.10509922 | Pesaran & Timmermann 1992 |
| 10.1287/mnsc.1060.0520 | Christoffersen & Diebold 2006 |
| 10.1002/j.1538-7305.1956.tb03809.x | Kelly 1956 |
| 10.1162/neco.1991.3.1.79 | Jacobs et al. 1991 |
| 10.1111/j.1468-2354.2005.00361.x | Elliott & Timmermann 2005 |
| 10.2307/2672906 | Piotroski 2000 |
| 10.1111/1468-0262.00152 | White 2000 |
| 10.1198/000313007X188252 | Grömping 2007 |
| 10.1093/imaman/5.1.45 | Hand & Henley 1993 |

**Patents [patent]:** 58 AEGIS-cited patents (§2c-i) and 25 new ones (§2c-ii), 83 in all.
There were also 11 `xhr/query` searches (§2c).

**Failed or blocked, and what I used instead**

| Source | What happened | Used instead |
|---|---|---|
| journals.ametsoc.org (Brier 1950; also reached via doi.org) | 403 | Crossref record, the NOAA WPC citation slide, and Gneiting & Raftery's attribution |
| apps.dtic.mil (Gneiting & Raftery technical report) | 403 | The UW-hosted PDF |
| www.rand.org RM-670 (Shapley) | 403 | Wikipedia's formula, axioms and citation |
| www.academia.edu (Satopää et al. 2014) | 403 | Crossref, plus the Satopää-Pemantle-Ungar PDF that describes it |
| patents.justia.com | 403 (curl probe) | Google Patents xhr |
| www.freepatentsonline.com | TLS failure | Google Patents xhr |
| dblp.org | Bot wall (Anubis) | Crossref |
| link.springer.com (Auer et al.) | Redirect to login | Crossref |
| encyclopediaofmath.org | 502 | Wikipedia |
| a.tellusjournals.se (Langland & Baker) | 503 | Crossref |
| northerntrust.com (Essentia Analytics) | 503 | Essentia not used as a source |
| globaltrading.net (Essentia Analytics) | Registration wall | Essentia not used as a source |
| essentia-analytics.com | Truncated | Essentia not used as a source |
| ipe.com (Inalytics) | 405 | Hedge Fund Journal, 2009 |
| factset.com news page (Cabot acquisition) | Title only | FactSet Insight |
| nber.org/papers/w13704 | Wrong paper: my guessed working-paper number | AQR page and Crossref for Cohen & Frazzini |
| api.semanticscholar.org | Records came back without abstracts | Not used for content |
| My guessed IEEE Access DOI for "Decision Provenance" | Resolved to another paper | arXiv 1804.05741 |
| patents.google.com/patent/<n> HTML | 503 "automated queries" page all session | The xhr endpoints, for everything |
| xhr endpoints: US8433638B2, US20220129765A1, CN121581250A | 503 after retries | **Unverified**, listed as leads only |
