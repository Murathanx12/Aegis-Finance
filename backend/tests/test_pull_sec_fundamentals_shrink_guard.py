"""The facts history refuses to be rebuilt narrower than what is on disk.

2026-09-26: `pull_sec_fundamentals --universe-from-bars` without `--limit 3000`
(default 25) rewrote the 3,000-name `sec_facts_history.parquet` as a 25-name
table; the factory then scored every fundamentals rule on 25 companies. The
table is untracked, so the only protection is a refusal at the write.
"""
import pandas as pd

from scripts import pull_sec_fundamentals as P


def _hist(tickers):
    return pd.DataFrame({"ticker": list(tickers), "cik": ["1"] * len(tickers), "fact": ["revenue"] * len(tickers),
                         "filed": pd.to_datetime(["2025-01-01"] * len(tickers)), "end": None, "start": None,
                         "period_days": 90, "val": 1.0, "form": "10-Q"})


def test_refuses_a_rebuild_narrower_than_half(tmp_path):
    path = tmp_path / "sec_facts_history.parquet"
    _hist([f"T{i}" for i in range(100)]).to_parquet(path, index=False)
    msg = P.history_shrink_refusal(path, _hist(["A", "B", "C"]))
    assert msg and msg.startswith("REFUSED") and "3 tickers" in msg and "100" in msg


def test_allows_a_rebuild_of_similar_width(tmp_path):
    path = tmp_path / "sec_facts_history.parquet"
    _hist([f"T{i}" for i in range(100)]).to_parquet(path, index=False)
    assert P.history_shrink_refusal(path, _hist([f"T{i}" for i in range(90)])) is None


def test_first_write_and_explicit_allow_pass(tmp_path):
    path = tmp_path / "sec_facts_history.parquet"
    assert P.history_shrink_refusal(path, _hist(["A"])) is None
    _hist([f"T{i}" for i in range(100)]).to_parquet(path, index=False)
    assert P.history_shrink_refusal(path, _hist(["A"]), allow=True) is None


def test_unreadable_existing_history_is_a_refusal_not_a_pass(tmp_path):
    path = tmp_path / "sec_facts_history.parquet"
    path.write_bytes(b"not a parquet")
    msg = P.history_shrink_refusal(path, _hist(["A"]))
    assert msg and msg.startswith("REFUSED")
