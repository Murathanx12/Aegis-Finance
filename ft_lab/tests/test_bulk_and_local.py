"""Offline tests for the bulk converter, the bulk grader and the local-extract CLI's refusals.
Synthetic data only: no GPU, no network, no model load.

  ft_lab/.venv/Scripts/python.exe -m pytest ft_lab/tests -q -p no:cacheprovider
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ft_lab import analyze_bulk as A
from ft_lab import bulk_events as B
from ft_lab import local_extract as L
from ft_lab import safety as S


def test_done_keys_skips_a_torn_last_line(tmp_path, monkeypatch):
    out = tmp_path / "bulk.jsonl"
    out.write_text(json.dumps({"key": "a|X"}) + "\n" + json.dumps({"key": "b|Y"}) + "\n" + '{"key": "c|', encoding="utf-8")
    monkeypatch.setattr(B, "OUT", out)
    assert B.done_keys() == {"a|X", "b|Y"}      # the torn row is redone, not half-counted


def test_features_are_stable_columns_and_no_event_is_the_baseline():
    df = pd.DataFrame({"event_type": ["no_event", "earnings_report", "spinoff"], "direction": [0, 1, -1],
                       "magnitude": ["NEGLIGIBLE", "MODERATE", "LARGE"], "confidence": [0.9, 0.8, 0.5]})
    X = A.features(df, ["no_event", "earnings_report"])
    # dummies: earnings_report, other_event (no_event dropped) + 5 numeric
    assert X.shape == (3, 2 + 5)
    assert X[0, :2].sum() == 0 and X[1, 0] == 1 and X[2, 1] == 1


def test_per_date_stats_counts_months_and_blocks():
    dates = pd.bdate_range("2026-05-01", "2026-07-31").strftime("%Y-%m-%d")
    df = pd.DataFrame({"entry_date": np.repeat(dates, 3), "v": 0.01})
    r = A.per_date_stats(df, "v")
    assert r["share_months_positive"] == 1.0 and r["n_blocks"] >= 12 and r["mean"] == 0.01


def test_local_extract_refuses_without_an_adapter(tmp_path, monkeypatch, capsys):
    import ft_lab.loader as LD
    monkeypatch.setattr(LD, "ADAPTER_DIR", tmp_path / "missing")
    inp = tmp_path / "in.jsonl"
    inp.write_text(json.dumps({"item_id": "x"}) + "\n", encoding="utf-8")
    rc = L.main(["--in", str(inp), "--out", str(tmp_path / "out.jsonl")])
    assert rc == 3 and "REFUSED" in capsys.readouterr().out
    assert not (tmp_path / "out.jsonl").exists()


def test_local_extract_refuses_when_memory_is_short(tmp_path, monkeypatch, capsys):
    import ft_lab.loader as LD
    (tmp_path / "ad").mkdir()
    (tmp_path / "ad" / "adapter_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LD, "ADAPTER_DIR", tmp_path / "ad")
    monkeypatch.setattr(S, "STOP_FILE", tmp_path / "no_stop")
    monkeypatch.setattr(S, "free_ram_gb", lambda: 0.5)
    inp = tmp_path / "in.jsonl"
    inp.write_text(json.dumps({"item_id": "x"}) + "\n", encoding="utf-8")
    rc = L.main(["--in", str(inp), "--out", str(tmp_path / "out.jsonl"), "--min-free-ram-gb", "3"])
    assert rc == 3 and "free RAM" in capsys.readouterr().out


def test_local_extract_refuses_when_the_gpu_is_busy(tmp_path, monkeypatch, capsys):
    import ft_lab.loader as LD
    (tmp_path / "ad").mkdir()
    (tmp_path / "ad" / "adapter_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LD, "ADAPTER_DIR", tmp_path / "ad")
    monkeypatch.setattr(S, "STOP_FILE", tmp_path / "no_stop")
    monkeypatch.setattr(S, "free_ram_gb", lambda: 16.0)
    monkeypatch.setattr(S, "gpu_state", lambda: {"used_mib": 5000.0, "total_mib": 8000.0})
    inp = tmp_path / "in.jsonl"
    inp.write_text(json.dumps({"item_id": "x"}) + "\n", encoding="utf-8")
    rc = L.main(["--in", str(inp), "--out", str(tmp_path / "out.jsonl")])
    assert rc == 3 and "GPU busy" in capsys.readouterr().out


def test_psych_target_rounds_float_noise_and_nulls_nan():
    from ft_lab import prompts as P
    t = json.loads(P.psych_target({"tone": 0.30000000000000004, "emotion": "neutral", "uncertainty": 0.7000000000000001,
                                   "surprise": 0.1, "mgmt_confidence": float("nan"), "novelty": 0.5,
                                   "attention": 0.6000000000000001, "expected_move": "SMALL"}))
    assert t["tone"] == 0.3 and t["uncertainty"] == 0.7 and t["mgmt_confidence"] is None


def test_valid_psych_turns_a_nan_mgmt_confidence_into_null():
    from ft_lab import prompts as P
    o = P.parse_json('{"tone": 0.1, "emotion": "neutral", "uncertainty": 0.2, "surprise": 0.1, '
                     '"mgmt_confidence": NaN, "novelty": 0.3, "attention": 0.4, "expected_move": "SMALL"}')
    assert P.valid_psych(o)["mgmt_confidence"] is None
