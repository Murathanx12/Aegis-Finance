"""A FUTURE split must not move a consensus signal at an earlier date.

2026-11-11: the split-adjusted IBES summary restates history in today's shares and
rounds to cents. A firm that splits many times LATER reads stdev 0.00 years earlier, so
"low dispersion" bought future splitters -- future winners -- and Book G (v0 and
Amendment 1), `information_classes.exp_disp` and the farm's `rev_dispersion` all
carried the leak. This file plants a future split in a synthetic panel and checks
the invariant on the fixed path (as-quoted values via `ibes_pit_consensus`), and
checks that the SAME invariant fails on the leaky construction, so the test is known
to be able to fail.

Synthetic data only; no network, no licensed file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import book_signals as BS
from backend.services import ibes_pit_consensus as PIT
from backend.services import information_classes as IC

N_FIRMS = 40
N_MONTHS = 18
SPLITTER = 0                 # firm 0 splits 256x AFTER the panel ends
FUTURE_SPLIT = 256.0


def _months():
    today = pd.Timestamp.today().normalize()
    first = (today - pd.DateOffset(years=6)).to_period("M").to_timestamp()
    return [first + pd.DateOffset(months=i) + pd.Timedelta(days=14) for i in range(N_MONTHS)]


def _unadjusted():
    """As quoted: EPS 1.0-3.0; dispersion rises with firm index, except the
    SPLITTER, which carries the HIGHEST dispersion in the panel both per unit of
    EPS (v0) and per dollar of price (Amendment 1)."""
    rows = []
    rng = np.random.default_rng(11)
    for i in range(N_FIRMS):
        mean = 3.0 if i == SPLITTER else 1.0 + 2.0 * (i / N_FIRMS)
        cv = 0.30 if i == SPLITTER else 0.02 + 0.006 * i
        for m, d in enumerate(_months()):
            me = round(mean * (1 + 0.01 * m) + float(rng.normal(0, 0.005)), 2)
            rows.append({"ticker": f"T{i:02d}", "statpers": d, "fpi": "1", "measure": "EPS",
                         "numest": 8.0, "numup": 2.0, "numdown": 1.0, "meanest": me,
                         "medest": me, "stdev": round(cv * me, 2), "fpedats": d})
    return pd.DataFrame(rows)


def _adjusted_like_the_vendor(u: pd.DataFrame) -> pd.DataFrame:
    """What `statsum_epsus` ships: today's share basis, rounded to cents."""
    a = u.copy()
    f = np.where(a["ticker"] == f"T{SPLITTER:02d}", FUTURE_SPLIT, 1.0)
    for c in ("meanest", "medest", "stdev"):
        a[c] = np.round(a[c] / f, 2)
    return a


def _link():
    return pd.DataFrame({"ticker": [f"T{i:02d}" for i in range(N_FIRMS)],
                         "permno": [1000 + i for i in range(N_FIRMS)],
                         "sdate": pd.Timestamp("1980-01-01"), "edate": pd.NaT, "score": 1})


def _adj_table():
    """IBES `adj`: the splitter's factor is 256 until the (future) split, then 1."""
    split_day = pd.Timestamp.today().normalize() - pd.DateOffset(months=6)
    return pd.DataFrame({"ticker": [f"T{SPLITTER:02d}"] * 2,
                         "spdates": [pd.Timestamp("1980-01-01"), split_day],
                         "adj": [FUTURE_SPLIT, 1.0]})


def _assert_splitter_is_not_unanimous(disp_by_permno: dict):
    """THE INVARIANT: the planted high-dispersion firm is not read as low-dispersion."""
    sp = 1000 + SPLITTER
    assert sp in disp_by_permno, "the splitter was dropped instead of scored"
    others = [v for k, v in disp_by_permno.items() if k != sp]
    assert disp_by_permno[sp] > np.median(others), (
        f"future splitter scored {disp_by_permno[sp]:.4f}, median of others "
        f"{np.median(others):.4f}: a split that has not happened yet moved the signal")


# -- the fixed path ---------------------------------------------------------

def test_as_quoted_panel_carries_the_declared_basis_and_permno():
    c = PIT.from_frames(_unadjusted(), _link(), _adj_table())
    assert set(c["share_basis"]) == {PIT.AS_QUOTED}
    assert c["permno"].nunique() == N_FIRMS
    sp = c[c["permno"] == 1000 + SPLITTER]
    assert (sp["adj_factor"] == FUTURE_SPLIT).all()
    assert (c[c["permno"] != 1000 + SPLITTER]["adj_factor"] == 1.0).all()


def test_information_classes_exp_disp_is_untouched_by_a_future_split():
    piv = IC.expectations_pivots(consensus=PIT.from_frames(_unadjusted(), _link(), _adj_table()))
    last = piv["exp_disp"].iloc[-1].dropna()
    _assert_splitter_is_not_unanimous({int(k): float(v) for k, v in last.items()})


def test_book_g_low_tercile_does_not_hold_the_future_splitter():
    c = PIT.from_frames(_unadjusted(), _link())
    month = c[c["statpers"] == c["statpers"].max()]
    for scale in ("meanest", "price"):
        f = month.assign(price=40.0)
        low = BS.forecast_dispersion(f, scale=scale, min_names=20)
        assert 1000 + SPLITTER not in low, scale
        allv = BS.forecast_dispersion(f, scale=scale, min_names=20, tercile=0.0)
        _assert_splitter_is_not_unanimous(allv)


def test_book_g_replay_loader_reads_the_unadjusted_file(tmp_path, monkeypatch):
    from backend import config
    from scripts import night_books_efg_replay as EFG

    u, lk = tmp_path / "statsumu.parquet", tmp_path / "link.parquet"
    _unadjusted().to_parquet(u)
    _link().to_parquet(lk)
    monkeypatch.setattr(config, "IBES_STATSUMU_EPSUS_PATH", u)
    monkeypatch.setattr(config, "IBES_STATSUMU_LINK_PATH", lk)
    y = pd.Timestamp(_months()[0]).year
    ib = EFG.load_ibes_dispersion(y, y + 3)
    assert set(ib["share_basis"]) == {PIT.AS_QUOTED}
    frames = EFG.by_month(ib)
    ym = max(frames)
    pool = pd.DataFrame({"permno": frames[ym]["permno"], "price": 40.0})
    held = EFG.book_g_selector(frames, scale="price")(pool, ym)
    assert held and 1000 + SPLITTER not in held
    avoided = EFG.book_g_selector(frames, side="top", scale="price")(pool, ym)
    assert avoided[0] == 1000 + SPLITTER, "the splitter is the MOST dispersed name"


def test_a_revision_across_a_split_is_on_one_share_basis():
    u = _unadjusted()
    # firm 1: true EPS flat at 2.00, a 2:1 split at month 9 halves the quoted value
    t1 = u["ticker"] == "T01"
    mo = u.loc[t1, "statpers"].rank(method="first").astype(int) - 1
    u.loc[t1, "meanest"] = np.where(mo >= 9, 1.00, 2.00)
    split_day = sorted(u.loc[t1, "statpers"])[9]
    adj = pd.concat([_adj_table(), pd.DataFrame({
        "ticker": ["T01", "T01"], "spdates": [pd.Timestamp("1980-01-01"), split_day],
        "adj": [2.0, 1.0]})], ignore_index=True)
    c = PIT.from_frames(u, _link(), adj)
    rev = PIT.rebased_revision(c)
    r1 = rev[c["permno"] == 1001].dropna()
    assert np.allclose(r1.to_numpy(), 0.0), "a split read as a -50% revision"


def test_a_revision_with_no_known_factor_refuses_rather_than_going_all_nan():
    """Review 3: a missing ibes.adj made exp_rev all-NaN SILENTLY."""
    c = PIT.from_frames(_unadjusted(), _link(), None)
    assert c["adj_factor"].isna().all()
    with pytest.raises(PIT.IbesUnadjustedUnavailable):
        PIT.rebased_revision(c)
    with pytest.raises(PIT.IbesUnadjustedUnavailable):
        IC.expectations_pivots(consensus=c)


def test_a_row_with_an_unknown_factor_is_nan_not_basis_mixed():
    c = PIT.from_frames(_unadjusted(), _link(), _adj_table())
    c.loc[c["permno"] == 1001, "adj_factor"] = np.nan
    r = PIT.rebased_revision(c)
    assert r[c["permno"] == 1001].isna().all()
    assert r[c["permno"] == 1002].notna().sum() > 0


# -- the leaky construction must FAIL the same invariant --------------------

def _leaky_consensus():
    """The old loaders: the vendor-adjusted values, mislabelled as quoted."""
    c = PIT.from_frames(_adjusted_like_the_vendor(_unadjusted()), _link(), _adj_table())
    assert (c.loc[c["permno"] == 1000 + SPLITTER, "stdev"] == 0.0).all(), \
        "fixture: the splitter's spread must round to 0.00 on today's basis"
    return c


def test_the_invariant_fails_on_the_leaky_information_classes_input():
    piv = IC.expectations_pivots(consensus=_leaky_consensus())
    last = piv["exp_disp"].iloc[-1].dropna()
    with pytest.raises(AssertionError):
        _assert_splitter_is_not_unanimous({int(k): float(v) for k, v in last.items()})


def test_the_invariant_fails_on_the_leaky_book_g_input():
    c = _leaky_consensus()
    month = c[c["statpers"] == c["statpers"].max()].assign(price=40.0)
    low = BS.forecast_dispersion(month, scale="price", min_names=20)
    assert 1000 + SPLITTER in low, "the leak puts the splitter in the held leg"
    with pytest.raises(AssertionError):
        _assert_splitter_is_not_unanimous(
            BS.forecast_dispersion(month, scale="price", min_names=20, tercile=0.0))


# -- refusals ---------------------------------------------------------------

def test_forecast_dispersion_refuses_a_frame_without_the_basis_declaration():
    month = _adjusted_like_the_vendor(_unadjusted())
    month = month.assign(permno=range(len(month)))
    with pytest.raises(ValueError, match="share_basis"):
        BS.forecast_dispersion(month)


def test_expectations_refuse_an_undeclared_frame():
    with pytest.raises(ValueError, match="share_basis"):
        IC.expectations_frame(_unadjusted().assign(permno=1))


def test_loader_refuses_when_the_unadjusted_file_is_absent(tmp_path, monkeypatch):
    from backend import config
    from scripts import night_books_efg_replay as EFG

    monkeypatch.setattr(config, "IBES_STATSUMU_EPSUS_PATH", tmp_path / "absent.parquet")
    with pytest.raises(PIT.IbesUnadjustedUnavailable):
        PIT.load_consensus()
    with pytest.raises(EFG.CharacteristicPanelUnavailable):
        EFG.load_ibes_dispersion(2000, 2001)


def test_mixed_parquet_dtypes_do_not_break_the_factor_join():
    """Parquet hands back `string[python]` tickers and us/ns timestamps; the join
    must not refuse them (it did on the first real run, 2026-11-11)."""
    u = _unadjusted().astype({"ticker": "string"})
    u["statpers"] = u["statpers"].astype("datetime64[us]")
    adj = _adj_table().astype({"ticker": "string"})
    c = PIT.from_frames(u, _link(), adj)
    assert (c.loc[c["permno"] == 1000 + SPLITTER, "adj_factor"] == FUTURE_SPLIT).all()
