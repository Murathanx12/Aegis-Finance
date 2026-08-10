# The research ↔ portfolio-management flywheel

Murat's correction, and the architecture it implies:

> *"research discovers what has evidence → Optimus uses that evidence to manage
> the portfolio → hundreds of shadow portfolios test alternative ways of using
> it → their outcomes create new research questions → validated improvements
> flow back into Optimus."*

Aegis had both halves and no connection between them. Thirty NIGHT verdicts,
eighty-nine pre-registrations and a 148-row graveyard lived in prose the PM
could not read; the PM shipped dollar figures the lab had never graded. This
document describes the loop that now exists, the one link that is still
one-directional, and where each piece lives.

```
        ┌──────────────────────────────────────────────────┐
        │                 RESEARCH LAB                     │
        │   pre-registration, corpse check, power check,   │
        │   placebo, adjudication → a verdict + receipts   │
        └───────────────────────┬──────────────────────────┘
                                │  writes evidence_grade,
                                │  permitted_role, reliability_weight
                                ▼
        ┌──────────────────────────────────────────────────┐
        │   SIGNAL REGISTRY   backend/data/signal_registry │
        │   30 signals · 11 CLOSED · 4 QUEUED · 15 usable  │
        │   enforced in code, not by memory                │
        └───────┬──────────────────────────────┬───────────┘
                │                              │
                ▼                              ▼
   ┌────────────────────────┐    ┌──────────────────────────────┐
   │  OPPORTUNITY FUNNEL    │    │      PORTFOLIO ARENA         │
   │  5,324 → 1,500 → 250   │    │  384 frozen genomes,         │
   │  → 40 → 25 candidates  │    │  manifest committed first    │
   └───────────┬────────────┘    └──────────────┬───────────────┘
               │                                │ finalists only
               ▼                                ▼
        ┌──────────────────────────────────────────────────┐
        │                  OPTIMUS PM                      │
        │   one solved portfolio over holdings+candidates   │
        │   attended recommendations, never an order        │
        └───────────────────────┬──────────────────────────┘
                                ▼
        ┌──────────────────────────────────────────────────┐
        │        FORWARD / SHADOW OUTCOME LEDGER           │
        │   every decision freezes what it knew and why    │
        └───────────────────────┬──────────────────────────┘
                                ▼
        ┌──────────────────────────────────────────────────┐
        │   LEARNING SAMPLES → deterministic reliability   │
        │   update → back to the REGISTRY (attended)       │
        └──────────────────────────────────────────────────┘
```

## The four rules that keep it from becoming a feedback loop

**1. Research constrains the search, in code.** The Arena's genome pool is
generated *from* the registry, so a closed mechanism has no binding and no
genome. The funnel asks `permits(signal_id, role)` before every ordering step.
`check_closed()` raises. None of this depends on anyone remembering a verdict.

**2. OBSERVATIONAL data still reaches the PM.** NIGHT-9's mandate is explicit —
research sets reliability *weights*, it does not block labelled information.
What research forbids is an ungraded number being *presented* as validated, so
every analyst-derived figure in the brief prints OBSERVATIONAL beside it.

**3. Synthetic and real never mix.** Synthetic worlds score the *instrument*
(can the search find a planted truth? how large a winner does it manufacture
from noise?). Real point-in-time history scores a *strategy*. Synthetic
profit is never evidence of alpha, and the reports keep them in separate
sections with that sentence in both.

**4. P&L never reaches the LLM's hands.** Outcomes write only to
`learning_samples.jsonl`. The single path from an outcome to a decision runs
through `update_reliability()` — deterministic, shrunk toward the prior,
capped at ±0.05 per update, and requiring 30 resolved samples before it will
calibrate anything at all. It returns a *proposal*; changing the registry is
an attended edit that leaves a diff. `record_outcome()` returns `None` on
purpose: a function that both records a P&L and hands it back is one refactor
away from being called inside a sizing routine.

## The link that is still one-directional — the honest gap

ARENA-1's `analyst_skill` world plants a genuine +8 %/yr analyst-revision
effect, above the Arena's measured detection threshold, and **the Arena did not
find it**: best analyst genome ranked 33rd, zero in the top 10.

That is the registry working as designed. `analyst_target_level_haircut` is
graded RISK_INPUT, so the generator only places it at weight 0.2 beside a
weight-1.0 picker — no analyst-*led* genome exists in the pool, so none can
win, even in a world where analysts are the truth.

**Consequence: the search can confirm what the lab believes and can never
overturn it.** Every corpse stays a corpse by construction rather than by
evidence.

The proposed fix, registered and not built: a **heresy sleeve** — a tagged set
of genomes that lead with a CLOSED or RISK_INPUT-only mechanism, excluded from
every selection rule, reported separately, unable to promote anything. They
exist so that if a corpse ever starts winning, something notices.

## Where each piece lives

| piece | path |
|---|---|
| Signal registry (data) | `backend/data/signal_registry.yaml` |
| Signal registry (enforcement) | `backend/services/signal_registry.py` |
| Book reconciliation | `backend/services/pm_reconcile.py` |
| Opportunity funnel | `backend/services/opportunity_funnel.py` |
| Shadow register + learning ledger | `backend/services/shadow_portfolios.py` |
| PM engine / actions / brief | `backend/services/pm_engine.py`, `pm_actions.py`, `scripts/morning_brief.py` |
| Arena genome + manifest | *Aegis module* `aegis_brain/arena/genome.py` |
| Arena evaluator (screen) | *Aegis module* `aegis_brain/arena/evaluate.py` |
| Synthetic worlds | *Aegis module* `aegis_brain/arena/synthetic.py` |
| Registry → panel bindings | *Aegis module* `aegis_brain/arena/bindings.py` |
| Adjudicator (verdicts) | *Aegis module* `aegis_brain/pf/run.py` |

## The standing numbers this loop produced on 2026-08-11

* **False-discovery bar: +4.87 %/yr excess CAGR.** The best of 384 genomes
  when nothing predicts anything. No Arena claim below it means anything.
* **Arena detection threshold: +8 %/yr decile spread.** Below it, a ranking is
  not evidence.
* **Analyst levels: −8 to −18 %/yr gross** on 21 years of PIT IBES. Third
  independent instrument. The PM does not rank on them.
* **Analyst target revisions: +1.5 to +6.1 %/yr gross, net-dead on turnover.**
  The levels-vs-revisions distinction the PM was built on is real; its
  tradability is not established.
