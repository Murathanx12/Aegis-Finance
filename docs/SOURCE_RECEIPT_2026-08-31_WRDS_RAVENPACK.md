# SOURCE RECEIPT — WRDS RavenPack entitlement — 2026-08-31

**Question (brief g §7.1):** does our WRDS account include RavenPack, which
would be the historical-news lane (2000 → Jul 2026) for T13 and event research
without buying a retail archive?

**Answer: NO. Not entitled.** Checked 2026-08-31 ~03:45 ET against
`wrds.Connection(wrds_username="murathan12")`, 318 libraries listed.

## What the account actually has

| library | tables | date range | rows |
|---|---|---|---|
| `ravenpack_trial` | 8 (`rpa_full_equities`, `rpa_full_global_macro`, `rpa_entity_mappings`, `rpa_taxonomy`, `rpa_source_list`, …) | **2020-09-30 → 2020-09-30 (ONE day)** | 409,198 equity events |
| `rpnasamp` | identical 8 | identical one day | identical 409,198 |

No `ravenpack`, `ravenpack_dj`, `ravenpack_full`, `ravenpack_web` or `rpna_*`
production library exists in the entitlement list.

## What the one day is still good for

Not history, but a **schema reference** for `EventCluster` v0 (brief g §6).
RavenPack's production feed on one full day shows the fields a mature vendor
found necessary, several of which map 1:1 onto our planned block:

- `event_similarity_key` + `event_similarity_days` — their canonical-event
  dedupe (our `event_id` / `independent_source_count` problem);
- `relevance` vs `event_relevance` — entity-level vs event-level weighting;
- `event_sentiment_score` — per-event, not per-article;
- `topic` / `group` / `type` — a three-level event taxonomy
  (our `event_type`);
- `rp_entity_id` + `rpa_entity_mappings` — entity resolution kept as its own
  table, not re-solved per article.

409,198 equity events in ONE day also calibrates the volume a whole-market
news sensor must survive: ~150m events/year. Per-article LLM calls at that
volume are not a design; clustering first is load-bearing, not an optimization.

## Consequence for the data-acquisition order (brief g §7)

1. ~~WRDS RavenPack~~ — **closed, not entitled.** Asking WRDS/HKU for an
   upgrade is a separate attended decision with a price tag, not a session task.
2. **EDGAR** bulk ($0) moves up to first position for under-covered names.
3. **GDELT** (1979→, 15-min updates, free) is the world/Asia sensor lane.
4. A paid archive (RavenPack direct, X full-archive, or a retail news API)
   is now a **buy decision** with this receipt as the "free option is gone"
   evidence.

*Checked by:* one `list_libraries()` + `list_tables()` + min/max/count probe
per library; the range probe is the receipt (`2020-09-30` twice, not an
unfetched guess — a library that EXISTS can still hold one day).
