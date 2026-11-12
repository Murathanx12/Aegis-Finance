"""The world digest runs by US market phase (CH-05 R5, owner 2026-11-11).

Every clock here is a FIXED, injected datetime (never the real date); the
calendar is the real XNYS one from `market_sessions` (offline library), the
envelope is a fake snapshot, and no provider is ever called.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import world_digest_phase as P

UTC = timezone.utc
SCALE = 1_000_000_000


def at(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


# ── the phase, from the exchange calendar ─────────────────────────────────────

@pytest.mark.parametrize("now,phase,in_window", [
    (at(2026, 11, 11, 11, 59), "PRE_MARKET", False),   # Wed 06:59 ET (EST): slot opens 07:00
    (at(2026, 11, 11, 12, 0), "PRE_MARKET", True),     # 07:00 ET
    (at(2026, 11, 11, 15, 0), "SESSION", False),       # 10:00 ET: session slot opens 11:30
    (at(2026, 11, 11, 16, 30), "SESSION", True),       # 11:30 ET
    (at(2026, 11, 11, 22, 0), "AFTER_CLOSE", False),   # 17:00 ET: waits for the 17:30 news pull
    (at(2026, 11, 11, 23, 30), "AFTER_CLOSE", True),   # 18:30 ET
    (at(2026, 11, 14, 14, 59), "CLOSED", False),       # Saturday 09:59 ET
    (at(2026, 11, 14, 15, 0), "CLOSED", True),         # Saturday 10:00 ET
    (at(2026, 11, 26, 16, 0), "CLOSED", True),         # Thanksgiving: a weekday holiday
])
def test_phase_from_the_real_calendar(now, phase, in_window):
    ph = P.market_phase(now)
    assert (ph["phase"], ph["in_window"]) == (phase, in_window)


def test_early_close_and_daylight_saving_come_from_the_calendar():
    # Black Friday 2026-11-27 closes 13:00 ET = 18:00Z: 18:30Z is after the close.
    assert P.market_phase(at(2026, 11, 27, 18, 30))["phase"] == "AFTER_CLOSE"
    assert P.market_phase(at(2026, 11, 27, 17, 30))["phase"] == "SESSION"
    # July is EDT: 07:00 ET is 11:00Z, not 12:00Z.
    summer = P.market_phase(at(2026, 7, 15, 11, 0))
    assert summer["phase"] == "PRE_MARKET" and summer["in_window"]
    assert summer["slot_opens_utc"] == "2026-07-15T11:00:00+00:00"


def test_a_naive_clock_is_refused():
    with pytest.raises(ValueError, match="aware"):
        P.market_phase(datetime(2026, 11, 11, 12, 0))


# ── the decision ──────────────────────────────────────────────────────────────

def snap(digest_usd: float = 0.0, other_usd: float = 0.0, cap_usd: float = 15.0, blocked=None) -> dict:
    calls = {"a": {"purpose": "world_digest_extract", "held_units": int(digest_usd * SCALE)},
             "b": {"purpose": "investigator_news", "held_units": int(other_usd * SCALE)}}
    return {"cap_units": int(cap_usd * SCALE), "calls": calls, "month": "2026-11", "blocked": blocked}


def digest(out: Path, stamp: datetime, *, until: datetime | None = None, skipped: int = 0, **kw) -> None:
    name = stamp.strftime("%Y%m%dT%H%M%SZ")
    d = {"stamp": name, "window": {"since": None, "until": (until or stamp).isoformat()},
         "extraction": {"budget_skipped": skipped}, "dry_run": False, **kw}
    (out / f"world_digest_{name}.json").write_text(json.dumps(d), encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    out = tmp_path / "digest"
    out.mkdir()
    dec = tmp_path / "schedule" / "decisions.jsonl"

    def decide(now, *, snapshot=None, n_items=500, snapshot_fn=None, phase_fn=None):
        kw = {} if phase_fn is None else {"phase_fn": phase_fn}
        return P.decide(now, out_dir=out, decisions_path=dec,
                        snapshot_fn=snapshot_fn or (lambda: snapshot or snap()),
                        count_new_items=lambda since, until: n_items, **kw)
    return SimpleNamespace(out=out, dec=dec, decide=decide)


PRE = at(2026, 11, 11, 12, 30)          # Wed 07:30 ET, pre-market slot open
SESSION = at(2026, 11, 11, 17, 0)       # Wed 12:00 ET


def test_outside_a_slot_window_it_skips(env):
    r = env.decide(at(2026, 11, 11, 15, 0))
    assert (r["decision"], r["reason"]) == ("SKIP", "NOT_IN_WINDOW")


def test_due_run_covers_since_the_last_complete_run_and_takes_the_phase_ceiling(env):
    digest(env.out, at(2026, 11, 10, 23, 40))                      # Tue after-close run
    r = env.decide(PRE)
    assert (r["decision"], r["reason"]) == ("RUN", "DUE")
    assert r["hours"] == pytest.approx(12 + 50 / 60 + C.WORLD_DIGEST_PHASE_OVERLAP_H, abs=1e-3)
    assert r["budget_usd"] == C.WORLD_DIGEST_PHASE_CEILING_USD["PRE_MARKET"]
    assert r["spend"]["share_usd"] == pytest.approx(C.WORLD_DIGEST_MONTHLY_SHARE * 15.0)


def test_an_incomplete_run_does_not_move_the_window(env):
    digest(env.out, at(2026, 11, 10, 12, 30))                       # complete
    digest(env.out, at(2026, 11, 10, 23, 40), skipped=7)            # budget-skipped items
    r = env.decide(PRE)
    assert r["decision"] == "RUN"
    assert r["hours"] == pytest.approx(24 + C.WORLD_DIGEST_PHASE_OVERLAP_H, abs=1e-3)
    assert "SINCE_LAST_COMPLETE_RUN world_digest_20261110T123000Z" in r["coverage"]["basis"]


def test_a_long_gap_is_clamped_and_no_history_uses_the_default(env):
    r = env.decide(PRE)
    assert r["hours"] == C.WORLD_DIGEST_HOURS and r["coverage"]["basis"].startswith("NO_COMPLETE_RUN")
    digest(env.out, at(2026, 11, 5, 12, 0))
    assert env.decide(PRE)["hours"] == C.WORLD_DIGEST_PHASE_MAX_HOURS


def test_one_successful_run_serves_the_slot(env):
    digest(env.out, at(2026, 11, 11, 12, 5))
    r = env.decide(PRE)
    assert (r["decision"], r["reason"]) == ("SKIP", "SLOT_SERVED")


def test_dry_runs_degraded_runs_and_future_stamps_never_serve_a_slot(env):
    digest(env.out, at(2026, 11, 11, 12, 5), dry_run=True)
    digest(env.out, at(2026, 11, 11, 12, 10), status="DEGRADED_MODEL_BUDGET")
    digest(env.out, at(2026, 11, 11, 13, 0))                        # after `now`
    assert env.decide(PRE)["decision"] == "RUN"


def test_two_failed_attempts_in_a_slot_refuse_red(env):
    env.dec.parent.mkdir(parents=True)
    line = json.dumps({"decision": "RUN", "slot": "2026-11-11:PRE_MARKET"})
    env.dec.write_text(line + "\n" + line + "\n", encoding="utf-8")
    r = env.decide(PRE)
    assert (r["decision"], r["reason"]) == ("REFUSED", "ATTEMPTS_EXHAUSTED")


def test_only_digest_purposes_count_against_the_share(env):
    r = env.decide(PRE, snapshot=snap(digest_usd=1.0, other_usd=5.0))
    assert r["spend"]["digest_mtd_usd"] == pytest.approx(1.0)
    assert r["decision"] == "RUN"


def test_an_exhausted_share_refuses_and_the_budget_never_exceeds_what_is_left(env):
    share = C.WORLD_DIGEST_MONTHLY_SHARE * 15.0
    r = env.decide(PRE, snapshot=snap(digest_usd=share - 0.01))
    assert (r["decision"], r["reason"]) == ("REFUSED", "SHARE_EXHAUSTED")
    r = env.decide(PRE, snapshot=snap(digest_usd=share - 0.10))
    assert r["decision"] == "RUN" and r["budget_usd"] == pytest.approx(0.10, abs=1e-4)


def test_over_pace_skips_optional_phases_but_runs_essential_ones(env):
    # 2026-11-11 17:00Z is ~34% through November: pace ~ $3.06 of a $9 share.
    heavy = snap(digest_usd=5.0)
    r = env.decide(SESSION, snapshot=heavy)
    assert (r["decision"], r["reason"]) == ("SKIP", "OVER_PACE") and r["spend"]["over_pace"]
    assert env.decide(PRE, snapshot=heavy)["decision"] == "RUN"
    assert env.decide(SESSION, snapshot=snap(digest_usd=1.0))["decision"] == "RUN"


def test_nothing_new_waits_without_consuming_the_slot(env):
    r = env.decide(PRE, n_items=C.WORLD_DIGEST_PHASE_MIN_NEW_ITEMS - 1)
    assert (r["decision"], r["reason"]) == ("SKIP", "NOTHING_NEW")
    assert env.decide(PRE)["decision"] == "RUN"


def test_an_unreadable_envelope_or_calendar_refuses_without_leaking_text(env):
    def boom():
        raise OSError("C:/private/path SECRET_TOKEN")
    r = env.decide(PRE, snapshot_fn=boom)
    assert (r["decision"], r["reason"]) == ("REFUSED", "ENVELOPE_UNREADABLE")
    assert "SECRET_TOKEN" not in json.dumps(r) and r["error"] == "OSError"
    assert env.decide(PRE, snapshot=snap(blocked="UNKNOWN_SERVED_MODEL"))["reason"] == "ENVELOPE_BLOCKED"

    def no_calendar(now):
        raise RuntimeError("exchange_calendars missing")
    r = env.decide(PRE, phase_fn=no_calendar)
    assert (r["decision"], r["reason"]) == ("REFUSED", "CALENDAR_UNAVAILABLE")


def test_the_declared_schedule_is_well_formed():
    assert set(C.WORLD_DIGEST_PHASE_CEILING_USD) == set(P.PHASES) == set(C.WORLD_DIGEST_PHASE_OPENS_MIN)
    assert all(0 < v <= 1.0 for v in C.WORLD_DIGEST_PHASE_CEILING_USD.values())  # the $1 run ceiling
    assert set(C.WORLD_DIGEST_PHASE_ESSENTIAL) <= set(P.PHASES)
    assert 0 < C.WORLD_DIGEST_MONTHLY_SHARE <= 1
    assert C.WORLD_DIGEST_PHASE_MAX_HOURS <= C.WORLD_DIGEST_MAX_ITEM_AGE_DAYS * 24
    assert C.WORLD_DIGEST_EXTRACT_PROVIDER == "deepseek"          # local typing is OFF by default


# ── the CLI: skip rc 0, refuse rc 2, run -> the run's rc ─────────────────────

@pytest.fixture
def cli(tmp_path, monkeypatch):
    from scripts import world_digest as S
    from backend.services import world_digest as WD
    monkeypatch.setattr(S, "_ensure_streams", lambda: None)
    monkeypatch.setattr(WD, "optimus", lambda root=None: tmp_path)
    (tmp_path / "digest").mkdir()
    return S


def _args(S):
    return S.argparse.Namespace(hours=24.0, budget=0.9, dry_run=False, no_write=False)


def test_cli_skip_is_rc0_with_a_receipt_line(cli):
    rc = cli.phase_auto(_args(cli), now=at(2026, 11, 11, 15, 0), snapshot_fn=snap,
                        count_fn=lambda a, b: 0, run_fn=lambda a: pytest.fail("no run on a skip"))
    assert rc == 0
    rows = [json.loads(x) for x in cli._phase_decisions_path().read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["decision"] == "SKIP" and rows[-1]["reason"] == "NOT_IN_WINDOW"


def test_cli_refusal_is_rc2(cli):
    rc = cli.phase_auto(_args(cli), now=PRE, snapshot_fn=lambda: snap(digest_usd=50.0),
                        count_fn=lambda a, b: 500, run_fn=lambda a: pytest.fail("no run"))
    assert rc == 2


def test_cli_run_passes_the_decided_hours_and_budget_and_returns_the_runs_rc(cli):
    seen = {}

    def fake_run(a):
        seen.update(hours=a.hours, budget=a.budget)
        return 2                                           # e.g. DEGRADED_MODEL_BUDGET
    rc = cli.phase_auto(_args(cli), now=PRE, snapshot_fn=snap, count_fn=lambda a, b: 500,
                        run_fn=fake_run)
    assert rc == 2
    assert seen["budget"] == C.WORLD_DIGEST_PHASE_CEILING_USD["PRE_MARKET"]
    assert seen["hours"] == C.WORLD_DIGEST_HOURS
    rows = [json.loads(x) for x in cli._phase_decisions_path().read_text(encoding="utf-8").splitlines()]
    assert [r["decision"] for r in rows] == ["RUN", "RUN_RESULT"] and rows[-1]["rc"] == 2


def test_phase_auto_refuses_dry_run_combination(cli):
    assert cli.main(["--phase-auto", "--dry-run"]) == 2


def test_run_lock_guard_refuses_a_concurrent_second_run(tmp_path):
    import threading
    from scripts import world_digest as S
    lock = tmp_path / "run.lock"
    errors: list = []

    def second():
        try:
            with S.RunLock(lock):
                errors.append(None)
        except RuntimeError as exc:
            errors.append(str(exc))
    with S.RunLock(lock):
        t = threading.Thread(target=second)
        t.start()
        t.join(10)
    assert errors and errors[0] and "run.lock.guard" in errors[0]   # the OS lock, not the marker
    with S.RunLock(lock):                                   # released cleanly
        assert lock.exists()
    assert not lock.exists()


def test_run_lock_takes_over_a_marker_whose_pid_is_dead(tmp_path, monkeypatch, capsys):
    """A restart on 2026-11-12 killed a run and its marker cost the whole slot."""
    import json as _json
    from scripts import world_digest as S
    lock = tmp_path / "run.lock"
    lock.write_text(_json.dumps({"pid": 424242, "t": "x"}), encoding="utf-8")
    monkeypatch.setattr(S._SS, "pid_alive", lambda pid: False)
    with S.RunLock(lock):
        assert _json.loads(lock.read_text(encoding="utf-8"))["pid"] != 424242
    assert "TOOK OVER" in capsys.readouterr().out
    assert not lock.exists()


def test_run_lock_still_refuses_a_fresh_marker_whose_pid_is_alive(tmp_path, monkeypatch):
    import json as _json
    import pytest as _pytest
    from scripts import world_digest as S
    lock = tmp_path / "run.lock"
    lock.write_text(_json.dumps({"pid": 424242, "t": "x"}), encoding="utf-8")
    monkeypatch.setattr(S._SS, "pid_alive", lambda pid: True)
    with _pytest.raises(RuntimeError, match="holds run.lock"):
        with S.RunLock(lock):
            pass
    assert lock.exists()                                   # the live run keeps its marker


def test_run_lock_keeps_the_age_rule_for_an_unreadable_marker(tmp_path):
    import pytest as _pytest
    from scripts import world_digest as S
    lock = tmp_path / "run.lock"
    lock.write_text("not json", encoding="utf-8")
    with _pytest.raises(RuntimeError, match="holds run.lock"):
        with S.RunLock(lock):
            pass
