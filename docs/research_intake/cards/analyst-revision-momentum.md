# CARD: analyst-revision-momentum

## Index fields
- topic: Analyst revision momentum (recommendation and forecast revisions, first-mover raises)
- mechanism_class: information_asymmetry, behavioural_bias
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Narasimhan Jegadeesh, Joonghyuk Kim, Susan D. Krische, Charles M.C. Lee (2004), "Analyzing the
Analysts: When Do Recommendations Add Value?," *The Journal of Finance*, 59(3): 1083-1124.
Verified via independent corroborating search records (Wiley Online Library DOI listing
`10.1111/j.1540-6261.2004.00657.x`, JSTOR stable/3694731, and the authors' own citation list, all
agreeing on journal/volume/issue/pages/year; direct fetch of both the Wiley and JSTOR pages 403'd
this pass, so this citation rests on cross-source corroboration rather than a single direct fetch).
Cristi A. Gleason, Charles M.C. Lee (2003), "Analyst Forecast Revisions and Market Price
Discovery," *The Accounting Review*, 78(1): 193-225. DOI 10.2308/accr.2003.78.1.193. Verified via
independent corroborating search records (SemanticScholar, ScirP reference listing; direct fetch
403'd).

## The claim, in one sentence
Jegadeesh et al. (2004): changes in consensus analyst recommendations (upgrades/downgrades) carry
genuine, exploitable return-predictive information, and the combination of a positive recommendation
CHANGE with positive price momentum identifies the names where recommendations add the most value
— pure momentum stocks with favorable revisions outperform, while "glamour" stocks recommended
without momentum support do not. Gleason & Lee (2003): the market's price response to an analyst
forecast REVISION is slower and less complete the less "sophisticated" the revision looks (e.g.
small, trend-following revisions that merely nudge toward consensus rather than genuinely new
information), and is faster/more complete when the revising analyst is a recognized, high-status
("celebrity"/All-Star) forecaster — i.e. revision-driven price discovery is itself gradual and
analyst-identity-dependent, not instantaneous.

## Mechanism: why the inefficiency could exist, and who is on the other side
Two distinct mechanisms bundled under "analyst revision momentum" in practice: (1) analysts possess
or synthesize genuine private/non-public-yet information (channel checks, management access,
industry expertise) that is reflected in a rating/estimate CHANGE before the market fully prices it
— the counterparty is whoever does not have analyst access or does not follow revisions closely;
(2) a pure UNDER-REACTION story (Gleason & Lee) — even when a revision carries no special private
information, the market is slow to process it fully, especially from low-visibility analysts,
because investor attention is scarce and status/reputation acts as an attention-allocation
shortcut. AEGIS's own `FINDING_2026-08-24_REVISION_FORECASTER.md` measured exactly this decomposition
directly and found the FIRST mechanism's public-information component is almost entirely mechanical
(an earnings surprise predicts the next analyst revision with rank correlation **+0.623**, t
**+60.4**) and therefore already priced — the revision's predictable component carries no return
information (IC 0.0028-0.0071, t 0.21-0.48, both far under the required MDE).

## Assumptions
Requires that the revision event be observed BEFORE the return window it is meant to predict (a
timing assumption AEGIS's own prior work found violated once already — see "known failure modes"
below), and requires that whatever component of a revision is being tested is NOT simply the
market's own already-priced reaction to the same public news the analyst is reacting to.

## Measurable variables: the precursor observable BEFORE the move
The raw revision event (upgrade/downgrade, or a price-target/EPS-estimate change) is PIT-observable
at its filing timestamp. AEGIS's own `net_raises` (net count of price-target raises) and `breadth`
(net raises scaled by distinct covering brokers) are both already-built precursors on the IBES
bridge. The specific variable this task's brief names as "what is left" — **timeliness and
first-seen PIT** — refers to whether a name's FIRST revision after a long quiet period is a sharper
precursor than an ordinary revision-flow aggregate; this is the exact construction of the UNSIGNED
DRAFT trial `docs/TRIALS/TRIAL-ANALYST-SNOWBALL-1.md`, which flags the 90-day quiet-gap first-mover
raise as its precursor and is explicit that "first-seen" matters because a name just entering
IBES coverage has no genuine quiet spell to break (a coverage-start exclusion is built into the
draft's construction for exactly this reason).

## Sample period and markets
Jegadeesh et al. (2004): US equities with Zacks/IBES recommendation data, 1985-1998 (exact bounds
not independently re-extracted beyond the abstract this pass). Gleason & Lee (2003): US equities
with IBES analyst forecast data; sample period centered on the 1990s (exact bounds not
independently re-extracted beyond the abstract this pass). AEGIS's own closed trials
(`ANALYST-IBES-1`, `REVISION-FORECASTER-1`) ran on the CRSP/IBES bridge through the available
WRDS vintage (through 2024-12-31 per the entitled CRSP window); the unsigned snowball draft's
yfinance-instrument count spans 2011-12-08..2026-10-05.

## Effect size as published
Jegadeesh et al. (2004) and Gleason & Lee (2003) effect sizes were not independently re-extracted
in numeric form this pass beyond the qualitative findings above (both abstracts/summaries describe
directional and conditional results — e.g. "momentum stocks with favorable revisions outperform" —
without a single headline number quoted in the search summaries retrieved). AEGIS's own directly
measured, already-verified numbers on its own data are the more decision-relevant figures here:
link (event state -> revision) IC **+0.623**, t **+60.4**; link (revision -> subsequent return,
correctly timed) IC **+0.0028** (h5) / **+0.0071** (h21), t **0.21**/**0.48**; composition
(event state -> return directly) IC **-0.0005**, t **-0.04** — i.e. on AEGIS's own panel the
revision-mediated channel is measurably and precisely a dead link, not merely an unreplicated one.
`ANALYST-IBES-1` (2026-08-11) separately recorded EPS revision breadth as dead net, max net t
**0.88**.

## Known failure modes and post-publication decay
McLean & Pontiff (2016, *Journal of Finance* 71(1): 5-32) and Harvey, Liu & Zhu (2016, *Review of
Financial Studies* 29(1): 5-68) are the standing general decay/multiplicity references (not
independently re-verified for the analyst-revision literature specifically this pass). AEGIS's own
specific, already-paid-for failure mode is more informative than generic decay: the FIRST
implementation of the revision-return link in `REVISION-FORECASTER-1` scored the revision against
returns measured FROM THE EVENT rather than from the moment the revision was actually observed
(`t1`, a median of 20 calendar days after the event) — an in-sample timing leak that produced a
spurious t of **4.04** and a plausible-sounding story ("the predictable part of the revision is
priced, the residual carries the alpha") that was **entirely an artifact of window overlap**. The
corrected, correctly-timed version collapsed to t 0.21-0.81. This is flagged in CLAUDE.md protocol
11's family ("a number that comes out positive — the first question is which part of the sample it
is") and is pinned by `test_revision_forecaster.py` so the bug cannot silently return. The
revision-tilt implementation (`net_raises`, `breadth`, `ear_flow` as a top-500 large-cap overlay)
separately found the tilt adds essentially nothing on a large-cap base (−0.038%/mo vs. the market
in validation, t −0.60; −0.002%/mo vs. its own untilted base) — `FAILED_VARIANT`,
`docs/research_notes/2026-09-29/revision_tilt_2026-09-29.md`.

## What AEGIS has on disk to test it
`backend/data/optimus/wrds/bulk/ibes__ptgdet.parquet` / `ibes__ptgdetu.parquet` (12-month
price-target detail, per `docs/DATA_CATALOG.md`'s duplicate-finding table, aliased identically
under `tr_ibes__*` names) linked to CRSP permnos via `ibcrsphist`, consumed by
`backend/services/crsp_pit_bridges.py` (`first_movers`, `analyst2_panel`) and
`crsp_event_bridge.py` (`target_signs`). `pit_features.firm_reliability` for broker-skill
weighting (already tested standalone: `ANALYST-SKILL-1`, `ADOPT_AT_TRIVIAL_EFFECT`, not funded).
No new data pull is needed for the first-seen/timeliness construction named in this task's brief —
the gap is a conditioning column and an event-study construction, not a missing source.

## The falsifiable question and the declared primary metric, with costs
The unsigned draft trial already specifies this precisely: *for US common stocks on the CRSP/IBES
bridge, does the first 12-month price-target raise ending a >= 90-calendar-day spell with no raise
by any broker (t0) (1) draw at least two OTHER brokers to raise within ~63 sessions more often than
a matched non-first-mover raise does, and (2) produce a positive market-relative return from the
first session after t0 is public, with no information after t0?* Primary metrics: (1) follow-through
probability difference vs. two controls (matched "chaser" raises; random size/vol/momentum-matched
raise dates); (2) t0 return minus the market, net of one round trip at max(Corwin-Schultz,
flat-band). The draft's own stated power analysis is explicit that the RETURN leg is **likely
underpowered** (declared effect size 0.4pp against sibling closures' measured gaps of about
-0.6%/month) — the follow-through leg is well-powered and is the part worth running first.

## Whether a corpse already exists here
Heavily populated. `ANALYST-IBES-1` (2026-08-11): EPS revision breadth dead net, max t 0.88.
`REVISION-FORECASTER-1` (`docs/FINDING_2026-08-24_REVISION_FORECASTER.md`): event-conditioned,
properly-timed revision -> return link measured directly, **STOP**, composition IC -0.0005.
Revision-tilt overlay (`docs/research_notes/2026-09-29/revision_tilt_2026-09-29.md`):
`FAILED_VARIANT`. The nearest CRSP-bridge sibling to the "first mover" construction,
`first_mover_raises` as a MONTHLY cross-sectional book (30-day gap, not 90): `CANNOT_DISTINGUISH`
(`docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md` §2) — explicitly closes
that implementation, not the broader first-mover mechanism. The 90-day-gap, event-study (not
monthly-book) construction with the coverage-start exclusion is the one genuinely UNRESOLVED cut:
`docs/TRIALS/TRIAL-ANALYST-SNOWBALL-1.md`, status **UNSIGNED DRAFT**, not yet in `rule_experiments`,
no outcome read on the CRSP/IBES instrument.

## Needs evidence
- Independent literature on the 90-day-quiet-gap "first mover" snowball construction
  specifically (as opposed to revision momentum in general, already three times closed here) --
  whether anyone outside this programme has tested a quiet-gap-conditioned first revision as an
  event-study signal, or whether `TRIAL-ANALYST-SNOWBALL-1.md`'s construction is genuinely novel.
- Post-2010 replication/decay evidence for Jegadeesh-Kim-Krische-Lee (2004) specifically (McLean
  & Pontiff 2016 is cited here as the standing decay reference, not independently re-verified for
  THIS mechanism).

## hyp_lab family
`family_unmapped` — no `HYP_LAB_FAMILIES` entry covers analyst-revision mechanisms specifically
(the closest by surface similarity, `insider_event`, is about insider Form-4 transactions, a
different data source and a different actor entirely). This is a second structural gap in the
taxonomy alongside the portfolio-construction gap in the Markowitz card.

## Verdict
**READY_TO_CELL** for the 90-day-quiet-gap first-mover-snowball construction; the
revision-mediated return channel in general is **ALREADY_CLOSED** (split verdict, justified below).
**NEEDS_DATA is the wrong label here — the data exists — so the honest verdict is split by
construction.** The revision-mediated return channel in general is **ALREADY_CLOSED** (three
independent closures: `ANALYST-IBES-1`, `REVISION-FORECASTER-1`, revision-tilt). The specific
90-day-quiet-gap first-mover-snowball construction is **READY_TO_CELL**, pending only a human/
orchestrator SIGNATURE on the already-written unsigned draft (`TRIAL-ANALYST-SNOWBALL-1.md`) — it
is not blocked on data, build, or design, only on registration, and its own honest prior (stated in
the draft) is that the return leg most likely dies the same way its siblings did.

## needs_evidence
- Does a first 12-month price-target raise that ends a >= 90-day no-raise spell draw at least two
  other brokers to raise within ~63 sessions more often than a matched non-first-mover raise (the
  well-powered follow-through leg of the unsigned `docs/TRIALS/TRIAL-ANALYST-SNOWBALL-1.md`)?
- Does that first-mover raise earn a positive market-relative return, net of one round trip, from
  the first session after it is public (the leg the draft itself expects to be underpowered)?
- What are the published numeric effect sizes and exact sample bounds of Jegadeesh et al. (2004)
  and Gleason & Lee (2003), which this pass did not re-extract?
