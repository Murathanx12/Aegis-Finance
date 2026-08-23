# HANDOFF — for the next session (written 2026-08-23 evening)

**Read this first.** Supersedes `HANDOFF_2026-08-23_PROFIT_FIRST_SESSION.md`
for ordering; that document keeps the detail of what was built and why.

Governing docs: `docs/ROADMAP_2026-08-23_PROFIT_FIRST.md` (three licences,
queue) · `CLAUDE.md` (canon).

---

## 1. Where we are, in one paragraph

The programme spent five months building a disciplined research machine and
0 months earning money with it. Murat's ruling of 2026-08-23 reordered that:
**research rigour governs what Aegis CLAIMS, not what it TESTS in paper.**
Three licences now exist. The arena — ten paper books, daily decisions, frozen
information states, self-grading — is the product, and it is live. Demonstrated
market edge remains **0%**, which is the honest number and the one to move.

## 2. State of the machine

### LIVE in production
| | |
|---|---|
| deploy | verify the tip is live; last verified `624b7fa` |
| arena | **9 active books** (was 10 — see §3), daily 17:45 ET, trading days only |
| forecast populations | 3, each with its own health row and quiet clock |
| event store | wired to the arena's fetch; starts accruing on the next arena run |
| paper broker | targets + liquidation guards + per-target credentials |

### Waiting on a human, and ONLY these
1. **Create a second Alpaca PAPER account** and set `ALPACA_ARENA_API_KEY_ID`
   / `ALPACA_ARENA_API_SECRET_KEY`, then `AEGIS_PAPER_BROKER_TARGET=arena:<BOOK>`
   and one boot with `AEGIS_SEED_ALPACA_MIRROR=1`. The code refuses to reuse
   the lane's account, so this cannot be shortcut — and must not be.
2. Nothing else. The router flip, the lab decision and the identity fix are
   done.

## 3. What changed this session that the next session must know

**`PROFIT_ALLOCATOR_v1` is RETIRED.** It was seeded with the trust router's
cluster adjustment OFF; that setting is part of its policy identity; the
setting was corrected to ON, so the book correctly refuses its own seed. Its
ledger and NAV row are untouched on disk. `spec.RETIRED` records why.

**Book identity is now PER BOOK** (`fingerprint_scheme: "book-v1"`). Before
this, a comment typed anywhere in the arena YAML drifted all ten books. Adding
a challenger is now safe. **The ten live seeds migrate on first contact** — so
watch the next arena run's logs for ten `migrated to per-book identity` lines.
If a book instead raises `ConfigDrift` mentioning *"refusing to migrate"*, the
YAML changed before the migration ran: restore it, let the stamp take, re-edit.

**The lab is retired** (`docs/DECISION_2026-08-23_RETIRE_LAB.md`). Do not start
`rd_loop`. The abandoned v5 rewrite is on branch `lab-v5-abandoned`.

## 4. Do these next, in order

### P0 — verify what is already running
1. **Monday's `why_moved` run must break `live_forward`'s quiet clock.**
   Falsifiable: if `forecast_populations.populations.live_forward.last_written`
   still reads `2026-08-12` on Tuesday, the 2026-08-22 fix did not take and
   that is the P0. **Never backfill.**
2. **Confirm the ten seed migrations landed** (§3) and that nine books ran.
3. **Confirm `event_store` moved off `ABSENT`** after the first arena pass.

### P1 — the first paper book with a real evidence clock
4. **`PROFIT_ALLOCATOR_v2`.** Now unblocked: per-book identity means adding it
   to the YAML cannot disturb the other nine. Same rules as v1, seeded under
   the corrected router from birth. **It must NOT be given capital authority
   beyond v1's aggression knob** — the router still fails `edge_recovery_rate`
   (0.19 vs a 0.7 bar) and only decision days fix that.
5. **Seed one arena book to external paper** once §2.1 is done.

### P2 — the actor layer, which now has a validated premise
6. **Walk-forward the analyst persistence estimate.** One split is not an
   evidence clock; n=50 is thin. Cheap and honest.
7. **Grade on magnitude, not direction.** A hit-rate edge is not an economic
   one, and a `RESEARCH_CLAIM` needs the size.
8. **Extend the corpus** — Form 4 insiders, then 13F institutions, via the
   existing collectors. `disclosure_lag_days` already exists on the record.
   **Commentators last**: no clean timestamped feed exists, so that is an
   ingestion problem, not a statistics one.

### P3 — research, in parallel, blocking nothing
9. Memory-feasible linear arm · `signals_raw_plus` replication (a second
   vendor's characteristics panel, zero pulls) · risk-price forward
   registration · T2 prereg.
10. `optionm.opprcd` (4.31B rows) stays deferred until a named consumer exists.

## 5. Traps that cost real time this session

- **The local `.env` holds PROD Alpaca keys, loaded LAZILY.**
  `alpaca_available()` reads False until something imports `backend.db`, then
  True. A smoke-test `sync()` placed **12 real sell orders**. Never call
  `sync`/`seed` interactively.
- **Never push on a suite launched before your last edit.** CI caught two real
  bugs that way. Re-run after the final edit.
- **Verify in a clean clone** — but note `test_investigator_*` needs a sibling
  `Aegis module/` directory and fails in a scratchpad clone for that reason
  alone, not because anything is broken.
- **Prod deploys can lag ~100 minutes** behind a green CI. Do not conclude the
  deploy is broken until you have watched several CI runs go green with no
  movement.
- **`config_hash` is no longer the verification key.** A test that tampers with
  it to provoke drift will now pass; tamper with `book_fingerprint`.

## 6. The standard to hold

Three confounds were caught this session *before* they became findings, and all
three were the same shape — **correct arithmetic against the wrong world**:
an EW-market benchmark that measured sector exposure and called it analyst
skill; a blended null that credited pure-buy analysts with a base-rate gap; and
a "broken join" that was a US/global universe mismatch.

That is the house failure mode. When a result appears, the first question is
not "is the maths right" — it is **"is this the world the question was about."**
