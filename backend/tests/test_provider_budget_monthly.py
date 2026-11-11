"""OD-2 monthly DeepSeek envelope (CH-04, 2026-11-10). Offline; tmp envelopes only.

From 2026-10-15 to 2026-11-10 every PC DeepSeek call was refused because the
single envelope was never created, and hyp_lab wrote `status: OK` at rc 0 over a
BUDGET_REFUSED generation. These pin: the ONE host envelope (the file the
runtime's 10-15 guard also uses) is created from config and never replaced; the
cap binds the running month's calls; every refusal is one line with spend, cap
and the remedy; the callers that swallowed it now go red. Old-code / new-code
interleaving is in `test_provider_budget_mixed_versions.py`.
"""
import json
from types import SimpleNamespace as NS

import pytest

from backend import config as C
from backend.services import provider_budget as PB
from backend.services import task_receipts as TR


@pytest.fixture
def month_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("AEGIS_DEEPSEEK_BUDGET_PATH", raising=False)
    monkeypatch.setattr(PB, "_default_dir", lambda: tmp_path)
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 15.0)
    return tmp_path


def reserve(**kw):
    return PB.reserve("system", "user", 100, model="deepseek-chat",
                      base_url="https://api.deepseek.com", purpose="fixture", **kw)


def settle_ok(ticket, tokens_out=10):
    return PB.settle(ticket, NS(model="deepseek-flash", usage=NS(
        prompt_tokens=20, completion_tokens=tokens_out, prompt_cache_hit_tokens=0)))


def test_first_call_creates_the_one_host_envelope_from_config(month_dir):
    p = month_dir / "deepseek_local.json"
    assert PB.path() == p and not p.exists()
    settle_ok(reserve())
    s = json.loads(p.read_text(encoding="utf-8"))
    assert s["cap_units"] == PB._units(15.0) and s["schema"] == PB.SCHEMA
    assert s["opening_units"] == 0 and len(s["calls"]) == 1
    settle_ok(reserve())                      # the same file again, never recreated
    assert len(json.loads(p.read_text(encoding="utf-8"))["calls"]) == 2
    assert sorted(x.name for x in month_dir.glob("*.json")) == [p.name]


def test_cap_comes_from_config_and_is_bounded(month_dir, monkeypatch):
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 7.5)
    assert PB.snapshot()["cap_units"] == PB._units(7.5)
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 25.0)
    with pytest.raises(PB.BudgetRefused, match="AEGIS_DEEPSEEK_MONTHLY_CAP_USD"):
        reserve()
    assert not list(month_dir.glob("deepseek_local*.json"))


def test_reads_never_create_the_envelope(month_dir):
    assert PB.preflight_snapshot()["virtual"] is True
    assert PB.snapshot()["held_usd"] == 0
    line = PB.status_line()
    assert line.startswith("DEEPSEEK BUDGET OK") and "$15.00 cap" in line
    assert "first call creates it" in line
    assert not list(month_dir.glob("deepseek_local*.json"))


def test_exhausted_refusal_is_one_line_with_spend_cap_and_remedy(month_dir, monkeypatch):
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 0.0004)   # one call reserves ~$0.00043
    with pytest.raises(PB.BudgetRefused) as exc:
        reserve()
    line = str(exc.value)
    assert "\n" not in line and line.startswith("DEEPSEEK BUDGET REFUSED (EXHAUSTED)")
    assert "held $0.0000 of $0.00 cap" in line and "raise --cap" in line
    assert PB.main(["status"]) == 0           # nothing held yet: the CLI admits


def test_status_cli_exits_two_when_refusing(month_dir, capsys):
    assert PB.main(["init"]) == 0 and PB.path().exists()
    data = json.loads(PB.path().read_text(encoding="utf-8"))
    data["opening_units"] = data["cap_units"]
    PB.path().write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    assert PB.main(["status"]) == 2
    assert "DEEPSEEK BUDGET REFUSED (EXHAUSTED): " in capsys.readouterr().out


def test_raise_is_attended_monotone_and_keeps_spend(month_dir, monkeypatch):
    settle_ok(reserve())
    before = PB.snapshot()
    with pytest.raises(PB.BudgetRefused, match="never lowered"):
        PB.raise_cap(10, evidence="lower")
    with pytest.raises(PB.BudgetRefused):
        PB.raise_cap(21, evidence="above the hard ceiling")
    with pytest.raises(PB.BudgetRefused):
        PB.raise_cap(18, evidence="")
    line = PB.raise_cap(18, evidence="owner said so")
    after = PB.snapshot()
    assert after["cap_units"] == PB._units(18) and "$18.00 cap" in line
    assert after["calls"] == before["calls"] and after["held_usd"] == before["held_usd"]


def _write_envelope(d, *, created, calls, blocked=None, cap=15, opening=0.0):
    (d / "deepseek_local.json").write_text(json.dumps({"schema": PB.SCHEMA,
        "session_id": "fixture", "created_utc": created, "cap_units": PB._units(cap),
        "opening_units": PB._units(opening), "opening_evidence": "fixture",
        "calls": {k: {"held_units": PB._units(usd), "status": "SETTLED_PEAK_ESTIMATE",
                      "started_utc": when} for k, (usd, when) in calls.items()},
        "daily": {}, "blocked": blocked}), encoding="utf-8")


def _month_start(months_back=0):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month - months_back
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}-01T00:00:00+00:00"


def test_only_the_running_months_calls_count_against_the_cap(month_dir):
    """A file created last month: last month's $14.9 and opening do not bind this month."""
    _write_envelope(month_dir, created=_month_start(1), opening=0.5,
                    calls={"old": (14.4, _month_start(1)), "new": (0.25, _month_start(0)),
                           "undated": (0.01, "")})
    s = PB.snapshot()
    assert s["held_usd"] == pytest.approx(0.26)        # this month + the undated call
    assert s["cap_units"] == PB._units(15) and s["opening_units"] == 0
    assert s["lifetime_held_units"] == PB._units(15.16)
    settle_ok(reserve())                               # admitted: the month has room
    raw = json.loads((month_dir / "deepseek_local.json").read_text(encoding="utf-8"))
    assert len(raw["calls"]) == 4 and raw["cap_units"] == PB._units(15)   # appended, not reset


def test_a_block_on_the_shared_file_blocks_and_survives_the_month(month_dir):
    _write_envelope(month_dir, created=_month_start(1), blocked="unknown returned model",
                    calls={"old": (0.1, _month_start(1))})
    with pytest.raises(PB.BudgetRefused, match=r"\(BLOCKED\)"):
        reserve()


def test_raise_in_a_later_month_writes_the_month_cap_not_the_lifetime_cap(month_dir):
    _write_envelope(month_dir, created=_month_start(1), calls={"old": (1.0, _month_start(1))})
    PB.raise_cap(18, evidence="owner said so")
    raw = json.loads((month_dir / "deepseek_local.json").read_text(encoding="utf-8"))
    assert raw["month_caps"] == {PB.month_id(): PB._units(18)}
    assert raw["cap_units"] == PB._units(15)          # the 10-15 guard stays stricter
    assert PB.snapshot()["cap_units"] == PB._units(18)


def test_status_says_exhausted_when_no_call_can_fit(month_dir, monkeypatch):
    """Review #88 O2: status and reserve use one rule."""
    _write_envelope(month_dir, created=_month_start(0), calls={"a": (14.99985, _month_start(0))})
    line = PB.status_line()
    assert line.startswith("DEEPSEEK BUDGET REFUSED (EXHAUSTED)")
    with pytest.raises(PB.BudgetRefused, match="EXHAUSTED"):
        reserve()


def test_status_names_the_uncapped_paths(month_dir, capsys):
    line = PB.status_line()
    assert "covers calls routed through attempt()" in line and "UNCAPPED" in line and "\n" not in line
    assert PB.main(["status"]) == 0
    out = capsys.readouterr().out
    for x in PB.UNCAPPED_DEEPSEEK_PATHS:
        assert x in out


def test_unreadable_envelope_refuses_and_is_never_replaced(month_dir):
    (month_dir / PB.ENVELOPE_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(PB.BudgetRefused, match="UNREADABLE"):
        reserve()
    assert (month_dir / PB.ENVELOPE_NAME).read_text(encoding="utf-8") == "{not json"


def test_fixed_envelope_keeps_the_attended_contract(month_dir, monkeypatch, tmp_path):
    fixed = tmp_path / "fixed" / "envelope.json"
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(fixed))
    with pytest.raises(PB.BudgetRefused, match=r"\(MISSING\)"):
        reserve()
    assert not fixed.exists()
    assert PB.main(["init"]) == 2 and not fixed.exists()


def test_daily_call_cap_line_names_the_reset(month_dir):
    reserve(production_cap=1)
    with pytest.raises(PB.BudgetRefused, match="resets at UTC midnight"):
        reserve(production_cap=1)


def test_budget_refused_status_reads_refused_not_degraded():
    assert TR.map_status("BUDGET_REFUSED") == "REFUSED"
    assert TR.map_status("OK") == "OK"


def test_learner_names_the_envelope_only_when_it_refuses(month_dir, monkeypatch):
    from learner import rule_distillation as RD
    monkeypatch.setattr(PB, "host_envelope_required", lambda: True)
    assert RD._budget_refusal_line() is None
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 0.0005)
    PB.main(["init"])
    data = json.loads(PB.path().read_text(encoding="utf-8"))
    data["opening_units"] = data["cap_units"]
    PB.path().write_text(json.dumps(data), encoding="utf-8")
    assert RD._budget_refusal_line().startswith("DEEPSEEK BUDGET REFUSED (EXHAUSTED)")


def test_world_digest_refusal_prints_the_accounting_line(month_dir, monkeypatch, capsys):
    from scripts import world_digest as S
    monkeypatch.setattr(PB, "host_envelope_required", lambda: True)
    monkeypatch.setattr(S, "_host_budget_required", lambda: True)
    monkeypatch.setattr(S, "_ensure_streams", lambda: None, raising=False)
    monkeypatch.setattr(S.WD, "work_dir", lambda: month_dir / "wd")
    monkeypatch.setattr(S.WD, "stop_file", lambda: month_dir / "wd" / "STOP")
    monkeypatch.setattr(S, "_balance", lambda *a, **k: pytest.fail("downstream reached"))
    PB.main(["init"])
    data = json.loads(PB.path().read_text(encoding="utf-8"))
    data["opening_units"] = data["cap_units"]
    data["opening_evidence"] = "SECRET_EVIDENCE"
    PB.path().write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    assert S.main(["--no-write"]) == 2
    out = capsys.readouterr().out
    assert "SHARED_ENVELOPE_EXHAUSTED" in out
    assert "DEEPSEEK BUDGET REFUSED (EXHAUSTED)" in out and "$15.00 cap" in out
    assert "SECRET_EVIDENCE" not in out


def test_hyp_lab_nightly_is_red_when_generation_was_budget_refused(monkeypatch, tmp_path, capsys):
    from scripts import hyp_lab as S
    L, HL = S.L, S.HL
    monkeypatch.setattr(L, "RECEIPTS", tmp_path)
    monkeypatch.setattr(L, "STOP", tmp_path / "STOP")
    monkeypatch.setattr(S, "stop_report", lambda p: None)
    monkeypatch.setattr(S, "wait_ram", lambda *a, **k: 8.0)
    monkeypatch.setattr(HL, "spent", lambda *a, **k: {"binding_usd": 0.0})
    monkeypatch.setattr(S, "family_policy", lambda *a, **k: {"ev_weights": {}})
    for name, value in [("load_state", {}), ("family_record", {}), ("family_budget", {}),
                        ("policy_gen_quotas", {}), ("rank", []), ("weekly_guarantee", []),
                        ("family_policy_report", {}), ("render_markdown", None),
                        ("policy_ev_weights", {})]:
        monkeypatch.setattr(L, name, lambda *a, _v=value, **k: _v)
    line = "DEEPSEEK BUDGET REFUSED (EXHAUSTED): 2026-11 held $15.0000 of $15.00 cap -- raise"
    monkeypatch.setattr(S, "generate", lambda *a, **k: {
        "provider": "deepseek", "ok": False, "status": "BUDGET_REFUSED",
        "error": f"shared host envelope refused before dispatch: {line}"})
    rc = S.cmd_nightly(NS(k=3, cap=0.4, providers="deepseek", time_box=60))
    assert rc == 2
    rec = json.loads(next(tmp_path.glob("nightly_*.json")).read_text(encoding="utf-8"))
    assert rec["status"] == "BUDGET_REFUSED" and line in rec["reason"]
    assert line in capsys.readouterr().out
