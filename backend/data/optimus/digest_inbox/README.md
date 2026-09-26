# Digest inbox -- paste Dow Jones articles here

Open an article in the MuratClaw (Work) Chrome, select all (Ctrl+A), copy, and paste it into
`DIGEST.md` under a separator line `=== url | date | source` (every field optional), or save the
page as a `.txt` file into this folder. Then run `python -m scripts.digest_ingest --once --claims`:
each entry is stored locally (never committed), its claims become `source:<column>` forecast rows,
and they are graded from the next session. Links worth pasting: `WEEKEND_READING_LIST.md`.
