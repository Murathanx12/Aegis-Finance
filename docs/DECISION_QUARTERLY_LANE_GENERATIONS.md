# DECISION — Quarterly lane generations (Murat, 2026-08-19 evening)

Murat's instruction, recorded verbatim in intent: every ~3 months the
paper-lane fleet gains a NEW GENERATION of lanes embodying whatever the
referee has verified since the last generation. Existing lanes are never
edited and never stopped early; generations run side by side and the
comparison is the product.

## The standing rule

1. **Cadence:** a generation window opens every quarter from inception
   (2026-06-08). Generation 2 target launch: **2026-09-08**. A window may
   pass unused (nothing verified ⇒ nothing launched — a lane needs a
   finding, not a calendar).
2. **What qualifies a new lane:** at least one referee-surviving result
   (registered trial, receipt on disk) that the lane's rule transports
   into forward practice. "We think" does not qualify; "we measured, and
   here is the receipt" does.
3. **Never backdated.** A lane's history starts at its flag flip.
   Comparisons are presented BOTH calendar-aligned (same weeks for
   everyone) and age-aligned (each lane's own day 1..N). No "as if it
   started in June" curves, ever — that is the survivorship machine.
4. **Every treatment lane ships with its control twin** (same universe,
   same cadence, minus the one rule being tested), so the generation
   comparison isolates the finding rather than the weather.
5. **Old generations keep running.** They are the baseline the new
   generation must beat in the open. Retiring a lane is itself an
   attended, recorded decision with a reason.
6. **Reads:** quarterly internal generation reads at SCREEN discipline
   (looking is fine, claiming needs the pre-registered bar); the
   24-month no-public-skill-claims rule is untouched and applies per
   lane from its own inception.
7. **Launch mechanics:** per `seed-a-lane` — pre-registered YAML, own
   config hash, own inception, env-gated, Murat flips the flag. Nothing
   here weakens that.

## Generation 2 candidates (from findings verified as of 2026-08-19)

- **G2-WINNER-HOLD pair** — transports CONVEXITY-PRESERVATION-1
  (trims/exits at +40 destroyed 60d wealth; Holm-surviving):
  - `g2_rebalance_control`: base balanced rules, standard periodic
    rebalance (rebalancing IS systematic winner-trimming — that is the
    point of this control).
  - `g2_winner_exempt`: identical, except a position up ≥40% since entry
    is EXEMPT from rebalance trims for the next 60 trading days (the
    window the trial measured). One rule difference, nothing else.
- **G2-RISK-SIZED pair** — transports the NET tournament risk result
  (ridge predicts vol IC ~0.65; return ranking NOT_ESTABLISHED):
  - `g2_equal_weight_control`: equal weight, same universe.
  - `g2_inverse_vol`: weights ∝ 1/predicted vol from the frozen ridge
    risk head; predictions logged nightly PIT before use.
- Both pairs run the same universe and calendar; four lanes total, sized
  to keep the fleet legible.

Designs go to full pre-registration (hypothesis, rules as YAML, §64
power note on the 90-day read) before 2026-09-08; Murat signs and flips.

— recorded 2026-08-19 evening; generation-2 preregs are the next
day-session deliverable
