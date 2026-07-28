# External AI research intake — the protocol (frozen 2026-07-28)

**Purpose:** Murat runs research sweeps in ANY external tool (ChatGPT, Gemini,
DeepSeek, Claude web, workflow harnesses). This document is how their output
enters the program **without contaminating it**. Nothing here is new — the
pipeline has already run successfully at least five times (panel rounds 4, 7,
8, 11, and the 2026-07-27 sweep); this doc freezes what worked so any session
can execute it identically.

## The pipeline (manual on purpose)

1. **RUN** the sweep externally, ideally with the standard prompt template
   below.
2. **BANK** the output verbatim → `docs/research/RESEARCH_SWEEP_<date>.md`
   (or paste it in chat and the session banks it). Banked docs are never
   edited afterwards — integrity caveats (dead harnesses, shuffled URLs,
   partial runs) go in a `§0` header, not into the body.
3. **ADJUDICATE** → `docs/research/AI_PANEL_<date>.md`. **Only adjudication
   dispositions are binding.** Rules, all receipt-backed:
   - External claims are **HYPOTHESES, never evidence**. A claim changes a
     decision only after its citation is independently verified (fetch the
     paper/abstract — not the tool's summary of it).
   - Anything touching a **frozen spec or a live lane** → auto-DECLINED
     (freeze violation). Sweep 07-27 #1 (rebalance randomization on live
     lanes) died here.
   - Anything **re-opening a closed family** → DECLINED with the receipt,
     unless it rebuts that specific receipt. Sweep 07-27 #2 (Cop re-spec)
     died on the batch-2 head-to-head.
   - **Hallucination check is not optional.** Caught so far: DeepSeek invented
     a trial ("INSTR-REVERSAL") and narrated an unbuilt engine as done; GPT
     cited an unverifiable SSRN id twice; one harness died mid-run and its
     killed agents were tallied as "refuted" verdicts (all void); one sweep's
     URLs arrived shuffled and had to be re-matched line by line.
4. **REGISTER** survivors through `scripts/prior_check.py` + the
   pre-register-trial skill. No data touch before the freeze commit — the
   registration cites the panel doc as provenance.
5. **INGEST**: committed docs reach the Optimus brain corpus on the next
   re-ingest; no extra step. **Deliberate exclusion:** RESEARCH_SWEEP docs
   stay OUT of the `prior_check` corpus (it reads registry / TRIALS /
   AI_PANEL / NEG_RESULTS / taxonomy only) — unvetted external claims must
   not be able to pass or fail a prior check.

## Why this stays manual

The human relay IS a control point, not friction to engineer away. An
automated feed (API poller, inbox watcher, auto-committing agent) would pipe
unverified claims into decision-adjacent documents with no adjudication gate —
the exact channel the hallucination catches above would have slipped through.
Cost of the manual loop is ~one paste per sweep. Revisit only if volume
exceeds ~1 sweep/week sustained, and even then automate the BANKING step only,
never the adjudication.

## Standard sweep prompt (paste into any external tool)

> I run a pre-registered quantitative equity research program. Universe: US
> equities (CRSP), monthly, explore window 2004-2018 with 2019-2024 held out;
> everything is net of realistic costs; large/mid and small segments are
> scored separately; microcaps don't count. ~158 candidate signals have been
> tested; nearly all rejected. Closed families (do NOT re-propose):
> accruals, low-vol/low-beta, PEAD/earnings-drift at monthly cadence,
> analyst target prices, supply-chain links, industry momentum,
> single-trigger regime rotation, LLM/agent stock-picking, cost-based appeals
> for large/mid rejects.
>
> Task: [THE QUESTION].
>
> Requirements:
> 1. Every claim needs a working URL (SSRN/arXiv/DOI/journal page). No URL,
>    no claim.
> 2. Quote the paper's own numbers: direction, magnitude, sample window,
>    universe, and whether returns are gross or net of costs. Flag anything
>    tested only pre-2004 or only in microcaps.
> 3. Distinguish clearly between (a) what a cited source shows and (b) your
>    own reasoning. Label each.
> 4. Flag withdrawn/retracted papers and failed replications if you find them
>    — negative evidence is as valuable as positive.
> 5. Do not recommend actions. Deliver evidence; the decision layer is
>    elsewhere.

## What makes a sweep useful (adjudication checklist)

- [ ] URL per claim, resolvable
- [ ] Gross vs net stated; post-2004 non-microcap evidence flagged explicitly
- [ ] Original-paper claims separated from replication evidence
- [ ] Withdrawn/retracted status checked
- [ ] Contradictions with our NEGATIVE_RESULTS ledger surfaced, not smoothed over
- [ ] The tool's own reasoning labeled as such
