---
name: seed-a-lane
description: The attended procedure for starting a NEW forward paper record — a PC paper book (the path that works today) or a website lane (dormant while the hosted backend is off since 2026-11). Use whenever a new lane, book, lane variant or seed flag is requested. Seeding is attended — the owner or the brain flips the switch; builders and unattended sessions never improvise a seed.
---

# Seed a Lane (attended)

New strategies enter the forward record ONLY as new entries with their own frozen
identity (config hash or contract hash) and their own inception. Nothing is appended to,
or retrofitted onto, a record that is already accruing.

## Which kind is being asked for (2026-11-19)

| Kind | Lives in | State today | Switch |
|---|---|---|---|
| **PC paper book** (no broker) | `backend/data/optimus/...` per book, run by a scheduled task through `scripts/runtime_task.py` | **the working path** | the book's flag on its OWN task (`--set AEGIS_<BOOK>=1`), set by the brain, attended |
| **Broker paper account** (Alpaca paper fleet) | the execution repo `aegis-alpha-terminal` and the PC fleet managers | owner decision pending: retire the six accounts and reseed (ROADMAP CH-17) | the owner, attended, in a US session; not seeded from this repo |
| **Website lane** (`paper_nav`, `/api/pi/track-record`) | the hosted backend's database on Railway | **DORMANT**: hosting is off by owner decision; the env-flag step below cannot be run | `AEGIS_SEED_<NAME>=1` for one boot on the hosted service |

If the request does not say which, ask. A "new lane" asked for today almost always means
a PC paper book.

## Why this exists (paid-for lessons)

- **2026-06-17:** a seed flag was flipped while the wiring didn't exist — the
  seed was a silent NO-OP discovered only via the registry dump. Build and
  test the wiring BEFORE asking for the flag.
- Timing artifact same day: "registry still shows N" can be a race with the
  background seed's commit — re-query before declaring failure.
- In-place YAML edits reuse old content hashes and corrupt segment identity.
- **2026-11-10 (CH-17):** six paper accounts had `account_created=False` for weeks —
  nothing was ever seeded, and every status line looked healthy. Verify the seed on the
  book's own first receipt, never on the switch having been set.

## Procedure A — a PC paper book (works today)

1. **Licence first.** A paper book is a `PRODUCT_EXPERIMENT`: it needs a **frozen
   strategy contract before its first decision** (policy hash, timestamp, inputs, costs,
   fill convention, objective), committed under `docs/TRIALS/` (pattern:
   `CONTRACT_NEWS_OVERLAY_v*.json`, `DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v*.json`). No
   significance gate and no preregistration. If the book is meant to back a
   `RESEARCH_CLAIM` or a `CAPITAL_CANDIDATE`, run `pre-register-trial` as well.
2. **A new mechanism is its own book.** Never a weight inside an existing composite and
   never a change to a book already in forward paper: a "v2" is a NEW contract version
   with its own inception.
3. **Build the wiring, off by default** (patterns: `scripts/news_overlay_book.py`,
   `scripts/llm_selector_book.py`): a `step` that writes only when the book's flag is on
   and REFUSES with a non-zero exit otherwise; a `replay` that writes only under `--out`
   and is labelled BACKFILL, never forward evidence; a `grade` that marks forward rows
   only. Costs are never omitted. The flag name goes into `SETTABLE` in
   `scripts/runtime_task.py`, so it can be set on that book's task and on no other.
4. **Test before the switch exists:** flag off → refusal and no file written; a foreign
   or edited contract is refused; a second `step` for the same session is idempotent; a
   back-dated `--date` row is never graded; existing books' files are byte-untouched.
5. **Hand over the switch; do not flip it.** List the by-hand steps exactly: the release
   tag, the scheduled task (name, schedule in ET, the wrapper arguments including
   `--set AEGIS_<BOOK>=1`), and the first session it should decide in. Creating or
   changing a scheduled task is brain-only and attended; a task that can reach an order
   path is the owner's.
6. **Verify the seed on the book's own receipt** (see `verify-prod-after-deploy`): the
   first FORWARD row exists, is dated to the session it decided in, carries the contract
   hash, and the status page row for the task is green. A flag that is set while the
   receipt does not advance is the 2026-06-17 no-op again.
7. **Every pause carries an expiry.** If the book is switched off, write down who
   switched it off and when it comes back.

## Procedure B — a website lane (DORMANT: not runnable while hosting is off)

The code is intact (`backend/main.py` reads `AEGIS_SEED_BOOK_LANES`,
`AEGIS_SEED_CONSERVATIVE_ATR`, `AEGIS_SEED_SMALLMID_QUALITY`, `AEGIS_SEED_TSMOM_XA`,
`AEGIS_SEED_ALPACA_MIRROR`, `AEGIS_SEED_ARENA` at boot), but the flag is an environment
variable on the hosted service, and the hosted service is off. **Unknown, and not to be
guessed:** whether the hosted database (the existing lanes' `paper_nav` history) is
preserved, and whether these lanes will resume on Railway, move to the PC, or be closed.
The local `backend/data/aegis_pi.db` holds only `book:` portfolios, so seeding a website
lane into it would start a second, disconnected record. Do not do that; ask the owner.

When hosting returns, the procedure is:

1. **Pre-register first** (see pre-register-trial): hypothesis, decision rule,
   canonical doc in `docs/TRIALS/`, committed BEFORE any forward data accrues.
2. **Own config file, own hash:** the new lane gets its own YAML (pattern:
   `backend/data/conservative_atr_lanes.yaml`) — never appended into a live config
   whose hash identifies existing segments. Mandates copied byte-identical
   where the trial demands a matched control.
3. **Build the full wiring, no-op until seeded** (mirror the exit-lane pattern,
   `backend/services/portfolio_intelligence/exit_lane.py`): idempotent `seed_*`
   function that registers the trial on seed; env-gated hook in `backend/main.py`
   (`AEGIS_SEED_<NAME>=1`); scheduler daily/MTM/nav-freshness, track-record router, and
   registry N_eff all skip-until-seeded.
4. **Test before the flag exists in prod:** hash isolation from every existing
   config; no-op-pre-seed; idempotent double-seed; registry-row-on-seed;
   frozen controls byte-untouched; overlay/decision rule fires on synthetic
   data. The lane suite (`backend/tests/portfolio_intelligence/`) must be green offline.
5. **Ship, then hand the owner the flag.** Only after the wiring is deployed and
   verified, ask the owner to set the env flag and redeploy. Never set a seed flag
   yourself.
6. **Verify the seed live:** registry `cumulative_trials` incremented; the new
   trial row carries the decision rule; the lane appears with its own hash;
   ALL pre-existing lanes' NAV/inceptions/segments untouched
   (lane-integrity-check). NAV for the new lane appears at the next hourly
   MTM — null mid-cycle is normal, not a failure.
7. **Ask the owner to UNSET the flag** after the seed is confirmed (seeds are
   idempotent, but unset is the attended discipline).

## Hard rules

- No forward record without its frozen identity committed first: a strategy contract
  for a paper book; a pre-registered trial row and canonical doc for a website lane or
  anything that will back a claim.
- No strategy change to an in-flight lane or book — a "v2" is a NEW one.
- The session builds and verifies; the human flips switches.
- Builders never deploy and never enable, create or disable a scheduled task.
- No order, no account reset and no broker call from this procedure, paper included.
