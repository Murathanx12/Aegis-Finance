"""Offline discovery against real seals, selection and warning construction."""
import base64
from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.services import telegram_bridge
from backend.services.saved_earnings_calendar_input import build_saved_earnings_calendar_input
from scripts import pre_event_owner_warning_discover as discovery


@pytest.fixture
def case(tmp_path, monkeypatch):
    once = discovery.once
    now = datetime.now(timezone.utc).replace(hour=21, minute=0, second=0, microsecond=0)
    observed = now - timedelta(minutes=30)
    receipts = tmp_path / "receipts"
    journal = tmp_path / "journal"
    ledger = tmp_path / "ledger"
    receipts.mkdir()
    journal.mkdir()
    (ledger / "pc_book").mkdir(parents=True)
    monkeypatch.setattr(once.capture, "_private_identity", lambda _p: (1, 2))
    monkeypatch.setattr(once.private_journal, "_journal_identity", lambda _p: (3, 4))
    for name in ("send_owner_once", "owner_chat_id"):
        monkeypatch.setattr(telegram_bridge, name, lambda *_a, **_k: pytest.fail("transport"))
    monkeypatch.setattr(once.capture, "capture_earnings_calendar",
                        lambda **_k: pytest.fail("provider"))
    account = "SYNTHETIC_ACCOUNT"
    snapshot = {"t": (now - timedelta(minutes=5)).isoformat(), "tag": "sim_owner",
                "account_number": account, "equity": 2000, "cash": 1000,
                "long_market_value": 1000, "short_market_value": 0, "n_positions": 2,
                "positions": [{"symbol": t, "qty": 5, "market_value": 500,
                               "current_price": 100} for t in ("AAA", "BBB")]}
    (ledger / "pc_book" / "state_latest.json").write_text(json.dumps(snapshot))

    def save(index=1, ticker="AAA", days=2, age=0):
        stamp = (observed - timedelta(days=age)).isoformat()
        event = (now + timedelta(days=days)).date().isoformat()
        raw = json.dumps({"earningsCalendar": [{"symbol": ticker, "date": event,
                          "hour": "amc", "quarter": 1, "year": now.year,
                          "epsEstimate": 1, "epsActual": None,
                          "revenueEstimate": 100, "revenueActual": None}]}).encode()
        packet = build_saved_earnings_calendar_input(
            raw, ticker=ticker, observed_utc=stamp, cutoff_utc=stamp)
        receipt = {"schema": once.capture._SCHEMA, "source": once.capture._SOURCE,
                   "ticker": ticker, "from": (observed - timedelta(days=age) + timedelta(days=1)).date().isoformat(),
                   "to": (observed - timedelta(days=age) + timedelta(days=7)).date().isoformat(),
                   "request_utc": stamp, "observed_utc": stamp, "cutoff_utc": stamp,
                   "response_sha256": once.selector.sha(raw),
                   "response_bytes_b64": base64.b64encode(raw).decode(),
                   "input_id": packet["input_id"]}
        receipt["receipt_id"] = once.capture._seal(receipt)
        path = receipts / f"earnings-calendar-{index:032x}.json"
        path.write_text(json.dumps(receipt))
        return path

    kwargs = dict(receipt_dir=receipts, ledger_dir=ledger, journal_dir=journal,
                  expected_account_sha256=once.selector.sha(account.encode()), now=now)
    return kwargs, save


def test_empty_is_explicit_noop(case):
    kwargs, _ = case
    code, output = discovery.run(**kwargs)
    assert code == 0 and output["reason"] == "NO_SAVED_RECEIPT"
    assert output["status"] == "NO_OP"


def test_multiple_selects_one_earliest_event_and_no_transport(case, monkeypatch):
    kwargs, save = case
    save(1, "AAA", 3)
    selected = save(2, "BBB", 2)
    calls = []
    original = discovery.once.run

    def wrapped(**options):
        calls.append(options)
        return original(**options)

    monkeypatch.setattr(discovery.once, "run", wrapped)
    code, output = discovery.run(**kwargs)
    assert code == 0 and output["ticker"] == "BBB" and output["delivery"] == "PREVIEW"
    assert len(calls) == 1 and calls[0]["receipt_path"] == selected
    assert "send" not in calls[0] and not list(kwargs["journal_dir"].iterdir())


def test_corrupt_only_and_corrupt_plus_valid(case):
    kwargs, save = case
    bad = kwargs["receipt_dir"] / ("earnings-calendar-" + "f" * 32 + ".json")
    bad.write_text("{broken")
    code, output = discovery.run(**kwargs)
    assert code == 2 and output["reason"] == "NO_VALID_RECEIPT"
    save()
    code, output = discovery.run(**kwargs)
    assert code == 0 and output["ticker"] == "AAA"


@pytest.mark.parametrize("suffix", [".json", ".result.json", ".result.pending.json"])
def test_duplicate_attempt_never_retried(case, suffix):
    kwargs, save = case
    save()
    _, preview = discovery.run(**kwargs)
    (kwargs["journal_dir"] / (preview["event_id"] + suffix)).write_text("ambiguous")
    code, output = discovery.run(**kwargs)
    assert code == 0 and output["reason"] == "DUPLICATE_EVENTS_SUPPRESSED"


def test_expired_receipt_and_event_refused(case):
    kwargs, save = case
    save(age=2)
    assert discovery.run(**kwargs)[0] == 2
    save(days=1)
    kwargs["now"] += timedelta(days=1)
    assert discovery.run(**kwargs)[0] == 2


def test_entry_limit_refuses_even_if_valid(case):
    kwargs, save = case
    save()
    for index in range(discovery.MAX_ENTRIES):
        (kwargs["receipt_dir"] / str(index)).touch()
    assert discovery.run(**kwargs)[1]["reason"] == "DISCOVERY_ENTRY_LIMIT"


def test_iif_and_bad_account_refused(case):
    kwargs, save = case
    save()
    assert discovery.run(**{**kwargs, "expected_account_sha256": "0" * 64})[0] == 2
    kwargs["now"] = kwargs["now"].replace(hour=9, minute=0)
    assert discovery.run(**kwargs)[0] == 2


def test_send_cli_not_available(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        discovery.main([
            "--receipt-dir", str(tmp_path / "receipts"),
            "--pc-paper-ledger", str(tmp_path / "ledger"),
            "--expected-account-sha256", "0" * 64,
            "--journal-dir", str(tmp_path / "journal"),
            "--send",
        ])
    assert exc.value.code == 2
    assert "unrecognized arguments: --send" in capsys.readouterr().err



def test_tampered_seal_refused_without_delegation(case, monkeypatch):
    kwargs, save = case
    path = save()
    receipt = json.loads(path.read_text())
    receipt["receipt_id"] = "0" * 64
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(discovery.once, "run", lambda **_k: pytest.fail("delegated"))
    assert discovery.run(**kwargs)[1]["reason"] == "NO_VALID_RECEIPT"


def test_newest_observation_wins_without_mtime(case, monkeypatch):
    kwargs, save = case
    older = save(1)
    newer = save(2)
    receipt = json.loads(older.read_text())
    observed = datetime.fromisoformat(receipt["observed_utc"]) - timedelta(minutes=5)
    raw = base64.b64decode(receipt["response_bytes_b64"])
    packet = build_saved_earnings_calendar_input(
        raw, ticker="AAA", observed_utc=observed.isoformat(), cutoff_utc=observed.isoformat())
    receipt.update(request_utc=observed.isoformat(), observed_utc=observed.isoformat(),
                   cutoff_utc=observed.isoformat(), input_id=packet["input_id"])
    receipt["receipt_id"] = discovery.once.capture._seal(receipt)
    older.write_text(json.dumps(receipt))  # Most recently written, oldest observation.
    calls = []
    original = discovery.once.run

    def wrapped(**options):
        calls.append(options["receipt_path"])
        return original(**options)

    monkeypatch.setattr(discovery.once, "run", wrapped)
    assert discovery.run(**kwargs)[0] == 0
    assert calls == [newer]


def test_root_swap_refused(case, monkeypatch):
    kwargs, save = case
    save()
    identities = iter([(1, 2), (1, 2), (1, 2), (9, 9)])
    monkeypatch.setattr(discovery.once.capture, "_private_identity", lambda _p: next(identities))
    assert discovery.run(**kwargs)[0] == 2


def test_changed_selected_receipt_refused(case, monkeypatch):
    kwargs, save = case
    selected = save()
    original = discovery.once.selector.frozen_read
    reads = 0

    def changed(path):
        nonlocal reads
        if path == selected:
            reads += 1
            if reads == 2:
                return b"changed"
        return original(path)

    monkeypatch.setattr(discovery.once.selector, "frozen_read", changed)
    assert discovery.run(**kwargs)[0] == 2


def test_budget_refused(case, monkeypatch):
    kwargs, _ = case
    ticks = iter([0, discovery.MAX_SECONDS + 1])
    monkeypatch.setattr(discovery.time, "monotonic", lambda: next(ticks))
    assert discovery.run(**kwargs)[0] == 2
