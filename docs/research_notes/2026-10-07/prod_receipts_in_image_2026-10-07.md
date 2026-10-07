# Prod receipts in image — 2026-10-07

## The finding (restated)

Prod deploy `e041ec14`, 2026-10-07 14:09 HKT: `/openapi.json` lists all six new
routes (`/api/arena/v1/latest`, `/api/legibility/v1/{forecast-lab,theory-lab,
system-health,brain}`, `/api/opportunities/latest`); every one answers 404
while `/api/health/full` is 200.

## Cause (reproduced locally, no Docker needed)

**Not** a Dockerfile/.dockerignore omission. Verified directly:

- `git ls-files backend/data/public_receipts` lists all 7 tracked files
  (`arena`, `forecast_lab`, `opportunities`, `system_health`,
  `theory_lab_basket`, `theory_lab_sticky`, `MANIFEST.json`; `brain` was
  genuinely missing — see "Also fixed" below) — the folder IS committed.
- `backend/Dockerfile` has `COPY backend/ backend/`, which brings the whole
  tree, `public_receipts/` included.
- `.dockerignore` excludes `.git .github .vscode .idea .claude __pycache__
  *.pyc *.egg-info .venv venv node_modules .next out .env* *.log *.parquet
  data_cache .cache .pytest_cache docs *.md` (with `!backend/requirements.txt`)
  — none of these patterns match any path component under
  `backend/data/public_receipts/` (`data` ≠ `data_cache`; `*.md` doesn't
  touch `.json` files).

**The real cause** is a path that resolves correctly from source and
differently once an env var moves in prod — the exact "frozen path family"
shape CLAUDE.md already warns about:

- `backend/config.py`: `DATA_DIR = Path(os.getenv("AEGIS_DATA_DIR", BACKEND_DIR
  / "data"))`. Locally `AEGIS_DATA_DIR` is unset, so `DATA_DIR ==
  BACKEND_DIR/data`. **On Railway `AEGIS_DATA_DIR=/data`** — a persistent
  volume — set deliberately (see the comment at `config.py:103-106`) so the
  volume does **not** shadow the image.
- `OPTIMUS_LEDGER_DIR = DATA_DIR / "optimus"` therefore follows that override.
- `publish_receipts.public_dir()` used to be
  `Path(OPTIMUS_LEDGER_DIR).parent / "public_receipts"` — a SIBLING of the
  ledger dir, on purpose, so a test that points the ledger dir at a tmp folder
  never reads the real published copies.
- In prod that sibling relationship means `public_dir()` resolves to
  `/data/public_receipts` (the volume), which is empty — nothing has ever
  published there — instead of `/app/backend/data/public_receipts` (the
  image, where the git-tracked copy actually lives). The live receipts are
  also absent from the fresh volume for these page kinds, so **both** the
  live path and the "fallback" path pointed at the same empty tree, and the
  committed copy was never consulted.

### Reproduced locally

```
AEGIS_IGNORE_DOTENV=1 AEGIS_DATA_DIR=/tmp/aegis_prod_sim AEGIS_PERSONAL_MODE=0 \
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8012
```

Before the fix: `/api/health` 200; all six of
`/api/arena/v1/latest`, `/api/legibility/v1/{forecast-lab,theory-lab,
system-health,brain}`, `/api/opportunities/latest` → **404**. Exact match to
the prod finding, reproduced without Docker and without touching `.env`.

## Fix

`backend/config.py` gains `PUBLIC_RECEIPTS_DIR`, fixed to the image and
**independent of `DATA_DIR`/`AEGIS_DATA_DIR`**:

```python
PUBLIC_RECEIPTS_DIR = Path(os.getenv("AEGIS_PUBLIC_RECEIPTS_DIR",
                                      str(BACKEND_DIR / "data" / "public_receipts")))
```

`backend/services/publish_receipts.py::public_dir()` now returns
`Path(_config.PUBLIC_RECEIPTS_DIR)` instead of
`Path(_config.OPTIMUS_LEDGER_DIR).parent / "public_receipts"`. In dev
(`AEGIS_DATA_DIR` unset) the two are byte-identical, so dev/CI behaviour is
unchanged. In prod, `PUBLIC_RECEIPTS_DIR` stays pinned to the image's
`backend/data/public_receipts/` regardless of where the volume is mounted.

Three test fixtures that previously got isolation "for free" from the old
sibling coupling (`test_legibility_routers.py::client`,
`test_opportunities_router.py::client`,
`test_publish_receipts_c15.py::world` and its two other
`OPTIMUS_LEDGER_DIR`-monkeypatching tests) now additionally monkeypatch
`_config.PUBLIC_RECEIPTS_DIR` to the matching tmp path.

Reproduced locally after the fix (same command as above, fresh
`AEGIS_DATA_DIR`): all six endpoints → **200**, each with
`served_from` naming the published copy, e.g.

```
"public_receipts/arena/latest.json (published 2026-10-07T06:17:10+00:00): the
live receipt directory on this server lacks this page's receipts; ages are
recomputed now from each receipt's own stamp"
```

## Also fixed: `brain` publishes now

`python -m scripts.publish_receipts` (no `--commit`) was run. Before: the
`brain` kind was `MISSING` (never published). After:

```
arena                OK           627,159 B
arena_stories        MISSING            0 B  the builder found no receipt on this machine
forecast_lab         OK            81,806 B
theory_lab_sticky    OK           564,752 B
theory_lab_basket    OK           566,282 B
system_health        OK            58,235 B
opportunities        OK         2,398,609 B
brain                OK            34,891 B
OK: 4,331,734 / 5,000,000 bytes; written=True
```

`backend/data/public_receipts/brain/latest.json` now exists.
`arena_stories` stays MISSING — no `decision_story/stories_*.jsonl` exists on
this machine yet, named rather than silently absent (it has no router
endpoint among the six under test; `/api/arena/v1/stories` is separate and
was not part of this finding).

**Public folder size: 4,347,015 bytes (≈4.33 MB) — under the 5 MB
(`PUBLIC_RECEIPTS_MAX_BYTES`) budget**, with ~653 KB of headroom. The
orchestrator still needs to run `publish_receipts --commit` (or the
equivalent daily-catalog step) to push this to `main` before Railway's next
build picks it up — writing the folder does not publish it by itself.

## New guards

1. `backend/tests/test_dockerfile_public_receipts.py` (new file, 3 tests):
   parses `backend/Dockerfile`'s `COPY` lines and `.dockerignore`'s patterns
   and checks every file `git ls-files backend/data/public_receipts` reports,
   deterministically, without Docker. Confirms today's finding (Dockerfile OK,
   .dockerignore OK) and catches a FUTURE edit (e.g. someone broadening
   `data_cache` to `data*`, or adding `*.json` to cut image size) before it
   ships.
2. `backend/tests/test_publish_receipts_c15.py`, two new tests:
   - `test_public_receipts_dir_does_not_follow_optimus_ledger_dir` — the
     direct regression guard: `public_dir()` must not move when
     `OPTIMUS_LEDGER_DIR` moves.
   - `test_routers_serve_the_real_committed_receipts_when_live_dir_is_empty_but_present`
     — the literal production shape (a live `OPTIMUS_LEDGER_DIR` that exists
     but is empty) exercised against the REAL, git-committed
     `backend/data/public_receipts/`, not a tmp fixture standing in for it.
     All six endpoints must be 200 with `served_from` naming the published
     copy.

## How the verify-prod check now reads

After the next deploy (commit carrying this fix + the `brain` publish +
whatever `--commit` run lands it on `main`), `verify-prod-after-deploy`
should see, for all six endpoints:

- `GET /api/arena/v1/latest` → 200, `served_from` starts with
  `public_receipts/arena/latest.json` until the live ROI receipt accrues on
  the volume, then flips to live (`served_from: null`) once `prefer_published`
  judges the live copy newer/more complete.
- `GET /api/legibility/v1/forecast-lab` → 200, same pattern, `served_from`
  starts with `public_receipts/forecast_lab/latest.json`.
- `GET /api/legibility/v1/theory-lab?board=sticky` and `?board=basket` → 200,
  `served_from` starts with `public_receipts/theory_lab_{sticky,basket}/latest.json`.
- `GET /api/legibility/v1/system-health` → 200, `served_from` starts with
  `public_receipts/system_health/latest.json`.
- `GET /api/legibility/v1/brain` → 200 (was 404 before this session; the kind
  had never been published), `served_from` starts with
  `public_receipts/brain/latest.json`.
- `GET /api/opportunities/latest` → 200, `served_from` contains
  `public_receipts/opportunities/latest.json (the sanitised public copy; no
  live receipt on this server)`.

Each should also still report `/api/health/full`'s `deploy.commit` equal to
the pushed sha and `scheduler.nav.all_fresh: true` per the skill's existing
steps — this fix changes nothing about health/NAV, only where the six pages'
fallback reads from.
