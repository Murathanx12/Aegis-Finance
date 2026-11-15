"""CH-46 news entity tagging by embeddings: title masking, the time split, thresholds, the
point-in-time kNN vote, the end-to-end pipeline on a synthetic corpus with a fake embedder
(no model, no network), the sidecar carrying no text, and the CLI's red exits. Every
sentence below is invented; dates are derived from `now`."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from backend.services import news_entities as NE
from backend.services import news_entity_embed as NEE
from backend.services import ticker_hub as TH

NOW = datetime.now(timezone.utc).replace(microsecond=0)

ISSUERS = """symbol,primary_name,aliases,country,is_adr
ZETA,Zetawave Semis Inc.,ZETA|Zetawave Semis,US,
AAAA,Aardvark Chipworks Inc.,AAAA|Aardvark Chipworks,US,
TINY,Tinycap Widgets Inc.,TINY|Tinycap Widgets,US,
BLUF,Bluefin Mariner Corp.,BLUF|Bluefin Mariner,US,
KORA,Korallo Biotherapeutics Inc.,KORA|Korallo Biotherapeutics,US,
VOLT,Voltaris Gridworks Inc.,VOLT|Voltaris Gridworks,US,
"""

#: (symbol, display name, sector, words of its business)
COMPANIES = (
    ("ZETA", "Zetawave Semis", "Semiconductors", "wafer fab chip lithography foundry node yield"),
    ("AAAA", "Aardvark Chipworks", "Semiconductors", "chip packaging substrate foundry memory die"),
    ("TINY", "Tinycap Widgets", "Machinery", "widget factory gearbox conveyor machining lathe"),
    ("BLUF", "Bluefin Mariner", "Marine", "tanker fleet shipping port freight vessel charter"),
    ("KORA", "Korallo Biotherapeutics", "Biotechnology", "trial drug antibody patients dosing oncology"),
    ("VOLT", "Voltaris Gridworks", "Utilities", "grid transmission substation power utility megawatt"),
)


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _corpus(root: Path, days: int = 24) -> None:
    """Labelled rows (the title names the company) and unlabelled rows (it does not), over
    `days` days, two sources. Each body names its company and, once, a different one."""
    for src in ("alpaca_benzinga_news", "yfinance_ticker_news"):
        for d in range(days):
            t = NOW - timedelta(days=days - d, hours=3)
            day = t.date().isoformat()
            p = root / "news_corpus" / src / f"{day}.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as fh:
                for k, (sym, name, _sec, words) in enumerate(COMPANIES):
                    other = COMPANIES[(k + 1 + d) % len(COMPANIES)]
                    body = (f"{name} said on the call that {words} improved. {words}. "
                            f"Analysts compared it with {other[1]} briefly. {name} expects more {words.split()[0]}.")
                    for kind, title in (("lab", f"{name} reports update number {d} from {src[:5]}"),
                                        ("unl", f"Market wrap {d} part {k} from {src[:5]}")):
                        fh.write(json.dumps({
                            "source": src, "first_seen_utc": _iso(t + timedelta(minutes=k)),
                            "published_utc": _iso(t + timedelta(minutes=k - 5)),
                            "url": f"https://example.com/{src}/{kind}/{d}/{k}", "title": title,
                            "body": body, "lang": "en", "tickers": [sym] if src.startswith("alpaca") else [],
                            "entity_tags": [], "raw_id": f"{kind}{d}{k}"}) + "\n")


@pytest.fixture()
def paths(tmp_path: Path) -> dict:
    root = tmp_path / "optimus"
    (root / "official").mkdir(parents=True)
    (root / "official" / "company_tickers.json").write_text(json.dumps({"t": _iso(NOW), "map": {"1": "ZETA"}}),
                                                            encoding="utf-8")
    (root / "potential_universe").mkdir()
    with (root / "potential_universe" / f"{NOW.date().isoformat()}.jsonl").open("w", encoding="utf-8") as fh:
        for sym, _n, sec, _w in COMPANIES:
            fh.write(json.dumps({"symbol": sym, "identity": {"sector": sec}}) + "\n")
    _corpus(root)
    ip = tmp_path / "issuers.csv"
    ip.write_text(ISSUERS, encoding="utf-8")
    P = TH.default_paths(root)
    P["issuers"] = ip
    return P


def _universe(P: dict) -> dict:
    return TH.load_universe(P, NE.tables(issuers=Path(P["issuers"])))


# ─────────────────────────────────────────── small pieces

def test_mask_title_removes_the_title_and_the_headline_anchor():
    title = "Zetawave Semis Raises Its Outlook Again"
    body = f"{title}. The company said demand grew. ZETAWAVE SEMIS RAISES ITS OUTLOOK AGAIN was the headline."
    out = NEE.mask_title(body, title)
    assert "outlook again" not in out.lower()
    assert "The company said demand grew." in out
    assert NEE.mask_title("short body", "") == "short body"


def test_count_mentions_counts_like_the_body_rule():
    text = "Tinycap Widgets grew. Later tinycap widgets fell. Not tinycap widgetsx."
    n, pos = NEE.count_mentions(text, "name:tinycap widgets")
    assert n == 2 and pos == 0.0
    assert NEE.count_mentions(text, "name:bluefin mariner") == (0, 1.0)
    assert NEE.count_mentions("Apple and apple", "cased_alias:Apple")[0] == 1


def test_wilson_interval_brackets_the_point():
    lo, hi = NEE.wilson(90, 100)
    assert lo < 0.9 < hi
    assert NEE.wilson(0, 0) == [None, None]


def test_time_split_is_ordered_by_time_with_an_embargo_and_refuses_few_labels():
    rows = [{"pos": ["X"] if i % 2 == 0 else [], "ep": 1_000_000 + i * 3600} for i in range(200)]
    part, info = NEE.time_split(rows, (0.6, 0.2, 0.2), embargo_hours=2)
    lab = [i for i, r in enumerate(rows) if r["pos"]]
    tr = max(rows[i]["ep"] for i in lab if part[i] == 0)
    va = [rows[i]["ep"] for i in lab if part[i] == 1]
    te = [rows[i]["ep"] for i in lab if part[i] == 2]
    assert tr < min(va) and max(va) < min(te)               # never shuffled
    assert info["rows"]["embargoed"] > 0
    assert all(part[i] == -1 for i, r in enumerate(rows) if not r["pos"])
    with pytest.raises(NEE.EmbedTagRefused) as e:
        NEE.time_split(rows[:20])
    assert e.value.code == NEE.TOO_FEW_LABELS


def test_choose_thresholds_hits_the_target_on_validation_or_says_unreachable():
    rng = np.random.default_rng(0)
    y = np.r_[np.ones(200), np.zeros(800)].astype(int)
    s = np.r_[rng.uniform(0.5, 1.0, 200), rng.uniform(0.0, 0.7, 800)].astype(np.float32)
    th = NEE.choose_thresholds(s, y, target=0.9, reject_pos_share=0.05, min_n=30)
    assert th["status"] == "OK"
    sel = s >= th["about"]
    assert y[sel].mean() >= 0.9 and sel.sum() >= 30
    assert th["reject"] <= th["about"]
    assert (s[y == 1] < th["reject"]).mean() <= 0.05 + 1e-9
    bad = NEE.choose_thresholds(rng.uniform(size=100).astype(np.float32), np.r_[np.ones(10), np.zeros(90)].astype(int),
                                target=0.99, min_n=30)
    assert bad["status"] == "TARGET_UNREACHABLE" and bad["about"] is None
    dec = NEE.decide(np.array([0.0, 0.5, 0.99], dtype=np.float32), {"about": 0.9, "reject": 0.3})
    assert list(dec) == ["reject", "uncertain", "about"]


def test_knn_vote_uses_only_strictly_earlier_labelled_rows():
    E = np.eye(4, dtype=np.float32)
    E[3] = E[0]                                             # row 3 is a copy of row 0, later
    ep = np.array([10, 20, 30, 40])
    bank = np.array([0, 1, 3])
    votes = NEE.knn_votes(E, ep, bank, [[7], [8], [9]], k=5)
    assert votes[0] == {}                                   # nothing earlier than the first row
    assert 9 not in votes[0] and 9 not in votes[1] and 9 not in votes[2]   # row 3 is later
    assert 7 in votes[3]                                    # its earlier copy votes for it
    assert 9 not in votes[3]                                # never itself


def test_check_out_dir_refuses_a_git_checkout(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(NEE.EmbedTagRefused) as e:
        NEE.check_out_dir(repo / "work")
    assert e.value.code == NEE.OUT_INSIDE_REPO
    assert NEE.check_out_dir(tmp_path / "work").is_dir()


def test_check_inputs_refuses_a_missing_corpus(tmp_path: Path):
    with pytest.raises(NEE.EmbedTagRefused) as e:
        NEE.check_inputs(NEE.default_paths(tmp_path / "nowhere"))
    assert e.value.code == NEE.CORPUS_MISSING


def test_family_of_names_every_source_family():
    assert NEE.family_of("alpaca_benzinga_news") == "benzinga"
    assert NEE.family_of("reader:wsj") == "reader_page"
    assert NEE.family_of("google_news_rss_ja_jp") == "google_news"
    assert NEE.family_of("sec_edgar_8k_ex99_body") == "sec_ex99"
    assert NEE.family_of("something_new") == "other"


# ─────────────────────────────────────────── end to end (fake embedder)

def _run(P: dict, out: Path) -> dict:
    emb = NEE.HashEmbedder(dim=96)
    NEE.build_company_index(out, emb, Path(P["issuers"]), _universe(P))
    ext = NEE.extract_rows(P, out, NOW, 90)
    NEE.embed_rows(out, emb, chunk=50)
    return {"extract": ext, "tag": NEE.tag(out)}


def test_pipeline_end_to_end_on_a_synthetic_corpus(paths, tmp_path: Path):
    out = NEE.check_out_dir(tmp_path / "work")
    res = _run(paths, out)
    ext, t = res["extract"], res["tag"]
    assert ext["rows_written"] == ext["rows_read"] > 0
    rows = list(NEE.iter_row_file(out))
    # labels are ONLY the hub's about tier, and the text never contains the title
    for r in rows:
        assert set(r["pos"]) == {h[0] for h in r["hub"] if h[2] == "about"}
        assert r["title"].lower() not in r["text"].lower()
    lab = [r for r in rows if r["pos"]]
    unl = [r for r in rows if not r["pos"]]
    assert lab and unl
    assert all(r["title"].split(" reports")[0] in {c[1] for c in COMPANIES} for r in lab)
    # train / validation / test are disjoint and ordered in time
    d = np.load(out / NEE.PAIRS_NAME)
    part = d["part"]
    eps = np.array([r["ep"] for r in rows])
    assert eps[part == 0].max() < eps[part == 1].min() <= eps[part == 1].max() < eps[part == 2].min()
    # pairs on unlabelled rows carry no label; on labelled rows both classes occur
    y, rowix = d["y"], d["row"]
    assert set(np.unique(y[part[rowix] == -1])) <= {-1}
    assert {0, 1} <= set(np.unique(y[part[rowix] == 0]))
    assert t["thresholds"]["status"] in ("OK", "TARGET_UNREACHABLE")
    for k in ("held_out_test", "held_out_by_source", "held_out_by_month", "uncertain_middle", "themes",
              "agreement_with_rule_tiers_all_pairs", "candidate_recall_all_labelled"):
        assert k in t
    assert t["candidate_recall_all_labelled"]["share"] > 0.9
    assert t["themes"]["n_themes"] == 0 or t["themes"]["precision_claim"] == "none"
    # the sidecar carries ids, tickers and numbers -- never a title or a body
    side = (out / "news_entity_embed_sidecar.jsonl").read_text(encoding="utf-8")
    assert "Market wrap" not in side and "said on the call" not in side
    first = json.loads(side.splitlines()[0])
    assert set(first) == {"schema", "row_id", "source", "eff_utc", "ticker", "score", "decision", "rule_tier",
                          "split", "model", "classifier"}
    assert first["decision"] in NEE.DECISIONS
    # the hub's own row ids
    hub_ids = {r["id"] for r in rows}
    assert first["row_id"] in hub_ids


def test_sheets_sample_only_rows_never_trained_on(paths, tmp_path: Path):
    out = NEE.check_out_dir(tmp_path / "work")
    _run(paths, out)
    sheet = NEE.labelling_sheet(out, n=30)
    audit = NEE.audit_sheet(out, n_each=5)
    import csv
    d = np.load(out / NEE.PAIRS_NAME)
    part, rowix = d["part"], d["row"]
    with open(sheet["path"], encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            assert int(r["split"]) != 0
            assert part[rowix[int(r["pair"])]] != 0
    with open(audit["path"], encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            assert part[rowix[int(r["pair"])]] == -1           # unlabelled rows only
    assert NEE.read_self_audit(out) is None
    (out / "self_audit_labels.csv").write_text("pair,kind,label\n1,PROMOTE,1\n2,PROMOTE,0\n3,DEMOTE,1\n",
                                               encoding="utf-8")
    sa = NEE.read_self_audit(out)
    assert sa["PROMOTE"]["n"] == 2 and sa["PROMOTE"]["about_true"] == 1
    assert "builder" in sa["labeller"]


def test_cli_exit_codes(paths, tmp_path: Path, monkeypatch, capsys):
    from scripts import news_entity_embed as CLI
    monkeypatch.setattr(NE, "entities_dir", lambda: Path(paths["issuers"]).parent)
    root = Path(paths["corpus"]).parent
    assert CLI.main(["build-index", "--out", str(tmp_path / "w0"), "--data-root", str(tmp_path / "nowhere"),
                     "--fake-embedder"]) == 2
    out = tmp_path / "w1"
    rc = CLI.main(["build-index", "--out", str(out), "--data-root", str(root), "--fake-embedder"])
    assert rc == 0, capsys.readouterr()
    b = json.loads((out / CLI.BUILD_RECEIPT).read_text(encoding="utf-8"))
    assert b["live_files_before"] == b["live_files_after"]
    rc = CLI.main(["tag", "--out", str(out)])
    assert rc in (0, 2)
    if rc == 0:
        assert CLI.main(["eval", "--out", str(out)]) == 0
        r = json.loads((out / CLI.EVAL_RECEIPT).read_text(encoding="utf-8"))
        assert "about_precision_held_out" in r["headline"]
        assert r["self_audit_result"] == "NOT YET LABELLED"
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert CLI.main(["tag", "--out", str(repo / "w")]) == 2
