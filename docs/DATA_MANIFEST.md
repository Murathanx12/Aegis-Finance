# docs/DATA_MANIFEST.md — the big local artefacts, and how to get them back

**Created 2026-09-03.** House rule: **receipts are committed, raw substrate is
not.** A derived JSON receipt with a headline number in it belongs in git. A
multi-gigabyte panel pulled from a vendor does not — it bloats the clone, it
churns `git status` mid-pull (which on 2026-08-20 flipped a launcher receipt's
`git_dirty` flag), and it is reproducible from its own script.

The failure mode this file exists to prevent is the other one: **an untracked
file that nobody can find again.** *Absence of a local object is not evidence of
absence* — but absence of a **record** of the object is how a session concludes
the data was never pulled and pulls it a second time. Every artefact below is
ignored on purpose, and named here so it stays findable.

**If you add an ignore rule for a data file, add its row here in the same
commit.** An ignore rule without a manifest row is the bug.

## Ignored by explicit rule

| Path | Size | Produced by | What it is | Rebuild |
|---|---:|---|---|---|
| `backend/data/optimus/wrds/crsp_monthly_panel_2013_2024.json` | ~31.9 MB | WRDS pull scripts (`scripts/wrds_*`) | CRSP monthly panel, 2013–2024. Substrate for the tracker/IBES backtests. | Re-pull from WRDS `crsp.msf` + `crsp.msenames` |
| `backend/data/optimus/wrds/tr13f_quarterly.json` | ~25.3 MB | WRDS pull scripts | Thomson Reuters 13F quarterly holdings. Substrate for the holder-provenance work (H2/H3). | Re-pull from WRDS `tr_13f.s34` |

The derived, committed evidence for both is in
`backend/data/optimus/tracker_backtest/` — `holder_h2_h3.json`,
`holder_fingerprint_summary.json`, `ibes_status_rules_2013_2024.json`,
`topn_concentration.json`. **Quote the receipt, not the panel.**

## Ignored by the blanket `*.parquet` rule (.gitignore line 63)

These are the LEARNER v1 tables. They are large, they are regenerable, and their
schema + every headline number is committed.

| Path | Size | Produced by | Rebuild |
|---|---:|---|---|
| `backend/data/optimus/learner/train_table.parquet` | ~200 MB | `python -m scripts.learner_run` | rerun the script |
| `backend/data/optimus/learner/beta_panel.parquet` | ~104 MB | `python -m scripts.band_horizon_run --build-betas` | rerun the script (~18 s from the CRSP daily files) |
| `backend/data/optimus/learner/beta_panel.parquet` | ~104 MB | `python -m scripts.band_horizon_run` | rerun the script |
| `backend/data/optimus/learner/oos_predictions_1m.parquet` | ~21.9 MB | `python -m scripts.learner_run` | rerun the script |
| `backend/data/optimus/learner/states/company_states.parquet` | ~35.9 MB | `python -m scripts.learner_states_run` | rerun the script (~11 min) |
| `backend/data/optimus/learner/states/market_states.parquet` | ~7 KB | `python -m scripts.learner_states_run` | rerun the script |
| `backend/data/optimus/actor_corpus/ibes_graded.parquet` (row-level analyst target grades) | varies | `scripts/tracker_ibes_backtest.py` | rerun the script |

Many more `*.parquet` panels live under `backend/data/optimus/` (aegis_panel,
crsp_pit, convexity, datasets, event_response, …). They are all ignored by the
same blanket rule and all regenerable by their own scripts; list them with
`find backend/data/optimus -name '*.parquet'`.

Committed counterparts, which are what a session should read:

- `backend/data/optimus/learner/train_table_schema.json` — the schema, the
  feature list, the missingness table, the schema hash.
- `backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json` — the
  STATES v1 receipt: state definitions, sizes, transitions, per-state conditional
  tables, the within-band control and the shuffled null. Written by
  `scripts/learner_states_run.py`; read it before quoting anything from
  `docs/STATES_2026-09-03_UNSUPERVISED_V1.md`.
- `backend/data/optimus/tracker_backtest/learner_v1.json` — the full
  pre-registration header, every arm's scoreboard, the verdicts.
- `backend/data/optimus/learner/shadow_book_2026-09-02.json` — the sealed
  shadow book.

Row-level parquet for `analyst_target_grades.json` and `time_machine_arena.json`
is **local-only** — read each receipt's `read_me_first` before quoting a number
that only exists in the rows.

## Ignored by the model rules (`*.joblib`, `*.pkl`)

| Path | Produced by | Provenance |
|---|---|---|
| `backend/data/optimus/learner/models/champion_full.joblib` | `scripts/learner_run.py` | vintage sha `3300a8550a4cc99e`, trained through 2024-11 — recorded in `learner_v1.json → sealed_models.full` |
| `backend/data/optimus/learner/models/champion_shadow.joblib` | `scripts/learner_shadow_seal.py` | vintage sha `1dcee45058e078aa` — `sealed_models.shadow` |
| `backend/models/crash_model.pkl` | `python -m engine.training.train_crash_model` | trained on deploy |

**A model binary is not evidence; its vintage hash in the receipt is.** If the
binary is missing, the receipt still tells you exactly which model produced the
numbers, and the script rebuilds it deterministically (`seed 20260902`).

## Secrets, which are ignored and stay put

`.env`, `.env.local`, `.env.production`, `.env.hidden`, `.env.*.hidden`, and (added
2026-09-03) `.env.bak` / `.env.bak.*`.

`.env.bak.2026-08-27` exists in the working tree and **contains live keys**. It
is ignored, it is deliberately **not deleted and not moved** by any session, and
it is not staged. If it should leave the tree, a human moves it. The reason for
the rule is on the record: on 2026-08-24 a CI-mimic recipe moved `.env` aside
inside a subshell whose EXIT trap never ran, and the machine lost every key on
it. Use `AEGIS_IGNORE_DOTENV=1` to reproduce CI; never move a key file.
