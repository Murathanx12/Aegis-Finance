# MARKET-GRAPH-1 — do LLM-extracted economic relationships know anything the correlation matrix does not?

**Pre-registration:** `Aegis module/TRIALS/PREREG_MARKET_GRAPH_1.md`, frozen at
commit `57cf834` before any edge existed.
**Free parameters enumerated:** `Aegis module/scripts/mg1_config.py`.
**Run artifacts:** `Aegis module/runs/MARKET-GRAPH-1/` (`tables.md` is generated
from the JSON; every number below is printed from it, none retyped).
**Date:** 2026-08-12. Resumed from a prior agent that died to an API stall with
the pipeline built and a 12-document pilot extracted.
**Cost:** $2.66 of a $12 allocation. **Extraction model:** `deepseek-v4-flash`
on all 3,637 calls, read off the response every time.

---

## 0. Verdict

| | pre-registered prior | result |
|---|---|---|
| **H1** — semantic edges add out-of-sample information about forward pairwise co-movement beyond the trailing correlation | ~50/50 | **DETECTABLE, and it survives every control.** Small: ΔR² = **+0.00097** against an MDE of 0.00062 (t = 4.35) on a baseline out-of-sample R² of 0.126 — a 0.8% relative improvement. On the 0.58% of pairs that carry an edge it removes **10.8%** of the baseline's own squared error (MDE 5.8%, t = 5.26). |
| **H2** — `semantic YES / numeric NO` pairs develop co-movement more often than matched `semantic NO / numeric NO` pairs | ~25/75 against | **HEADLINE DETECTABLE, DECISION RULE NOT MET.** +5.98pp against an MDE of 2.48pp (t = 6.76), surviving placebo, random edges, same-sector exclusion and same-2-digit-SIC exclusion — **but the pre-registration additionally requires the reversed-direction control, and that control is NOT detectable** (+0.0036 against MDE 0.0041). H2 is **not adopted**. |

**What this licenses:** research use of the semantic graph as one small
additional feature in a pairwise co-movement model, subject to the limits in §8.
**What it does not license:** any claim of transmission, causation, or lead-lag.
Correlation is symmetric, and the one arm designed to break that symmetry
could not. On this evidence the graph found **co-movement, not causation** —
which is the exact failure mode the pre-registration named in advance and the
reason it made H2 conditional on this control rather than on its own headline.

The reversed-direction number is 89% of its own MDE with the predicted sign.
Per §19 that is **not detectable, not a kill.** It is an underpowered null on
4,055 directed pairs, and the cheapest way to resolve it is more directed
edges — see §9.

---

## 1. What the previous agent left, and what its last words got wrong

The prior session ended on this diagnosis:

> *"Resolution is 13.9% — the binding constraint is exact-name matching
> ('Adobe' vs `ADOBE SYSTEMS INC`), not universe size."*

Measured on 36 edges from a 12-document pilot. On the full 16,094-edge corpus
the same exact-only matcher against the same legacy universe resolves **26.4%**,
not 13.9% — so most of the alarming number was small-sample noise, and it is
worth saying plainly that a diagnosis was drawn from n=36.

The attribution is also wrong. Fixing exact-name matching — apostrophe folding,
whole-token prefix matching in both directions, an alias table, a ticker
cross-reference — is worth **+1.73pp**. Rebuilding the universe is worth
**+2.37pp**. Together, +4.18pp. Neither is the binding constraint.

**The binding constraint is that a US 10-K mostly names companies that are not
US-listed securities.** The names on the page are Samsung, Sanofi, Sony,
Airbus, Nestlé, Tencent, SAP, Lenovo, Bayer, Panasonic, Roche, TSMC — and
BNSF Railway, McLane Company, Genentech, wholly-owned subsidiaries of listed
parents. **69.2% of every unresolved mention is not a CRSP security at any
date under any spelling**, and no amount of normalisation reaches it. The
remaining 30.8% is a universe-size limit, fixable by raising N=300 at O(N²)
cost in pairs.

That distinction was invisible in the first pass because the failures were
counted, not classified. The resolver now classifies every drop.

---

## 2. Two universe defects found and fixed, both of the same species

Both were found by looking at *who was in the panel*, never at an outcome.

**(a) Dual-class issuers were silently deleted.** `link_filings_by_cik` drops a
filing whose CIK maps to more than one permno — the right default, and the
wrong one for share classes: a dual-class issuer has two permnos under one CIK
*always*, so it was dropped *always*. The first universe contained **no
Alphabet at any of the 38 cut dates** while carrying Microsoft, Apple and Meta.
Fixed by re-linking the ambiguous residue to the permno with the larger market
cap at that date — a share-class choice read off the capitalisation table.
**780 filings recovered.**

**(b) The document gate was applied to universe membership.** A name entered
the panel only if its 10-K had linked through the EDGAR↔CRSP bridge, which is
an exact match on normalised company names — and CRSP abbreviates. `INTL
BUSINESS MACHS COR` never joins EDGAR's `INTL BUSINESS MACHINES`, so **IBM,
rank 24 by market cap, was absent from all 38 dates**, and with it 46 of every
300 names: measured overlap between the shipped universe and the true
top-300-eligible was **84.6%**. Substituting the 301st–346th largest companies
for the largest is a selection effect wearing a universe's clothes — the same
disease as a graph built on 13.9% of mentions, one stage earlier.

Membership is now market capitalisation alone. A 10-K is required only to make
a name an extraction *subject*; a name without one can still be the *target* of
somebody else's edge, which is what membership is for. Per-date document
coverage is now recorded rather than assumed: **250–257 of 300 names per date
(84.6%) are extraction subjects**, the rest are targets only.

The amendment is recorded with its date and reason in `mg1_config.py` and
`mg1_panel.py`. It was decided from composition — a named megacap was missing —
not from any outcome: the only grading run executed at that point carried 17
edge-instances and returned "not detectable" on every arm.

---

## 3. Three defects in the extraction path, all of the silent kind

**(a) Truncation misread as refusal — the one the brief warned about, at a
higher threshold.** With `max_tokens=2000`, 41 of 1,636 replies (2.5%) failed
to parse. **All 41 had `tokens_out` of exactly 2000.** Every single parse
failure was the cap; none was a refusal, none was a malformed answer. v4-flash
spends reasoning tokens from the same budget, so a 20-edge reply carrying 20
verbatim quotes does not fit. The loss is not random — it falls entirely on the
documents with the most relationships in them.

Raised to 6,000 and re-run on exactly the truncated documents
(`mg1_extract --repair`). **62 documents returned 1,137 edges — 18.3 per
document, against 4.0 per document for the corpus as a whole.** Confirmed: the
2.5% that was being thrown away was the richest 2.5%. Two documents (0.06%)
still hit 6,000 and are reported as such rather than counted as empty.
`finish_reason` is now stored on every record so this can never again be
inferred from a symptom.

**(b) The governor was the bottleneck, not the vendor.**
`research_budget.require()` reads spend out of the telemetry ledger — correct,
since an in-process counter resets on restart and a resumed campaign would
silently spend twice. But it re-parses the whole file on every call, and with a
concurrent 48-worker campaign writing to the same ledger it passed 20 MB
mid-run: extraction fell from ~250 documents/minute to ~13 while measured
vendor latency stayed flat at 2.9 s. The governor was not refusing anything; it
was reading. Now consulted at most once per 20 seconds across all workers,
while the two hard in-process ceilings stay checked on every single call. The
bounded exposure this buys is stated in the code: workers × TTL calls between
consultations, under $0.20 at 12 workers.

**(c) EDGAR fetching was single-threaded at 0.6 req/s** under a limiter that
permits 8. Now 8 workers behind the same shared limiter: 3,566 documents in
about 7 minutes instead of 90.

---

## 4. Resolution rate, before and after

Same 3,457-document / 16,094-edge corpus in every cell; one thing moved at a
time.

| universe | matcher | resolved / raw edges | rate |
|---|---|---|---|
| legacy | exact-only | 4,250 / 16,094 | **26.41%** |
| legacy | widened | 4,529 / 16,094 | 28.14% |
| rebuilt | exact-only | 4,632 / 16,094 | 28.78% |
| rebuilt | widened | 4,923 / 16,094 | **30.59%** |

- matcher alone: **+1.73pp**
- universe alone: **+2.37pp**
- both: **+4.18pp**

### Where the 11,090 unresolved mentions go

| bucket | n | share |
|---|---|---|
| `not_in_crsp` — foreign, private, subsidiary, brand. Irreducible. | 7,673 | **69.2%** |
| `outside_universe` — a real US-listed CRSP security, just not top-300 that date | 3,417 | 30.8% |

### Which route wrote each edge (edge-instances, both ends in the universe)

| route | n |
|---|---|
| `ticker` (PIT) | 8,409 |
| `name_pit` | 1,736 |
| `name_any` | 332 |
| `prefix` | 232 |
| `prefix_rev` | 205 |
| `rename` (alias table) | 9 |

The alias table is 17 entries, every one verified at startup against the
universe's own key set — an alias whose target does not exist is a rule that
runs green and does nothing, and this run prints the dead ones. All 17 are
live. `PHILIP MORRIS → ALTRIA` was in the inherited draft and was **removed**:
Philip Morris International has been separately listed since 2008, so that
alias would have merged two live tickers across the whole sample. The whole
table is in `mg1_resolve.py` and the `rename` route carries 9 edges, so any
reader can subtract it and re-read every number.

**10,923 edge-instances** with both ends in that date's universe, over **9,921
distinct (date, pair)** cells — **0.58% of the 1.70M graded pairs**.
Quote-verified 89.2%; mean confidence 0.884; 54.9% same-FF12-sector.

| edge type | n |
|---|---|
| competitor | 5,537 |
| customer | 3,382 |
| supplier | 982 |
| shared_technology | 859 |
| regulatory_exposure | 118 |
| shared_end_market | 45 |

---

## 5. The panel and the extraction

**Panel:** 38 quarterly cut dates, 2015-03-31 → 2024-06-28; top 300 by CRSP
market cap at each; 1,704,300 (date, pair) rows; 525 distinct permnos.
Co-movement is residual correlation after market and own-sector-excluding-self,
with betas fitted on the trailing 252 days and **applied** to the forward 126
days. corr(ρ_trail, ρ_fwd) = 0.343 — the baseline has real signal to beat.

**Extraction:** 3,566 documents fetched from EDGAR; Item 1 Business located
cleanly in 60.7%, `item1_loose` in 4.4%, keyword-window fallback in 18.4%, the
rest mixed — recorded per document, not assumed. 3,457 documents extracted,
16,094 raw edges, **48.3% of documents returned zero edges**. Across quintiles
of relationship vocabulary in the excerpt the zero-edge rate is 62.5%, 48.0%,
43.5%, 43.6%, 43.8% — it drops once, at the bottom quintile, and is then flat —
while mean edges per document climbs monotonically 2.1 → 6.7. So the extractor
is responsive to content, and the bulk of the silence is the model declining to
name a counterparty rather than the section finder handing it the wrong page.

3,637 calls; 16.1M uncached input tokens, 3.0M cached (15.8% hit — the frozen
system prefix is ~1,050 tokens of a ~5,000-token request, so this is close to
the ceiling that design allows), 1.4M output; **$2.66**.

---

## 6. H1 — incremental out-of-sample explanatory power

Primary metric exactly as pre-registered: per cut date, the mean squared-error
improvement from adding the semantic block to a ridge that already contains
`[ρ_trail, ρ_trail², same_sector]`, fitted walk-forward on strictly earlier cut
dates. **n for the SE is the number of graded cut dates (34), not the number of
pairs** — within a date every pair shares the same 126 days, so the collapse to
one number per date happens before any SE is taken, and the quarterly cadence
against a two-quarter window is handled by a Newey-West SE at two lags.
MDE = 2.80 × max(HAC, IID) SE.

| arm | dates | ΔR² | MDE | t | detectable | n |
|---|---|---|---|---|---|---|
| **semantic / all pairs** | 34 | **0.000968** | 0.000623 | **4.35** | **YES** | 1,524,900 pairs |
| semantic / cross-sector only | 34 | 0.000496 | 0.000384 | 3.62 | YES | 1,347,789 |
| semantic / cross-FF12 **and** cross-2-digit-SIC | 34 | 0.000464 | 0.000341 | 3.81 | YES | 1,325,885 |
| placebo_shuffled / all pairs | 34 | −5.1e−07 | 6.4e−06 | −0.22 | no | 1,524,900 |
| placebo_shuffled / cross-sector | 34 | −4.3e−07 | 7.7e−06 | −0.16 | no | 1,347,789 |
| placebo_shuffled / cross-FF12+SIC2 | 34 | −5.1e−07 | 8.6e−06 | −0.17 | no | 1,325,885 |
| random_matched_density / all pairs | 34 | 2.2e−06 | 8.0e−06 | 0.76 | no | 1,524,900 |
| random_matched_density / cross-sector | 34 | −4.9e−07 | 9.7e−06 | −0.14 | no | 1,347,789 |
| random_matched_density / cross-FF12+SIC2 | 34 | −4.0e−07 | 1.0e−05 | −0.11 | no | 1,325,885 |

Baseline out-of-sample R² = 0.1262; with the semantic block, 0.1271.

### Secondary: the same delta measured only on pairs that carry an edge

The model is still **fitted on the whole panel**, so the semantic block still
has to earn its place against 1.5M pairs; this only stops a 0.58%-coverage
feature from being graded mostly where it is identically zero. Reported as a
fraction of the baseline's own squared error **on those same pairs** — dividing
by the all-pair variance would print a much larger number that means nothing,
because edge-carrying pairs are not a random slice.

| arm | dates | MSE reduction | MDE | t | detectable | n |
|---|---|---|---|---|---|---|
| **semantic** | 34 | **10.8%** | 5.8% | **5.26** | **YES** | 8,917 pairs |
| placebo_shuffled | 34 | −0.017% | 0.13% | −0.36 | no | 8,917 |
| random_matched_density | 34 | +0.051% | 0.17% | 0.85 | no | 8,917 |

**Read:** the effect is unambiguously attached to *which companies the
relationships are between*. The placebo preserves the degree sequence and every
confidence value exactly and carries nothing; the random graph at matched
density carries nothing. It is not "the model got another dense feature block".

**It is also not a slow expensive sector dummy.** The pre-registration's own
warning was that a semantic edge rediscovering GICS is exactly that. FF12 has
twelve buckets, so this report adds a sharper arm the prereg did not name:
excluding same-FF12 *and* same-2-digit-SIC pairs. The effect survives at
essentially undiminished size (ΔR² 0.000464, t = 3.81). Whatever the edges
carry, it is not visible at 2-digit SIC.

---

## 7. H2 — the seductive cell, and the control that stopped it

Cases: pairs at date *t* with a semantic edge and **not** in the top decile of
trailing residual correlation. Controls: pairs with no edge, also outside the
top decile, matched **exactly** on (cut date, same-sector indicator, ρ_trail
decile), up to 5 per case, drawn without replacement by a seeded RNG. The
outcome is entry into the **top decile of forward residual correlation** in
(t, t+h]. Differenced **within each cut date** before any SE is taken (§18) —
never two separate significance claims.

| arm | cases / controls | dates | rate difference | MDE | t | detectable |
|---|---|---|---|---|---|---|
| **semantic / all pairs** | 6,265 / 31,325 | 38 | **+0.0598** | 0.0248 | **6.76** | **YES** |
| semantic / cross-sector | 3,083 / 15,415 | 38 | +0.0639 | 0.0318 | 5.63 | YES |
| semantic / cross-FF12+SIC2 | 2,871 / 14,355 | 38 | +0.0562 | 0.0324 | 4.85 | YES |
| placebo_shuffled / all pairs | 8,958 / 44,790 | 38 | +0.0057 | 0.0096 | 1.65 | no |
| placebo_shuffled / cross-sector | 8,017 / 40,085 | 38 | +0.0032 | 0.0115 | 0.78 | no |
| placebo_shuffled / cross-FF12+SIC2 | 7,909 / 39,545 | 38 | +0.0039 | 0.0101 | 1.08 | no |
| random_matched_density / all pairs | 8,941 / 44,705 | 38 | −0.0046 | 0.0093 | −1.39 | no |
| random_matched_density / cross-sector | 7,980 / 39,900 | 38 | −0.0049 | 0.0095 | −1.46 | no |
| random_matched_density / cross-FF12+SIC2 | 7,869 / 39,345 | 38 | −0.0027 | 0.0105 | −0.71 | no |

Same test on the continuous outcome (mean ρ_fwd difference):

| arm | cases / controls | dates | ρ difference | MDE | t | detectable |
|---|---|---|---|---|---|---|
| semantic | 6,265 / 31,325 | 38 | +0.0352 | 0.0128 | 7.70 | YES |
| placebo_shuffled | 8,958 / 44,790 | 38 | +0.0022 | 0.0045 | 1.39 | no |
| random_matched_density | 8,941 / 44,705 | 38 | −0.0023 | 0.0048 | −1.35 | no |

### The reversed-direction control

Correlation is symmetric, so a directed claim needs a directed statistic. For
every supplier/customer edge, the lead-lag cross-correlation of forward
residuals at lags 1–5 trading days in the **upstream → downstream** orientation
minus the same quantity **downstream → upstream**. Orientation comes from the
edge's own type and direction, never from the outcome; 187 edges whose
type/direction pair does not fix an orientation were dropped and counted rather
than guessed.

| statistic | dates | mean | MDE | t | detectable |
|---|---|---|---|---|---|
| **asymmetry (upstream-leads minus downstream-leads)** | 38 | **+0.00361** | 0.00407 | 2.48 | **no** |
| coin-flip placebo (same magnitudes, random sign) | 38 | −0.00192 | 0.00342 | −1.57 | no |

**This is the number that decides H2, and it does not clear its own bar.** The
pre-registration is explicit: *"H2 requires, in addition, that the
reversed-direction control behaves as predicted. Without it, `semantic YES /
numeric NO` is indistinguishable from 'the LLM emitted a plausible sentence.'"*
The sign is right and the magnitude is 89% of the MDE, which under §19 is
**not detectable, never a kill** — but it is also not the pre-registered
evidence, and the rule was written in advance precisely so that a large,
attractive headline could not talk its way past a missing control.

**H2 is recorded as NOT ADOPTED.** The honest reading of the whole section is
that `semantic YES / numeric NO` pairs really do develop co-movement at a
higher rate — that part is robust to all four other controls — but nothing here
distinguishes transmission from two companies simply being exposed to the same
thing.

---

## 8. Which controls ran, and what they cannot cover

**All five pre-registered controls ran.** None was skipped.

| control | ran? | outcome |
|---|---|---|
| 1. shuffled-semantic placebo (degree and confidence preserved) | **yes** | carries nothing, in every arm |
| 2. same-sector exclusion | **yes** | effect survives; a sharper cross-2-digit-SIC arm was added and it also survives |
| 3. random edges at matched density | **yes** | carries nothing, in every arm |
| 4. trailing-correlation-only baseline | **yes** | it is the reference in every delta; OOS R² 0.126 |
| 5. reversed-direction | **yes** | **not detectable** — the one that blocks H2 |

**Controls that did NOT run, and are therefore not passed:**

- **The exact-only matcher was not re-graded end to end.** `mg1_resolve
  --strict` exists and writes that graph, but H1/H2 were computed only on the
  widened graph. The widened matcher adds 291 of 4,923 resolved edges (5.9%),
  concentrated in `prefix`/`prefix_rev`/`rename`, so the exposure is small — but
  "small" is an argument, not a measurement, and it is recorded as unmeasured.
- **No sensitivity on `NUMERIC_YES_Q`, `HORIZON_DAYS` or `UNIVERSE_N`.** Each
  was fixed in advance and each was used exactly once. That is the correct
  discipline, and it also means the results are single-point.
- **No holdout beyond walk-forward.** Every cut date from the 5th onward is
  graded out of sample, but the whole 2015–2024 window was used.

**What the design cannot rule out, however many controls pass:**

- **Model-era priors.** The extractor reads a 2017 filing but is a 2026 model.
  EDGAR archives make the *document* point-in-time; they do not make the
  *reader* point-in-time. A model that knows which relationships mattered can
  favour them while quoting the 2017 text verbatim. The 89.2% quote-verification
  rate bounds fabrication, not hindsight. `LLM-LEAKAGE-PROBE-1` is the trial
  that addresses this and it is separate.
- **The graded graph is a biased subgraph.** 69% of extracted relationships
  never reach the panel because the counterparty is foreign, private or a
  subsidiary. Every number here describes relationships **among the 300 largest
  US-listed companies**, not relationships in general.
- **48.3% of documents produce no edge at all**, so the graph is also a
  statement about the half of filings this extractor is willing to speak about.
- **Nothing here has been costed, traded, or passed through G7.** ΔR² =
  0.00097 on pairwise correlation is not a return, and no step from here to a
  portfolio surface has been taken or estimated. Descriptive only, as
  pre-registered.

---

## 9. What would settle the open question, cheaply

The reversed-direction control failed on power, not on sign. It graded 4,055
directed pairs, drawn from 982 supplier and 3,382 customer edge-instances —
40% of the graph, the rest being symmetric types on which the control has
nothing to test. Three levers, in order of cost:

1. **Raise `UNIVERSE_N`.** 30.8% of unresolved mentions are real US-listed
   securities outside the top 300. Going to 1,000 costs O(N²) in pairs (≈500k
   per date against 45k) but would roughly double the directed edge count with
   no new LLM spend — the extraction is already paid for.
2. **Ask for directed edges specifically.** The extractor is type-agnostic and
   returned 5,537 competitor edges (symmetric by construction, useless to this
   control) against 4,364 directed ones. A second pass biased toward
   supply-chain language would move the ratio at roughly $1 per 1,000
   documents at current cache rates.
3. **Widen the lag grid.** Lags 1–5 assume the transmission is same-news-week.
   Supply-chain effects showing up in quarterly results would need lags out to
   20–60 days, which is free to compute from the residual cache already built.

None of these should be run as an extension of this trial. The parameters above
are frozen; changing them is a **new pre-registration with a new name**.

---

## 10. Files

| what | where |
|---|---|
| frozen parameters, with the one dated amendment | `Aegis module/scripts/mg1_config.py` |
| stage 1 — numeric spine, built before any edge exists | `scripts/mg1_panel.py` |
| stage 2 — point-in-time EDGAR text | `scripts/mg1_docs.py` |
| stage 3 — the extractor (frozen system prefix, `--repair`) | `scripts/mg1_extract.py` |
| stage 4 — name → permno, six routes, failure classification | `scripts/mg1_resolve.py` |
| stage 5 — H1, H2, five controls | `scripts/mg1_grade.py` |
| the resolution A/B | `scripts/mg1_resolution_ab.py` |
| table renderer (report numbers are printed, never retyped) | `scripts/mg1_tables.py` |
| run outputs | `Aegis module/runs/MARKET-GRAPH-1/` |

Reproduce:

```bash
cd "C:/Users/mrthn/Aegis module"
python -m scripts.mg1_panel
python -m scripts.mg1_docs --workers 8
python -m scripts.mg1_extract --workers 12
python -m scripts.mg1_extract --repair --workers 8
python -m scripts.mg1_resolve
python -m scripts.mg1_resolution_ab
python -m scripts.mg1_grade
python -m scripts.mg1_tables > runs/MARKET-GRAPH-1/tables.md
```
