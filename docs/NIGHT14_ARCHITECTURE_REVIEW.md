# The architecture review — 2026-08-12

Archive of Murat's review of the LLM layer, plus what I verified against it,
what I corrected, and what became a registered trial.

The review's central claim, and the reason it reorganised the night:

> **SWARM-1 is not testing the investment brain we have in mind. We built
> fourteen personas, not fourteen genuinely different information-processing
> systems.**

That is supported by our own measurements, taken before the review arrived:

| measured on LLM-SWARM-1 | value |
|---|---|
| records minted | 20,073 |
| `effective_distinct_ideas` ratio | **0.2996** |
| mean pairwise probability spread, same security x observable x horizon | **0.059** |
| honest abstentions | 27 of 8,014 calls |

Fourteen roles differing by 0.059 in probability is one forecaster wearing
fourteen hats. The review's diagnosis of the mechanism is the part worth
keeping: every role got the same point-in-time snapshot, was told it had **no
live feed**, and was forced into the same large output contract — scenarios,
price targets, multi-horizon probabilities — regardless of its information
class. A geopolitical analyst and a forensic accountant were made to answer the
same question in the same shape, so they answered it the same way.

---

## What I verified before acting on any of it

### 1. The models we have been calling do not exist

`GET https://api.deepseek.com/models` returns exactly two ids. The codebase
calls two different names. Reading `model` off the response body:

```
asked "deepseek-chat"     -> served deepseek-v4-flash
asked "deepseek-reasoner" -> served deepseek-v4-flash    <- SILENT ALIAS
asked "deepseek-v4-pro"   -> served deepseek-v4-pro
```

The review was right that V4 is the current generation. It cost two things:

- **A running arm was void.** The leakage probe's "chat vs reasoner" model
  comparison was v4-flash against itself, and would have reported *no model
  effect* — a null manufactured by a config bug. The agent was corrected
  mid-run, told to re-run paired as **flash vs pro**, and to store
  `served_model` on every record from now on.
- **Every dollar figure was wrong by 2.8x.** The price table priced two
  nonexistent models. Fixed, and the ledger now stores tokens (the fact the
  vendor reports) and recomputes dollars on read (a reconstruction from a table
  that drifts).

### 2. We have roughly four times more experimental headroom than I told him

| | before | verified |
|---|---|---|
| campaign spend, 10,866 calls | $16.08 | **$4.24** |
| per call | $0.0015 | **$0.00039** |
| remaining under the $40 ceiling | ~24,000 calls | **~91,000 calls** |

The vendor balance ($51.09) corroborates the corrected figure. My earlier
answer to "how much should I top up" was built on the wrong number.

### 3. Cached input is fifty times cheaper than a miss

v4-flash: `$0.0028` cached vs `$0.14` miss per Mtok. **A shared prompt prefix
across the arms of an experiment is worth more than any other cost
optimisation available to us** — and it happens to be exactly what a paired
arm design wants anyway.

---

## Where I disagree with the review

**One design flaw, in its strongest experiment.** `INTERNET-vs-SNAPSHOT-1`
proposes giving arm B tool-enabled web/news search and grading forward. Forward
is fine. But any historical version of that arm is **leakage by construction**:
a search executed today against a 2024 date returns the 2025-2026 index. This
is not a degree-of-contamination problem that careful prompting fixes — it is
the retrieval system answering a different question than the one asked.

So the tool-enabled arm is **forward-only**, or historical against an archived
point-in-time corpus, and every report must say which. It is registered that
way.

**One caution on the most exciting idea.** The review is right that
`semantic YES / statistical NO` — an economic relationship that exists before
correlation can see it — is the cell where an LLM could complement the engine
rather than duplicate it. It is also the cell where a hallucinated edge and a
real not-yet-priced edge look **identical**. An LLM will assert a relationship
between any two companies if asked. So `MARKET-GRAPH-1` carries a
reversed-direction control: if supplier->customer transmission is real,
customer->supplier at the same lag must be weaker. If both look equally good,
the model found co-movement, not causation.

**One number.** The review cites 22,607 forecasts collapsing to 6,772 effective
ideas. Our ledger holds 20,073 records; the ratio it quotes (0.2996) is ours and
is right.

---

## What I think is the sharpest point in the review

Not the graph, and not the NN. This:

> **p = 0.50 is rejected → the model learns to say 0.51.**

That rule was mine, added because the first WHY-MOVED batch produced 23 of 25
one-day claims at exactly 0.50. Banning the coin flip without offering an
alternative does not create information, it creates **fake precision** — and the
27-abstentions-in-8,014 number is the evidence that this is what happened.

The replacement is structural rather than prohibitive: freeze a **prior** before
the evidence, show the evidence, emit a **posterior**. `posterior == prior` is
then a first-class, informative answer — "this changed nothing" — instead of a
refusal to be scored. What gets graded is the **belief update**, and the
testable question becomes whether large updates predict abnormal outcomes.

That is the single change most likely to matter, and it costs nothing.

---

## What was registered tonight

Both passed the corpse linter against 331 prior experiments.

| trial | question | primary metric |
|---|---|---|
| **LLM-ARCHITECTURE-ARENA-1** | does varying the *information pipeline* buy more distinct information than varying the *persona*? | `effective_distinct_ideas` per dollar, per arm (leakage-free) |
| **MARKET-GRAPH-1** | do LLM-extracted economic relationships carry co-movement information the correlation matrix does not already have? | incremental out-of-sample explanatory power, beside its own MDE |

Arena arms: `A0 snapshot-persona (control)` · `A1 fine-grained chain` ·
`A2 prior->posterior belief update` · `A3 adversarial proposer/refuter` ·
`A4 tool-call retrieval (forward-only)` · `A5 v4-flash vs v4-pro, paired`.

**A0 is the control and A0 is the corpse.** The trial's job is to beat something
we already built and already measured, which is the only kind of comparison that
can retire it.

### The pre-declared null, so it cannot be reinterpreted later

If **no arm** beats A0 on distinct information per dollar, the finding is *the
ceiling belongs to the model, not the prompt* — and the correct response is to
stop buying diversity from DeepSeek and spend the budget on the graph and
teacher tracks instead. **That is a result, not a failure.**

### What none of this may do

Neither trial can give any arm production weight, specialist authority, or a
portfolio role. Amendment A5 binds unchanged: that requires resolved **forward**
records, and nothing resolves before **2026-08-16**. Immediate results are
allocation decisions about where to spend the next dollar — not evidence of
skill.

---

## On using the LLM as a judge

The review proposes it and then immediately fences it, correctly:

> LLM teaches semantics → NN learns patterns → **future reality supplies reward**.

Agreed, and the fence is the whole point. An LLM reward signal creates a system
optimised to impress the LLM. The licensed role is **critic**: given a
discovered pattern, propose the mechanism, the look-ahead path, the artifact
that could produce it, and the placebo that would kill it — then Aegis runs the
placebo. The LLM writes the kill test; it never awards the pass.
