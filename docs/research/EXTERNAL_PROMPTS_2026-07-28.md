# External AI research prompts — round 13 intake (2026-07-28)

Four prompts, one per model, each targeting a **different gap** and written against
that model's observed failure mode in the 2026-07-28 batch. Intake rules apply
(`EXTERNAL_RESEARCH_INTAKE.md`): responses are **hypotheses, not evidence**, and
nothing they say registers anything.

**Every prompt carries the same anti-fabrication clause**, because the last batch
produced: an unverifiable "FinLLM-Predict 12.3%" statistic, an unlocatable "Liu et
al. 2025", and a "retail pays an 18% speed tax" figure traced to a vendor press
release. One response also asserted a "terminal" look-ahead trap that the actual
literature has already solved.

---

## Prompt 1 — for GPT (its edge: methodology and framework extraction)

> I run a quantitative investment research program with an unusual constraint set,
> and I need you to extract **decision frameworks**, not stock ideas.
>
> Constraints: long-only, never short, no leverage, monthly rebalancing at most,
> US equities, one person, $100/month data budget. I have already tested and
> rejected 158 cross-sectional anomaly candidates using pre-registration, a hard
> 2004-2018 explore / 2019-2024 confirm wall, and deflated significance. My
> cost-killed shelf came back EMPTY — every large/mid-cap rejection was
> informational, not cost-driven. Published t-stats rank-correlate **−0.544** with
> my measured performance: fame predicts deadness.
>
> **Anti-fabrication clause: every factual claim must cite a real, locatable
> source with a URL. If you cannot verify something, write UNVERIFIED next to it.
> Do not invent paper titles, author names, or statistics. I will check.**
>
> Questions:
> 1. Among investors with 15+ year documented records of beating the S&P 500,
>    which ones used a method that is **specifiable as a rule set** rather than
>    discretionary judgment? For each, what is the rule set, and has anyone
>    published a factor decomposition of their returns (as Frazzini-Kabiller-Pedersen
>    did for Buffett)?
> 2. Buffett's alpha is explained by leverage 1.7:1 × Betting-Against-Beta ×
>    Quality-Minus-Junk. **Leverage is the active ingredient and I cannot use it.**
>    What does the evidence say about the unlevered, long-only QMJ/BAB long leg?
>    Is there a documented substitute for leverage that a no-margin investor can use
>    (holding period? concentration? sector tilt?) — with citations.
> 3. What is the strongest published argument that a **combination** of three
>    individually-marginal edges outperforms any one of them — and what is the
>    strongest argument that stacking marginal edges is just multiple testing in
>    disguise? Give me both sides with citations.
> 4. Design me an adversarial protocol: if I have a new strategy idea, what is the
>    sequence of tests that would kill it fastest and cheapest? I want the ordering
>    that maximises the probability of early death.

---

## Prompt 2 — for Gemini (failure mode: confident overclaiming — this prompt forces receipts)

> **Anti-fabrication clause, read first: every claim must cite a real, locatable
> source with a URL. Write UNVERIFIED beside anything you cannot source. Do not
> state confident conclusions you cannot back — I fact-checked your last response
> and your "LLM backtesting is a terminal trap" claim was overstated: Glasserman &
> Lin (arXiv 2309.17322) found the distraction effect exceeds look-ahead bias and
> published an anonymization procedure, and He/Lv/Manela/Wu (arXiv 2502.21206)
> released ChronoBERT/ChronoGPT, open-weight models trained only on
> point-in-time text. Please be more careful this round.**
>
> My question is about **failure**, specifically:
> 1. Document the **actual failure modes of retail and small-shop quantitative
>    investing**. Not theory — post-mortems, closed funds, published
>    disappointments. Who tried a systematic approach with a small budget, what
>    specifically killed them, and is there survivorship bias in what we hear?
> 2. **What is the realistic capacity and decay** of the strategies still claimed
>    to work at small scale? If an edge only exists in micro-caps, what does the
>    literature say about how much capital it absorbs before it disappears?
> 3. I want to build a **point-in-time news pipeline** on a $100/month budget. The
>    problem I have identified is **corpus contamination**: today's news archive is
>    a survivor's archive — coverage of companies that later died thins out, URLs
>    rot, retrieval is filtered by what stayed interesting. A chronologically
>    consistent model does not fix a contaminated corpus. **Is this problem
>    documented anywhere, and has anyone measured it?** If it has been measured,
>    how large is the bias?
> 4. What would you need to see, empirically, to conclude that a small operator
>    **should stop trying to beat the index**? Give me the specific falsification
>    criteria, not encouragement.

---

## Prompt 3 — for DeepSeek (its edge: non-English literature and open-source implementations)

> **Anti-fabrication clause, read first: your last response cited "FinLLM-Predict"
> with a 12.3% directional-accuracy improvement and a "Liu et al. 2025" sentiment
> study. I could not locate either. Please cite only sources you can name
> precisely enough for me to find, with URLs, and mark everything else UNVERIFIED.
> A correct "I don't know" is worth more to me than a plausible fabrication.**
>
> Where you are genuinely useful to me is coverage I cannot easily reach:
> 1. **Chinese, Japanese and Korean quantitative finance literature** on strategies
>    that beat a broad equity index long-only and unlevered. What is being
>    published in those markets that has not crossed into English-language finance
>    journals? Especially: regime/state-dependent allocation, commodity-equity
>    linkages, and retail-accessible factor implementations.
> 2. **Open-source implementations worth borrowing.** Concretely: which GitHub
>    projects actually implement point-in-time-safe backtesting with survivorship
>    handling, and which are toys? I care about correctness of the data layer, not
>    strategy cleverness. Name repos, star counts, last-commit recency, and the
>    specific thing each gets right or wrong.
> 3. I have verified that industrial metal returns predict aggregate equity returns
>    **with a sign flip by business-cycle state** (roughly −1.5%/month in
>    expansions, +0.5% in recessions, per one-standard-deviation metal move).
>    **Find me more state-dependent linkages of this shape** — cause-and-effect
>    relationships whose SIGN depends on regime rather than being fixed. Cite each.
> 4. What free, point-in-time-safe data exists that Western researchers routinely
>    overlook? Include Chinese and Japanese exchange/regulator sources.

---

## Prompt 4 — for Bigdata.com (its edge: an actual document database — use it as a document search, not an opinion engine)

> Use your **document retrieval** capability, not general knowledge. I want
> primary-source evidence, quoted, with document dates and identifiers. If a claim
> is not in a retrievable document, say so rather than filling the gap from
> training data.
>
> 1. Search **fund shareholder letters, annual reports and prospectuses** for
>    managers who have beaten the S&P 500 over 10+ years, and extract **what they
>    say their method is, in their own words.** I want quotes and document
>    citations, not summaries of what the press says about them.
> 2. Search **10-K risk factors and MD&A** for how companies describe their
>    **commodity input exposure** and hedging. I am trying to build a map of which
>    companies are genuinely exposed to which commodity, from primary disclosure
>    rather than sector labels. What fraction of companies quantify this exposure,
>    and in what form?
> 3. Retrieve **8-K filings under Items 1.03 (bankruptcy), 2.04 (obligation
>    acceleration) and 5.01 (change of control)** and tell me: what typically
>    precedes them in the same company's disclosure record over the prior 12 months?
>    I am looking for pre-distress disclosure signatures, not the distress event.
> 4. What do **broker research reports** say about the capacity and decay of
>    quality/low-volatility factor strategies since roughly 2018? I want the
>    sell-side view on whether these factors are crowded, with report dates.
>
> For every answer: document type, date, source, and a direct quote. Mark clearly
> where the retrieval returned nothing.

---

## Routing notes (for me, not for them)

- **Prompt 4 requires topped-up Bigdata.com credits** — the account returned "used
  up your credits" on 2026-07-28. It is pay-per-use, so it is a variable cost
  against the $100/month, not a subscription.
- Q3 in prompt 4 is deliberately aimed at the **successor design** that
  AI_PANEL_2026-07-28 §3.3 requires (matched non-filer control): pre-distress
  disclosure signatures are a *candidate matching variable*, not a signal.
- Prompt 2 Q3 (corpus contamination) is the **highest-value question in the whole
  batch.** If nobody has measured it, that is itself a publishable gap and it sits
  directly on the paper's methods lead.
- None of these responses may be cited as evidence. They are hypothesis intake.
  Anything that survives goes to `scripts/prior_check.py`, then pre-registration,
  then the wall — same as the other 158.
