# Adjudication — the 19,961-record ledger divergence (D4)

**Ordered by** `docs/HANDOFF_OPUS5_2026-08-15.md` Order 3.
**Adjudicated** 2026-08-15. **Nothing was copied, merged, or deleted.**

The boot warning that prompted this:

> `ledger migration: /app/backend/data/optimus/predictions.jsonl holds 19961
> record(s) absent from the persisted ledger at /data/optimus/predictions.jsonl
> — NOT copied (the persisted ledger is authoritative once non-empty)`

## 1. The question was asked backwards

The handoff framed this as "19,961 rows are missing from the persisted ledger,
decide whether to merge them or declare them dead." Both options assume the
persisted ledger is the real one and the image copy is the orphan.

It is the other way round. **The persisted ledger's 112 records are a partial
copy of the campaign ledger.** They are not the live product's accrual, and
`LIVE_FORWARD` currently contains no genuine live-product evidence at all.

## 2. Evidence

The migration guard computes `legacy_only` as a set difference over **full-record
content hashes** (`belief_state.ensure_ledger_migrated`), so a record matches
only if every field matches.

| Fact | Value | Source |
|---|---|---|
| Image-copy records | 20,073 | `backend/data/optimus/predictions.jsonl` (git-tracked) |
| Persisted records | 112 | `aegis_verified_state.prediction_ledger.n_records` |
| Reported `legacy_only` | 19,961 | boot warning |
| ⇒ intersection | 20,073 − 19,961 = **112** | arithmetic |
| ⇒ therefore | **persisted ⊆ image, exactly** | 112 of 112 matched |

A genuinely independent population cannot collide on 112 of 112 full-record
hashes: `prediction_id` is one of the hashed fields and is unique per record.

Four independent corroborations that the persisted 112 are specifically the
**first 112 rows** of the image file:

1. **Distinct specialists.** Prod reports 12. The image file's first 112 rows
   contain exactly 12; its last 112 contain 14.
2. **The six voids.** Prod reports `n_void: 6`. The entire 20,073-row file
   contains exactly six records carrying a `void_reason`, and they sit at
   indices 58, 60, 62, 64, 66, 68 — all inside the first 112.
3. **Distinct models.** Prod reports 1. The file is 100% `deepseek-chat`.
4. **Last written.** Prod reports 2026-08-12; the first 112 rows span
   2026-08-11/12.

## 3. What the records are

Every one of the 20,073, without exception:

- **Dated 2026-08-11 (87) or 2026-08-12 (19,986)** — the LLM-SWARM-1 /
  GRAND-ARENA-1 run. The same run tore the two `llm_calls.jsonl` lines
  quarantined under Order 1, at 10:32 and 10:42 UTC on 2026-08-12.
- **`model: "deepseek-chat"`** — a name the vendor silently served as
  `deepseek-v4-flash`. The model field is known-false on all of them.
- **No `population` field and no `arm` field.** They predate both.
- **`outcome: null` on all 20,073.** Nothing has ever resolved.

The six void records are worth naming, because they are the origin of a suspect
that has now cost two sessions: their `void_reason` is *"threshold given in
percent, not a decimal fraction"*. That is where "a size bound in percent where
a fraction is required" came from as the leading explanation for Night 1's
barren cells. It was the right diagnosis of **this** file and the wrong one for
Night 1 — refuted in Order 2 both by arithmetic and by live measurement.

## 4. Ruling

### 4a. The 19,961 — CAMPAIGN_FORWARD, alive, merge stays refused

They are not dead and must not be archived. `services/evidence_population.py`
already classifies them correctly: they are `CAMPAIGN_FORWARD`, the population
`ABLATION_FWD` certifies against and the one whose first resolutions fall due
**2026-08-16, attended**. The guard's refusal to copy them into `/data` was
right and stays.

What was missing was only this document. The warning now has an adjudication to
point at, which is the difference between a known state and a line nobody reads.

### 4b. The 112 — NOT live-product evidence

`evidence_population.py` describes `LIVE_FORWARD` as *"the deployed product's own
accrual — ~112 records on the Railway persistent volume."* That description is
false, and the code comment has been corrected.

Consequences:

- **`LIVE_FORWARD` has a true population of zero.** The product has accrued no
  forward evidence. This is not a problem to be fixed; it is the honest state,
  and it is what the README's new ⚪ ARMED badge says.
- **Any claim about the live deployment's forward record, built on those 112,
  would be reporting campaign swarm rows as live product evidence** — the exact
  pooling the module exists to prevent, having already happened once, quietly,
  in the direction nobody was watching.
- **`pi_ledger_resolve` resolves the `LIVE_FORWARD` ledger.** Left alone it will
  resolve campaign rows under the live population's name. See Order 4.

### 4c. What was NOT done, and why

The persisted ledger was **not** mutated. Deleting 112 rows from the
authoritative volume is irreversible, outward-facing, and changes what a
production surface reports; it needs Murat's word, not a session's judgement.
No data is at risk in the meantime — every one of the 112 exists in the campaign
ledger, which is git-tracked.

Instead the finding is enforced non-destructively: `evidence_population` now
carries `live_forward_is_established()`, which reports the population as
**UNESTABLISHED** when every record in it is content-identical to a campaign
record. A surface that cannot tell the difference now refuses to claim one.

## 5. The decision left for Murat

Quarantine the 112 out of `/data/optimus/predictions.jsonl` under a dated
migration receipt, leaving `LIVE_FORWARD` genuinely empty?

- **For:** it is the true state, and the resolver stops grading campaign rows as
  live ones.
- **Against:** it mutates the authoritative persisted ledger, which nothing has
  done before.
- **Not urgent:** the guard in 4c already prevents the false claim. The rows can
  sit there, correctly labelled unestablished, indefinitely.

**Recommendation: do it, once, attended, with a receipt** — after the 2026-08-16
campaign resolutions, so the two events cannot be confused in the record.
