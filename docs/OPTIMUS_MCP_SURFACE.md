# The read-only query surface the Optimus MCP wraps

**Implementation:** `backend/services/brain_queries.py` in `aegis-finance`.
**Wrapper:** the `optimus` repo, alongside `aegis_verified_state`,
`aegis_registry` and `brain_query` — the same shape as the tools that server
already runs.

Roadmap §11b. Written 2026-09-12 (chunk 8), pinned by
`backend/tests/test_brain_queries.py`.

## Why the split is this way round

The DATA lives in `aegis-finance`. The QUERY LAYER lives here too, so an MCP
tool cannot diverge from what the allocator itself reads — `farm_query` calls
the very function the registry export calls, and `leaderboard` reads the file
`to_registry()` wrote rather than recomputing it. Only the TRANSPORT (the MCP
tool registration and its JSON schema) belongs in `optimus`; building a second
server here would duplicate the one Optimus already runs.

Commits move between the two repos by hand. A change to these signatures is a
change on both sides, and `SURFACE` in `brain_queries.py` is the list to diff
against.

## Read-only is structural, not a flag

Qanat's MCP has 27 tools — 20 read, 7 write — and a `--read-only` mode that
restricts the agent to the 20. A flag can be off. **This surface has no write
tool at all.** `test_brain_queries.py` parses the module's AST and fails if it
ever calls `write_text`, `append`, `observe`, `supersede`, `mkdir`, `dump`,
`system`, `run` … or imports `subprocess`, `socket`, `requests`, a broker
client, or the execution ledger. That test also proves its own walker fires,
against a sample module that does write.

Three more refusals, each for a failure that has happened somewhere in this
programme:

1. **No query string, ever.** Filters are a typed DSL. There is no code path
   that evaluates an expression, so there is nothing to inject.
2. **Every read is bounded.** `limit` is capped at **1000** and the reply says
   `truncated: true` rather than quietly returning a page.
3. **Paths are sandboxed** to `backend/data/optimus`. A `job` name containing
   a path separator is refused: a job name is a name, and a path here would be
   a file-read primitive wearing a research tool's name.

A missing input answers `available: false` with a `why` beginning
`CANNOT DETERMINE`, never an empty success — a caller cannot otherwise tell an
empty answer from an absent one.

## The five signatures

```python
panel_query(fields: list[str] | None = None,
            filters: dict | None = None,
            limit: int = 500,
            as_of: str | None = None) -> dict
```
The joined news-return panel (`text_return_panel/news_returns_2025_26.parquet`,
340,465 rows on 2026-09-12). `filters` is `{field: {"op": ..., "value": ...}}`
with `op` in `eq · ne · in · not_in · gte · lte · gt · lt · between ·
contains`. A row MISSING the filtered field never matches.
`as_of` cuts on **`first_seen_utc`** — the stamp this repository wrote, not the
publisher's `published_utc`, which a vendor can backdate — and a row whose
anchor cannot be read is EXCLUDED and counted in
`n_dropped_no_readable_anchor`. Read that count: today only ~808 of 340,465
rows carry the anchor, so an `as_of` query returns almost nothing and that is a
fact about the anchor, not about the news.
Returns `{rows, n, n_matched, truncated, as_of_applied, as_of_anchor,
n_dropped_no_readable_anchor, available, source, pit_note}`.

```python
farm_query(preset: str | None = None,
           family_id: str | None = None,
           state: str | None = None,
           limit: int = 500) -> dict
```
`evidence_memory.registry_rows()` — the same call the registry export makes, so
this tool and the allocator cannot disagree. `state` is one of the registry's
own states (`IDEA / CONDITIONAL / SUPPORTED / REGIME_SPECIFIC / COST_KILLED /
REFUTED`). Returns `{rows, n, n_matched, truncated, meta, available, source}`.

```python
receipt(job: str, run: str | None = None) -> dict
```
One night job's receipt by name, newest night first. Night directories are
searched in NAME order, never mtime — on a fresh CI checkout every file is
written today, so an mtime order is an order on checkout time. Returns
`{available, job, run, path, n_nights_searched, receipt}` or
`{available: false, why: "CANNOT DETERMINE, no receipt at …"}`.

```python
leaderboard(limit: int = 500) -> dict
```
The registry export's `conditional_evidence` block from
`backend/data/signal_registry.yaml`, exactly as written — what the registry
SAYS, not what it would say if recomputed now. The key that answered
(`rules`, `families` or `rows`) is reported as `rows_key`, so a rename shows up
as a changed field rather than as an empty leaderboard.

```python
books(limit: int = 500, include_shadow: bool = False) -> dict
```
The declared paper books through `backend.services.paper_books`, never by
globbing a directory. Nested dataclasses (a `PaperBook` carries a whole
`Strategy`) are walked into rather than stringified, so the reply is real JSON
on the far side. Shadow books are excluded by default: a shadow book is a
diagnostic, and listing it beside the live ones is how a diagnostic gets quoted
as a track record.

## What this surface is NOT

It does not seed a lane, size a position, place an order, write a receipt,
grade a forecast or promote anything. It answers questions about what is
already on disk. Any tool that needs to CHANGE something is a different
surface, with its own approval path, and it does not live in this module.
