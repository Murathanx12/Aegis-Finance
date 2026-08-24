"""The provider's balance is a MEASUREMENT, and a failed measurement is not $0.

The whole value of `deepseek_balance` is that it is not derived from anything
this repository believes. That value is destroyed the moment a failed read
degrades to a number: a receipt saying `spend $0.00` is worse than one saying
`spend UNKNOWN`, because the first is quotable. Every test here is a variation
on that one sentence.

Offline by construction — the fast suite blocks sockets, and a balance reader
that needed the network to be tested would only ever be tested in production.
"""

from __future__ import annotations

import io
import json

import pytest

from backend.services import deepseek_balance as B


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _opener(payload, *, boom=None):
    def _open(req, timeout=None):
        if boom is not None:
            raise boom
        return _Resp(json.dumps(payload).encode("utf-8"))
    return _open


_OK = {"is_available": True,
       "balance_infos": [{"currency": "USD", "total_balance": "23.99",
                          "granted_balance": "0.00",
                          "topped_up_balance": "23.99"}]}


# ── the happy path, and the shape the receipt consumes ──────────────────────


def test_reads_the_usd_row():
    out = B.read_balance(api_key="k", opener=_opener(_OK))
    assert out["total_usd"] == 23.99
    assert out["granted_usd"] == 0.0
    assert out["is_available"] is True
    assert out["raw"] == _OK, "the vendor's bytes travel with the number"


def test_picks_the_USD_row_out_of_several_currencies():
    payload = {"balance_infos": [
        {"currency": "CNY", "total_balance": "170.00"},
        {"currency": "USD", "total_balance": "23.99"}]}
    assert B.read_balance(api_key="k",
                          opener=_opener(payload))["total_usd"] == 23.99


# ── every failure is a REFUSAL, never a number ──────────────────────────────


def test_no_key_REFUSES_rather_than_returning_a_default():
    with pytest.raises(B.BalanceUnavailable) as exc:
        B.read_balance(api_key="", opener=_opener(_OK))
    assert "DEEPSEEK_API_KEY" in str(exc.value)


def test_a_transport_failure_REFUSES():
    with pytest.raises(B.BalanceUnavailable):
        B.read_balance(api_key="k", opener=_opener(None, boom=OSError("down")))


def test_unparseable_json_REFUSES():
    def _open(req, timeout=None):
        return _Resp(b"<html>502</html>")
    with pytest.raises(B.BalanceUnavailable):
        B.read_balance(api_key="k", opener=_open)


def test_a_payload_with_no_USD_row_REFUSES_AND_NAMES_THE_CURRENCIES():
    """The account could be denominated in CNY. Returning the first row would
    report a yuan balance as dollars and every derived cost would be 7x off."""
    payload = {"balance_infos": [{"currency": "CNY", "total_balance": "170"}]}
    with pytest.raises(B.BalanceUnavailable) as exc:
        B.read_balance(api_key="k", opener=_opener(payload))
    assert "CNY" in str(exc.value)


def test_a_usd_row_with_no_readable_total_REFUSES():
    payload = {"balance_infos": [{"currency": "USD", "total_balance": "n/a"}]}
    with pytest.raises(B.BalanceUnavailable):
        B.read_balance(api_key="k", opener=_opener(payload))


def test_zero_is_a_REAL_balance_and_is_not_confused_with_a_failure():
    """An exhausted account reads 0.00 and that must survive as a number —
    the refusal path is for NOT KNOWING, not for knowing it is empty."""
    payload = {"balance_infos": [{"currency": "USD", "total_balance": "0.00"}]}
    assert B.read_balance(api_key="k",
                          opener=_opener(payload))["total_usd"] == 0.0


# ── the snapshot ledger ─────────────────────────────────────────────────────


def test_snapshot_appends_and_survives_reading_back(tmp_path):
    p = tmp_path / "bal.jsonl"
    a = B.snapshot("night_start", path=p, api_key="k", opener=_opener(_OK))
    assert a["persisted"] is True
    later = {"balance_infos": [{"currency": "USD", "total_balance": "23.05"}]}
    b = B.snapshot("night_end", path=p, api_key="k", opener=_opener(later))
    rows = B.snapshots(p)
    assert [r["label"] for r in rows] == ["night_start", "night_end"]
    assert "raw" not in rows[0], "the vendor blob is not duplicated per line"
    assert B.spend_between(a["read_at"], b["read_at"], p) == 0.94


def test_spend_between_returns_NONE_for_a_missing_endpoint(tmp_path):
    """Not 0.0. 'No measurement' and 'no spend' are different findings and a
    receipt that renders them identically is the bug this module exists for."""
    p = tmp_path / "bal.jsonl"
    a = B.snapshot("only_one", path=p, api_key="k", opener=_opener(_OK))
    assert B.spend_between(a["read_at"], "2099-01-01T00:00:00+00:00", p) is None


def test_a_topup_inside_the_window_is_reported_NEGATIVE_not_clamped(tmp_path):
    """Clamping a top-up to zero hides the real spend underneath it."""
    p = tmp_path / "bal.jsonl"
    a = B.snapshot("before", path=p, api_key="k", opener=_opener(_OK))
    up = {"balance_infos": [{"currency": "USD", "total_balance": "43.99"}]}
    b = B.snapshot("after_topup", path=p, api_key="k", opener=_opener(up))
    assert B.spend_between(a["read_at"], b["read_at"], p) == -20.0


def test_snapshots_of_a_missing_file_is_empty_not_an_error(tmp_path):
    assert B.snapshots(tmp_path / "nope.jsonl") == []


def test_a_torn_line_is_SKIPPED_and_the_rest_still_read(tmp_path):
    p = tmp_path / "bal.jsonl"
    B.snapshot("good", path=p, api_key="k", opener=_opener(_OK))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write('{"total_usd": 1.0, "read_a\n')
    assert len(B.snapshots(p)) == 1


def test_two_reads_in_the_same_clock_TICK_get_distinct_keys():
    """Windows advances `datetime.now()` in ~15.6 ms steps, so a loop of reads
    returns byte-identical microsecond stamps. `read_at` is the lookup key for
    `spend_between`, so a collision computes a real spend as $0.00. This is the
    regression that made the stamp monotonic rather than merely precise."""
    stamps = [B._now() for _ in range(200)]
    assert len(set(stamps)) == 200
    assert stamps == sorted(stamps)
