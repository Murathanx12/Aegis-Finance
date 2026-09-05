# STALE — cells fitted on the pre-fix panel

These prediction series were fitted before `learner/dataset.py` was corrected on
2026-09-06. The target-revision legs (`target_rev_1m`, `target_rev_3m`) had been
a ratio of two DIFFERENT share bases: `meanptg` is the unadjusted consensus, so a
2:1 split between vintages read as a −50% revision and a 1-for-10 reverse split as
+900%. 4,359 rows at 1m and 12,523 at 3m carried it.

The panel was rebuilt on the fix. Every file here is therefore a set of
predictions fitted on a SUPERSEDED panel, and the original cache key said nothing
about which panel it came from — the next pass would have served them silently
and reported them as results on the corrected data. That is the same class of
error as the whole weekend's other four: **a stale input and a real result are
indistinguishable once a default stands between them.**

`_cache_key` now carries a `_panel_fingerprint()` — a short hash of the panel
file's size and mtime — so a rebuilt panel simply cannot match an old key. Not a
content hash: hashing 418 MB on every cell lookup would cost more than the refit
it saves, and size+mtime both change on any rebuild, which is the event that
matters.

Kept, not deleted, for the same reason as the other superseded folders: they are
the record of what was computed and when.
