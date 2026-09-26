# Owed hooks, 2026-09-27: cluster-aware bridge, archive-clean readers, health caller

What landed in the commit that carries this note, and the two patches it could not apply.

## Landed

1. **Cluster-aware bridge.** `scripts/bridge_report.py` loads the newest
   `signal_structure_*.json`, the monthly NET parquet it names and `etf_monthly.parquet`.
   - Every row gets `cluster_full` and `cluster_sealed`.
   - A book frozen after the receipt is placed by its rule's primary cell (`clusters.rules_*`).
     It is not counted as a new bet.
   - The report prints a "distinct bets under test" count beside the book count.
   - It prints a cluster table where each cluster is one observation (the members' mean forward
     relative).
   - It prints a per-book 2024-26 decomposition: alpha/mo and t, beta to SMH/MTUM/IWM, and R².
     The dominant ETF is the largest positive t in the full-window fit, with t ≥ 2.
   - It prints "expected alpha after SMH/MTUM/IWM" beside "expected rel. to SPY".
   - It prints forward vs SPY beside forward vs the dominant ETF. A missing ETF series refuses
     by name.
   - `FACTOR_BETA` joins the taxonomy, before `RANDOMNESS`. It fires when beta × (ETF − SPY)
     over the forward window is negative and the book, net of that move, no longer trails SPY
     by more than one monthly sigma.
   - `docs/BRIDGE.md` and the README section were re-rendered, not hand-edited.
2. **Four corpus readers use `news_registry.grade_row`.** The readers are
   `night_e1_news_return_panel` (`build` and `_corpus_rows`), `night_l2_typed_events` (the
   corpus plan and the panel plan), `n5_event_compression.load_news_rows`, and
   `morning.step_digest`.
   - Each one excludes `pit_grade: archive` rows.
   - Each receipt carries a `news_registry.archive_receipt` block: `rows_read`,
     `archive_rows_excluded` by source, and `rows_without_stamp_pair`.
   - About the stamp pair: the terminal repo's observation corpus stamps only `observed_at`
     (the provider publish time). No row there can be proven an archive. Three of the four
     readers read that corpus, so their `archive_rows_excluded` is 0 by construction. The
     `rows_without_stamp_pair` count says so, rather than letting "0 excluded" read as clean.
3. **The health step has a caller.** `daily_pass` gains a final `health` step.
   - It writes the `system_health` receipt and never fails the pass.
   - It copies every non-ALIVE row into its `refusals`, so `print_receipt` prints them.
   - The `daily_pass` probe inside it judges the PREVIOUS pass, because today's receipt is
     written after this step.
   - `scripts/stack_health.py` is now a thin wrapper over `system_health`. Its CLI is the same
     plus `health_probe`'s flags, and it uses `health_probe`'s exit codes. `--deep` adds two
     completion rows. `/api/control/sim/preflight` keeps its `{green, red, rows, at}` shape.
   - The broker `/v2/account` check is gone, because `system_health` has no broker probe. That is
     a gap to add there, not to re-grow here.

## Owed patch 1: `attention_z` archive exclusion (`backend/services/pit_features.py`, not mine tonight)

`news_frame` reads `first_seen_utc` only. Its docstring names the defect: 2015 Benzinga items
first seen in 2026-09 are counted as 2026-09 news. They inflate `attention_z` on the backfill
days and mark those sessions COVERED. The patch drops archive rows before both the count and
the coverage stamps, and counts them:

```python
def news_frame(news_rows: Iterable[dict] | pd.DataFrame) -> pd.DataFrame:
    from backend.services.news_registry import is_archive          # + wave-2 §3
    recs = news_rows.to_dict("records") if isinstance(news_rows, pd.DataFrame) else list(news_rows)
    out = []
    stamps = []
    n_archive = 0                                                   # +
    for r in recs:
        if is_archive(r):                                           # +
            n_archive += 1                                          # +
            continue                                                # +
        fs = r.get("first_seen_utc")
        ...
    df.attrs["coverage_stamps"] = stamps
    df.attrs["archive_rows_excluded"] = n_archive                   # +
    return df
```

In `compute()` (line ~543), print it on the receipt: keep the frame and write
`meta["attention_archive_rows_excluded"] = nf.attrs.get("archive_rows_excluded", 0)` when
`meta is not None`. Test: a two-row frame with one archive row gives one ticker row and
`attrs["archive_rows_excluded"] == 1`.

## Owed patch 2: the 30-minute health tick (`scripts/always_on_lab.py`, not mine; the lab runs old code)

Three edits must land together. `always_on_lab` asserts at import that `PERIODS`, `TIMEOUTS` and
`HANDLERS` equal `LOOPS`. So adding the config keys without the loop, or the loop without the
keys, is an `AssertionError` on the lab's next start. That is why neither half was applied here.

```python
# scripts/always_on_lab.py, LOOPS, immediately before ("status", ...):
    ("health", "every subsystem probed from the evidence it wrote ($0, no model)"),

# backend/config.py
LAB_LOOP_PERIODS_MINUTES["health"] = 30        # inside the dict literal
LAB_LOOP_TIMEOUT_S["health"] = 300             # inside the dict literal

# scripts/always_on_lab.py, beside loop_status:
def loop_health(state: LabState) -> dict:
    """docs/HEALTH_PROBES_2026-09-26.md owed caller: the probe table every 30
    minutes, persisted, so HEALTH.md is never older than half an hour."""
    from backend.services import system_health as SH
    out = SH.run(ctx=SH.make_ctx(allow_proc=True), persist=True)
    bad = [r for r in out["rows"] if r["verdict"] != "ALIVE"]
    return {"status": "ok", "rows": len(out["rows"]), "counts": out["counts"],
            "exit_code": out["exit_code"], "receipt_path": out.get("path"),
            "non_alive": [SH.row_line(r)[:200] for r in bad],
            "headline": f"health rc {out['exit_code']}: {out['counts']}"}

# HANDLERS:
    "health": loop_health,
```

The loop does not touch the model, so it stays out of `LAB_MODEL_LOOPS`.
`test_always_on_lab.py` covers the three-way equality. The lab must be restarted by PID, never
by image name. The new loop proves itself with its first `lab_status.json` row
`loops.health.last_tick_utc`.

## Also owed, found on the way

- **The SMH and MTUM daily series.** They are absent from the survivorship-free panel and from
  the `global_prices` cache, so every SMH- or MTUM-dominant book's forward twin refuses by name.
  - SMH-dominant: `big_dv`, `mom_12_1_liqw__ew`, `resid_mom_12_1_large`, `qc395`.
  - MTUM-dominant: `net_raises`, `mom_flow`, `skill_mom` ×2, `low_dtc_mom`, `mom_flow_ivw`.
  - One `global_prices.ensure(["SMH", "MTUM"], start="2026-09-01")` before the first forward
    grading (2026-10-26) unblocks them. It is a network pull and was not made tonight.
- **The monthly parquets are gitignored.** The per-book decomposition is computed from
  `monthly_returns_<run>.parquet`, which is not tracked. The committed bridge receipt carries the
  numbers. On a CI checkout the bridge prints `NO_MONTHLY_SERIES` for them; the cluster ids still
  come from the tracked JSON.
