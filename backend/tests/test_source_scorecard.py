"""Source scorecard: synthetic corpus + synthetic bars, dates derived from today.

No network, no browser, no LLM. Pins the point-in-time entry rule, OPEN
horizons, UNGRADEABLE-by-name, date-clustered standard errors, the source-drift
control, and the empty-corpus refusal.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import source_scorecard as SS

N_SESSIONS = 320
N_NAMES = 30


def _calendar() -> pd.DatetimeIndex:
    end = pd.Timestamp(date.today()) - pd.offsets.BDay(1)
    return pd.bdate_range(end=end, periods=N_SESSIONS)


def _bars(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cal = _calendar()
    rows = []
    syms = ["SPY"] + [f"S{i:02d}" for i in range(N_NAMES)]
    for k, s in enumerate(syms):
        r = rng.normal(0.0003, 0.015 + 0.001 * (k % 5), len(cal))
        close = 50.0 * np.exp(np.cumsum(r))
        opn = close * np.exp(rng.normal(0, 0.003, len(cal)))
        vol = np.full(len(cal), 1e5 * (1 + k))
        rows.append(pd.DataFrame({"symbol": s, "date": cal, "open": opn, "close": close,
                                  "volume": vol}))
    return pd.concat(rows, ignore_index=True)


def _et(day: pd.Timestamp, hh: int, mm: int) -> str:
    return pd.Timestamp(day.date()).replace(hour=hh, minute=mm).tz_localize(SS.NY_TZ) \
        .tz_convert("UTC").isoformat()


def _write_corpus(root: Path, claims: list[dict]) -> None:
    """One synthetic WSJ article per claim (no real text) + the claims file."""
    day = date.today().isoformat()
    (root / "_claims").mkdir(parents=True, exist_ok=True)
    with (root / "_claims" / f"{day}.jsonl").open("w", encoding="utf-8") as fh:
        for i, c in enumerate(claims):
            sha = f"sha{i:04d}"
            d = root / "wsj" / day
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{sha}.json").write_text(json.dumps({
                "sha": sha, "publisher": "wsj", "column": "wsj_heard_on_the_street",
                "url": f"https://www.wsj.com/finance/synthetic-{i}", "title": f"Synthetic {i}",
                "published_utc": c["published_utc"], "first_seen_utc": c["published_utc"],
                "text": "synthetic body"}), encoding="utf-8")
            fh.write(json.dumps({"source_id": "wsj_heard_on_the_street", "article_sha": sha,
                                 "ticker": c["ticker"], "direction": c["direction"],
                                 "magnitude_bucket": "unstated", "horizon_days_stated": 63,
                                 "published_utc": c["published_utc"],
                                 "first_seen_utc": c["published_utc"],
                                 "pit_grade": "first_seen_only"}) + "\n")
    (root / "_claims" / "_extracted.txt").write_text(
        "\n".join(f"sha{i:04d}" for i in range(len(claims))), encoding="utf-8")


@pytest.fixture(scope="module")
def panel() -> SS.PricePanel:
    return SS.PricePanel(_bars())


# ── the next-session entry rule ──────────────────────────────────────────────

def test_entry_is_the_first_session_opening_after_publication(panel):
    cal = panel.calendar
    d = cal[200]
    # after the open on a session day -> the NEXT session, never that day's close
    assert panel.entry_index(_et(d, 15, 0)) == 201
    assert panel.entry_index(_et(d, 9, 30)) == 201
    # before the open -> that same session's open
    assert panel.entry_index(_et(d, 8, 0)) == 200
    # date only -> the next session after that date
    assert panel.entry_index(str(d.date()), date_only=True) == 201
    assert panel.entry_index(str(d.date())) == 201
    # a digest's midnight-UTC stamp is a date, not a time
    assert panel.entry_index(f"{d.date()}T00:00:00+00:00") == 201
    # a weekend publication enters on the next session
    sat = d + pd.offsets.Week(weekday=5)
    assert cal[panel.entry_index(_et(sat, 12, 0))] > sat


def test_entry_price_is_the_open_and_exit_the_close(panel):
    u = {"unit_id": "u1", "source": "wsj", "column": "c", "claim_type": "directional_stance",
         "ticker": "S03", "direction": "up", "number_given": False,
         "ts": _et(panel.calendar[100], 16, 0)}
    df = SS.grade_units([u], panel)
    j = panel.col["S03"]
    r1 = df[df["h"] == 1].iloc[0]
    assert r1["entry_date"] == str(panel.calendar[101].date())
    assert r1["raw"] == pytest.approx(panel.C[101, j] / panel.O[101, j] - 1)
    r5 = df[df["h"] == 5].iloc[0]
    assert r5["raw"] == pytest.approx(panel.C[105, j] / panel.O[101, j] - 1)


# ── OPEN and UNGRADEABLE are counted, never dropped ─────────────────────────

def test_an_unelapsed_horizon_is_open(panel):
    n = len(panel.calendar)
    u = {"unit_id": "late", "source": "wsj", "column": "c", "claim_type": "directional_stance",
         "ticker": "S05", "direction": "down", "number_given": False,
         "ts": _et(panel.calendar[n - 4], 8, 0)}      # enters on session n-4
    df = SS.grade_units([u], panel).set_index("h")
    assert df.loc[1, "state"] == "GRADED"
    assert df.loc[5, "state"] == "OPEN"
    assert df.loc[21, "state"] == "OPEN"
    assert df.loc[63, "state"] == "OPEN"
    assert len(df) == len(SS.HORIZONS)
    # a publication after the last bar is OPEN at every horizon
    u2 = {**u, "unit_id": "future", "ts": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    assert set(SS.grade_units([u2], panel)["state"]) == {"OPEN"}


def test_a_ticker_with_no_bars_is_ungradeable_by_name(panel):
    u = {"unit_id": "ghost", "source": "wsj", "column": "c", "claim_type": "directional_stance",
         "ticker": "ZZZZ", "direction": "up", "number_given": False,
         "ts": _et(panel.calendar[150], 8, 0)}
    df = SS.grade_units([u], panel)
    assert set(df["state"]) == {"UNGRADEABLE_NO_BARS_FOR_TICKER"}
    counts = SS.unit_state_counts(df)["wsj|c"]
    assert counts["n_units"] == 1 and counts["n_gradeable_at_any_horizon"] == 0
    assert counts["by_horizon"]["h21"] == {"UNGRADEABLE_NO_BARS_FOR_TICKER": 1}


# ── the effective sample is date blocks ─────────────────────────────────────

def test_date_clustered_se_is_wider_than_naive_when_ten_claims_share_a_date():
    rng = np.random.default_rng(3)
    shared = 0.04 + rng.normal(0, 0.002, 10)          # one morning, one shock
    spread = rng.normal(0, 0.01, 10)                   # ten independent mornings
    x = np.concatenate([shared, spread])
    groups = np.array(["2026-01-05"] * 10 + [f"2026-02-{i + 1:02d}" for i in range(10)])
    se_c, se_n = SS.clustered_se(x, groups), SS.naive_se(x)
    assert se_c is not None and se_n is not None
    assert se_c > se_n
    # one date is not a sample: no clustered SE at all
    assert SS.clustered_se(shared, np.array(["d"] * 10)) is None


def test_cell_counts_dates_not_claims_and_says_too_few():
    today = date.today()
    rows = []
    for i in range(12):
        rows.append({"unit_id": f"u{i}", "source": "wsj", "column": "c", "claim_type": "s",
                     "ticker": f"T{i}", "direction": "up", "pub_date": (today - timedelta(days=30)).isoformat(),
                     "h": 5, "state": "GRADED", "raw": 0.01, "ex_spy": 0.01, "ex_ctrl": 0.01,
                     "signed_spy": 0.01, "signed_ctrl": 0.01, "hit": 1.0})
    st = SS.cell_stats(pd.DataFrame(rows), 5)
    assert st["n_graded"] == 12 and st["n_pub_dates"] == 1
    assert st["verdict"] == "TOO_FEW"
    assert st["n_dates_needed_for_target_mde"] >= SS.MIN_DATE_BLOCKS


def test_a_common_drift_is_not_directional_skill():
    """Every name the source writes about falls vs its cell; its "down" calls
    then beat the control -- and so would any call on those names."""
    rng = np.random.default_rng(11)
    base = date.today() - timedelta(days=400)
    rows = []
    for i in range(60):
        d = (base + timedelta(days=5 * i)).isoformat()
        for k, dirn in enumerate(("up", "down")):
            ex = -0.03 + rng.normal(0, 0.01)
            sg = 1.0 if dirn == "up" else -1.0
            rows.append({"unit_id": f"{i}{dirn}", "source": "s", "column": "c", "claim_type": dirn,
                         "ticker": f"T{i}{k}", "direction": dirn, "pub_date": d, "h": 21,
                         "state": "GRADED", "raw": ex, "ex_spy": ex, "ex_ctrl": ex,
                         "signed_spy": sg * ex, "signed_ctrl": sg * ex, "hit": float(sg * ex > 0),
                         "control_level": "cell"})
    df = SS.add_source_drift(pd.DataFrame(rows))
    down = SS.cell_stats(df[df["claim_type"] == "down"], 21)
    assert down["t_ctrl"] > SS.T_CRIT
    assert down["verdict"] == "BETA_EXPLAINS"
    w = SS.proposed_weights([{**down, "source": "s", "column": "c", "claim_type": "down", "h": 21}])
    assert set(w.values()) == {0.0}


# ── refusals and the receipt ─────────────────────────────────────────────────

def test_an_empty_corpus_refuses_by_name(tmp_path):
    with pytest.raises(SS.ScorecardRefused, match="EMPTY_CORPUS"):
        SS.load_corpus(tmp_path / "nothing_here")
    with pytest.raises(SS.ScorecardRefused, match="EMPTY_CORPUS"):
        SS.run(corpus_root=tmp_path, bars=_bars(), include_yf=False, out_dir=tmp_path / "o")


def test_run_writes_a_receipt_with_a_run_id_and_counts_new_rows(tmp_path):
    cal = _calendar()
    claims = [{"ticker": f"S{i % N_NAMES:02d}", "direction": "up" if i % 2 else "down",
               "published_utc": _et(cal[150 + 3 * i], 16, 0)} for i in range(14)]
    claims.append({"ticker": "NOPE", "direction": "up", "published_utc": _et(cal[200], 8, 0)})
    root = tmp_path / "corpus"
    _write_corpus(root, claims)
    out = tmp_path / "out"
    t0 = datetime.now(timezone.utc)
    rc = SS.run(corpus_root=root, bars=_bars(), include_yf=False, out_dir=out, now=t0)
    p = Path(rc["_path"])
    assert p.exists() and rc["run_id"] in p.name
    assert rc["new_rows_since_last_run"]["dowjones_units"] == 15
    assert rc["llm_calls"] == 0
    wsj = rc["units"]["wsj|wsj_heard_on_the_street"]
    assert wsj["n_units"] == 15
    assert wsj["by_horizon"]["h1"].get("UNGRADEABLE_NO_BARS_FOR_TICKER") == 1
    # every non-ALPHA cell proposes weight zero
    for c in rc["cells"]:
        k = f"{c['source']}|{c['column']}|{c['claim_type']}|h{c['h']}"
        if c["verdict"] != "ALPHA_DETECTED":
            assert rc["proposed_source_weights"][k] == 0.0
    assert all(c["verdict"] in ("ALPHA_DETECTED", "CANNOT_DISTINGUISH", "BETA_EXPLAINS", "TOO_FEW")
               for c in rc["cells"])
    # no article text on the receipt
    assert "synthetic body" not in p.read_text(encoding="utf-8")
    rc2 = SS.run(corpus_root=root, bars=_bars(), include_yf=False, out_dir=out,
                 now=t0 + timedelta(seconds=2))
    assert rc2["new_rows_since_last_run"]["dowjones_units"] == 0
    assert rc2["previous_run_id"] == rc["run_id"]
