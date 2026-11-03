"""Offline integration of the warning journal with the real owner bridge helper."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from backend.services import owner_event_warning as warning
from backend.services import telegram_bridge as bridge


def test_bound_ack_replays_without_second_transport(monkeypatch, tmp_path):
    now = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
    source = json.dumps({
        "ticker": "TEST", "form": "8-K", "exhibit": "EX-99.1",
        "event_type": "earnings_results", "accession": "0001234567-26-000001",
        "url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/results.htm",
        "published_at": (now - timedelta(hours=2)).isoformat(),
        "captured_at": (now - timedelta(hours=1)).isoformat(),
        "body": "Quarterly financial results are available.",
    })
    snapshot = json.dumps({
        "lane": "PC-PAPER", "as_of": (now - timedelta(hours=1)).isoformat(),
        "equity_usd": 1000, "positions": [{"ticker": "TEST", "market_value_usd": 100,
                                            "instrument": "equity", "leverage": 1}],
    })
    journal = tmp_path / "private_journal"
    journal.mkdir()
    monkeypatch.setattr(warning, "_journal_identity", lambda path: (1, 1))
    monkeypatch.setenv(bridge.OWNER_ENV, "123456")
    monkeypatch.setattr(bridge, "OUTBOX_PATH", tmp_path / "outbox.jsonl")
    transport = Mock(return_value={"message_id": 7, "chat": {"id": 123456, "type": "private"}})
    monkeypatch.setattr(bridge, "_call", transport)

    first = warning.warn(source, snapshot, now=now, journal_dir=journal,
                         sender=bridge.send_owner_once)
    assert first["artifact"]["status"] == "PROVISIONAL"
    assert first["delivery"] == "SENT"
    assert transport.call_count == 1

    second = warning.warn(source, snapshot, now=now + timedelta(minutes=5),
                          journal_dir=journal, sender=bridge.send_owner_once)
    assert second["delivery"] == "ALREADY_SENT"
    transport.assert_called_once()
