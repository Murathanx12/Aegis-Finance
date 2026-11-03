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
    assert calls[0]["send"] is False and not list(kwargs["journal_dir"].iterdir())


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


def test_exactly_64_directory_entries_allowed(case):
    kwargs, save = case
    save()
    assert discovery.MAX_ENTRIES == 64
    for index in range(63):
        (kwargs["receipt_dir"] / f"unrelated-{index}").touch()
    assert len(list(kwargs["receipt_dir"].iterdir())) == 64
    code, output = discovery.run(**kwargs)
    assert code == 0 and output["ticker"] == "AAA" and output["delivery"] == "PREVIEW"
    assert not list(kwargs["journal_dir"].iterdir())


def test_iif_and_bad_account_refused(case):
    kwargs, save = case
    save()
    assert discovery.run(**{**kwargs, "expected_account_sha256": "0" * 64})[0] == 2
    kwargs["now"] = kwargs["now"].replace(hour=9, minute=0)
    assert discovery.run(**kwargs)[0] == 2


def test_send_cli_requires_review(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        discovery.main([
            "--receipt-dir", str(tmp_path / "receipts"),
            "--pc-paper-ledger", str(tmp_path / "ledger"),
            "--expected-account-sha256", "0" * 64,
            "--journal-dir", str(tmp_path / "journal"),
            "--send",
        ])
    assert exc.value.code == 2
    assert "--send requires --review" in capsys.readouterr().err



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


def review_file(tmp_path):
    """Synthetic attestation only; never an independent adoption approval."""
    path = tmp_path / "test-review.json"
    path.write_text(json.dumps({
        "schema": "pre-event-warning-review/1",
        "independent_exact_source_review": True, "reviewer": "synthetic-test-only",
        "sha256": discovery.once._source_hashes(),
    }))
    return path


def synthetic_sender(monkeypatch, kwargs, *, wall_now=None):
    """Real once/durable journal, synthetic clocks and ACK; no native transport."""
    calls = []
    original = discovery.once.run

    def delegate(**options):
        return original(**options, wall_clock=lambda: wall_now or kwargs["now"],
                        epoch_clock=lambda: kwargs["now"].timestamp())

    def stub(text, *, tag, expected_owner, until):
        calls.append(text)
        assert len(calls) == 1 and expected_owner == "123456"
        assert kwargs["now"].timestamp() < until <= kwargs["now"].timestamp() + 30
        pending = json.loads(next(kwargs["journal_dir"].glob("*.json")).read_text())
        assert pending["state"] == "SENDING"
        journal = discovery.once.private_journal
        ack = {"state": "SENT", "messages": 1, "native_ack_sha256": "f" * 64,
               "tag_sha256": journal._digest({"tag": tag}),
               "text_sha256": journal._hash(text)}
        ack["delivery_binding_sha256"] = journal._digest({
            key: ack[key] for key in journal._ACK_HASH_KEYS})
        return ack

    monkeypatch.setattr(discovery.once, "run", delegate)
    monkeypatch.setattr(telegram_bridge, "owner_chat_id", lambda: "123456")
    monkeypatch.setattr(telegram_bridge, "send_owner_once", stub)
    return calls


@pytest.mark.parametrize("bad", ["missing", "wrong", "omitted_discovery", "wrong_hash"])
def test_send_requires_exact_review(case, tmp_path, bad):
    kwargs, save = case
    save()
    gate = review_file(tmp_path)
    document = json.loads(gate.read_text())
    name = "scripts/pre_event_owner_warning_discover.py"
    assert name in discovery.once.SOURCE_PATHS
    if bad == "missing":
        gate = None
    else:
        if bad == "wrong":
            document["independent_exact_source_review"] = False
        elif bad == "omitted_discovery":
            del document["sha256"][name]
        else:
            document["sha256"][name] = "0" * 64
        gate.write_text(json.dumps(document))
    code, output = discovery.run(**kwargs, send=True, review=gate)
    assert code == 2 and output["status"] == "REFUSED"
    assert not list(kwargs["journal_dir"].iterdir())


def test_changed_discovery_source_invalidates_review(case, tmp_path, monkeypatch):
    kwargs, save = case
    save()
    gate = review_file(tmp_path)
    root = tmp_path / "sources"
    for name in discovery.once.SOURCE_PATHS:
        source = discovery.once.ROOT / name
        if source.is_file():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    changed = root / "scripts/pre_event_owner_warning_discover.py"
    changed.write_bytes(changed.read_bytes() + b"\n# synthetic mutation\n")
    monkeypatch.setattr(discovery.once, "ROOT", root)
    assert discovery.run(**kwargs, send=True, review=gate)[0] == 2
    assert not list(kwargs["journal_dir"].iterdir())


def test_send_one_selected_event_and_suppress_confirmed_duplicate(case, tmp_path, monkeypatch):
    kwargs, save = case
    save(1, "AAA", 3)
    save(2, "BBB", 2)
    calls = synthetic_sender(monkeypatch, kwargs)
    gate = review_file(tmp_path)
    code, output = discovery.run(**kwargs, send=True, review=gate)
    assert code == 0 and output["ticker"] == "BBB" and output["delivery"] == "SENT"
    assert len(calls) == 1
    # Retain only the already-sent receipt, not a different eligible event.
    (kwargs["receipt_dir"] / f"earnings-calendar-{1:032x}.json").unlink()
    code, output = discovery.run(**kwargs, send=True, review=gate)
    assert code == 0 and output["reason"] == "DUPLICATE_EVENTS_SUPPRESSED"
    assert len(calls) == 1


@pytest.mark.parametrize("suffix", [".json", ".result.json", ".result.pending.json"])
def test_send_suppresses_ambiguous_journal(case, tmp_path, suffix):
    kwargs, save = case
    save()
    _, preview = discovery.run(**kwargs)
    (kwargs["journal_dir"] / (preview["event_id"] + suffix)).write_text("uncertain")
    code, output = discovery.run(**kwargs, send=True, review=review_file(tmp_path))
    assert code == 0 and output["reason"] == "DUPLICATE_EVENTS_SUPPRESSED"


def test_duplicate_created_after_selection_hits_durable_guard(case, tmp_path, monkeypatch):
    kwargs, save = case
    save()
    _, preview = discovery.run(**kwargs)
    original = discovery.once.run
    monkeypatch.setattr(telegram_bridge, "owner_chat_id", lambda: "123456")

    def competing_attempt(**options):
        pending = kwargs["journal_dir"] / (preview["event_id"] + ".result.pending.json")
        pending.write_text("uncertain competing attempt")
        return original(**options, wall_clock=lambda: kwargs["now"],
                        epoch_clock=lambda: kwargs["now"].timestamp())

    monkeypatch.setattr(discovery.once, "run", competing_attempt)
    code, output = discovery.run(**kwargs, send=True, review=review_file(tmp_path))
    assert code == 2 and output["delivery"] == "DUPLICATE_RECONCILE_REQUIRED"
    assert len(list(kwargs["journal_dir"].iterdir())) == 1


@pytest.mark.parametrize("root", ["capture", "journal"])
def test_root_replaced_at_final_pretransport_checkpoint(case, tmp_path, monkeypatch, root):
    kwargs, save = case
    save()
    # Exercise real temporary-directory replacement identities. The fixture's
    # ACL qualification remains synthetic; this makes no authentication claim.
    def identity(path):
        info = path.stat()
        return info.st_dev, info.st_ino

    monkeypatch.setattr(discovery.once.capture, "_private_identity", identity)
    monkeypatch.setattr(discovery.once.private_journal, "_journal_identity", identity)
    original_run = discovery.once.run
    original_deliver = discovery.once.delivery.deliver
    replaced = []
    transport = []
    retained = tmp_path / "retained-root"

    def forbidden_transport(*_args, **_kwargs):
        transport.append(True)
        pytest.fail("transport reached after root replacement")

    def delegate(**options):
        return original_run(**options, wall_clock=lambda: kwargs["now"],
                            epoch_clock=lambda: kwargs["now"].timestamp())

    def deliver(artifact, *, journal_dir, sender):
        def replace_then_check(text, *, tag):
            # The real delivery adapter has already fsynced SENDING and checked
            # its journal identity; the real sender's final check is next.
            record = journal_dir / (artifact["event_id"] + ".json")
            assert json.loads(record.read_text())["state"] == "SENDING"
            directory = kwargs["receipt_dir"] if root == "capture" else journal_dir
            before = identity(directory)
            directory.rename(retained)
            directory.mkdir()
            assert identity(directory) != before
            replaced.append(artifact["event_id"])
            return sender(text, tag=tag)

        return original_deliver(artifact, journal_dir=journal_dir, sender=replace_then_check)

    monkeypatch.setattr(discovery.once, "run", delegate)
    monkeypatch.setattr(discovery.once.delivery, "deliver", deliver)
    monkeypatch.setattr(telegram_bridge, "owner_chat_id", lambda: "123456")
    monkeypatch.setattr(telegram_bridge, "send_owner_once", forbidden_transport)
    gate = review_file(tmp_path)
    code, output = discovery.run(**kwargs, send=True, review=gate)
    assert code == 2 and output["delivery"] == "UNKNOWN_RECONCILE_REQUIRED"
    assert replaced == [output["event_id"]] and transport == []
    event = output["event_id"]
    record_root = retained if root == "journal" else kwargs["journal_dir"]
    assert json.loads((record_root / (event + ".json")).read_text())["state"] == "SENDING"
    result = json.loads((kwargs["journal_dir"] / (event + ".result.json")).read_text())
    assert result["state"] == "UNKNOWN_RECONCILE_REQUIRED" and result["ack"] is None
    assert not (kwargs["journal_dir"] / (event + ".result.pending.json")).exists()
    if root == "journal":
        # The result alone in the replacement root still prevents a retry.
        code, output = discovery.run(**kwargs, send=True, review=gate)
        assert code == 0 and output["reason"] == "DUPLICATE_EVENTS_SUPPRESSED"
        assert len(replaced) == 1 and transport == []


def test_expired_at_send_wall_clock_refused(case, tmp_path, monkeypatch):
    kwargs, save = case
    save(days=1)
    calls = synthetic_sender(monkeypatch, kwargs, wall_now=kwargs["now"] + timedelta(days=1))
    code, output = discovery.run(**kwargs, send=True, review=review_file(tmp_path))
    assert code == 2 and output["status"] == "REFUSED" and not calls
    assert not list(kwargs["journal_dir"].iterdir())


def test_iif_at_send_wall_clock_refused(case, tmp_path, monkeypatch):
    kwargs, save = case
    save(days=2)
    protected = (kwargs["now"] + timedelta(days=1)).replace(hour=9)
    calls = synthetic_sender(monkeypatch, kwargs, wall_now=protected)
    code, output = discovery.run(**kwargs, send=True, review=review_file(tmp_path))
    assert code == 2 and output["status"] == "REFUSED" and not calls
    assert not list(kwargs["journal_dir"].iterdir())


@pytest.mark.parametrize("send", [False, True])
def test_cli_explicit_send_and_review_forwarding(tmp_path, monkeypatch, send):
    options = ["--receipt-dir", str(tmp_path / "receipts"),
               "--pc-paper-ledger", str(tmp_path / "ledger"),
               "--expected-account-sha256", "0" * 64,
               "--journal-dir", str(tmp_path / "journal")]
    gate = tmp_path / "review.json"
    if send:
        options += ["--send", "--review", str(gate)]
    calls = []

    def stub(**kwargs):
        calls.append(kwargs)
        return 2, {"status": "REFUSED", "delivery": "NOT_SENT"}

    monkeypatch.setattr(discovery, "run", stub)
    assert discovery.main(options) == 2
    assert len(calls) == 1 and calls[0]["send"] is send
    assert calls[0]["review"] == (gate if send else None)


@pytest.mark.parametrize("mutation", ["budget", "receipt", "review"])
def test_discovery_constraints_remain_binding_inside_once(case, tmp_path, monkeypatch, mutation):
    kwargs, save = case
    path = save()
    gate = review_file(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(discovery.time, "monotonic", lambda: clock[0])
    original = discovery.once._review
    checks = 0

    def mutate(review):
        nonlocal checks
        checks += 1
        if checks == 2:
            if mutation == "budget":
                clock[0] = discovery.MAX_SECONDS + 1
            elif mutation == "receipt":
                path.write_bytes(path.read_bytes() + b"\n")
            else:
                gate.write_text("{}")
        original(review)

    monkeypatch.setattr(discovery.once, "_review", mutate)
    code, output = discovery.run(**kwargs, send=True, review=gate)
    assert checks == 2 and code == 2 and output["status"] == "REFUSED"
    assert not list(kwargs["journal_dir"].iterdir())
