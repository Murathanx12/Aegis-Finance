"""CH-46d: the classifier's REJECT as a demotion filter. The language gate, the rule that an
`about`-tier tag is never hidden, the sidecar's round trip and refusals, and the evaluation
script end to end on the CH-46 synthetic corpus with the fake (hash) embedder -- no model, no
network. Every sentence is invented; dates are derived from `now`."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.services import news_entity_embed as NEE
from backend.services import news_tag_demotion as ND
from backend.tests.test_news_entity_embed import _run, paths  # noqa: F401  (fixture)

CJK = "半导体公司发布三季度业绩报告"


# ─────────────────────────────────────────── the language gate

def test_the_gate_routes_mostly_non_latin_text_to_uncertain_and_leaves_english_alone():
    assert ND.non_english(CJK + " Zetawave")
    assert not ND.non_english("Zetawave Semis reported results; shares rose 3%.")
    assert not ND.non_english("")                                   # no letters: not gated
    assert ND.decide_demotion(0.01, 0.1, CJK) == ND.UNCERTAIN_LANGUAGE   # low score, still not rejected
    assert ND.decide_demotion(0.01, 0.1, "An English roundup of many names.") == ND.REJECT
    assert ND.decide_demotion(0.50, 0.1, "An English article about one company.") == ND.KEEP
    assert ND.decide_demotion(None, 0.1, "anything") == ND.UNSCORED
    # the house bar, not a new one: a few CJK characters inside English text pass
    assert not ND.non_english("Tokyo Electron (東京) reported a strong quarter for its chip tools.")


# ─────────────────────────────────────────── what may be hidden

ABOUT_TITLE = {"t": "ZETA", "m": "name_match", "rule": "name:zetawave", "where": "title", "tier": "about"}
ABOUT_CIK = {"t": "AAAA", "m": "sec_cik", "rule": "cik", "where": "field", "tier": "about"}
BODY = {"t": "TINY", "m": "name_match", "rule": "name:tinycap", "where": "body", "tier": "mentions"}
DIGEST = {"t": "BLUF", "m": "digest_typed", "rule": "world_digest", "where": "field", "tier": "mentions"}
PROVIDER = {"t": "KORA", "m": "source_field", "rule": "provider", "where": "field", "tier": "mentions"}


def test_demotion_never_touches_an_about_tag_even_when_the_sidecar_names_it():
    tags = [ABOUT_TITLE, ABOUT_CIK, BODY, DIGEST, PROVIDER]
    before = json.dumps(tags, sort_keys=True)
    dem = {("r1", t["t"]): {"action": "hide"} for t in tags}       # the sidecar names EVERY tag
    kept, hidden = ND.apply_demotions("r1", tags, dem)
    assert ABOUT_TITLE in kept and ABOUT_CIK in kept                 # about never hidden
    assert PROVIDER in kept                                          # provider tags are out of scope
    assert hidden == [BODY, DIGEST]
    assert len(kept) + len(hidden) == len(tags)                      # nothing added, nothing lost
    assert json.dumps(tags, sort_keys=True) == before                # pure: input untouched
    # another row's demotions do not apply
    assert ND.apply_demotions("r2", tags, dem) == (tags, [])
    # the CH-46 list form reads the same way
    assert ND.is_demotable(["TINY", "name_match", "mentions", "body"])
    assert not ND.is_demotable(["ZETA", "name_match", "about", "title"])
    assert not ND.is_demotable(["ZETA", "name_match", "about", "body"])


# ─────────────────────────────────────────── the sidecar

def test_the_sidecar_round_trips_and_refuses_a_foreign_or_missing_file(tmp_path: Path):
    lines = [ND.sidecar_line("r1", "TINY", 0.0312, 0.116, variant="v1", classifier="c", model="m",
                             declaration_sha="d"),
             ND.sidecar_line("r2", "BLUF", 0.09, 0.116, variant="v1", classifier="c", model="m",
                             declaration_sha="d")]
    p = tmp_path / "side.jsonl"
    assert ND.write_sidecar(p, lines) == 2
    back = ND.read_sidecar(p)
    assert set(back) == {("r1", "TINY"), ("r2", "BLUF")}
    assert back[("r1", "TINY")] == lines[0]
    assert set(lines[0]) == {"schema", "row_id", "ticker", "action", "score", "threshold", "variant",
                             "classifier", "model", "declaration_sha"}     # ids and numbers, no text
    with pytest.raises(ND.DemotionRefused) as e:
        ND.read_sidecar(tmp_path / "absent.jsonl")
    assert e.value.code == ND.SIDECAR_MISSING
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"schema": NEE.SCHEMA, "row_id": "r1", "ticker": "T"}) + "\n", encoding="utf-8")
    with pytest.raises(ND.DemotionRefused) as e:
        ND.read_sidecar(bad)
    assert e.value.code == ND.SIDECAR_BAD_SCHEMA
    with pytest.raises(ND.DemotionRefused):
        ND.write_sidecar(tmp_path / "x.jsonl", [{"schema": "other"}])
    assert not (tmp_path / "x.jsonl").exists()


# ─────────────────────────────────────────── the evaluation script end to end

def _live_hub(root: Path, ch46: Path) -> None:
    """A minimal live hub generation built from the CH-46 rows' own hub tags."""
    gen = root / "ticker_hub" / "g_test"
    gen.mkdir(parents=True)
    (root / "ticker_hub" / "CURRENT.json").write_text(json.dumps({"generation": "g_test"}), encoding="utf-8")
    uni, n = {}, 0
    with open(gen / "rows_test.jsonl", "w", encoding="utf-8") as fh:
        for r in NEE.iter_row_file(ch46):
            tags = [{"t": h[0], "m": h[1], "tier": h[2], "where": h[3]} for h in r["hub"]]
            for t in tags:
                uni.setdefault(t["t"], {"dollar_volume": 1e6 + n})
                n += 1
            fh.write(json.dumps({"id": r["id"], "tags": tags}) + "\n")
    (gen / "universe.json").write_text(json.dumps(uni), encoding="utf-8")


def _long_body_rows(P: dict, days: int = 24) -> None:
    """Rows whose LONG body names two companies twice each (so the hub's body rule tags both
    as `mentions`), one of them with a non-English body for the gate. Titles name nobody."""
    from datetime import datetime, timedelta, timezone

    from backend.tests.test_news_entity_embed import COMPANIES
    now = datetime.now(timezone.utc).replace(microsecond=0)
    filler = " ".join(["The sector discussion continued with general remarks about demand."] * 10)
    for d in range(days):
        t = now - timedelta(days=days - d, hours=2)
        p = Path(P["corpus"]) / "yfinance_ticker_news" / f"{t.date().isoformat()}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for k in range(3):
                a, b = COMPANIES[(d + k) % 6], COMPANIES[(d + k + 2) % 6]
                body = (f"{a[1]} and {b[1]} were discussed. {filler} {a[1]} {a[3]}. {b[1]} was named once more.")
                if k == 2:
                    body = (CJK + " ") * 60 + f"{a[1]} {a[1]} {b[1]} {b[1]}"
                fh.write(json.dumps({
                    "source": "yfinance_ticker_news", "first_seen_utc": t.isoformat(timespec="seconds"),
                    "published_utc": t.isoformat(timespec="seconds"),
                    "url": f"https://example.com/long/{d}/{k}", "title": f"Sector notebook {d} item {k}",
                    "body": body, "lang": "en", "tickers": [], "entity_tags": [], "raw_id": f"long{d}{k}"}) + "\n")


def test_sheet_and_evaluate_end_to_end_on_the_synthetic_corpus(paths, tmp_path: Path):  # noqa: F811
    from scripts import news_tag_demotion as S
    _long_body_rows(paths)
    ch46 = NEE.check_out_dir(tmp_path / "ch46")
    _run(paths, ch46)
    work = NEE.check_out_dir(tmp_path / "work")
    res = S.cmd_sheet(work, ch46)
    assert res["population_tags"] > 0
    assert res["thresholds"]["v1"] == res["thresholds"]["v1_recomputed"]      # no re-tuning
    assert res["thresholds"]["v2"] <= res["thresholds"]["v1"]                  # the stricter variant
    pop = [json.loads(x) for x in (work / S.POP_NAME).read_text(encoding="utf-8").splitlines()]
    assert all(p["part"] != 0 for p in pop)                                    # never a training row
    gated = [p for p in pop if p["gated"]]
    assert gated and all(p["dec1"] == ND.UNCERTAIN_LANGUAGE and p["dec2"] == ND.UNCERTAIN_LANGUAGE
                         for p in gated if p["score"] is not None)              # the gate, never a reject
    assert any(not p["gated"] for p in pop)
    rows = list(NEE.iter_row_file(ch46))
    for p in pop:                                                               # only body / digest mentions
        h = {x[0]: x for x in rows[p["ri"]]["hub"]}[p["ticker"]]
        assert ND.is_demotable(h)
    # the blind sheet carries no score, decision or rule column; the key does
    with open(work / S.BLIND_NAME, encoding="utf-8", newline="") as fh:
        hdr = next(csv.reader(fh))
    assert hdr == ["lid", "ticker", "company", "source_family", "title", "excerpt"]
    with open(work / S.KEY_NAME, encoding="utf-8", newline="") as fh:
        key = list(csv.DictReader(fh))
    assert key and {"score", "dec1", "arm"} <= set(key[0])
    # evaluate refuses until every sampled pair is labelled
    decl = tmp_path / "DECL.md"
    decl.write_text("declared before reading\n", encoding="utf-8")
    root = tmp_path / "live"
    _live_hub(root, ch46)
    prof = tmp_path / "profiles.json"
    prof.write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(S.EvalRefused):
        S.cmd_evaluate(work, ch46, decl, root, prof)
    with open(work / S.LABELS_NAME, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["lid", "label", "reason"])
        for k in key:
            w.writerow([k["lid"], 0, "synthetic"])
    r = S.cmd_evaluate(work, ch46, decl, root, prof)
    assert r["declaration"]["sha256"] == S._sha_file(decl)
    assert r["variant_1"]["verdict"] in ("OBSERVED", "CANNOT_DISTINGUISH", "FAILED_VARIANT")
    assert r["variants_tried"] == 2
    # the sidecar names only population tags, and the hub's about tags are untouched
    side = ND.read_sidecar(ND.default_sidecar_path(work))
    popkeys = {(p["row_id"], p["ticker"]) for p in pop if p["dec1"] == ND.REJECT}
    assert set(side) == popkeys
    t = r["hub_effect"]["top_by_dollar_volume"]
    assert t["about_tags_changed"] == 0
    assert r["hub_effect"]["live_hub_files_before_after"][0] == r["hub_effect"]["live_hub_files_before_after"][1]
    # no text in the receipt or the sidecar
    blob = json.dumps(r) + ND.default_sidecar_path(work).read_text(encoding="utf-8")
    assert "said on the call" not in blob and "Market wrap" not in blob


def test_cli_refuses_a_work_folder_inside_a_checkout(tmp_path: Path):
    from scripts import news_tag_demotion as S
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert S.main(["sheet", "--work", str(repo / "w"), "--ch46", str(tmp_path)]) == 2
    assert S.main(["sheet", "--work", str(tmp_path / "w"), "--ch46", str(tmp_path / "none")]) == 2


def test_the_verdict_rule_reads_the_interval_against_the_bar():
    from scripts import news_tag_demotion as S
    assert S.verdict(118, 120) == "OBSERVED"                 # lower bound above 0.90
    assert S.verdict(92, 101) == "CANNOT_DISTINGUISH"
    assert S.verdict(60, 100) == "FAILED_VARIANT"            # upper bound below 0.90
    assert S.allocate({"a": 10, "b": 30, "c": 0}, 8) == {"a": 2, "b": 6, "c": 0}
