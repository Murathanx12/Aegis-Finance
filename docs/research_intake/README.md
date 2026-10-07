# Research intake — the routine (2026-10-07)

**Input:** a topic or a paper (owner's brief, 2026-10-07: "use serious financial research as a
continuous source of theories" across portfolio construction, momentum, analyst revisions,
microstructure, risk, regime changes, volatility, earnings drift, insider information, attention,
institutional ownership, short interest, options, liquidity, seasonality, behavioural finance,
event studies, causal inference, online portfolio learning, portfolio optimisation — Markowitz
1952 is a foundational example, not a stopping point).

**Output:** one CARD file per topic/paper, `docs/research_intake/cards/<slug>.md`, following the
template below. A card is a research note, not a trial — it never registers a hypothesis and never
arms anything. A card that reaches `READY_TO_CELL` becomes the input to
`.claude/skills/pre-register-trial/SKILL.md`, which is a separate, later step with its own
tamper-evident commitment.

**Rule for the owner's reels, and for every other source: start from the REASON, not the
PATTERN.** A chart of a return series is not a hypothesis (Mission rule 2: "explaining a winner
afterwards is trivial; finding precursors observable beforehand is the research problem"). Before a
topic gets a card, it must survive one question: *what observation, available before the move, would
separate this mechanism from ordinary factor beta or noise?* If no answer exists, the card's verdict
is `NOT_A_HYPOTHESIS_YET` and nothing further is built on it.

## Before writing a card

1. Read `.claude/skills/pre-register-trial/SKILL.md` for the BLOCKED / DUPLICATE / RESURRECTION /
   PASS vocabulary — a card's "already tried" section uses the same discipline even though it does
   not run the linter itself (the linter runs at the pre-registration step, not the intake step).
2. Check for an existing corpse, in this order: `NEGATIVE_RESULTS.md` (repo root — **not**
   `docs/NEGATIVE_RESULTS.md`, that path does not exist, and looking for it there and concluding
   nothing is written down is exactly the "absence of a local object is not evidence of absence"
   trap this project paid for twice already), `docs/TRIALS/` (preregistrations and trial files, open
   and closed), `docs/research_notes/<date>/` (dated research passes — grep by mechanism keyword,
   not by date, since the relevant pass is rarely from today), and `mcp__optimus__brain_query` /
   `mcp__optimus__aegis_postmortems` if the Optimus MCP is reachable this session.
3. Check `docs/DATA_CATALOG.md` for what is already on disk before proposing a data pull. It is
   GENERATED (regenerate with `python -m backend.services.data_catalog`, or query it directly:
   `python -m backend.services.data_catalog --query <substring>`) and its full row list is a JSON
   receipt under `backend/data/optimus/data_catalog/`; the page itself is a summary (totals, the 40
   biggest files, duplicate/REPLAY findings), so a dataset not on that page is not necessarily
   absent — name the dataset from the services/docs that already consume it
   (`backend/services/crsp_pit_bridges.py`, `crsp_event_bridge.py`, `xs_ranker.py`, etc.) and cross-
   check against the catalog's totals, rather than trusting either source alone.
4. Check `backend/config.py`'s `HYP_LAB_FAMILIES` tuple for the fixed family taxonomy a theory
   might map to. A mechanism that matches none of them is `family_unmapped` — this is an honest
   answer (CLAUDE.md's "a generated label outside it is filed under UNMAPPED," review
   `docs/reviews/REVIEW_2026-10-06_C12_THEORY_CELLS.md` F6-F8), not a defect in the card.

## The card template

```
# CARD: <slug>

## Citation
Author(s), year, "exact title," journal/venue, volume(issue):pages, DOI if one exists.
Verified by fetching <URL> on <date>. If a fetch 403s, say so and name the independent
corroborating sources used instead (do not silently fall back to memory).

## The claim, in one sentence
<one sentence, no hedging, no methodology>

## Mechanism: why the inefficiency could exist, and who is on the other side
<the economic story — information asymmetry, risk premium, limits to arbitrage, behavioural
bias, estimation error, structural/regulatory friction — and name the counterparty: who is
forced to take the other side of the trade, or who is irrational/constrained in a way that
does not self-correct>

## Assumptions
<what has to be true for the mechanism to operate: market structure, investor composition,
data availability, no closer substitute>

## Measurable variables: the precursor observable BEFORE the move
<Mission rule 2 — this is the whole point of the card. Name the exact variable, its timing
relative to the move it is supposed to predict, and whether it is PIT-observable (known at
decision time, not reconstructed after the fact)>

## Sample period and markets
<what the original paper tested, and over what calendar span and universe>

## Effect size as published
<the number, in the paper's own units — bps/day, %/month, Sharpe, IC — never converted to a
different unit without saying so>

## Known failure modes and post-publication decay
<cite the replication/decay literature where it exists — McLean & Pontiff (2016), Harvey, Liu &
Zhu (2016) are the two standing references for "does this kind of result survive publication,"
cited once here and pointed to rather than re-derived on every card — plus any decay evidence
specific to this mechanism>

## What AEGIS has on disk to test it
<name the dataset(s) from docs/DATA_CATALOG.md / the services that consume them, with path>

## The falsifiable question and the declared primary metric, with costs
<one sentence, the ONE deciding metric, and which cost model prices it — this is a draft for a
future pre-registration, not a registration itself>

## Whether a corpse already exists here
<cite NEGATIVE_RESULTS.md / docs/TRIALS/ / a dated research note by path, or state "none found
this pass" — never silently assume novelty>

## hyp_lab family
<one of HYP_LAB_FAMILIES from backend/config.py, or `family_unmapped` with a one-line note on
the nearest existing family and why it doesn't fit>

## Verdict
READY_TO_CELL | NEEDS_DATA | ALREADY_CLOSED | NOT_A_HYPOTHESIS_YET
<one line of justification>
```

## Who runs this routine

Reuses `docs/research_notes/2026-10-07/social_media_theories_2026-10-07.md` §5's role split
(same shape, same reasoning, not re-derived here):

| step | who |
|---|---|
| topic/paper selection | owner, or the `QUEUE.md` ranking below |
| reconstruction + mechanism research + citation verification (this routine) | **Sonnet**, with web access — reading comprehension and literature search, not bulk extraction |
| bulk extraction if many papers/topics arrive at once | **DeepSeek** (the sole configured LLM provider) — cheap first pass, Sonnet still verifies |
| measurement design once a card reaches `READY_TO_CELL` (which control, which block unit, which multiplicity correction) | **Opus** — this is where the 2026-09-24 t-stat mistake and the exit-rule counterfactual mistake (both in `NEGATIVE_RESULTS.md`) actually happened; a design review before code is cheaper than after |
| pre-registration and the actual trial | the existing `pre-register-trial` skill and `docs/TRIALS/` machinery — not this routine |
| any claim on real capital | **Murat**, always — no LLM authority over real capital (CLAUDE.md, Three Licences) |

## What this routine is not

- Not a trial. No hypothesis here accrues data or gets evaluated until it is separately
  pre-registered.
- Not a backtest. A card may cite a published effect size; it never computes a new one.
- Not a data pull. `NEEDS_DATA` names a free source; it does not fetch it.
- Not permission to copy a published strategy. The owner's brief is explicit: extract the
  mechanism, the assumptions, the measurable variables, the known failure modes, the period, and
  how AEGIS could test it — never the parameters of someone else's backtest as a ready-to-trade
  rule.
