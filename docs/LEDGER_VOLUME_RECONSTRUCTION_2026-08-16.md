# The volume never changed — reconstruction of the "20,073 vs 112" boots

**Ordered by** the principal review §2: *"Before quarantining or deleting
anything from the production volume, reconstruct exactly which filesystem path
was mounted at each boot, which ledger each process read, whether the persistent
volume was mounted differently, why the observed population changed, and which
file is authoritative for each population. Observation is not enough here
because the proposed operation is irreversible."*

**Answer: the volume was mounted identically at every boot, both files were
readable at every boot, and the population never changed.** The open item was a
misreading of one log line, not an infrastructure fault.

Nothing was written, moved or deleted to establish this.

---

## 1. The question, as the last session left it

> *"I did **not** reconstruct why the 02:06 boot reported 20,073 records and the
> 04:07 boot reported 112. Something about volume mounting changed between them
> and I did not chase it."*
> — `HANDOFF_2026-08-16_SESSION_REVIEW.md` §9.7

## 2. The 02:06 boot, from its own deployment's logs

Deployment `7e2bbe35-5a47-427b-8218-c6df4850fc06` covers both the 17:42 UTC
start and the 02:06 UTC restart. Its logs:

```
Mounting volume on: .../bind-mounts/9fe74ada-…/vol_ejglke5as9a86nhc
Starting Container
2026-08-15 17:42:46  ledger migration: … 19961 record(s) absent … NOT copied
2026-08-15 17:42:46  Prediction-ledger persistence: {'dest_dir': '/data/optimus',
                     'legacy_dir': '/app/backend/data/optimus', … 
                     'legacy_records': 20073, 'dest_records': 112, …}

Mounting volume on: .../bind-mounts/9fe74ada-…/vol_ejglke5as9a86nhc
Starting Container
2026-08-16 02:06:29  ledger migration: … 19961 record(s) absent … NOT copied
2026-08-16 02:06:29  Prediction-ledger persistence: {'dest_dir': '/data/optimus',
                     'legacy_dir': '/app/backend/data/optimus', …
                     'legacy_records': 20073, 'dest_records': 112, …}
```

**Byte-identical migration reports.** Same volume ID `vol_ejglke5as9a86nhc`, same
`dest_dir`, same counts. The later boots at 04:36, 05:40 and 05:59 UTC (a new
deployment, bind-mount `b7276b11-…`, the **same** volume) print the same line.

## 3. So where did "20,073" come from

**From that log line.** Every boot reports both numbers a few characters apart:

```
'legacy_records': 20073,   <- the in-IMAGE campaign file, /app/backend/data/…
'dest_records': 112,       <- the persisted volume,       /data/optimus/…
```

`ledger_health()` reads `_config.OPTIMUS_LEDGER_DIR`, which is `/data/optimus`
whenever `AEGIS_DATA_DIR` is set — and it was set at every boot, since
`dest_dir` resolved to `/data/optimus` at every boot. `n_records` was therefore
**112 at 02:06 as well**; the 20,073 in the same log block belongs to the other
file.

## 4. Why both files exist, and why that is correct

`backend/services/evidence_population.py:143` routes the two populations to two
paths **on purpose**, with the reason in the code:

| population | path | records | authoritative for |
|---|---|---|---|
| `CAMPAIGN_FORWARD` | `/app/backend/data/optimus/predictions.jsonl` (in-image, git-tracked) | 20,073 | the LLM-SWARM-1 / GRAND-ARENA-1 campaign |
| `LIVE_FORWARD` | `/data/optimus/predictions.jsonl` (Railway volume) | 112 | the deployed product's own accrual |

> *"NOT derived from `AEGIS_DATA_DIR`: the campaign's history is a repository
> artifact and must not follow a volume mount around."*

The migration deliberately refuses to merge them: once the volume is non-empty
it is authoritative and the image copy is reported, not copied.

## 5. And the 112 are not an independent population

Established 2026-08-15 (`LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md`) and
re-checked here: `legacy_only = 19,961` is a set difference over **full-record
content hashes**, so

```
20,073 − 19,961 = 112   ⇒   persisted ⊆ image, all 112 of 112
```

with four independent corroborations (12 distinct specialists, the six
`void_reason` records at indices 58–68, one model, last-written 2026-08-12) all
pointing at the **first 112 rows** of the campaign file.

**`LIVE_FORWARD` therefore contains no live-product evidence at all.** It holds
a partial copy of the campaign run, and its 25 overdue records are 25 campaign
records that the nightly `pi_ledger_resolve` job cannot resolve.

## 6. What this licenses, and what it does not

**Licenses:** the campaign resolution against `CAMPAIGN_FORWARD` is untouched by
any of this. The resolver writes to the repo file; production reads the volume
and the migration will not copy into a non-empty destination. **The two
operations cannot contaminate each other, by construction and now by receipt.**

**Still does not license the quarantine.** The blocker the review named is
cleared — there is no unexplained mount behaviour — but the operation remains
irreversible and outward-facing, so it stays attended. What it should do is now
exactly specified:

* the 112 records in `/data/optimus/predictions.jsonl` are campaign records
  sitting in the live population by accident of an early copy;
* quarantining them (moving them to a dated sidecar, not deleting) leaves
  `LIVE_FORWARD` at zero records, which is the honest state — the live product
  has never written a forecast;
* `ledger_health` then reports `DEGRADED` for the *right* reason ("the ledger is
  empty — no forecast has ever been written"), which is a true statement about
  the product rather than a false statement about a backlog.

**One thing worth flagging separately:** three container restarts inside ninety
minutes (04:36, 05:40, 05:59 UTC) and one unexplained restart at 02:06 UTC on a
deployment started 8.4 hours earlier. None of them lost data — the volume is
doing its job — but a service restarting that often is worth a look before the
paid night runs against it.

— builder, 2026-08-16. Read-only: no file on the volume was opened for writing.
