"""The public assets say only what the tree and the receipts say.

`scripts/render_public_assets.py` draws the front-page hero (style C, the orbit), the live
results panel, the module-by-module diagram (style A, the blackline), the social card and the
HTML motion page, in the language the owner chose on 2026-10-07
(`docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md`). A picture of the code or of a number goes
stale silently, so this file pins it: the committed files are byte-for-byte what the generator
renders, every module path printed exists and defines what is printed beside it, every number
on the results panel is the receipt's number, the featured accounts are what the declared
selection rule picks, the motion is internally consistent, and no SVG can load anything
external or carry an image. Offline, stdlib only.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts import render_public_assets as RPA

REPO = Path(__file__).resolve().parents[2]
SVG_NS = "{http://www.w3.org/2000/svg}"
EXPECTED_SIZE = {RPA.HERO_SVG: (1200, 1000), RPA.RESULTS_SVG: (1200, 470),
                 RPA.PIPELINE_SVG: (1200, 1060), RPA.OG_SVG: (1200, 630)}
ALL_OUTPUTS = [*EXPECTED_SIZE, RPA.FRONT_HTML]


def _committed(path: Path) -> bytes:
    # A Windows checkout with core.autocrlf rewrites LF to CRLF; the bytes that matter are
    # the ones git stores, which are LF.
    return path.read_bytes().replace(b"\r\n", b"\n")


def _text_content(svg: str) -> str:
    """What a reader sees: each <text> is one line (its <tspan>/<textPath> runs joined)."""
    root = ET.fromstring(svg.encode("utf-8"))
    return "\n".join("".join(t.itertext()) for t in root.iter(f"{SVG_NS}text"))


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.parametrize("path", ALL_OUTPUTS, ids=lambda p: p.name)
def test_the_generator_reproduces_the_committed_file_byte_for_byte(path):
    fresh = RPA.outputs()[path].encode("utf-8")
    assert fresh == RPA.outputs()[path].encode("utf-8"), "two renders differ: not deterministic"
    assert path.is_file(), f"{path} is not committed; run python -m scripts.render_public_assets"
    assert _committed(path) == fresh, (
        f"{path.relative_to(REPO).as_posix()} is stale; run python -m scripts.render_public_assets")


@pytest.mark.parametrize("path", list(EXPECTED_SIZE), ids=lambda p: p.name)
def test_each_svg_is_well_formed_with_its_declared_size(path):
    root = ET.fromstring(_committed(path))
    w, h = EXPECTED_SIZE[path]
    assert root.tag == f"{SVG_NS}svg"
    assert (root.get("width"), root.get("height")) == (str(w), str(h))
    assert root.get("viewBox") == f"0 0 {w} {h}"
    assert root.find(f"{SVG_NS}title") is not None and root.find(f"{SVG_NS}desc") is not None


@pytest.mark.parametrize("path", list(EXPECTED_SIZE), ids=lambda p: p.name)
def test_each_svg_renders_through_an_img_tag_with_nothing_external_and_no_image(path):
    """GitHub shows an SVG through <img>: no script runs and no second file loads. The owner's
    rule on top: no raster anywhere (2026-10-07, "no PNGs")."""
    svg = _committed(path).decode("utf-8")
    root = ET.fromstring(svg.encode("utf-8"))
    tags = {el.tag.replace(SVG_NS, "") for el in root.iter()}
    assert not tags & {"script", "foreignObject", "iframe", "use", "image"}, tags
    assert not re.search(r"\son[a-z]+\s*=", svg), "event-handler attribute"
    assert "@import" not in svg and "@font-face" not in svg
    for el in root.iter():
        for k, v in el.attrib.items():
            if k.endswith("href"):
                assert v.startswith("#"), (k, v[:40])
    assert not re.search(r"url\((?!#)", svg), "a url() that is not a local #fragment"
    assert "prefers-reduced-motion" in svg


def test_the_html_page_is_self_contained():
    html = _committed(RPA.FRONT_HTML).decode("utf-8")
    assert html.startswith("<!doctype html>")
    assert not re.search(r"<(?:link|iframe|img)\b", html)
    assert not re.search(r"\b(?:src|href)\s*=\s*[\"']?https?:", html), "an external resource"
    assert "@import" not in html and "@font-face" not in html
    assert "prefers-reduced-motion" in html
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "two inlined SVGs share an id"


def test_every_printed_module_exists_and_defines_what_is_printed_beside_it():
    missing, undefined = [], []
    for st in RPA.STAGES:
        for m in st.modules:
            p = REPO / m.path
            if not p.is_file():
                missing.append(f"stage {st.n}: {m.path}")
                continue
            src = p.read_text(encoding="utf-8", errors="replace")
            for sym in m.symbols:
                pat = rf"^\s*(?:async\s+)?(?:def|class)\s+{sym}\b|^\s*{sym}\s*=|[\"']{sym}[\"']"
                if not re.search(pat, src, re.M):
                    undefined.append(f"stage {st.n}: {sym} in {m.path}")
    assert not missing, f"the diagram prints paths that do not exist: {missing}"
    assert not undefined, f"the diagram prints names its module does not define: {undefined}"


def test_nine_stages_in_order_and_both_pictures_draw_every_one():
    assert [s.n for s in RPA.STAGES] == list(range(1, 10))
    assert [s.title for s in RPA.STAGES] == [
        "WORLD SENSORS", "EVIDENCE", "WORLD STATE / THEORY", "FORECASTS", "DECISION",
        "PAPER ACTION", "OUTCOME", "ATTRIBUTION", "LEARNING"]
    pipe = _text_content(RPA.render_pipeline())
    hero = _text_content(RPA.render_hero())
    for st in RPA.STAGES:
        assert st.title in pipe and st.title in hero
        assert st.caption in hero
        for m in st.modules:
            assert m.label in pipe, m.label
    assert RPA.LOOP_TO_DECISION in pipe and RPA.LOOP_TO_THEORY in pipe


def test_no_string_overflows_its_box():
    assert RPA.check_budgets() == []


def test_the_quoted_sentence_and_the_tagline_are_still_in_the_docs_they_cite():
    doc = _squash((REPO / RPA.SOURCE_DOC).read_text(encoding="utf-8"))
    assert RPA.PRODUCT_SENTENCE in doc, "the card no longer quotes the V1 Beta doc verbatim"
    pack = _squash((REPO / "docs" / "FUNDING_EVIDENCE_PACK_2026-10-07.md").read_text(encoding="utf-8"))
    assert f"**{RPA.TAGLINE.lower()}**" in pack.lower()


def test_the_social_card_carries_name_sentence_and_url():
    text = _squash(_text_content(_committed(RPA.OG_SVG).decode("utf-8")))
    assert "AEGIS" in text and "FINANCE" in text
    assert RPA.PRODUCT_SENTENCE in text
    assert RPA.LIVE_URL in text


# ------------------------------------------------------------------ the numbers
def _roi() -> dict:
    return json.loads((RPA.PAPER_DIR / f"roi_{RPA.RESULTS_RUN_ID}.json").read_text(encoding="utf-8"))


def test_every_number_on_the_results_panel_is_the_receipts_number():
    d = RPA.results_data()
    rows = {r["account"]: r for r in _roi()["rows"]}
    text = _text_content(_committed(RPA.RESULTS_SVG).decode("utf-8"))
    html = _committed(RPA.FRONT_HTML).decode("utf-8")
    for f in d["featured"]:
        r = rows[f["account"]]
        assert (f["roi"], f["spy"], f["excess"]) == (r["roi_pct"], r["spy_same_window_pct"], r["vs_spy_pp"])
        for s in (RPA._num(f["excess"]), f"{RPA._num(f['roi'])}%", f"SPY {RPA._num(f['spy'])}%", f["label"]):
            assert s in text, s
            assert s in html, s
    assert f"roi_{RPA.RESULTS_RUN_ID}" in text and str(d["priced"]) in text


def test_the_featured_accounts_are_what_the_declared_rule_picks():
    """Recomputed here, independently: per named family, the live non-control account with the
    largest excess over SPY. A control (random twin, comparator, `__` twin) is never featured."""
    rows = _roi()["rows"]
    d = RPA.results_data()
    assert [f["family"] for f in d["featured"]] == [fam for fam, _ in RPA.FEATURED_FAMILIES]
    for f in d["featured"]:
        assert not any(m in f["account"] for m in RPA.CONTROL_MARKERS)
        pool = [r for r in rows if r["family"] == f["family"] and r.get("status") == "LIVE"
                and r.get("vs_spy_pp") is not None
                and not any(m in r["account"] for m in RPA.CONTROL_MARKERS)]
        assert f["excess"] == max(r["vs_spy_pp"] for r in pool)
    assert d["priced"] == sum(1 for r in rows if r.get("vs_spy_pp") is not None)


def test_the_chart_is_the_lead_account_against_its_matched_twin_on_shared_dates():
    d = RPA.results_data()
    c = d["chart"]
    assert c["twin"] == f"{d['featured'][0]['account']}_random_twin"
    assert c["dates"] == sorted(c["dates"]) and len(c["dates"]) >= 2
    assert c["acct"][-1] == d["featured"][0]["roi"]          # the last mark IS the pinned receipt


def test_one_basket_shown_twice_says_so():
    d = RPA.results_data()
    shared = [f for f in d["featured"] if f["shares_names_with"]]
    for f in shared:
        other = next(g for g in d["featured"] if g["name"] == f["shares_names_with"])
        assert f["tickers"] == other["tickers"] and f["tickers"]
        assert RPA._shared(f) in _text_content(_committed(RPA.RESULTS_SVG).decode("utf-8"))


# ------------------------------------------------------------------ the motion
def test_the_wave_reaches_each_stage_when_its_bubble_lights():
    """The dots' delays and the bubbles' delays come from one clock: just before a stage the
    wave is arriving (its arrival time), just after it the wave is leaving (arrival + dwell)."""
    for n in range(1, 10):
        leave = (RPA.arrival(n) + RPA.P - RPA.TRAVEL) % RPA.CYCLE
        # in the limit the two clocks agree exactly ...
        assert abs(RPA.wave_time(RPA.theta(n) - 1e-6) - RPA.arrival(n)) < 0.01, n
        assert abs(RPA.wave_time(RPA.theta(n) + 1e-6) - leave) < 0.01, n
        # ... and the dots nearest a bubble (half a degree away) swell within its first 0.15 s,
        # the wave easing in and out of every stage rather than hitting it at full speed
        assert 0 < RPA.arrival(n) - RPA.wave_time(RPA.theta(n) - 0.5) < 0.15, n
        assert 0 < (RPA.wave_time(RPA.theta(n) + 0.5) - leave) % RPA.CYCLE < 0.15, n
    arrivals = [RPA.arrival(n) for n in range(1, 10)]
    assert arrivals == sorted(arrivals) and arrivals[0] == RPA.TRAVEL


def test_check_mode_says_stale_instead_of_passing(tmp_path, monkeypatch, capsys):
    stale = tmp_path / "architecture_pipeline.svg"
    stale.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(RPA, "PIPELINE_SVG", stale)
    assert RPA.main(["--check"]) == 1
    assert "STALE" in capsys.readouterr().out
    assert stale.read_text(encoding="utf-8") == "<svg/>", "--check must write nothing"


def test_the_results_panel_refuses_without_its_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(RPA, "PAPER_DIR", tmp_path)
    with pytest.raises(SystemExit, match="REFUSED"):
        RPA.render_results()


def test_every_asset_the_readme_shows_exists():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    shown = sorted(set(re.findall(r"docs/assets/[\w./-]+\.(?:png|svg)", readme)))
    for must in ("docs/assets/aegis_loop.svg", "docs/assets/paper_results_live.svg",
                 "docs/assets/architecture_pipeline.svg"):
        assert must in shown
    assert [p for p in shown if not (REPO / p).is_file()] == []
