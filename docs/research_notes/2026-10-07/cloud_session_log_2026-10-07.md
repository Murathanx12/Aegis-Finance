# Cloud session log, 2026-10-07 (the V1 Beta offload batch)

The cloud session's own log, kept so a reviewer can see why each piece of work exists. Tasks A-E
were set by the owner's brief; the brief allowed up to two extras (Task F), each to be justified
here BEFORE it was built, in three to five lines: why it is high EV, why it cannot conflict with
the local session, and its exact acceptance.

## Starting point

- `main` = `92f147f6334f3651a98277f0aada1eaa5c26671b` (unchanged since the brief was written; fetched
  and checked before branching).
- Branch: the harness pins this session to `claude/beautiful-meitner-hq5614`; the brief's suggested
  name `cloud/2026-10-07-ledger-split-and-identity` could not be used. Same content, one PR.
- MCP actually available: GitHub, claude-code-remote, Bigdata.com, Canva, Claude Docs, Cloudflare,
  Context7, Figma, Gamma, Gmail, Google Calendar/Drive, Miro, Notion, Supabase. **No Exa, no Optimus**:
  `brain_query` / `aegis_postmortems` / `aegis_verified_state` could not be run; corpse checks rest on
  tracked files. Web verification used the built-in WebFetch / WebSearch.

## Task F1: evidence-ladder null calibration (chosen 2026-10-07 ~14:10 HKT)

- **Why high EV:** the README and the `/arena` page now show `OBSERVED -> EARLY_EVIDENCE -> REPLICATED`
  as the public evidence ladder, and the rungs are awarded by a sign rule whose rate under NO edge was
  never measured (review C3 F7 said REPLICATED's bar is "too low for the rung's name" without a
  number). If a no-edge book earns the badge often, every future badge misleads a reader; that is
  a claim-integrity defect, priced before it fires rather than after.
- **Why no local conflict:** a new script, a new test and a note. `book_dna` is imported, never
  edited; no paper or lane path is touched; the rule change, if any, is the owner's.
- **Acceptance:** the module's own `subwindows` + `evidence_label` drive every single-look cell; a
  vectorised copy used for daily re-looks agrees with them on every sampled pair or the audit refuses;
  a seeded receipt under `backend/data/optimus/audits/`; tests pin the measured band to the rule.

## Task F2

Not taken. Q8 (external research instruments) was the candidate; the research cards' own fetch logs
(which publishers 403, which open APIs resolve a DOI) answer most of it, and they are in the PR.
