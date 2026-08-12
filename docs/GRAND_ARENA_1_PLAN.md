# GRAND-ARENA-1 — chunked plan, resumable across sessions

**Opened 2026-08-12.** The brief asks for 14 phases in one run. That is more
than one session can do to a standard worth trusting, and a thin version of this
campaign would produce exactly the result the review criticises. So it is split
into chunks that each end at a **committable, verifiable artifact**, and any
session can pick up the next one without reconstructing context.

Standing rule for every chunk: **historical LLM reasoning cannot certify alpha**
— the foundation model may know later history. Historical LLM results are
`ARCHITECTURE_RESULT_ONLY`. Protected quantitative holdouts and the forward
paper record remain the certification layer.

---

## Chunk status

| # | Chunk | State | Artifact |
|---|---|---|---|
| **0** | Research budget + machine verification | **DONE** | `backend/services/research_budget.py`, 12 tests |
| **1** | KNOWN-WORLD-1 — can learners recover planted rules? | **RUNNING** (started 2026-08-12) | `docs/GRAND_ARENA_KNOWN_WORLDS.md` |
| **2** | EXIT-LAB-1 — counterfactual decision factory | **RUNNING** (started 2026-08-12) | `docs/GRAND_ARENA_EXIT_LAB.md` |
| 3 | LLM-SWARM-1 — thousands of gradeable calls | NEXT | `docs/GRAND_ARENA_SWARM.md` |
| 4 | WHY-MOVED at scale (universe, not one book) | pending | extends chunk 3 |
| 5 | Regime learning | pending | — |
| 6 | Exposure/timing arena | pending | — |
| 7 | Portfolio construction arena (P0–P15) | pending | — |
| 8 | Evolution arena | pending | — |
| 9 | **ABLATION** — what does the LLM actually add? | pending, **depends on 3+7** | — |
| 10 | Protected evaluation (one shot, frozen) | pending, **depends on 9** | — |
| 11 | Forward paper tournament | pending, attended | — |
| 12 | `GRAND_ARENA_1_VERDICT.md` — the 25 answers | pending | the deliverable |

**Do chunks in order where a dependency is marked. Chunk 9 is the one that
answers Murat's actual question; chunks 3 and 7 exist to make it possible.**

---

## Chunk 0 — DONE. And it inverted the review's premise.

The brief said the 150-call/day production guard would strangle the swarm and
should be raised.

**It would not have, because it never applied.** `llm.daily_call_cap = 150`
governs `llm_analyzer` (the production path). `why_moved` and
`optimus_specialists` construct their own client and call DeepSeek directly —
so the research swarm was not throttled, it was **ungoverned**.

For a campaign of thousands of calls that is the more dangerous of the two
failures. Nothing would have stopped a runaway loop except the vendor balance
emptying, and the first symptom would have been a dead key on the *production*
path that shares it.

So the fix is not a raised cap. It is a **separate governor the research paths
actually consult**, with production's guard left exactly where it is (pinned by
a test that fails if the two are ever merged).

Three brakes, because they fail differently:
- **calls** — `RESEARCH_LLM_MAX_CALLS` (12,000). The hard ceiling.
- **dollars** — `RESEARCH_LLM_MAX_USD` ($25). Soft, because cost is an estimate
  against a dated price table; when unpriced models are in the ledger the
  refusal says **LOWER BOUND** rather than implying precision.
- **zero yield** — halts when >40% of calls produce no prediction and no
  hypothesis. Not a spend limit, an *information* limit: a campaign buying
  tokens instead of gradeable output should be inspected, not funded to
  completion. Not armed below n=50, because halting on three unlucky parses
  would be its own kind of stupidity.

Enforcement reads the **telemetry ledger**, not an in-process counter — a
counter resets on restart, so a crashed-and-resumed campaign would silently
spend twice. And if telemetry is unreadable the governor **refuses** rather than
assuming zero spend, which would disarm every ceiling at exactly the moment the
accounting broke.

Refusals write no telemetry row: they never reached the vendor, and counting
them would dilute the zero-yield denominator they exist to protect.

---

## Chunk 3 — LLM-SWARM-1 (next up)

Prerequisites now met: budget governor exists, telemetry records real token
counts, ledger persists across deploys, fast horizons exist.

- Broad universe selected on PIT-visible information only.
- ~14 specialist roles; **no agent sees another's answer before forming its
  own** — otherwise the panel is one forecaster and §20 collapses the effective
  n to 1.
- Structured output, numeric probabilities. **ABSTAIN is required to be
  available and is better than fake precision.** Reject `p=0.50` filler: the
  first WHY-MOVED batch was 23 of 25 one-day `return_sign` claims at 0.50, which
  accrues records fast and says nothing.
- Report `effective_distinct_ideas`, zero-yield rate, cost, and cost per
  gradeable output.
- **Never treat repeated samples of one model as independent observations.**
  Asking DeepSeek 1,000 times is not n=1,000; it is one correlated opinion. Use
  the volume for *diversity of exploration*, and let market outcomes supply the
  evidence.

## Chunk 9 — the ablation (why the others exist)

Full system, then remove one component at a time: no LLM · no news · no
geopolitical lens · no revisions · no options · no regime state · no WHY-MOVED
experience · no specialist reliability · no quant signals · one generic LLM
instead of specialists · **random LLM text as placebo**.

Three outcomes, all publishable:
- Full ≫ no-LLM, reproducibly → we have something.
- Full ≈ no-LLM → the LLM is currently presentation and research assistance.
  **Say it plainly.**
- Full < no-LLM → redesign the LLM layer.
- LLM helps only in a narrow domain → stop asking it to do everything. That is
  a success, not a consolation.

---

## Things a resuming session must not re-derive

- **Selection vs management.** Four independent measurements now agree: the edge
  is in selection, the losses are in management and sizing (NIGHT-12 exposure,
  NIGHT-13 factorial, NIGHT-13 ensemble, NIGHT-14 WINNER-GENOME).
- **WINNER-GENOME left execution untested.** The design forms on day 0 and
  holds. The CUHK captain says active intraday entry/exit was the core. A null
  on selection is **not** a null on execution — that gap is chunk 6's job.
- **Corroboration ≠ skill.** WHY-MOVED's 84.2% is a coherence score on n=19 from
  one day. It must never sit beside a Brier score as if it were the same
  currency.
- **THEME-CASCADE is closed** with a well-powered corpse (spread t=0.10). Do not
  re-propose second-order supply-chain beneficiaries without the four
  conditions in `PREREG_THEME_CASCADE_1.md`.
- **Trailing stops are a corpse**, not a candidate: −3.08%/yr under G7 (§15).
  They appear in EXIT-LAB as the control.
- **CANON §19 and §20 are unchanged by volume.** More data moves the MDE; it
  does not move the rule. A number below its MDE is not detectable and is never
  a kill.
