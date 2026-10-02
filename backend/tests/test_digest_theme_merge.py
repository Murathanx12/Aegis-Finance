"""The digest folds near-duplicate themes and opens with what CHANGED.

Offline and pure. The fixtures are shaped like the 2026-09-29 digests, where
"US-Iran war lifts oil, yields" and "Treasury yields spike, bond selloff" came
out as two themes in three of five runs.
"""
from __future__ import annotations

import json

from backend.services import world_digest as WD


def _th(title, kw, rows=(), cont=None, n=10, s=0.0, imps=()):
    return {"title": title, "keywords": list(kw), "rows": list(rows), "continues": cont,
            "n_news_rows": n, "tone": {"sentiment_news": s},
            "implications": [{"subject": a, "direction": b} for a, b in imps]}


IRAN = _th("US-Iran war lifts oil, yields; equities pressured",
           ["Iran war", "oil surge", "Treasury yields"], rows=range(0, 20))
YIELDS = _th("Treasury yields spike, bond selloff pressures stocks",
             ["Treasury yields", "bond selloff", "mortgage rates"], rows=range(40, 50))
NVDA = _th("Nvidia record buyback and AI infrastructure", ["Nvidia buyback", "AI chips"],
           rows=range(60, 70))
AMD = _th("AMD acquires World Labs", ["AMD", "World Labs", "AI acquisition"], rows=range(80, 85))


def test_a_shared_keyword_phrase_merges_the_iran_and_yields_themes():
    out, merges = WD.merge_near_duplicate_themes([IRAN, NVDA, YIELDS, AMD])
    assert [t["title"] for t in out] == [IRAN["title"], NVDA["title"], AMD["title"]]
    assert merges == [{"kept": IRAN["title"], "merged": YIELDS["title"], "why": "keyword_phrase"}]
    kept = out[0]
    assert set(kept["rows"]) == set(range(0, 20)) | set(range(40, 50))
    assert "bond selloff" in kept["keywords"] and len(kept["keywords"]) <= 6
    assert kept["merged_from"] == [YIELDS["title"]]
    assert "merged_from" not in IRAN                     # the input is not mutated


def test_a_single_shared_generic_word_does_not_merge_two_ai_stories():
    out, merges = WD.merge_near_duplicate_themes([NVDA, AMD])
    assert len(out) == 2 and merges == []


def test_two_themes_that_continue_the_same_previous_theme_are_one_story():
    a = _th("AI infrastructure boom fuels capex", ["AI buildout", "capex"], rows=[1, 2], cont="X")
    b = _th("Nvidia buyback lifts chips", ["Nvidia buyback", "semis"], rows=[3, 4], cont="x ")
    assert WD.themes_are_near_duplicates(a, b) == "same_continues"


def test_heavy_row_overlap_merges_even_without_shared_words():
    a = _th("Alpha story", ["one two"], rows=range(10))
    b = _th("Beta story", ["three four"], rows=range(6, 12))
    assert WD.themes_are_near_duplicates(a, b) == "row_overlap"
    c = _th("Gamma story", ["five six"], rows=range(9, 30))
    assert WD.themes_are_near_duplicates(a, c) is None


def test_what_changed_names_new_growing_fading_and_dropped():
    prev = {"stamp": "P", "themes": [
        _th("Iran standoff lifts oil", ["Iran war", "oil surge"], n=100, s=-0.1,
            imps=[("XOM", "up"), ("CCL", "down")]),
        _th("Treasury yields hit 5%", ["Treasury yields", "rate hikes"], n=60),
        _th("Boeing glitch delays MAX", ["Boeing", "737 MAX certification"], n=10)]}
    cur = {"themes": [
        _th("US-Iran war lifts oil", ["Iran war", "tankers"], n=140, s=-0.3,
            cont="Iran standoff lifts oil", imps=[("XOM", "up"), ("INTC", "down")]),
        _th("Bond selloff eases", ["Treasury yields", "bond rally"], n=20),
        _th("SpaceX reaches orbit", ["SpaceX Starship", "orbit launch"], n=15)]}
    ch = WD.what_changed(cur, prev)
    assert ch["previous"] == "P"
    assert ch["new"] == ["SpaceX reaches orbit"]
    assert ch["dropped"] == ["Boeing glitch delays MAX"]
    by = {c["title"]: c for c in ch["continuing"]}
    assert by["US-Iran war lifts oil"]["trend"] == "growing"
    assert by["US-Iran war lifts oil"]["sentiment_delta"] == -0.2
    assert by["US-Iran war lifts oil"]["new_implications"] == ["INTC down"]
    assert by["US-Iran war lifts oil"]["dropped_implications"] == ["CCL down"]
    assert by["Bond selloff eases"]["trend"] == "fading"
    lines = "\n".join(WD.render_changes(ch))
    assert lines.startswith("## What changed since the previous digest (P)")
    assert "**new**: SpaceX reaches orbit" in lines and "**dropped**: Boeing" in lines
    assert lines.index("growing") < lines.index("fading")


def test_the_first_digest_says_there_is_nothing_to_compare_with():
    ch = WD.what_changed({"themes": [IRAN]}, None)
    assert ch["previous"] is None and ch["new"] == [IRAN["title"]]
    assert "no previous digest" in "\n".join(WD.render_changes(ch))


def test_previous_digest_skips_dry_runs_and_later_stamps(tmp_path):
    od = tmp_path / "digest"
    od.mkdir()
    (od / "world_digest_20000101T000000Z.json").write_text(
        json.dumps({"stamp": "20000101T000000Z", "themes": []}), encoding="utf-8")
    (od / "world_digest_20000101T060000Z.json").write_text(
        json.dumps({"stamp": "20000101T060000Z", "themes": [], "dry_run": True}), encoding="utf-8")
    (od / "world_digest_20000101T120000Z.json").write_text(
        json.dumps({"stamp": "20000101T120000Z", "themes": []}), encoding="utf-8")
    import unittest.mock as um
    with um.patch.object(WD, "out_dir", lambda root=None: od):
        got = WD.previous_digest("20000101T120000Z")
    assert got["stamp"] == "20000101T000000Z"


def test_render_puts_the_changes_above_the_themes():
    d = {"changes": WD.what_changed({"themes": [IRAN]}, {"stamp": "P", "themes": []}),
         "theme_merges": [{"kept": "A", "merged": "B", "why": "keyword_phrase"}]}
    lines = WD.render_changes(d["changes"])
    assert lines[0].startswith("## What changed") and "**new**" in lines[2]
