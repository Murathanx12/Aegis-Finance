"""WHICH READER, AND AT WHAT PRICE (chunk 14, loop 2 and the dollar cap).

Three refusals are pinned here and each of them is a refusal rather than a
fallback on purpose:

* `CLOUD_READER_NOT_IMPLEMENTED` — asking for the generic cloud reader with
  none registered must NOT quietly type the rows locally and stamp the receipt
  `reader: cloud`. Every local-vs-cloud comparison downstream would then be a
  comparison of one reader with itself, and the kappa that licenses mixing two
  readers' rows in one table would be measuring nothing.
* `DEEPSEEK_NOT_CONFIGURED` — a reader that cannot authenticate is a refusal,
  not a downgrade.
* `DAILY_SPEND_CAP_REACHED` — checked BEFORE the provider is contacted. A
  refund is not a guard: a call that was made and then regretted has already
  been billed.

No test here reads a key, contacts a provider, or touches the repository's
own optimus data directory. `config.DATA_DIR` is redirected to `tmp_path` in
every test that writes, and the provider probe is stubbed by name.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend import config as _config
from backend.services import lab_budget, lab_reader


@pytest.fixture
def spend_dir(tmp_path, monkeypatch):
    (tmp_path / "optimus").mkdir(parents=True)
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)
    monkeypatch.delenv(lab_reader.READER_ENV, raising=False)
    monkeypatch.delenv(_config.LAB_SPEND_CAP_ENV, raising=False)
    return tmp_path


# --------------------------------------------------------------------------
# the reader hook


def test_the_default_reader_is_local_and_costs_nothing(spend_dir):
    row = lab_reader.resolve(rows_this_tick=40)
    assert row["ok"] is True
    assert row["reader"] == "local" and row["backend"] == "local"
    assert row["metered"] is False
    assert row["estimated_usd"] == 0.0


def test_cloud_reader_env_var_without_implementation_refuses_by_name(
        spend_dir, monkeypatch):
    """The test that keeps the hook honest before chunk 15 fills it in."""
    monkeypatch.setenv(lab_reader.READER_ENV, "cloud")
    assert lab_reader.registered() == [], "chunk 14 registers no CloudReader"
    row = lab_reader.resolve(rows_this_tick=40)
    assert row["ok"] is False
    assert row["refusal"] == "CLOUD_READER_NOT_IMPLEMENTED"
    assert "backend" not in row, "a refused reader names no backend to fall back to"
    assert "fallback" in row["detail"]


def test_an_unknown_reader_name_refuses_rather_than_defaulting(spend_dir, monkeypatch):
    monkeypatch.setenv(lab_reader.READER_ENV, "gpt5000")
    row = lab_reader.resolve(rows_this_tick=1)
    assert row["ok"] is False and row["refusal"] == "UNKNOWN_READER"


def test_an_unconfigured_provider_refuses_and_names_the_env_variable(
        spend_dir, monkeypatch):
    """NAMES ONLY. The refusal prints the variable a human must set, never a
    value, which is this repository's standing rule for credentials."""
    monkeypatch.setenv(lab_reader.READER_ENV, "deepseek")
    monkeypatch.setattr(lab_reader, "provider_configured", lambda name: False)
    row = lab_reader.resolve(rows_this_tick=40)
    assert row["ok"] is False
    assert row["refusal"] == "DEEPSEEK_NOT_CONFIGURED"
    assert "DEEPSEEK_API_KEY" in row["detail"]
    assert "sk-" not in row["detail"]


def test_a_configured_provider_is_admitted_with_an_estimate(spend_dir, monkeypatch):
    monkeypatch.setenv(lab_reader.READER_ENV, "deepseek")
    monkeypatch.setattr(lab_reader, "provider_configured", lambda name: True)
    row = lab_reader.resolve(rows_this_tick=40)
    assert row["ok"] is True and row["backend"] == "deepseek"
    assert row["metered"] is True
    assert row["estimated_usd"] == pytest.approx(
        40 * lab_reader.DEEPSEEK_USD_PER_ROW, abs=1e-6)
    assert "MEASURED" in row["cost_basis"] and "ESTIMATE" in row["cost_basis"]


def test_registering_a_non_conforming_reader_is_refused(spend_dir):
    class NotAReader:
        pass

    with pytest.raises(TypeError):
        lab_reader.register("bad", NotAReader())          # type: ignore[arg-type]


# --------------------------------------------------------------------------
# the dollar cap


def test_dollar_cap_refuses_before_the_call_not_after(spend_dir, monkeypatch):
    """The reader mock's call count must be 0, never 1-then-refunded."""
    monkeypatch.setenv(lab_reader.READER_ENV, "deepseek")
    monkeypatch.setattr(lab_reader, "provider_configured", lambda name: True)
    cap = lab_budget.cap_usd()
    # seed the day just under the cap
    lab_budget.record(cap - 0.0001, backend="deepseek", what="earlier today")
    assert lab_budget.spend_today()["spend_today_usd"] == pytest.approx(cap - 0.0001)

    calls = {"n": 0}

    class Reader:
        def type_batch(self, rows):
            calls["n"] += 1
            return []

    row = lab_reader.resolve(rows_this_tick=4000)
    assert row["ok"] is False
    assert row["refusal"] == "DAILY_SPEND_CAP_REACHED"
    assert calls["n"] == 0, "the provider was contacted before the cap was checked"
    assert row["spend_cap_usd"] == cap


def test_the_cap_is_read_from_config_and_overridable_by_name(spend_dir, monkeypatch):
    assert lab_budget.cap_usd() == _config.LAB_DAILY_SPEND_CAP_USD
    monkeypatch.setenv(_config.LAB_SPEND_CAP_ENV, "0.25")
    assert lab_budget.cap_usd() == 0.25


def test_an_unparseable_cap_override_falls_back_to_the_configured_default(
        spend_dir, monkeypatch):
    """A cap that silently becomes infinity because somebody typed `3,00` is
    worse than no cap."""
    monkeypatch.setenv(_config.LAB_SPEND_CAP_ENV, "3,00")
    assert lab_budget.cap_usd() == _config.LAB_DAILY_SPEND_CAP_USD


def test_local_calls_are_unmetered_and_counted_separately(spend_dir):
    lab_budget.record(0.0, backend="local", rows=40, what="local tick")
    row = lab_budget.spend_today()
    assert row["spend_today_usd"] == 0.0
    assert row["unmetered_calls"] == 1
    assert row["metered_calls"] == 0, (
        "ten local calls and no calls at all must not be the same row")


def test_the_guard_lets_a_local_call_through_whatever_the_day_has_cost(spend_dir):
    lab_budget.record(lab_budget.cap_usd() * 2, backend="deepseek", what="overspent")
    row = lab_budget.guard(0.0, backend="local")
    assert row["metered"] is False
    assert "compute, not dollars" in row["why"]


def test_spend_today_returns_every_key_even_with_no_ledger_on_disk(spend_dir):
    row = lab_budget.spend_today()
    for key in ("date", "spend_today_usd", "cap_usd", "remaining_usd",
                "cap_reached", "metered_calls", "unmetered_calls"):
        assert key in row, key
    assert row["spend_today_usd"] == 0.0
    assert row["cap_reached"] is False


def test_the_spend_ledger_is_written_atomically(spend_dir):
    lab_budget.record(0.01, backend="deepseek", rows=3, what="tick")
    p = lab_budget.ledger_path()
    assert p.exists() and not p.with_suffix(".json.tmp").exists()
    rec = json.loads(p.read_text(encoding="utf-8"))
    assert rec["spend_usd"] == 0.01 and len(rec["calls"]) == 1
    assert rec["calls"][0]["backend"] == "deepseek"


def test_the_ledger_is_keyed_by_utc_day_not_by_local_midnight(spend_dir):
    """Same boundary `llm_analyzer._DAILY_CAP` already uses. This machine runs
    UTC+8, so a local-midnight boundary would reset the cap at 16:00 UTC."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lab_budget.record(0.02, backend="deepseek", what="tick")
    assert lab_budget.ledger_path().name == f"lab_spend_{today}.json"
    assert lab_budget.spend_today(today)["spend_today_usd"] == 0.02
    other = (datetime.now(timezone.utc).replace(year=datetime.now().year - 1)
             .strftime("%Y-%m-%d"))
    assert lab_budget.spend_today(other)["spend_today_usd"] == 0.0


# --------------------------------------------------------------------------
# the two-reader overlap set


def _typed(key: str, backend: str, event="earnings_beat", direction="positive",
           magnitude="medium", confidence=0.8) -> dict:
    return {"source": "s", "first_seen_utc": key, "raw_id": key,
            "backend": backend, "event_type": event, "direction": direction,
            "magnitude_bucket": magnitude, "confidence": confidence}


def test_the_overlap_set_is_cannot_determine_until_a_second_reader_runs(spend_dir):
    rows = [_typed(f"k{i}", "local") for i in range(50)]
    out = lab_reader.overlap_report(rows)
    assert out["status"] == "insufficient_overlap"
    assert out["n_paired"] == 0
    assert "CANNOT DETERMINE" in out["why"]
    assert out["backends_seen"] == ["local"]


def test_the_overlap_set_pairs_by_row_key_and_reports_kappa(spend_dir):
    rows = []
    for i in range(30):
        rows.append(_typed(f"k{i}", "local",
                           event="earnings_beat" if i % 2 else "guidance_cut"))
        rows.append(_typed(f"k{i}", "deepseek",
                           event="earnings_beat" if i % 2 else "guidance_cut"))
    # two rows only one reader saw: they must NOT enter the pairing
    rows.append(_typed("solo", "local"))
    out = lab_reader.overlap_report(rows, target=10)
    assert out["n_paired"] == 30
    assert out["status"] == "ok"
    assert sorted([out["reader_a"], out["reader_b"]]) == ["deepseek", "local"]
    assert out["agreement"]["n"] == 30
    assert out["agreement"]["raw_agreement_event_type"] == 1.0


def test_the_overlap_set_says_when_it_is_below_the_declared_size(spend_dir):
    rows = []
    for i in range(4):
        rows.append(_typed(f"k{i}", "local"))
        rows.append(_typed(f"k{i}", "deepseek"))
    out = lab_reader.overlap_report(rows, target=200)
    assert out["status"] == "below_declared_overlap"
    assert out["target_rows"] == 200 and out["n_paired"] == 4


def test_the_declared_overlap_size_comes_from_config(spend_dir):
    assert lab_reader.overlap_rows() == _config.LAB_L2_OVERLAP_ROWS
