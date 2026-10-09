"""`render_public_assets --bump-pin` (2026-10-07 chunk): the public pictures refresh
themselves from the winners.

Synthetic receipts and a copied script file throughout -- never the real
`backend/data/optimus/paper_accounts/` or the real `scripts/render_public_assets.py` -- so a
test run never mutates the live pin or the live receipts. Dates derived from the receipts
themselves, never `today`.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import render_public_assets as RPA

REPO = Path(__file__).resolve().parents[2]


def _roi(account: str = "book_a", *, family: str = "llm_portfolio:personal", gen: str,
        roi_pct: float = 5.0, spy: float = 1.0, capital: float = 1_000_000.0,
        since: str = "2026-09-01") -> dict:
    return {"generated_utc": gen,
           "rows": [{"account": account, "family": family, "status": "LIVE",
                     "roi_pct": roi_pct, "spy_same_window_pct": spy, "vs_spy_pp": roi_pct - spy,
                     "start_capital": capital, "inception": since, "book_id": None}]}


def _dna(account: str = "book_a", *, sessions: int = 5, label: str = "OBSERVED(5)",
        tickers: tuple = ("AAA", "BBB")) -> dict:
    return {"books": [{"account": account, "sessions_graded": sessions,
                       "evidence": {"label": label}, "tickers": list(tickers)}]}


def _write_pair(paper_dir: Path, run_id: str, *, gen: str, **kw) -> None:
    (paper_dir / f"roi_{run_id}.json").write_text(json.dumps(_roi(gen=gen, **kw)), encoding="utf-8")
    (paper_dir / f"book_dna_{run_id}.json").write_text(json.dumps(_dna()), encoding="utf-8")


@pytest.fixture
def paper_dir(tmp_path, monkeypatch):
    d = tmp_path / "paper_accounts"
    d.mkdir()
    monkeypatch.setattr(RPA, "PAPER_DIR", d)
    monkeypatch.setattr(RPA, "REFRESH_DIR", d)
    return d


@pytest.fixture
def three_families(paper_dir):
    """One roi/book_dna pair per FEATURED_FAMILIES, all LIVE, so `results_data()` never
    refuses for a missing family while a test only cares about the pin logic."""
    def _write(run_id: str, gen: str) -> None:
        rows = []
        for i, (fam, _) in enumerate(RPA.FEATURED_FAMILIES):
            acct = f"acct_{i}"
            rows.append({"account": acct, "family": fam, "status": "LIVE", "roi_pct": 5.0 + i,
                        "spy_same_window_pct": 1.0, "vs_spy_pp": 4.0 + i,
                        "start_capital": 100_000.0, "inception": "2026-09-01", "book_id": None})
        (paper_dir / f"roi_{run_id}.json").write_text(
            json.dumps({"generated_utc": gen, "rows": rows}), encoding="utf-8")
        (paper_dir / f"book_dna_{run_id}.json").write_text(
            json.dumps({"books": [{"account": f"acct_{i}", "sessions_graded": 1,
                                   "evidence": {"label": "OBSERVED(1)"}, "tickers": []}
                                  for i in range(len(RPA.FEATURED_FAMILIES))]}), encoding="utf-8")
    return _write


@pytest.fixture
def pin_copy(tmp_path):
    p = tmp_path / "render_public_assets.py"
    shutil.copy(RPA.__file__, p)
    return p


@pytest.fixture
def readme_copy(tmp_path):
    p = tmp_path / "README.md"
    p.write_text(RPA.README.read_text(encoding="utf-8"), encoding="utf-8")
    return p


@pytest.fixture
def rendered_dirs(tmp_path, monkeypatch):
    assets, design = tmp_path / "assets", tmp_path / "design"
    monkeypatch.setattr(RPA, "ASSETS", assets)
    monkeypatch.setattr(RPA, "DESIGN", design)
    monkeypatch.setattr(RPA, "HERO_SVG", assets / "aegis_loop.svg")
    monkeypatch.setattr(RPA, "RESULTS_SVG", assets / "paper_results_live.svg")
    monkeypatch.setattr(RPA, "PIPELINE_SVG", assets / "architecture_pipeline.svg")
    monkeypatch.setattr(RPA, "OG_SVG", assets / "og_preview.svg")
    monkeypatch.setattr(RPA, "GAUNTLET_SVG", assets / "gauntlet.svg")
    monkeypatch.setattr(RPA, "FRONT_HTML", design / "aegis_front_page.html")
    return assets, design


def _set_pin(pin_copy: Path, run_id: str) -> None:
    text = pin_copy.read_text(encoding="utf-8")
    new, n = RPA.PIN_RE.subn(f'RESULTS_RUN_ID = "{run_id}"', text, count=1)
    assert n == 1
    pin_copy.write_text(new, encoding="utf-8")


# ──────────────────────────────────────────────────────── _candidate_run_ids / choose

def test_candidate_run_ids_need_both_receipts_and_a_dateable_roi(paper_dir):
    _write_pair(paper_dir, "2026-01-01T000000Z", gen="2026-01-01T00:00:00+00:00")
    # a roi with no matching book_dna is never a candidate
    (paper_dir / "roi_2026-01-02T000000Z.json").write_text(
        json.dumps(_roi(gen="2026-01-02T00:00:00+00:00")), encoding="utf-8")
    # a roi with no generated_utc is never a candidate, even with a book_dna twin
    (paper_dir / "roi_2026-01-03T000000Z.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    (paper_dir / "book_dna_2026-01-03T000000Z.json").write_text(json.dumps(_dna()), encoding="utf-8")
    assert RPA._candidate_run_ids() == ["2026-01-01T000000Z"]


def test_choose_new_run_id_picks_the_newest_by_generated_utc_not_by_name(paper_dir):
    # deliberately out-of-name-order generated_utc stamps
    _write_pair(paper_dir, "2026-01-05T000000Z", gen="2026-01-01T00:00:00+00:00")
    _write_pair(paper_dir, "2026-01-01T000000Z", gen="2026-01-09T00:00:00+00:00")
    assert RPA.choose_new_run_id() == "2026-01-01T000000Z"


def test_choose_new_run_id_orders_timezone_offsets_by_utc(paper_dir):
    _write_pair(paper_dir, "2026-01-02T023000Z", gen="2026-01-02T02:30:00+02:00")
    _write_pair(paper_dir, "2026-01-02T010000Z", gen="2026-01-02T01:00:00+00:00")
    assert RPA.choose_new_run_id() == "2026-01-02T010000Z"


def test_choose_new_run_id_refuses_with_nothing_available(paper_dir):
    with pytest.raises(SystemExit, match="REFUSED"):
        RPA.choose_new_run_id()


def test_choose_new_run_id_validates_an_explicit_id(paper_dir):
    with pytest.raises(SystemExit, match="REFUSED"):
        RPA.choose_new_run_id("2026-01-01T000000Z")
    (paper_dir / "roi_2026-01-01T000000Z.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSED"):           # roi exists, book_dna does not
        RPA.choose_new_run_id("2026-01-01T000000Z")
    (paper_dir / "book_dna_2026-01-01T000000Z.json").write_text(json.dumps(_dna()), encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSED"):           # still no generated_utc
        RPA.choose_new_run_id("2026-01-01T000000Z")


# ──────────────────────────────────────────────────────── _rewrite_pin_line

def test_rewrite_pin_line_matches_exactly_once(tmp_path):
    p = tmp_path / "one.py"
    p.write_text('x = 1\nRESULTS_RUN_ID = "2026-01-01T000000Z"\ny = 2\n', encoding="utf-8")
    old = RPA._rewrite_pin_line("2026-02-02T000000Z", path=p)
    assert old == "2026-01-01T000000Z"
    assert 'RESULTS_RUN_ID = "2026-02-02T000000Z"' in p.read_text(encoding="utf-8")


@pytest.mark.parametrize("body", ["x = 1\n",                                          # zero
                                  'RESULTS_RUN_ID = "a"\nRESULTS_RUN_ID = "b"\n'])     # two
def test_rewrite_pin_line_refuses_unless_exactly_one_match(tmp_path, body):
    p = tmp_path / "bad.py"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSED"):
        RPA._rewrite_pin_line("2026-02-02T000000Z", path=p)
    assert p.read_text(encoding="utf-8") == body, "a refused rewrite must write nothing"


def test_the_real_committed_script_has_exactly_one_pin_line():
    text = RPA.README  # noqa: F841 -- just reusing the import; see the assertion below
    src = Path(RPA.__file__).read_text(encoding="utf-8")
    assert len(RPA.PIN_RE.findall(src)) == 1


# ──────────────────────────────────────────────────────── bump_pin: refusals

def test_bump_pin_refuses_when_the_newest_pair_is_identical(paper_dir, three_families, pin_copy,
                                                             readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    rc = RPA.bump_pin("2026-01-01T000000Z", pin_path=pin_copy, readme_path=readme_copy)
    assert rc == 2
    assert RPA.RESULTS_RUN_ID == "2026-01-01T000000Z"
    assert 'RESULTS_RUN_ID = "2026-01-01T000000Z"' in pin_copy.read_text(encoding="utf-8")
    assert list(paper_dir.glob("public_assets_refresh_*.json")) == []


def test_bump_pin_refuses_when_the_newest_pair_is_older(paper_dir, three_families, pin_copy,
                                                        readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-05T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-01T00:00:00+00:00")   # older generated_utc
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    rc = RPA.bump_pin(None, pin_path=pin_copy, readme_path=readme_copy)
    assert rc == 2
    assert list(paper_dir.glob("public_assets_refresh_*.json")) == []


def test_bump_pin_refuses_on_a_budget_failure_and_writes_nothing(paper_dir, three_families, pin_copy,
                                                                 readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "check_budgets", lambda: ["stage 1 title: too long"])
    rc = RPA.bump_pin(None, pin_path=pin_copy, readme_path=readme_copy)
    assert rc == 2
    assert RPA.RESULTS_RUN_ID == "2026-01-01T000000Z"
    assert 'RESULTS_RUN_ID = "2026-01-01T000000Z"' in pin_copy.read_text(encoding="utf-8")
    assets_dir, _ = rendered_dirs
    assert not assets_dir.exists()
    assert list(paper_dir.glob("public_assets_refresh_*.json")) == []


def test_bump_pin_refuses_when_a_featured_family_has_no_live_account(paper_dir, pin_copy, readme_copy,
                                                                     rendered_dirs, monkeypatch):
    # only ONE of the three FEATURED_FAMILIES is represented
    fam = RPA.FEATURED_FAMILIES[0][0]
    rows = [{"account": "solo", "family": fam, "status": "LIVE", "roi_pct": 5.0,
            "spy_same_window_pct": 1.0, "vs_spy_pp": 4.0, "start_capital": 100_000.0,
            "inception": "2026-09-01", "book_id": None}]
    (paper_dir / "roi_2026-01-01T000000Z.json").write_text(
        json.dumps({"generated_utc": "2026-01-01T00:00:00+00:00", "rows": rows}), encoding="utf-8")
    (paper_dir / "book_dna_2026-01-01T000000Z.json").write_text(
        json.dumps({"books": [{"account": "solo", "sessions_graded": 1,
                               "evidence": {"label": "OBSERVED(1)"}, "tickers": []}]}), encoding="utf-8")
    _set_pin(pin_copy, "2025-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2025-01-01T000000Z")
    rc = RPA.bump_pin("2026-01-01T000000Z", pin_path=pin_copy, readme_path=readme_copy)
    assert rc == 2
    assert RPA.RESULTS_RUN_ID == "2025-01-01T000000Z"
    assert list(paper_dir.glob("public_assets_refresh_*.json")) == []


# ──────────────────────────────────────────────────────── bump_pin: success

def test_bump_pin_chooses_the_newest_pair_renders_and_writes_a_receipt(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-03T000000Z", "2026-01-03T00:00:00+00:00")   # the newest
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")

    rc = RPA.bump_pin(None, pin_path=pin_copy, readme_path=readme_copy)

    assert rc == 0
    assert RPA.RESULTS_RUN_ID == "2026-01-03T000000Z"
    assert 'RESULTS_RUN_ID = "2026-01-03T000000Z"' in pin_copy.read_text(encoding="utf-8")
    assets_dir, design_dir = rendered_dirs
    for name in ("aegis_loop.svg", "paper_results_live.svg", "architecture_pipeline.svg",
                "og_preview.svg", "gauntlet.svg"):
        assert (assets_dir / name).is_file()
    assert (design_dir / "aegis_front_page.html").is_file()

    receipt_p = paper_dir / "public_assets_refresh_2026-01-03T000000Z.json"
    assert receipt_p.is_file()
    receipt = json.loads(receipt_p.read_text(encoding="utf-8"))
    assert receipt["old_run_id"] == "2026-01-01T000000Z"
    assert receipt["run_id"] == "2026-01-03T000000Z"
    assert len(receipt["featured"]) == len(RPA.FEATURED_FAMILIES)
    assert {f["family"] for f in receipt["featured"]} == {fam for fam, _ in RPA.FEATURED_FAMILIES}
    # every asset's sha256 in the receipt matches the bytes on disk
    assert len(receipt["assets"]) >= 6
    for rel, sha in receipt["assets"].items():
        import hashlib
        on_disk = next(p for p in (*assets_dir.glob("*"), design_dir / "aegis_front_page.html",
                                   receipt_p, readme_copy) if p.name == Path(rel).name)
        assert hashlib.sha256(on_disk.read_bytes()).hexdigest() == sha

    # the README block was rewritten to cite the NEW run id and is self-consistent
    readme_text = readme_copy.read_text(encoding="utf-8")
    assert "2026-01-03T000000Z" in readme_text
    assert RPA.RESULTS_BLOCK_START in readme_text and RPA.RESULTS_BLOCK_END in readme_text

    # a second bump against the same data is correctly "identical"
    rc2 = RPA.bump_pin(None, pin_path=pin_copy, readme_path=readme_copy)
    assert rc2 == 2


def test_bump_pin_rewrite_mismatch_is_refused_and_restores_the_global(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch):
    """If the on-disk pin disagrees with what this process believes is pinned (e.g. another
    process rewrote it), the bump refuses rather than silently overwriting someone else's
    change, and RESULTS_RUN_ID is restored."""
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2099-01-01T000000Z")       # disagrees with the in-memory old_id below
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    rc = RPA.bump_pin("2026-01-02T000000Z", pin_path=pin_copy, readme_path=readme_copy)
    assert rc == 2
    assert RPA.RESULTS_RUN_ID == "2026-01-01T000000Z"
    assert list(paper_dir.glob("public_assets_refresh_*.json")) == []


def test_bump_pin_missing_readme_markers_leaves_every_output_untouched(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    readme_copy.write_text("# missing markers\n", encoding="utf-8")
    before = pin_copy.read_bytes()
    assert RPA.bump_pin("2026-01-02T000000Z", pin_path=pin_copy, readme_path=readme_copy) == 2
    assert pin_copy.read_bytes() == before
    assert RPA.RESULTS_RUN_ID == "2026-01-01T000000Z"
    assert readme_copy.read_text(encoding="utf-8") == "# missing markers\n"
    assert not rendered_dirs[0].exists()
    assert not list(paper_dir.glob("public_assets_refresh_*.json"))


def test_bump_pin_on_disk_mismatch_does_not_touch_outputs(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2099-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    before = pin_copy.read_bytes()
    assert RPA.bump_pin("2026-01-02T000000Z", pin_path=pin_copy, readme_path=readme_copy) == 2
    assert pin_copy.read_bytes() == before
    assert not rendered_dirs[0].exists()
    assert not list(paper_dir.glob("public_assets_refresh_*.json"))


def test_bump_pin_write_failure_restores_previous_files(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    source_before, readme_before = pin_copy.read_bytes(), readme_copy.read_bytes()
    write_bytes = Path.write_bytes
    failed = False

    def fail_once(path, data):
        nonlocal failed
        if path == RPA.RESULTS_SVG and not failed:
            failed = True
            raise OSError("simulated write failure")
        return write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_once)
    assert RPA.bump_pin("2026-01-02T000000Z", pin_path=pin_copy, readme_path=readme_copy) == 2
    assert pin_copy.read_bytes() == source_before
    assert readme_copy.read_bytes() == readme_before
    assert RPA.RESULTS_RUN_ID == "2026-01-01T000000Z"
    assert not list(rendered_dirs[0].glob("*"))
    assert not list(paper_dir.glob("public_assets_refresh_*.json"))


def test_bump_pin_persistent_failure_keeps_disk_pin_and_restores_earlier_output(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    assets, _ = rendered_dirs
    assets.mkdir()
    RPA.HERO_SVG.write_bytes(b"old hero")
    RPA.RESULTS_SVG.write_bytes(b"old results")
    write_bytes = Path.write_bytes

    def always_fail(path, data):
        if path == RPA.RESULTS_SVG:
            raise OSError("persistent lock")
        return write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", always_fail)
    assert RPA.bump_pin("2026-01-02T000000Z", pin_path=pin_copy, readme_path=readme_copy) == 2
    assert 'RESULTS_RUN_ID = "2026-01-01T000000Z"' in pin_copy.read_text(encoding="utf-8")
    assert RPA.HERO_SVG.read_bytes() == b"old hero"
    assert RPA.RESULTS_SVG.read_bytes() == b"old results"


def test_snapshot_renders_without_raw_paper_receipts(
        paper_dir, three_families, pin_copy, readme_copy, rendered_dirs, monkeypatch, tmp_path):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    three_families("2026-01-02T000000Z", "2026-01-02T00:00:00+00:00")
    _set_pin(pin_copy, "2026-01-01T000000Z")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    assert RPA.bump_pin("2026-01-02T000000Z", pin_path=pin_copy, readme_path=readme_copy) == 0
    expected = {path: value for path, value in RPA.outputs().items()}
    monkeypatch.setattr(RPA, "PAPER_DIR", tmp_path / "empty_raw_inputs")
    assert RPA.results_data()["receipt"] == "docs/assets/public_results_2026-01-02T000000Z.json"
    assert RPA.outputs() == expected


# ──────────────────────────────────────────────────────── the README block generator

def test_readme_results_block_is_what_update_readme_results_block_writes(
        paper_dir, three_families, readme_copy):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    import scripts.render_public_assets as RPA2
    old = RPA2.RESULTS_RUN_ID
    RPA2.RESULTS_RUN_ID = "2026-01-01T000000Z"
    try:
        d = RPA2.results_data()
        block = RPA2.readme_results_block(d)
        changed = RPA2.update_readme_results_block(d, path=readme_copy)
        assert changed
        assert block in readme_copy.read_text(encoding="utf-8")
        # numbers in the alt text match the receipt, same contract as the SVG's own number test
        alt = RPA2.readme_alt_text(d)
        for f in d["featured"]:
            assert f"{f['roi']:+.2f}%" in alt
            assert f"{f['excess']:+.2f} pp" in alt
    finally:
        RPA2.RESULTS_RUN_ID = old


def test_update_readme_results_block_refuses_without_markers(tmp_path, paper_dir, three_families):
    three_families("2026-01-01T000000Z", "2026-01-01T00:00:00+00:00")
    import scripts.render_public_assets as RPA2
    old = RPA2.RESULTS_RUN_ID
    RPA2.RESULTS_RUN_ID = "2026-01-01T000000Z"
    try:
        d = RPA2.results_data()
        no_markers = tmp_path / "README.md"
        no_markers.write_text("# hello\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="REFUSED"):
            RPA2.update_readme_results_block(d, path=no_markers)
        assert no_markers.read_text(encoding="utf-8") == "# hello\n"
    finally:
        RPA2.RESULTS_RUN_ID = old
