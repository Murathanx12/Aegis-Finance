# SUPERSEDED — receipts written under the old verdict vocabulary

Every receipt in this folder carries `verdict: NOVEL`. **Their NUMBERS are fine;
their WORD is not.**

A code review on 2026-09-06 counted 25 of 92 committed verdicts saying `NOVEL`,
and found that not one of them had cleared the bar `scripts/weekend_lab_jobs.py`
defines for that word:

    DSR > 0.95 after the family  ·  SPA p < 0.10  ·  PBO < 0.5
    ·  the sign holding in >= 2 of 3 eras

W5c, W6 and W7 had each rolled their own `"NOVEL" if survivors else "NOISE"` on a
bare |t| >= 2, bypassing `verdict_from` entirely, and `features_options.job` and
`features_graph.job` carried their own words in from another lane.

The cause is structural, not clerical: a FEATURE SCREEN has no book and therefore
no Sharpe to deflate, so it can never satisfy a bar written for a book. It now
gets its own vocabulary — `SCREEN_SURVIVOR` / `SCREEN_ONLY` / `CANNOT DETERMINE`
/ `NOISE` — and can never reach NOVEL. NOVEL is reserved for something that
survived a book, a family and a deflation.

The point is not pedantic. W5's two options coefficients were labelled NOVEL;
W5b then built the book they had earned, and **all 24 of its cells lost GROSS.**
A vocabulary applied inconsistently is worse than none, because the word still
carries the weight of the definition.

Kept, not deleted: these are the record of what was claimed and when. Nothing
here may be quoted as a current verdict; the corrected re-runs are in the parent
directory. Fixed in commits `35915db` and `fee1010`.
