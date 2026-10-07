# CARD: post-earnings-announcement-drift

## Citation
Ray Ball, Philip Brown (1968), "An Empirical Evaluation of Accounting Income Numbers," *Journal
of Accounting Research*, 6(2): 159-178. Verified via independent corroborating search records
(SemanticScholar, SSRN retrospective by the same authors, ScirP reference listing, and the
American Accounting Association's own 1986 Seminal Contributions citation, all agreeing on
journal/volume/issue/pages; direct JSTOR/ProQuest fetch 403'd this pass). Victor L. Bernard,
Jacob K. Thomas (1989), "Post-Earnings-Announcement Drift: Delayed Price Response or Risk
Premium?," *Journal of Accounting Research*, 27 (Supplement): 1-36. DOI 10.2307/2491062. Verified
by fetching `https://ideas.repec.org/a/bla/joares/v27y1989ip1-36.html` directly (2026-10-07; title,
authors, journal, volume, pages confirmed; DOI resolves to `10.2307/2491062`, not `10.2307/2490232`
as initially guessed by analogy to the Ball-Brown DOI — the fetch caught and corrected this).

## The claim, in one sentence
After a company's quarterly earnings announcement, its stock continues to drift in the direction
of the earnings surprise for weeks to months afterward — "good news" firms keep outperforming and
"bad news" firms keep underperforming — rather than the price fully adjusting at the announcement
itself, which is the single most-replicated violation of semi-strong-form market efficiency in the
accounting/finance literature (first documented by Ball & Brown 1968; named and quantified as a
systematic, exploitable-looking drift by Bernard & Thomas 1989).

## Mechanism: why the inefficiency could exist, and who is on the other side
Bernard & Thomas's own paper frames the two competing explanations the literature still argues
over: (1) **delayed price response** — the market under-reacts to the full information content of
an earnings surprise, gradually incorporating it over subsequent weeks/months, perhaps because
investors naively extrapolate from past earnings using a seasonal random-walk model and are
slow to recognize serial correlation in quarterly earnings changes; or (2) **risk premium** — the
"drift" is not mispricing at all but compensation for a priced risk factor correlated with the
earnings-surprise sort. The behavioral/under-reaction story's counterparty is whoever is too slow,
inattentive, or cognitively anchored to immediately price in the full implication of a surprise —
plausibly retail investors or under-resourced analysts who update beliefs gradually rather than
instantaneously (this is also the lens the LLM-era "attention" and "belief elasticity" literature
the owner's brief names revisits).

## Assumptions
Requires that the earnings announcement date and the magnitude/sign of the "surprise" (actual vs.
some expectation benchmark — historically a seasonal random walk, later the analyst consensus
estimate) are both well-defined and PIT-observable; requires that the risk-premium explanation can
be distinguished from under-reaction by finding a drift that is NOT explained by standard risk
factors (size, book-to-market, beta) — which is exactly the test Bernard & Thomas run.

## Measurable variables: the precursor observable BEFORE the move
The standardized unexpected earnings (SUE) — the earnings surprise at the announcement date,
scaled by its own historical standard deviation — is the canonical precursor, observable the
moment the earnings number and the expectation benchmark are both public, i.e. strictly before the
drift period it is meant to predict. In AEGIS's own CRSP/IBES bridge this exists as the `ear_*`
family (`ear_fresh`, `ear_mom`, `ear_drift`) in `backend/services/crsp_event_bridge.py`, and the
specific conditioning variable this task names — a **consecutive-beat streak count** (how many
quarters in a row a name has beaten the IBES consensus) — is a second, distinct precursor already
built and already tested as the `earnings_streak` hyp_lab family (see "already tried" below).

## Sample period and markets
Ball & Brown (1968): US-listed firms, 1946-1966 (annual earnings announcements; the paper predates
quarterly-reporting-standard coverage). Bernard & Thomas (1989): NYSE/AMEX firms with Compustat
quarterly data and CRSP returns, 1974-1986 (exact bounds per the paper's own sample construction,
not independently re-extracted beyond the abstract this pass).

## Effect size as published
Bernard & Thomas (1989): a long position in the highest decile of unexpected-earnings firms
combined with a short position in the lowest decile earns an annualized abnormal return of
**roughly 25%** over the 60 trading days following the announcement, before transaction costs —
the number most commonly quoted from this paper.

## Known failure modes and post-publication decay
McLean & Pontiff (2016, *Journal of Finance* 71(1): 5-32, DOI 10.1111/jofi.12365) find that
published return-predicting variables in general see returns **26% lower out-of-sample and 58%
lower post-publication**, consistent with publication-informed trading eroding anomalies over
time — PEAD, being among the oldest and most famous of all such anomalies, is a natural candidate
for this decay, though it was not singled out by name in the search summary of that paper this
pass. Harvey, Liu & Zhu (2016, *Review of Financial Studies* 29(1): 5-68) argue more broadly that
the standard significance bar (t > 2.0) used to validate factors like this one is far too lenient
given how many factors have been tested in total (316+ published), which bears on how much weight
to put on any single historical PEAD estimate taken in isolation. AEGIS's own directly relevant
measurement: `ear_drift`/`ear_mom` (the standard PEAD-shaped continuation signals on AEGIS's CRSP
panel) are reported as **decaying post-2009 and DEPRIORITIZED**
(`docs/research_notes/2026-10-06/snowball_and_theory_objects_2026-10-06.md` row 13), consistent
with the general decay pattern rather than an exception to it.

## What AEGIS has on disk to test it
The IBES actuals-vs-estimates bridge with PIT timing, `backend/services/crsp_event_bridge.py`'s
`ear_*` family (`eap_raises`, `ear_fresh`, `ear_mom`, `ear_drift`), built on the WRDS IBES detail
file (`backend/data/optimus/wrds/bulk/ibes__detusecd_sepint.parquet` and siblings, per
`docs/DATA_CATALOG.md`'s duplicate-finding table) linked to CRSP permnos — already built, already
PIT-safe, no new data pull required for any variant of this question including the streak
conditioning.

## The falsifiable question and the declared primary metric, with costs
*Does a cohort of names on a CONSECUTIVE quarterly-beat streak (>= 3 beats in a row) exhibit a
weaker NEXT-quarter drift / higher subsequent miss probability than a single-beat cohort (the
"expectations ratchet" / bar-raising hypothesis), or a STRONGER one (naive extrapolation /
continuation), measured net of the engine's standard cost model?* This exact question was already
run. Primary metric used: design-signed mean return at the 63-session horizon, net of costs,
t-statistic on the (consecutive-beat minus first-beat) spread.

## Whether a corpse already exists here
**Already run and closed.** `docs/research_notes/2026-10-06/theory_cells_2026-10-06.md` §(c):
consecutive EPS beats (>=3) minus first beats, H63 drift, design-signed **-0.48%/mo, t -1.11, 3 of
8 years positive** — verdict **`FAILED_VARIANT`**, hyp_lab family `earnings_streak`. The
companion review `docs/reviews/REVIEW_2026-10-06_C12_THEORY_CELLS.md` additionally flags that
`beat_streak`'s primary metric was not band-neutral as originally declared (its validate-window
sign flips between bands) — a construction defect noted on the corpse itself, not just a null
result, so a RESURRECTION of this exact mechanism would need to name that construction fix as its
new instrument, not merely "try again." The adjacent, opposite-signed, already-closed siblings are
`ear_drift`/`ear_mom` (continuation-shaped PEAD, DEPRIORITIZED, decaying post-2009).

## hyp_lab family
`earnings_streak` — this is the one card in this batch with an exact match in the fixed
`HYP_LAB_FAMILIES` taxonomy; the family exists specifically because this mechanism was already
built and run.

## Verdict
**ALREADY_CLOSED.** The exact consecutive-beat-streak conditioning this card's brief names was
pre-registered as a theory cell, run on the CRSP/IBES bridge, and returned `FAILED_VARIANT`
(-0.48%/mo, t -1.11) — cite `docs/research_notes/2026-10-06/theory_cells_2026-10-06.md` and
`docs/reviews/REVIEW_2026-10-06_C12_THEORY_CELLS.md`, do not re-discover it as new. The one
un-closed thread is the review's own flagged construction defect (non-band-neutral primary); a
RESURRECTION naming that fix as the new instrument is the only legitimate way back into this
mechanism, per the `pre-register-trial` skill's BLOCKED/RESURRECTION discipline.
