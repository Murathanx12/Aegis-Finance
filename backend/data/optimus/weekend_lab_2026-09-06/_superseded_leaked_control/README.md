# SUPERSEDED — receipts written by the leaked matched-control code

These receipts were produced by `W7_matched_loser` before 2026-09-06, when its
control pool was

    pool = g.drop(index=list(win.index) + list(los.index))

which excluded future LOSERS as well as winners. That makes "being eligible as a
control" a statement about the future: a control had to be a name whose 12-month
outcome landed in neither tail. Any formation feature that predicts outcome
DISPERSION then differs from the winners by construction, and the archetype these
receipts rank first — `log_dollar_vol_20d`, "thinly traded for its size", at
Holm p 0.000178 — is exactly a dispersion proxy. After the fix it is t −2.76,
Holm 0.158, and does not survive.

The `W9_survivor_books` receipts here are moved with them because W9 HARVESTS the
survivor list out of whatever receipts are in this directory, so a leaked W7
receipt left in place keeps feeding a corrected claim.

**They are kept, not deleted.** A superseded receipt is history: it is the record
of what was believed and why, and deleting it would remove the evidence that the
correction happened at all. Nothing in this folder may be quoted as a current
result.

Fixed in commit `35915db`. The correction is at the top of
`docs/BUILD_WEEKEND_LAB_2026-09-06.md`; the finding is in
`docs/REVIEW_2026-09-06_CODE.md` (C1).
