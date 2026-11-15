"""The bars feed's honest status, credential naming and network wait (2026-11-15).

Engineer defects D2/D3. Real receipts replayed here as SYNTHETIC fixtures:

* `20261114T095621Z` -- all four US panels advanced, only the five frozen
  foreign symbols failed, and the whole run was reported `refused`. Now
  DEGRADED (rc 3) naming the five, US panels OK.
* `20261114T024403Z` -- the boot burst: the network was not up, every key probe
  failed, and six keys were blamed. Now WAIT_NETWORK (rc 4) when the venue was
  never reached, and a plain refusal only when it AUTHORITATIVELY rejected.

Plus: the dedicated data key takes precedence, the receipt names the key NAME
and flags a paper-account fallback, and no secret value is ever serialised.
Every date derives from today; no network (resolvers/probes are injected).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend import config
from scripts import night_p6_bars_and_regret as P6
from scripts import pull_bars_refresh as BR

NOW = datetime.now(timezone.utc)
LAST, _CAL = BR.last_closed_session(NOW)
FIVE = ["EVO.ST", "HAG.DE", "KOG.OL", "RHM.DE", "SAAB-B.ST"]


def _days(n_back: int) -> list[date]:
    days, _ = BR._sessions(LAST - timedelta(days=60), LAST)
    return days[-(n_back + 1):] if n_back else days[-1:]


def _panel(path: Path, newest_back: int, symbols=("AAA", "BBB")) -> Path:
    """A panel whose newest bar is `newest_back` sessions before the last close."""
    days, _ = BR._sessions(LAST - timedelta(days=90), LAST)
    days = days[:len(days) - newest_back][-30:]
    rows = [{"symbol": s, "date": pd.Timestamp(d), "open": 10.0, "high": 10.0, "low": 10.0,
             "close": 10.0, "volume": 1000, "vwap": 10.0, "trades": 10}
            for s in symbols for d in days]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _bars(symbols, *dates) -> pd.DataFrame:
    return pd.DataFrame([{"symbol": s, "date": pd.Timestamp(d), "open": 10.0, "high": 10.0,
                          "low": 10.0, "close": 10.0, "volume": 1000, "vwap": 10.0, "trades": 10}
                         for s in symbols for d in dates])


def _frozen_failed(symbols=FIVE):
    """The shape of the real stage's refusal (receipt 20261114T095621Z), synthetic."""
    def refresher(session, *, observed_at):
        return {"status": "refused", "required_session": session.isoformat(),
                "reason": "WAIT_EXACT_FROZEN_MARKS; daily attempt markers preserved",
                "errors": [],
                "coverage": {"status": "INCOMPLETE_OR_UNKNOWN_TARGET_COVERAGE",
                             "symbols": [{"symbol": s, "status": "STALE"} for s in symbols]},
                "history_coverage": {"status": "INCOMPLETE", "symbols": [
                    {"symbol": s, "missing_sessions": [session.isoformat()],
                     "invalid_sessions": []} for s in symbols]},
                "n_new_rows": 0}
    return refresher


def _frozen_ok(session, *, observed_at):
    return {"status": "ok", "n_new_rows": 0}


def _run(tmp_path, panels, puller, refresher, **kw):
    return BR.refresh(panels, now_utc=NOW, puller=puller, required_mark_refresher=refresher,
                      receipt_dir=tmp_path / "r", index=tmp_path / "r" / "i.jsonl", **kw)


def _two_panels(tmp_path, grader_back=1, ranker_back=1, grader_syms=("AAA", "BBB")):
    return {"grader_2025_26": _panel(tmp_path / "g.parquet", grader_back, grader_syms),
            "ranker_deep": _panel(tmp_path / "k.parquet", ranker_back)}


# ───────────────────────── status: DEGRADED vs REFUSED ──────────────────────

def test_us_advanced_and_only_the_five_foreign_failed_is_degraded_rc3(tmp_path):
    """Replay of 20261114T095621Z: was `refused`, now DEGRADED naming the five."""
    panels = _two_panels(tmp_path)
    rec = _run(tmp_path, panels, lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture"),
               _frozen_failed())
    assert rec["status"] == "degraded"
    assert rec["exit_code"] == 3 == config.BARS_REFRESH_RC["degraded"]
    feed = rec["feed"]
    assert feed["us_panels_ok"] is True
    assert all(v["state"] == "OK" and v["reached_last_close"] for v in feed["us_panels"].values())
    assert feed["foreign"]["failed_symbols"] == sorted(FIVE)
    assert feed["foreign"]["undeclared_failed"] == []
    assert all(sym in rec["reason"] for sym in FIVE)
    assert Path(rec["path"]).exists()
    assert json.loads(Path(rec["path"]).read_text())["status"] == "degraded"


def test_main_returns_the_documented_exit_code(tmp_path, monkeypatch, capsys):
    for status, rc in (("ok", 0), ("unchanged", 0), ("refused", 2), ("degraded", 3),
                       ("refused_network", 4)):
        monkeypatch.setattr(BR, "refresh", lambda **kw: {"status": status, "headline": "h"})
        assert BR.main([]) == rc, status
    capsys.readouterr()


def test_a_us_panel_that_did_not_reach_the_last_close_is_refused_even_if_foreign_ok(tmp_path):
    """The failure the brief names: overall OK while a US panel is stale."""
    panels = _two_panels(tmp_path, grader_back=3, ranker_back=3)
    old_day = _days(8)[0]                           # an old session: nothing new
    rec = _run(tmp_path, panels, lambda s, st: (_bars(["AAA", "BBB"], old_day), "fixture"),
               _frozen_ok)
    assert rec["status"] == "refused" and rec["exit_code"] == 2
    assert rec["feed"]["us_panels_ok"] is False
    assert "did not reach" in rec["reason"]


def test_one_stale_us_panel_among_two_is_refused_and_named(tmp_path):
    """ranker advances, the grader panel holds a symbol the venue returns nothing for."""
    panels = _two_panels(tmp_path, grader_syms=("CCC",))
    rec = _run(tmp_path, panels, lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture"),
               _frozen_ok)
    assert rec["status"] == "refused"
    assert rec["feed"]["us_panels"]["ranker_deep"]["state"] == "OK"
    assert rec["feed"]["us_panels"]["grader_2025_26"]["state"] == "NOT_ADVANCED"
    assert "grader_2025_26" in rec["reason"]


def test_an_undeclared_foreign_failure_or_an_unnamed_one_is_refused(tmp_path):
    panels = _two_panels(tmp_path)
    puller = lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture")      # noqa: E731
    rec = _run(tmp_path, panels, puller, _frozen_failed(FIVE + ["ZZZ.XX"]))
    assert rec["status"] == "refused" and "ZZZ.XX" in rec["reason"]

    panels2 = _two_panels(tmp_path / "b")
    def unnamed(session, *, observed_at):
        return {"status": "refused", "reason": "ValueError: INVALID_FROZEN_MARK_REFRESH_RECEIPT",
                "n_new_rows": 0}
    rec2 = _run(tmp_path / "b", panels2, puller, unnamed)
    assert rec2["status"] == "refused" and "name no symbol" in rec2["reason"]


def test_all_current_and_foreign_ok_is_ok_then_unchanged(tmp_path):
    panels = _two_panels(tmp_path)
    puller = lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture")      # noqa: E731
    first = _run(tmp_path, panels, puller, _frozen_ok)
    assert first["status"] == "ok" and first["exit_code"] == 0
    second = _run(tmp_path, panels, puller, _frozen_ok)
    assert second["status"] == "unchanged" and second["exit_code"] == 0


# ───────────────────────────── the network wait ─────────────────────────────

def test_wait_for_network_is_bounded_and_injectable():
    sleeps, calls = [], []

    def never(host, port):
        calls.append(host)
        raise OSError("getaddrinfo failed")
    r = BR.wait_for_network("https://data.example.test", resolver=never,
                            sleep=sleeps.append, tries=3, interval_s=45.0)
    assert r["ok"] is False and r["tries"] == 3 and len(calls) == 3
    assert sleeps == [45.0, 45.0] and r["waited_s"] == 90.0 and "getaddrinfo" in r["error"]

    n = {"i": 0}

    def second_time(host, port):
        n["i"] += 1
        if n["i"] < 2:
            raise OSError("down")
        return [("addr",)]
    ok = BR.wait_for_network("https://data.example.test", resolver=second_time,
                             sleep=lambda s: None, tries=3, interval_s=1.0)
    assert ok["ok"] is True and ok["tries"] == 2


def test_the_network_never_coming_up_is_refused_network_and_no_key_is_tried(tmp_path):
    """Replay of 20261114T024403Z (boot burst): red rc 4, not a credential refusal."""
    panels = _two_panels(tmp_path, grader_back=1, ranker_back=1)
    before = {k: v.read_bytes() for k, v in panels.items()}

    def puller(*a):
        pytest.fail("a key was tried although the network never came up")
    rec = _run(tmp_path, panels, puller, _frozen_ok,
               network_waiter=lambda: {"ok": False, "tries": 3, "waited_s": 90.0,
                                       "host": "data.example.test",
                                       "error": "OSError: getaddrinfo failed"})
    assert rec["status"] == "refused_network" and rec["exit_code"] == 4
    assert "WAIT_NETWORK" in rec["reason"] and "no credential was tried" in rec["reason"]
    assert before == {k: v.read_bytes() for k, v in panels.items()}


def test_an_injected_puller_never_touches_dns(tmp_path, monkeypatch):
    monkeypatch.setattr(BR, "wait_for_network",
                        lambda *a, **k: pytest.fail("DNS touched by a test puller"))
    panels = _two_panels(tmp_path)
    _run(tmp_path, panels, lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture"), _frozen_ok)


# ───────────────────────────── credentials (names) ──────────────────────────

SECRET_A, SECRET_B, SECRET_C = "FAKEKEYID_aaa111", "FAKESECRET_bbb222", "FAKESECRET_ccc333"


def _terminal_env(tmp_path, lines: list[str]) -> Path:
    p = tmp_path / "terminal.env"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_the_dedicated_pair_takes_precedence_over_a_paper_account(tmp_path):
    env = _terminal_env(tmp_path, [f"AAT_HACK1_KEY_ID={SECRET_A}", f"AAT_HACK1_SECRET_KEY={SECRET_B}"])
    c = P6.data_credential_detail(
        environ={"ALPACA_DATA_KEY_ID": "DEDICATED_ID_x", "ALPACA_DATA_SECRET_KEY": "DEDICATED_SEC_x"},
        terminal_env=env, probe=lambda k, s: "ok")
    assert c["name"] == "ALPACA_DATA_KEY_ID" and c["credential_is_paper_account"] is False
    assert c["key_id"] == "DEDICATED_ID_x" and c["warning"] is None
    assert c["tried"]["dedicated_data"] == "ok" and "HACK1" not in c["tried"]


def test_the_dedicated_pair_may_live_in_the_terminal_env_too(tmp_path):
    env = _terminal_env(tmp_path, ["ALPACA_DATA_KEY_ID=D1", "ALPACA_DATA_SECRET_KEY=D2"])
    c = P6.data_credential_detail(environ={}, terminal_env=env, probe=lambda k, s: "ok")
    assert c["name"] == "ALPACA_DATA_KEY_ID" and c["credential_is_paper_account"] is False


def test_without_the_dedicated_pair_the_fallback_order_is_unchanged_and_flagged(tmp_path):
    env = _terminal_env(tmp_path, [f"AAT_HACK2_KEY_ID={SECRET_A}", f"AAT_HACK2_SECRET_KEY={SECRET_B}",
                                   "AAT_HACK1_KEY_ID=h1", "AAT_HACK1_SECRET_KEY=h1s"])
    seen = []

    def probe(k, s):
        seen.append(k)
        return "rejected" if k == "h1" else "ok"           # HACK1 revoked -> HACK2
    c = P6.data_credential_detail(environ={}, terminal_env=env, probe=probe)
    assert seen == ["h1", SECRET_A]                          # HACK1 asked before HACK2
    assert c["name"] == "AAT_HACK2_KEY_ID" and c["credential_is_paper_account"] is True
    assert "CREDENTIAL_IS_PAPER_ACCOUNT" in c["warning"] and "ALPACA_DATA_KEY_ID" in c["warning"]
    assert c["tried"]["HACK1"] == "rejected"
    assert SECRET_A not in c["warning"] and SECRET_B not in c["warning"]


def test_a_dedicated_pair_that_is_rejected_falls_through_with_the_outcome_recorded(tmp_path):
    env = _terminal_env(tmp_path, [f"AAT_HACK1_KEY_ID={SECRET_A}", f"AAT_HACK1_SECRET_KEY={SECRET_B}"])
    c = P6.data_credential_detail(
        environ={"ALPACA_DATA_KEY_ID": "dead", "ALPACA_DATA_SECRET_KEY": "dead2"},
        terminal_env=env, probe=lambda k, s: "rejected" if k == "dead" else "ok")
    assert c["name"] == "AAT_HACK1_KEY_ID" and c["tried"]["dedicated_data"] == "rejected"


def test_boot_burst_is_network_not_credential_and_a_real_401_is_a_credential_refusal(tmp_path):
    env = _terminal_env(tmp_path, [f"AAT_HACK1_KEY_ID={SECRET_A}", f"AAT_HACK1_SECRET_KEY={SECRET_B}",
                                   "AAT_HACK2_KEY_ID=k2", "AAT_HACK2_SECRET_KEY=s2"])
    with pytest.raises(P6.DataNetworkUnavailable) as ni:
        P6.data_credential_detail(environ={}, terminal_env=env, probe=lambda k, s: "network")
    assert "WAIT_NETWORK" in str(ni.value) and SECRET_A not in str(ni.value)
    assert isinstance(ni.value, SystemExit)                  # old `except SystemExit` callers still see it

    with pytest.raises(SystemExit) as ci:
        P6.data_credential_detail(environ={}, terminal_env=env, probe=lambda k, s: "rejected")
    assert not isinstance(ci.value, P6.DataNetworkUnavailable)
    assert "REFUSED" in str(ci.value) and SECRET_A not in str(ci.value)


def test_refresh_maps_the_two_refusals_to_the_two_statuses(tmp_path):
    panels = _two_panels(tmp_path)

    def net(*a):
        raise P6.DataNetworkUnavailable("WAIT_NETWORK: x")

    def cred(*a):
        raise SystemExit("REFUSED: no data credential authenticates")
    assert _run(tmp_path, panels, net, _frozen_ok)["status"] == "refused_network"
    assert _run(tmp_path / "c", _two_panels(tmp_path / "c"), cred, _frozen_ok)["status"] == "refused"


def test_the_receipt_names_the_key_and_no_secret_value_is_ever_written(tmp_path, monkeypatch, capsys):
    """Through the REAL `_pull_default` path: values enter, only names leave."""
    fake = {"key_id": SECRET_A, "secret": SECRET_B, "name": "AAT_HACK1_KEY_ID", "label": "HACK1",
            "kind": "paper_trading_account", "credential_is_paper_account": True,
            "tried": {"dedicated_data": "absent", "HACK1": "ok"},
            "source": "terminal repo .env, HACK1 (AAT_HACK1_KEY_ID) (data endpoint only, verified)",
            "warning": "CREDENTIAL_IS_PAPER_ACCOUNT: the bar feed is using AAT_HACK1_KEY_ID"}
    monkeypatch.setattr(P6, "data_credential_detail", lambda **kw: dict(fake))
    seen_headers = []

    def fake_get(path, params, kid, sec, timeout=90.0):
        seen_headers.append((kid, sec))                      # the venue DOES get the values
        return {"bars": {"AAA": [{"t": f"{LAST.isoformat()}T04:00:00Z", "o": 1, "h": 1, "l": 1,
                                  "c": 1, "v": 1, "vw": 1, "n": 1}]}}
    monkeypatch.setattr(P6, "_get", fake_get)
    panels = {"ranker_deep": _panel(tmp_path / "k.parquet", 1, ("AAA",))}
    rec = BR.refresh(panels, now_utc=NOW, receipt_dir=tmp_path / "r",
                     index=tmp_path / "r" / "i.jsonl",
                     network_waiter=lambda: {"ok": True, "tries": 1, "waited_s": 0.0,
                                             "host": "h", "error": None},
                     required_mark_refresher=_frozen_ok)
    assert seen_headers and seen_headers[0] == (SECRET_A, SECRET_B)
    assert rec["credential"]["name"] == "AAT_HACK1_KEY_ID"
    assert rec["credential"]["credential_is_paper_account"] is True
    assert "CREDENTIAL_IS_PAPER_ACCOUNT" in rec["warning"]
    blob = json.dumps(rec, default=str) + Path(rec["path"]).read_text(encoding="utf-8") \
        + (tmp_path / "r" / "i.jsonl").read_text(encoding="utf-8") + capsys.readouterr().out
    for secret in (SECRET_A, SECRET_B):
        assert secret not in blob
    assert "key_id" not in rec["credential"] and "secret" not in rec["credential"]


def test_a_string_credential_from_an_older_puller_still_records(tmp_path):
    panels = _two_panels(tmp_path)
    rec = _run(tmp_path, panels, lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture"), _frozen_ok)
    assert rec["pull"]["credential_source"] == "fixture"
    assert rec["credential"]["credential_is_paper_account"] is None


def test_config_declares_the_dedicated_pair_first_and_the_old_order_after():
    order = [e["label"] for e in config.BARS_DATA_CREDENTIAL_ORDER]
    assert order == ["dedicated_data", "process_env", "HACK1", "HACK2", "HACK4", "HACK5",
                     "HACK6", "HACK3"]
    first = config.BARS_DATA_CREDENTIAL_ORDER[0]
    assert (first["key"], first["secret"]) == ("ALPACA_DATA_KEY_ID", "ALPACA_DATA_SECRET_KEY")
    assert not first["paper"] and all(e["paper"] for e in config.BARS_DATA_CREDENTIAL_ORDER[2:])
    assert set(config.BARS_REFRESH_OPTIONAL_FOREIGN_SYMBOLS) == set(FIVE)
    assert len(set(config.BARS_REFRESH_RC.values())) == 4     # 0/2/3/4 all distinct codes


# ───────────────────────── review-149 fixes ─────────────────────────────────

def test_one_of_two_names_advancing_is_not_a_current_panel(tmp_path):
    """Coverage, not the panel's max date: AAA reached the close, BBB did not."""
    panels = _two_panels(tmp_path)
    rec = _run(tmp_path, panels, lambda s, st: (_bars(["AAA"], LAST), "fixture"), _frozen_ok)
    assert rec["status"] == "refused" and rec["exit_code"] == 2
    cov = rec["feed"]["us_panels"]["ranker_deep"]["coverage"]
    assert cov["n_prev"] == 2 and cov["n_reached"] == 1 and cov["share"] == 0.5
    assert rec["panels"]["ranker_deep"]["coverage"]["share"] == 0.5     # printed per panel
    assert rec["feed"]["us_panels"]["ranker_deep"]["state"] == "NOT_ADVANCED"


def test_full_coverage_is_ok_and_the_threshold_is_config(tmp_path, monkeypatch):
    panels = _two_panels(tmp_path)
    rec = _run(tmp_path, panels, lambda s, st: (_bars(["AAA", "BBB"], LAST), "fixture"), _frozen_ok)
    assert rec["status"] == "ok"
    assert rec["feed"]["us_panels"]["grader_2025_26"]["coverage"]["share"] == 1.0
    assert config.BARS_REFRESH_MIN_COVERAGE == 0.90


def test_the_process_env_pair_is_unknown_not_not_paper(tmp_path):
    c = P6.data_credential_detail(
        environ={"APCA_API_KEY_ID": "I1", "APCA_API_SECRET_KEY": "S1"},
        terminal_env=tmp_path / "none.env", probe=lambda k, s: pytest.fail("unverified entry probed"))
    assert c["name"] == "APCA_API_KEY_ID" and c["credential_is_paper_account"] is None
    assert c["warning"] is None
    assert [e for e in config.BARS_DATA_CREDENTIAL_ORDER if e["label"] == "process_env"][0]["paper"] is None


def test_a_rejected_dedicated_pair_leaves_a_warning_in_the_receipt(tmp_path):
    env = _terminal_env(tmp_path, [f"AAT_HACK1_KEY_ID={SECRET_A}", f"AAT_HACK1_SECRET_KEY={SECRET_B}"])
    c = P6.data_credential_detail(
        environ={"ALPACA_DATA_KEY_ID": "dead", "ALPACA_DATA_SECRET_KEY": "dead2"},
        terminal_env=env, probe=lambda k, s: "rejected" if k == "dead" else "ok")
    assert "DEDICATED_DATA_KEY_REJECTED" in c["warning"] and "CREDENTIAL_IS_PAPER_ACCOUNT" in c["warning"]
    assert "dead" not in c["warning"].replace("DEDICATED_DATA_KEY_REJECTED", "").replace(
        "ALPACA_DATA_KEY_ID", "")
    rec = _run(tmp_path, _two_panels(tmp_path),
               lambda s, st: (_bars(["AAA", "BBB"], LAST), {**c, "key_id": None, "secret": None}),
               _frozen_ok)
    assert "DEDICATED_DATA_KEY_REJECTED" in rec["warning"]


def test_the_network_down_status_can_never_read_idle_in_map_status():
    from backend.services import task_receipts as TR
    assert TR.map_status("refused_network") == "REFUSED"
    assert TR.map_status("degraded") == "DEGRADED"
    assert "refused_network" in config.BARS_REFRESH_RC
    assert TR.map_status("wait_network") == "IDLE"          # why the word was renamed


def test_the_no_secret_assertion_holds_on_the_refusal_paths_too(tmp_path, monkeypatch, capsys):
    fake = {"key_id": SECRET_A, "secret": SECRET_B, "name": "AAT_HACK1_KEY_ID", "label": "HACK1",
            "kind": "paper_trading_account", "credential_is_paper_account": True,
            "tried": {"HACK1": "ok"}, "source": "terminal repo .env, HACK1 (AAT_HACK1_KEY_ID)",
            "warning": "CREDENTIAL_IS_PAPER_ACCOUNT: x"}
    monkeypatch.setattr(P6, "data_credential_detail", lambda **kw: dict(fake))
    monkeypatch.setattr(P6, "_get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError(f"boom with {SECRET_A} {SECRET_B}")))        # a venue error that echoes a key
    panels = {"ranker_deep": _panel(tmp_path / "k.parquet", 1, ("AAA",))}
    ok_net = lambda: {"ok": True, "tries": 1, "waited_s": 0.0, "host": "h", "error": None}  # noqa: E731
    rec = BR.refresh(panels, now_utc=NOW, receipt_dir=tmp_path / "r", index=tmp_path / "r" / "i.jsonl",
                     network_waiter=ok_net, required_mark_refresher=_frozen_ok)
    assert rec["status"] == "refused"
    blob = json.dumps(rec, default=str) + Path(rec["path"]).read_text(encoding="utf-8") \
        + capsys.readouterr().out
    # the vendor's own error text is the one place a value could leak: it must be scrubbed
    assert SECRET_A not in blob and SECRET_B not in blob
    # and the network-down path
    rec2 = BR.refresh({"ranker_deep": _panel(tmp_path / "k2.parquet", 1, ("AAA",))}, now_utc=NOW,
                      receipt_dir=tmp_path / "r2", index=tmp_path / "r2" / "i.jsonl",
                      network_waiter=lambda: {"ok": False, "tries": 3, "waited_s": 90.0,
                                              "host": "h", "error": "OSError"},
                      required_mark_refresher=_frozen_ok)
    assert rec2["status"] == "refused_network"
    assert SECRET_A not in Path(rec2["path"]).read_text(encoding="utf-8")
