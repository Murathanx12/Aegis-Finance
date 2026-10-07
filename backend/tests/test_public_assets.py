"""The public assets in docs/assets/ say only what the tree and the V1 Beta doc say.

`scripts/render_public_assets.py` draws the README hero (the V1 Beta pipeline, with the module
behind every stage) and the social-preview card. A picture of the code goes stale silently, so
this file pins it: the committed SVGs are byte-for-byte what the generator renders, every
module path printed exists, every function printed is defined, the quoted product sentence and
the dated V1 tally are still in the doc they cite, and neither SVG can load anything external.
Offline, stdlib only.
"""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts import render_public_assets as RPA

REPO = Path(__file__).resolve().parents[2]
SVG_NS = "{http://www.w3.org/2000/svg}"
EXPECTED_SIZE = {RPA.PIPELINE_SVG: (1200, 860), RPA.OG_SVG: (1200, 630)}


def _committed(path: Path) -> bytes:
    # A Windows checkout with core.autocrlf rewrites LF to CRLF; the bytes that matter are
    # the ones git stores, which are LF.
    return path.read_bytes().replace(b"\r\n", b"\n")


def _text_content(svg: str) -> str:
    """What a reader sees: the <tspan> runs of one <text> are one line (joined with nothing,
    as they render), and separate <text> elements are separate lines."""
    root = ET.fromstring(svg.encode("utf-8"))
    return "\n".join("".join(t.itertext()) for t in root.iter(f"{SVG_NS}text"))


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.parametrize("path", list(EXPECTED_SIZE), ids=lambda p: p.name)
def test_the_generator_reproduces_the_committed_svg_byte_for_byte(path):
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
def test_each_svg_renders_through_an_img_tag_with_nothing_external(path):
    """GitHub shows an SVG through <img>: no script runs and no second file loads, so the
    asset must not need either. Fonts are system stacks; the only image is a data: URI."""
    svg = _committed(path).decode("utf-8")
    root = ET.fromstring(svg.encode("utf-8"))
    tags = {el.tag.replace(SVG_NS, "") for el in root.iter()}
    assert not tags & {"script", "foreignObject", "iframe", "use"}, tags
    assert not re.search(r"\son[a-z]+\s*=", svg), "event-handler attribute"
    assert "@import" not in svg and "@font-face" not in svg
    for el in root.iter():
        for k, v in el.attrib.items():
            if k.endswith("href"):
                assert v.startswith(("data:image/png;base64,", "#")), (k, v[:40])
    assert not re.search(r"url\((?!#)", svg), "a url() that is not a local #fragment"


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


def test_the_diagram_has_nine_stages_in_order_and_every_one_is_drawn():
    assert [s.n for s in RPA.STAGES] == list(range(1, 10))
    assert [s.title for s in RPA.STAGES] == [
        "WORLD SENSORS", "EVIDENCE", "WORLD STATE / THEORY", "FORECASTS",
        "OPPORTUNITY / DECISION", "PAPER ACTION OR ABSTENTION", "OUTCOME",
        "REGRET / ATTRIBUTION", "LEARNING"]
    text = _text_content(RPA.render_pipeline())
    for st in RPA.STAGES:
        assert st.title in text
        for m in st.modules:
            assert m.label in text, m.label
    assert RPA.HONEST_HEAD in text and RPA.LOOP_TO_DECISION in text and RPA.LOOP_TO_THEORY in text


def test_no_string_overflows_its_box():
    assert RPA.check_budgets() == []


def test_the_quoted_sentence_and_the_dated_tally_are_still_in_the_doc_they_cite():
    doc = _squash((REPO / RPA.SOURCE_DOC).read_text(encoding="utf-8"))
    assert RPA.PRODUCT_SENTENCE in doc, "the card no longer quotes the V1 Beta doc verbatim"
    m = re.search(r"Tally: (\d+) clause met, (\d+) partially, (\d+) not yet", doc)
    assert m, "the V1 Beta doc no longer states its acceptance tally"
    assert tuple(int(g) for g in m.groups()) == RPA.V1_TALLY
    pack = _squash((REPO / "docs" / "FUNDING_EVIDENCE_PACK_2026-10-07.md").read_text(encoding="utf-8"))
    assert f"**{RPA.TAGLINE.lower()}**" in pack.lower()


def test_the_social_card_carries_name_sentence_honesty_line_and_url():
    text = _squash(_text_content(_committed(RPA.OG_SVG).decode("utf-8")))
    assert "AEGIS Finance" in text
    assert RPA.PRODUCT_SENTENCE in text
    assert RPA.HONEST_HEAD in text and RPA.HONEST_TAIL in text
    assert RPA.LIVE_URL in text


def test_the_png_export_when_present_is_exactly_1200_by_630():
    png = RPA.ASSETS / "og_preview.png"
    if not png.is_file():
        pytest.skip("og_preview.png is an optional one-off export (docs/assets/README.md)")
    head = png.read_bytes()[:26]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR"
    assert struct.unpack(">II", head[16:24]) == (1200, 630)


def test_check_mode_says_stale_instead_of_passing(tmp_path, monkeypatch, capsys):
    stale = tmp_path / "architecture_pipeline.svg"
    stale.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(RPA, "PIPELINE_SVG", stale)
    assert RPA.main(["--check"]) == 1
    assert "STALE" in capsys.readouterr().out
    assert stale.read_text(encoding="utf-8") == "<svg/>", "--check must write nothing"


def test_the_card_refuses_rather_than_drawing_a_substitute_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(RPA, "LOGO_PNG", tmp_path / "absent.png")
    with pytest.raises(SystemExit, match="REFUSED"):
        RPA.render_og()


def test_every_asset_the_readme_shows_exists():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    shown = sorted(set(re.findall(r"docs/assets/[\w./-]+\.(?:png|svg)", readme)))
    assert "docs/assets/architecture_pipeline.svg" in shown
    assert "docs/assets/logo.png" in shown
    assert [p for p in shown if not (REPO / p).is_file()] == []
