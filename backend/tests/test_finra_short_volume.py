"""FINRA daily short-sale volume: parsing, the next-session PIT rule, coverage, resumability.

Offline. Two fixture files in FINRA's real format (header, pipe rows, trailing
record count; the second with fractional volumes as recent files carry). No
network: every pull uses an injected `fetch`.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

# strategy_library FIRST: it imports the ext module at load; importing the ext
# first would hand the library a half-initialised module (the factory's order)
from backend.services import strategy_library as SL  # noqa: F401,I001
from backend.services import finra_short_volume as F
from backend.services import pit_features as pf

FILE_A = (b"Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
          b"20260924|AAA|400|0|1000|B,Q,N\n"
          b"20260924|BBB|100|5|1000|Q,N\n"
          b"20260924|BRK/B|10|0|20|N\n"
          b"3\n")
FILE_B = (b"Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
          b"20260925|AAA|420830.989754|0|1173148.600045|B,Q,N\n"
          b"20260925|BBB|632170.318973|2210|1208543.547838|B,Q,N\n"
          b"2\n")
XML_403 = (b'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>AccessDenied</Code>'
           b"<Message>Access Denied</Message></Error>")
HTML_200 = b"<!DOCTYPE html><html><body>Please sign in</body></html>"


# ── parsing ──────────────────────────────────────────────────────────────────

def test_parse_file_reads_the_real_format():
    a = F.parse_file(FILE_A, expect=date(2026, 9, 24))
    assert list(a.columns) == list(F.COLUMNS)
    assert len(a) == 3 and set(a["symbol"]) == {"AAA", "BBB", "BRK/B"}
    assert a.loc[a.symbol == "AAA", "short_volume"].item() == 400.0
    assert (a["date"] == pd.Timestamp("2026-09-24")).all()
    b = F.parse_file(FILE_B, expect=date(2026, 9, 25))
    assert b.loc[b.symbol == "AAA", "total_volume"].item() == pytest.approx(1173148.600045)


def test_parse_refuses_a_truncated_file_by_its_trailer():
    bad = FILE_A.replace(b"3\n", b"5\n")
    with pytest.raises(F.FinraRefused, match="trailer"):
        F.parse_file(bad)


def test_parse_refuses_the_wrong_date_and_a_foreign_header():
    with pytest.raises(F.FinraRefused, match="dated"):
        F.parse_file(FILE_A, expect=date(2026, 9, 25))
    with pytest.raises(F.FinraRefused, match="header"):
        F.parse_file(b"a|b|c\n1|2|3\n")


def test_refuses_html_even_with_status_200():
    with pytest.raises(F.FinraRefused):
        F.classify(200, "text/html; charset=utf-8", HTML_200, date(2026, 9, 24))
    # a text/plain content type does not launder an HTML body
    with pytest.raises(F.FinraRefused, match="markup"):
        F.classify(200, "text/plain", HTML_200, date(2026, 9, 24))


def test_403_access_denied_is_not_published_and_a_500_raises():
    assert F.classify(403, "application/xml", XML_403, date(2026, 9, 26)) == ("not_published", None)
    with pytest.raises(F.FinraShortVolumeError):
        F.classify(500, "text/html", b"oops", date(2026, 9, 26))


def test_url_pattern_is_the_verified_one():
    assert F.url_for(date(2026, 9, 25)) == \
        "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260925.txt"


# ── pull: idempotent, resumable, refuses HTML without losing earlier days ────

class _Fake:
    def __init__(self, files: dict, html_on: str | None = None):
        self.files, self.html_on, self.calls = files, html_on, []

    def __call__(self, url: str):
        self.calls.append(url)
        d = url[-12:-4]
        if d == self.html_on:
            return 200, "text/html", HTML_200
        if d in self.files:
            return 200, "text/plain", self.files[d]
        return 403, "application/xml", XML_403


def test_pull_is_idempotent_and_resumable(tmp_path):
    files = {"20260924": FILE_A, "20260925": FILE_B}
    fake = _Fake(files, html_on="20260925")
    kw = dict(root=tmp_path, fetch=fake, sleep=lambda s: None, today=date(2026, 10, 10))
    # 2026-09-25 answers HTML: refused; 09-24 (already staged) survives
    with pytest.raises(F.FinraRefused):
        F.pull(date(2026, 9, 23), date(2026, 9, 25), **kw)
    assert (tmp_path / "_days" / "20260924.parquet").exists()
    assert not (tmp_path / "_days" / "20260925.parquet").exists()
    # 09-23 had no file (403) and is old -> recorded, never asked again
    fake.html_on = None
    fake.calls.clear()
    rec = F.pull(date(2026, 9, 23), date(2026, 9, 25), **kw)
    assert [u[-12:-4] for u in fake.calls] == ["20260925"]
    assert rec["fetched_ok"] == 1
    man = F.consolidate(tmp_path)
    assert man["rows"] == 5 and man["dates"] == 2
    assert len(man["years"]["2026"]["sha256"]) == 64
    # a third run fetches nothing at all
    fake.calls.clear()
    rec = F.pull(date(2026, 9, 23), date(2026, 9, 25), **kw)
    assert fake.calls == [] and rec["to_fetch"] == 0
    assert not list((tmp_path / "_days").glob("*.parquet"))


def test_a_recent_403_is_retried_not_recorded(tmp_path):
    fake = _Fake({})
    F.pull(date(2026, 9, 25), date(2026, 9, 25), root=tmp_path, fetch=fake,
           sleep=lambda s: None, today=date(2026, 9, 26))
    F.pull(date(2026, 9, 25), date(2026, 9, 25), root=tmp_path, fetch=fake,
           sleep=lambda s: None, today=date(2026, 9, 26))
    assert len(fake.calls) == 2          # asked again: not published YET


def test_pull_paces_between_files(tmp_path):
    slept = []
    F.pull(date(2026, 9, 24), date(2026, 9, 25), root=tmp_path,
           fetch=_Fake({"20260924": FILE_A, "20260925": FILE_B}),
           sleep=slept.append, today=date(2026, 10, 10))
    assert slept == [F.PACE_S]


# ── the PIT rule and the coverage rule ───────────────────────────────────────

def _synthetic(n_sessions: int = 300, missing: dict | None = None) -> pd.DataFrame:
    """AAA ratio 0.4 every day except a spike of 0.9 on the LAST session."""
    sess = pd.bdate_range("2025-01-01", periods=n_sessions)
    rows = []
    for i, d in enumerate(sess):
        for sym, r in (("AAA", 0.9 if i == n_sessions - 1 else 0.4), ("CCC", 0.5)):
            if missing and d in missing.get(sym, ()):
                continue
            rows.append({"date": d, "symbol": sym, "short_volume": r * 1000.0,
                         "total_volume": 1000.0})
    return pd.DataFrame(rows), sess


def test_a_decision_on_day_d_does_not_see_day_ds_file():
    sv, sess = _synthetic()
    last = sess[-1]
    f = pf.short_volume_features(sv, [last], ["AAA"]).set_index("ticker")
    # decision ON the spike day: the spike's file is not yet public
    assert f.loc["AAA", "short_vol_asof"] == sess[-2]
    assert f.loc["AAA", "short_vol_ratio_21"] == pytest.approx(0.4)
    # the next session sees it
    g = pf.short_volume_features(sv, [last + pd.Timedelta(days=1)], ["AAA"]).set_index("ticker")
    assert g.loc["AAA", "short_vol_asof"] == last
    assert g.loc["AAA", "short_vol_ratio_21"] == pytest.approx((20 * 0.4 + 0.9) / 21)
    assert g.loc["AAA", "short_vol_ratio_chg_21"] == pytest.approx((0.9 - 0.4) / 21)
    assert g.loc["AAA", "short_vol_ratio_z"] > 0


def test_features_are_invariant_to_files_on_or_after_the_decision_date():
    sv, sess = _synthetic()
    d = sess[-40]
    full = pf.short_volume_features(sv, [d], ["AAA", "CCC"]).set_index("ticker")
    cut = pf.short_volume_features(sv[sv["date"] < d], [d], ["AAA", "CCC"]).set_index("ticker")
    cols = list(pf.SHORT_VOL_COLUMNS)
    pd.testing.assert_frame_equal(full[cols], cut[cols])


def test_fewer_than_15_of_21_sessions_is_nan():
    sv, sess = _synthetic()
    d = sess[-1] + pd.Timedelta(days=1)          # window = the last 21 sessions
    window = sess[-21:]
    for n_missing, expect_nan in ((6, False), (7, True)):
        miss = {"AAA": set(window[:n_missing])}
        s2, _ = _synthetic(missing=miss)
        f = pf.short_volume_features(s2, [d], ["AAA"]).set_index("ticker")
        assert f.loc["AAA", "short_vol_ratio_21_n"] == 21 - n_missing
        assert bool(np.isnan(f.loc["AAA", "short_vol_ratio_21"])) is expect_nan
        if expect_nan:
            assert np.isnan(f.loc["AAA", "short_vol_ratio_chg_21"])
            assert np.isnan(f.loc["AAA", "short_vol_ratio_z"])


def test_z_needs_its_baseline_and_stale_files_are_nan():
    sv, sess = _synthetic(n_sessions=100)        # < 21 + 126 sessions of r21 history
    f = pf.short_volume_features(sv, [sess[-1] + pd.Timedelta(days=1)], ["AAA"]).set_index("ticker")
    assert np.isfinite(f.loc["AAA", "short_vol_ratio_21"])
    assert np.isnan(f.loc["AAA", "short_vol_ratio_z"])
    late = pf.short_volume_features(sv, [sess[-1] + pd.Timedelta(days=30)], ["AAA"]).set_index("ticker")
    assert np.isnan(late.loc["AAA", "short_vol_ratio_21"])


def test_a_symbol_missing_from_a_file_is_an_uncovered_day_not_a_skipped_one():
    sv, sess = _synthetic()
    # CCC absent for the last 7 sessions: FINRA's calendar still counts them
    s2 = sv[~((sv["symbol"] == "CCC") & (sv["date"].isin(sess[-7:])))]
    f = pf.short_volume_features(s2, [sess[-1] + pd.Timedelta(days=1)], ["CCC"]).set_index("ticker")
    assert f.loc["CCC", "short_vol_ratio_21_n"] == 14
    assert np.isnan(f.loc["CCC", "short_vol_ratio_21"])


# ── the factory hook and the rules ───────────────────────────────────────────

def test_attach_maps_month_end_t_to_files_dated_on_or_before_t():
    from backend.services import strategy_library_ext as E
    sv, sess = _synthetic()
    t = sess[-1]                                  # the spike day is the month-end row
    panel = pd.DataFrame({"symbol": ["AAA", "CCC"], "date": [t, t], "is_month_end": [True, True],
                          "eligible": [True, True]})
    out, info = E.attach_short_volume(panel, sv=sv)
    a = out.set_index("symbol")
    # row t decides at t's close and enters at t+1's open: t's file (published
    # after t's close) is the last one it may use, and it does
    assert a.loc["AAA", "short_vol_asof"] == t
    assert a.loc["AAA", "short_vol_ratio_21"] == pytest.approx((20 * 0.4 + 0.9) / 21)
    assert "STRICTLY BEFORE" in info["pit_rule"]


def test_rules_carry_falsifiers_controls_and_were_registered_before_scoring():
    from backend.services import strategy_library as SL
    from backend.services import strategy_library_ext as E
    ids = {r.id for r in SL.RULES}
    for r in E.FINRA_STRATEGIES:
        assert r.id in ids, SL.EXTRA_REFUSED.get(r.id)
        assert r.falsifier and r.controls and r.claimed_number
        assert r.first_registered_utc == E.REGISTERED_FINRA
    main = {r.id: r for r in E.FINRA_STRATEGIES if not r.control}
    assert set(main) == {"low_short_vol_ratio", "short_vol_ratio_falling", "mom_low_short_vol"}
    for rid, r in main.items():
        assert f"{rid}_21_40" in r.controls and "matched_random_twin" in r.controls
        assert "IWM" in r.falsifier


def test_size_band_rel_ranks_inside_each_band():
    from backend.services import strategy_library as SL
    from backend.services import strategy_library_ext as E
    d = pd.Timestamp("2026-08-31")
    p = pd.DataFrame({"date": [d] * 6, "symbol": list("ABCDEF"), "eligible": [True] * 6,
                      "median_dollar_vol": [1e6, 2e6, 3e6, 5e8, 6e8, 7e8],
                      "x": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3]})
    r = E.size_band_rel(SL.col("x", -1))(p)
    # the lowest x in EACH band ranks top of its band
    assert r.iloc[0] == r.iloc[3] == 1.0
