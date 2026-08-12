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
| **0** | Research budget + machine verification | **DONE** `9ed42d2` | `backend/services/research_budget.py`, 12 tests |
| **1** | KNOWN-WORLD-1 — can learners recover planted rules? | **DONE** `2ce58f3` | `docs/GRAND_ARENA_KNOWN_WORLDS.md` |
| **2** | EXIT-LAB-1 — counterfactual decision factory | **DONE** `8429ab4` | `docs/GRAND_ARENA_EXIT_LAB.md` |
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

## Chunk 1 — DONE. 82 cells, and the most important result of the campaign.

Pre-registered at `05e5315`, verdict rules frozen before any learner ran. Every
world passed `verify()` against its own declared plant before scoring, and every
signal world had an oracle ceiling clearing 1.98×–4.23× its MDE — so the MISSED
cells are **learner** failures, not unrecoverable worlds.

**27 RECOVERED · 16 PARTIAL · 26 MISSED · 13 CORRECT-NULL · 0 FALSE-POSITIVE.**

### The three negative controls are clean — and one is a warning

**WORLD-I (pure noise): 13/13 CORRECT-NULL.** And the nulls are *informative*,
not vacuous: deliberately misaligning the label by one month makes the **same
harness** print IC +0.4283 at t = 87.8, 44× its MDE. The tripwire has teeth.

**WORLD-L (no timing edge): 5/5 CORRECT-NULL — but not because the learners
behaved.** The evolutionary policy **invented a timing rule**: zero exposure in
52% of months, raw annualised Sharpe 0.500 against the static 0.478. *Reported
the way a dashboard would report it, that is a discovery.* It was refused by
two things and **neither was the learner** — matched-average-exposure comparison
(gain collapses to +1.89%/yr) and its own MDE (2.43%/yr). The conservative
offline-Q did the same thing more quietly. This is the exact failure this whole
campaign exists to catch, caught.

**WORLD-J (cost-killed edge): 7/7 refused to trade.** Gross recovered by 6 of 7;
net never declared. Breakeven 12–21 bps against 65 charged. Honest limit: at
2.5× the oracle breakeven this is the *easy* version — a near-breakeven variant
has not been run.

### WORLD-K — the sharpest finding, and it rhymes with the standing bet

All four action learners MISSED. Not because they failed to find the
replacement rule — ridge found it (+33pp replace-share on stale names), evo
found it (+29pp). They missed because **every learner reached for cash**, 20% to
39% of actions, in a world where cash is *never* optimal. Cash is a
market-level bet, so it injected market variance and pushed their own MDEs to
4.1–5.1%/yr against a 3.6%/yr ceiling.

**They made themselves undetectable by de-risking.** The *conservative*
offline-Q was worst at 39%, and structurally so: pessimism subtracts an
uncertainty allowance from every action, and cash has no uncertainty to be
pessimistic about.

### Which learners are trusted for later chunks

| learner | verdict |
|---|---|
| **contextual bandit** | **TRUSTED** for specialist/sector attribution — the only instrument that recovered G and H (100% of pulls to the skilled specialist, 0–0.5% to the decoy) where 6 of 7 cross-sectional learners failed |
| ridge / logistic | TRUSTED as **detectors**, NOT as explainers — in world F they tilt toward momentum on average while the world reverses it exactly where money is lost |
| LightGBM | TRUSTED **with a caveat** — recovered F and G but failed H, G's mirror; conditional structure it reports needs independent confirmation |
| evolutionary | CONDITIONALLY trusted, discipline-dependent (see WORLD-L) |
| HMM | **NOT TRUSTED** as a regime instrument — 58.8% state accuracy against a 76.0% Bayes ceiling; every world-C cell PARTIAL |
| offline-Q | **NOT TRUSTED** for exit/action work (WORLD-K) |
| MLP | **NOT TRUSTED** at this sample size — 1 recovery in 9, and it missed the *linear* world A |

### Two silent defects caught only because the answer was known

LinUCB with a unit-scale confidence width against 0.02-scale rewards ran green
**as a uniform random policy** (35% to the skilled arm instead of 100%).
Single-restart Baum-Welch landed at 52% state accuracy — chance — where five
restarts reach 59%. Neither would have been visible in a real-market run.

### Caveats disclosed rather than buried

Worlds D, K and L were re-specified **before** the sweep from oracle
calculations, because their own optimal policies sat below their MDEs. Worlds
E–H were **not** power-checked in advance; their ceilings cleared 2× afterwards,
but that was luck — later chunks must compute ceilings before sweeping.

**§20: median 2.36 effective distinct learners from 7 nominal.** So zero false
positives is less impressive than it looks, and any future one is worth more.
Checkpoint resume verified: truncating to 70 cells and re-running reproduces all
82 verdicts exactly.

## Chunk 2 — DONE, and it did two things

**25.3M state-action rows, 152M state-action-horizon outcome cells, 11,145 CRSP
securities, 23 years.** That is the denominator NIGHT-12's null never had — 60
rows from one portfolio was an anecdote.

1. **The cash null survived.** Given the real denominator, `SELL→CASH` is never
   the best action at any horizon tested.
2. **An instrument that never saw NIGHT-7 independently reproduced the
   trailing-stop corpse**: −4.94 pp against an MDE of 4.82, sign holding in 8 of
   8 regime blocks. A finding that reappears from a different instrument is a
   finding; the first version could have been an artifact of its own harness,
   and now it is not.

Baselines win, which is the honest and expected outcome. One comparison at
−2.55 pp against an MDE of 2.77 is labelled **NOT DETECTABLE** rather than read
as a kill (CANON §19).

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
