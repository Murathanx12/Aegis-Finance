"""backend.services.licensed_data -- synthetic fixtures only (no licensed rows in the repo)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend.services import licensed_data as ld

AS_OF = date(2026, 10, 13)


def _members() -> pd.DataFrame:
    return pd.DataFrame({
        "row_label": [2, 3, 4], "page": [1, 1, 2],
        "Ticker": ["AAA UW Equity", "1234 JT Equity", "BBB IS Equity"],
        "bbg_key": ["AAA UW", "1234 JT", "BBB IS"], "symbol": ["AAA", "1234", "BBB"],
        "exch_code": ["UW", "JT", "IS"], "name": ["Alpha Inc", "Beta KK", "Gamma Ltd"],
        "weight_pct": [60.0, 39.9, None], "shares_mn": [10.0, 5.0, 1.0], "price_local": [100.0, 2000.0, None],
        "country": ["US", "JP", "IN"], "aegis_market": ["US", "JP", "IN"],
        "yahoo_symbol": ["AAA", "1234.T", None], "match_method": ["symbol", "symbol", "unmatched"],
        "in_contest_universe": [True, True, False], "has_aegis_bars": [True, False, False],
    })


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write(root: Path, *, as_of: object = AS_OF.isoformat(), rows: int | None = None,
           parquet: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    df = _members()
    if parquet:
        f = root / "wls_members_x.parquet"
        df.to_parquet(f, index=False)
    else:
        f = root / "wls_members_x.csv"
        df.to_csv(f, index=False)
    man = {"datasets": {
        "wls_members": {"kind": "index_membership", "as_of": as_of,
                        "outputs": [{"table": "members", "file": f.name, "sha256": _sha(f),
                                     "rows": len(df) if rows is None else rows}]},
        "a_screenshot": {"kind": "image", "as_of": AS_OF.isoformat(), "outputs": []},
    }}
    (root / "MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")
    return f


def test_missing_folder_is_unavailable_not_an_empty_frame(tmp_path):
    r = ld.wls_members(tmp_path / "nope", today=AS_OF)
    assert r.status.status == ld.UNAVAILABLE and r.frame is None and not r.status.usable
    inv = ld.inventory(tmp_path / "nope", today=AS_OF)
    assert [s.status for s in inv] == [ld.UNAVAILABLE]


def test_ok_load_is_typed_and_dated_by_the_manifest_not_the_mtime(tmp_path):
    _write(tmp_path)
    r = ld.wls_members(tmp_path, today=date(2026, 11, 10))
    assert r.status.status == ld.OK, r.status.line()
    assert r.status.rows == 3 and r.status.age_days == 28 and r.status.as_of == "2026-10-13"
    df = r.frame
    assert df["row_label"].dtype == "int64" and df["weight_pct"].dtype == "float64"
    assert df["in_contest_universe"].dtype == bool
    assert df["weight_pct"].isna().sum() == 1            # '--' in the source stays missing, never 0
    assert list(df.yahoo_symbol.dropna()) == ["AAA", "1234.T"]


def test_parquet_is_preferred_and_loads_the_same(tmp_path):
    _write(tmp_path, parquet=True)
    r = ld.load("wls_members", "members", root=tmp_path, today=AS_OF)
    assert r.status.status == ld.OK and r.status.path.endswith(".parquet") and len(r.frame) == 3


def test_stale_compares_the_age_to_the_kind_shelf_life(tmp_path, monkeypatch):
    _write(tmp_path)
    monkeypatch.setitem(ld.config.LICENSED_DATA_MAX_AGE_DAYS, "index_membership", 10)
    r = ld.wls_members(tmp_path, today=date(2026, 10, 30))
    assert r.status.status == ld.STALE and r.status.age_days == 17 and r.status.max_age_days == 10
    assert r.frame is not None                            # usable, but labelled


def test_undateable_as_of_is_never_fresh(tmp_path):
    _write(tmp_path, as_of="sometime in October")
    r = ld.wls_members(tmp_path, today=AS_OF)
    assert r.status.status == ld.UNDATED and r.status.age_days is None


def test_a_dropped_row_is_invalid(tmp_path):
    _write(tmp_path, rows=4)                              # manifest says 4, file holds 3
    r = ld.wls_members(tmp_path, today=AS_OF)
    assert r.status.status == ld.INVALID and r.frame is None and "4" in r.status.reason


def test_edited_bytes_are_invalid(tmp_path):
    f = _write(tmp_path)
    f.write_text(f.read_text(encoding="utf-8").replace("Alpha Inc", "Alpha Corp"), encoding="utf-8")
    r = ld.wls_members(tmp_path, today=AS_OF)
    assert r.status.status == ld.INVALID and "sha256" in r.status.reason


def test_missing_required_column_is_invalid(tmp_path):
    f = _write(tmp_path)
    df = pd.read_csv(f).drop(columns=["weight_pct"])
    df.to_csv(f, index=False)
    man = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    man["datasets"]["wls_members"]["outputs"][0]["sha256"] = _sha(f)
    (tmp_path / "MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")
    r = ld.wls_members(tmp_path, today=AS_OF)
    assert r.status.status == ld.INVALID and "weight_pct" in r.status.reason


def test_listed_file_missing_is_unavailable(tmp_path):
    f = _write(tmp_path)
    f.unlink()
    r = ld.wls_members(tmp_path, today=AS_OF)
    assert r.status.status == ld.UNAVAILABLE and "missing" in r.status.reason


def test_cli_exit_code_is_red_unless_everything_loads(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ld.config, "LICENSED_DATA_DIR", tmp_path / "absent")
    assert ld.main([]) == 2
    _write(tmp_path / "ok")
    monkeypatch.setattr(ld.config, "LICENSED_DATA_DIR", tmp_path / "ok")
    # the screenshot row is NOT_CONVERTED: reported, but not a refusal
    assert ld.main([]) == 0
    out = capsys.readouterr().out
    assert "[OK] wls_members/members" in out and "[NOT_CONVERTED] a_screenshot" in out


def test_default_folder_is_outside_the_repo():
    from backend import config
    repo = Path(ld.__file__).resolve().parents[2]
    assert repo not in Path(config.LICENSED_DATA_DIR).resolve().parents


@pytest.mark.parametrize("kind_table", sorted(ld.SCHEMAS))
def test_every_schema_has_columns(kind_table):
    assert ld.SCHEMAS[kind_table]
