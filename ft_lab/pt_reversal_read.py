"""TRIAL-PT-REVERSAL-1: the ONE registered read on the 2025 (train) cells.

Construction, decision rule and power are frozen in
docs/TRIALS/TRIAL-PT-REVERSAL-1-price-target-next-session-fade.md; the file's sha256 is in
receipts/pt_reversal_registration.json and is re-checked here before anything is read.

    --count   labels only (no outcome is opened): directional PT cells, weekly blocks, coverage
    --read    the single read; refuses if receipts/pt_reversal_read.json already exists, if the
              trial file's hash changed, or if the registered minimum (>= 300 cells, >= 30 weekly
              blocks) is not met (in which case nothing is read and the read is not consumed)

    ft_lab/.venv/Scripts/python.exe -m ft_lab.pt_reversal_read --count
    ft_lab/.venv/Scripts/python.exe -m ft_lab.pt_reversal_read --read
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ft_lab import config as C
from ft_lab import evaluate as E

TRIAL = C.REPO / "docs" / "TRIALS" / "TRIAL-PT-REVERSAL-1-price-target-next-session-fade.md"
REG = C.RECEIPTS / "pt_reversal_registration.json"
OUT = C.RECEIPTS / "pt_reversal_read.json"
MODEL_TAG = "qwen2.5-1.5b-instruct+ft_lab/extract_qwen15_lora/last"
EVENT = "analyst_target_change"
COSTS = {"net20": 0.0020, "net40": 0.0040, "net60": 0.0060}
MIN_CELLS, MIN_BLOCKS = 300, 30
TEST_EFFECT = 0.0034      # the test-block gross fade, the refutation power bar


def labels() -> pd.DataFrame:
    rows = []
    with open(C.WORK / "bulk_events.jsonl", encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("source") == "panel_cell_first_doc" and r.get("split") == "train" and r.get("valid")
                    and r.get("model") == MODEL_TAG):
                rows.append((r["key"].split("|")[0], r["symbol"], r["event_type"], int(r["direction"])))
    return pd.DataFrame(rows, columns=["first_uid", "symbol", "event_type", "direction"]).drop_duplicates(
        ["first_uid", "symbol"])


def events(with_outcome: bool) -> tuple[pd.DataFrame, dict]:
    lab = labels()
    cols = ["first_uid", "symbol", "entry_date", "split"] + (["x_oc"] if with_outcome else [])
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=cols)
    cells = cells[cells["split"] == "train"]
    df = cells.merge(lab, on=["first_uid", "symbol"], how="inner")
    ev = df[(df["event_type"] == EVENT) & df["direction"].isin([-1, 1])].copy()
    weeks = pd.to_datetime(ev["entry_date"]).dt.to_period("W-FRI").astype(str)
    cov = {"train_cells_total": int(len(cells)), "train_cells_converted": int(len(df)),
           "directional_pt_cells": int(len(ev)), "weekly_blocks": int(weeks.nunique()),
           "entry_dates": int(ev["entry_date"].nunique()),
           "raises": int((ev["direction"] == 1).sum()), "cuts": int((ev["direction"] == -1).sum())}
    return ev, cov


def five_session(ev: pd.DataFrame) -> pd.Series:
    b = pd.read_parquet(C.BARS, columns=["symbol", "date", "open", "close"],
                        filters=[("date", ">=", pd.Timestamp("2024-12-01")), ("date", "<", pd.Timestamp("2026-02-01"))])
    b = b[b["symbol"].isin(set(ev["symbol"]) | {"SPY"})].sort_values(["symbol", "date"]).reset_index(drop=True)
    b["close_4"] = b.groupby("symbol")["close"].shift(-4)
    b["date_4"] = b.groupby("symbol")["date"].shift(-4)
    b["r5"] = b["close_4"] / b["open"] - 1.0
    b = b.join(b[b["symbol"] == "SPY"].set_index("date")["r5"].rename("spy5"), on="date")
    b.loc[(b["date_4"] - b["date"]).dt.days > 10, "r5"] = np.nan
    b["x5"] = b["r5"] - b["spy5"]
    m = pd.Series(b["x5"].values, index=(b["symbol"] + "|" + b["date"].dt.strftime("%Y-%m-%d")).values)
    m = m[~m.index.duplicated()]
    return (ev["symbol"] + "|" + ev["entry_date"].astype(str)).map(m)


def stats(ev: pd.DataFrame, col: str) -> dict:
    per = ev.groupby("entry_date")[col].mean().dropna()
    r = E.block_stats(per)
    bm = per.groupby(pd.Index(per.index).str[:7]).mean()
    r["by_month"] = {k: round(float(v), 5) for k, v in bm.items()}
    r["months_positive"] = int((bm > 0).sum())
    r["n_months"] = int(len(bm))
    loo = {m: float(per[~pd.Index(per.index).str.startswith(m)].mean()) for m in bm.index}
    r["loo_month_worst"] = round(min(loo.values()), 5) if loo else None
    top = per.sort_values(ascending=False).head(5)
    r["top5_dates_share_of_total"] = round(float(top.sum() / per.sum()), 3) if per.sum() else None
    r["n_cells"] = int(ev[col].notna().sum())
    return r


def verdict(g: dict, n20: dict, n40: dict) -> dict:
    m, t, mde = g["mean"], g["t"] or 0.0, g["mde"]
    exists = (m > 0 and t >= 2.0 and g["months_positive"] >= 7 and (g["loo_month_worst"] or 0) > 0)
    if exists:
        tradable = n20["mean"] >= 0.0010 and (n20["t"] or 0) >= 2.0 and n40["mean"] > 0
        return {"verdict": "CONDITIONAL_POSITIVE", "tradable_gate": tradable,
                "action": "register a forward PAPER log" if tradable else "DEPRIORITIZED as a trade"}
    if m <= 0 or (mde is not None and mde <= TEST_EFFECT):
        return {"verdict": "FAILED_VARIANT", "tradable_gate": False, "action": "RETIRED_FROM_CURRENT_SEARCH"}
    return {"verdict": "CANNOT_DISTINGUISH", "tradable_gate": False, "action": "none; underpowered"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--count", action="store_true")
    g.add_argument("--read", action="store_true")
    a = ap.parse_args(argv)
    reg = json.loads(REG.read_text(encoding="utf-8"))
    sha = hashlib.sha256(TRIAL.read_bytes()).hexdigest()
    if sha != reg["sha256"]:
        raise SystemExit(f"REFUSED: trial file hash {sha[:16]} != registered {reg['sha256'][:16]}")
    if a.count:
        _, cov = events(with_outcome=False)
        print(json.dumps(cov, indent=1))
        return 0
    if OUT.exists():
        raise SystemExit(f"REFUSED: {OUT.name} exists; the registered read happens once")
    _, cov = events(with_outcome=False)
    if cov["directional_pt_cells"] < MIN_CELLS or cov["weekly_blocks"] < MIN_BLOCKS:
        print(json.dumps({"not_read": "below registered minimum", **cov}, indent=1))
        return 2
    ev, cov = events(with_outcome=True)
    n_missing = int(ev["x_oc"].isna().sum())
    ev = ev[ev["x_oc"].notna()].copy()
    ev["gross"] = -ev["direction"] * ev["x_oc"]
    for k, c in COSTS.items():
        ev[k] = ev["gross"] - c
    ev["gross5_descriptive"] = -ev["direction"] * five_session(ev)
    res = {k: stats(ev, k) for k in ("gross", *COSTS)}
    rec = {"trial": "TRIAL-PT-REVERSAL-1", "trial_sha256": sha, "registered_utc": reg["registered_utc"],
           "read_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "licence": C.LICENCE,
           "coverage": {**cov, "x_oc_missing_dropped": n_missing},
           "primary_gross_fade": res["gross"], "net20": res["net20"], "net40": res["net40"], "net60": res["net60"],
           "decision": verdict(res["gross"], res["net20"], res["net40"]),
           "reported_only": {"raises_gross": stats(ev[ev["direction"] == 1], "gross"),
                             "cuts_gross": stats(ev[ev["direction"] == -1], "gross"),
                             "fade_5_session_gross": stats(ev, "gross5_descriptive")}}
    OUT.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rec, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
