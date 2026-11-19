"""CH-66: the investigator's filing-text tool and the full-exhibit store.

Offline, synthetic, under tmp_path. Dates derive from `now`; nothing here reads
the live store or opens a socket (the fetch is a fake callable).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import investigator_filing_text as FT
from backend.services import investigator_tools as IT
from backend.services import sec_exhibit_full as SX

NOW = datetime.now(timezone.utc).replace(microsecond=0)
CUT = C.SEC_EXHIBIT_COLLECTOR_CUT_CHARS
CONFIGURATION = C.INVESTIGATOR_FILING_TEXT_CONFIGURATIONS[0]
BASE = "https://www.sec.gov/Archives/edgar/data/"


def _full_text(tag: str) -> str:
    head = (f"EX-99.1 {tag} Reports Quarter Results. " + "Revenue rose. " * 400)[:CUT]
    return head + " Business Outlook For the next quarter the Company expects revenue " \
                  "of $100 million to $110 million. " + "Tail. " * 50


def _row(acc: str, *, cik: int = 111, tickers=(), filed: datetime | None = None,
         body: str | None = None, published="auto", name: str = "ex99-1.htm") -> dict:
    filed = filed or (NOW - timedelta(days=2))
    return {
        "source": "sec_edgar_8k_ex99_body",
        "first_seen_utc": (filed + timedelta(hours=1)).isoformat(),
        "published_utc": filed.isoformat() if published == "auto" else published,
        "url": f"{BASE}{cik}/{acc.replace('-', '')}/{name}",
        "title": "8-K - Example Corp (Filer) - EX-99.1",
        "body": _full_text(acc)[:CUT] if body is None else body,
        "tickers": list(tickers),
        "entity_tags": ["8-K:2.02", f"cik:{cik:010d}", "exhibit:EX-99.1", f"accession:{acc}"],
        "raw_id": f"{acc}:{name}", "pit_grade": "native_stamp",
    }


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    dr = tmp_path / "optimus"
    corpus = dr / C.SEC_EXHIBIT_BODY_DIRNAME
    corpus.mkdir(parents=True)
    cm = dr / C.SEC_EXHIBIT_CIK_MAP_RELPATH
    cm.parent.mkdir(parents=True)
    cm.write_text(json.dumps({"0": {"cik_str": 111, "ticker": "AAA", "title": "A"},
                              "1": {"cik_str": 222, "ticker": "BBB", "title": "B"}}),
                  encoding="utf-8")
    rows = [
        _row("0001-26-000001"),                                   # AAA via CIK, cut
        _row("0001-26-000002", filed=NOW - timedelta(days=1), body="Short release."),
        _row("0001-26-000003", filed=NOW + timedelta(hours=3)),   # after as-of
        _row("0001-26-000004", published=""),                     # no timestamp
        _row("0001-26-000005", published="2026-01-01T00:00:00"),  # naive: unusable
        _row("0002-26-000001", cik=222, tickers=["BBB"], filed=NOW - timedelta(days=3)),
        _row("0003-26-000001", cik=333, filed=NOW - timedelta(days=4)),  # no ticker anywhere
    ]
    day = (NOW - timedelta(days=1)).date().isoformat()
    (corpus / f"{day}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return dr


def _paths(root: Path, tmp_path: Path) -> dict:
    p = SX.default_paths(root)
    p["funnel"] = tmp_path / "funnel.json"
    return p


def _fake_get(calls: list, fail: dict | None = None):
    def get(url: str) -> bytes:
        calls.append(url)
        if fail and len(calls) in fail:
            raise RuntimeError(f"HTTP {fail[len(calls)]} {url}")
        acc = url.split("/")[-2]
        acc = f"{acc[:4]}-{acc[4:6]}-{acc[6:]}"
        return _full_text(acc).encode("utf-8")
    return get


def _run(root, tmp_path, **kw):
    calls = kw.pop("calls", [])
    kw.setdefault("all_tickers", True)
    return SX.run(_paths(root, tmp_path), http_get=_fake_get(calls, kw.pop("fail", None)),
                  to_text=lambda b: b.decode("utf-8"), now=NOW, sleep=lambda s: None,
                  clock=lambda: NOW, **kw), calls


# ------------------------------------------------------------ frozen surface

def test_frozen_tool_module_bytes_tools_and_arm_lists_are_unchanged():
    raw = Path(IT.__file__).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest()[:16] == "d0d8acab2a4e7b0c", (
        "investigator_tools.py changed: its bytes are pinned by the IIF-1 launch manifest")
    assert list(IT.TOOLS) == ["search_news", "read_filings", "query_revisions",
                              "query_options", "query_earnings", "query_prices"]
    assert FT.TOOL_NAME not in IT.TOOLS
    base = list(IT.TOOLS)
    assert IT.tools_for_arm("A_snapshot") == []
    for arm in ("B_tools", "C_tools_only", "B_anon", "D_all"):
        assert IT.tools_for_arm(arm) == base
    assert IT.TOOLS["read_filings"].description == (
        "Recent SEC filings (8-K item codes and classification) for a ticker.")
    assert json.dumps(IT.openai_tool_schemas(["read_filings"]), sort_keys=True) == json.dumps(
        [{"type": "function", "function": {
            "name": "read_filings",
            "description": "Recent SEC filings (8-K item codes and classification) for a ticker.",
            "parameters": {"type": "object", "required": ["ticker"], "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "minimum": 1, "maximum": 90}}}}}], sort_keys=True)


def test_flag_defaults_off_and_frozen_arms_never_get_the_text_tool(monkeypatch):
    assert C.INVESTIGATOR_FILING_TEXT_ENABLED is False
    assert FT.tools_for_configuration(CONFIGURATION) == IT.tools_for_arm("B_tools")
    monkeypatch.setattr(C, "INVESTIGATOR_FILING_TEXT_ENABLED", True)
    assert FT.tools_for_configuration(CONFIGURATION)[-1] == FT.TOOL_NAME
    assert [s["function"]["name"] for s in FT.tool_schemas(CONFIGURATION)][-1] == FT.TOOL_NAME
    for arm in ("A_snapshot", "B_tools", "C_tools_only", "B_anon", "D_all"):
        assert FT.tools_for_configuration(arm) == IT.tools_for_arm(arm)
        assert not FT.filing_text_enabled(arm)
        # even if somebody lists a frozen arm as a text configuration
        monkeypatch.setattr(C, "INVESTIGATOR_FILING_TEXT_CONFIGURATIONS", (CONFIGURATION, arm))
        assert FT.TOOL_NAME not in FT.tools_for_configuration(arm)
    with pytest.raises(KeyError):
        FT.tools_for_configuration("investigator:typo")


def test_tool_refuses_in_words_when_not_offered(root):
    res = FT.run_filing_text_tool({"ticker": "AAA"}, configuration=CONFIGURATION, root=root)
    assert res.status == IT.STATUS_UNAVAILABLE and "not offered" in res.reason
    assert "LOOKUP FAILED" in FT.as_model_text(res)


# ------------------------------------------------------------ the read

def test_point_in_time_exclusion_and_counts(root):
    out = FT.read_filings_text("aaa", as_of_utc=NOW, root=root)
    accs = [r["accession"] for r in out["rows"]]
    assert accs == ["0001-26-000002", "0001-26-000001"]            # newest first
    assert out["counts"]["excluded_no_timestamp"] == 2             # blank and naive
    assert out["_audit"]["excluded_after_as_of"] == 1
    assert all(r["filed_utc"] <= out["as_of_utc"] for r in out["rows"])
    # moving the clock forward admits the later filing; nothing else changes
    later = FT.read_filings_text("AAA", as_of_utc=NOW + timedelta(hours=4), root=root)
    assert [r["accession"] for r in later["rows"]][0] == "0001-26-000003"
    # before everything: nothing datable is admissible, but undated rows are still reported
    early = FT.read_filings_text("AAA", as_of_utc=NOW - timedelta(days=10), root=root)
    assert early["rows"] == [] and early["counts"]["excluded_no_timestamp"] == 2
    with pytest.raises(ValueError):
        FT.read_filings_text("AAA", as_of_utc=datetime(2020, 1, 1), root=root)


def test_old_fields_kept_and_truncation_flag(root):
    out = FT.read_filings_text("AAA", as_of_utc=NOW, root=root)
    short, cut = out["rows"]
    for r in out["rows"]:
        assert {"form", "filed", "items", "classification"} <= set(r)
        assert r["form"] == "8-K" and r["items"] == ["2.02"]
        assert r["source_url"].startswith(BASE) and r["filed_utc"]
        assert len(r["text_excerpt"]) <= C.INVESTIGATOR_FILING_TEXT_EXCERPT_CHARS
    assert cut["truncated_at_source"] is True and cut["text_chars"] == CUT
    assert cut["text_source"] == "collector_body" and cut["outlook_excerpt"] is None
    assert short["truncated_at_source"] is False and short["text_excerpt"] == "Short release."
    assert str(CUT) in out["warning"] and "may be missing" in out["warning"]


def test_empty_unavailable_and_ok_stay_distinct(root, tmp_path, monkeypatch):
    monkeypatch.setattr(C, "INVESTIGATOR_FILING_TEXT_ENABLED", True)
    budget = IT.ToolBudget()
    kw = {"configuration": CONFIGURATION, "as_of_utc": NOW}
    assert FT.run_filing_text_tool({"ticker": "ZZZ"}, budget, root=root, **kw).status == IT.STATUS_EMPTY
    missing = FT.run_filing_text_tool({"ticker": "AAA"}, budget, root=tmp_path / "nowhere", **kw)
    assert missing.status == IT.STATUS_UNAVAILABLE and SX.CORPUS_MISSING in missing.reason
    bad = FT.run_filing_text_tool({"ticker": "AAA", "as_of_utc": "2099"}, budget, root=root, **kw)
    assert bad.status == IT.STATUS_UNAVAILABLE and "bad arguments" in bad.reason
    ok = FT.run_filing_text_tool({"ticker": "AAA"}, budget, root=root, **kw)
    assert ok.status == IT.STATUS_OK and "no usable timestamp" in ok.caveat
    text = FT.as_model_text(ok)
    assert "truncated_at_source" in text and "_audit" not in text
    assert "excluded_after_as_of" not in text
    assert len(budget.log) == 4 and budget.used == 4      # as in the frozen layer, every call is charged
    assert "as_of_utc" not in FT.PARAMETERS["properties"]


def test_model_text_drops_whole_rows_and_says_so(root, monkeypatch):
    monkeypatch.setattr(C, "INVESTIGATOR_FILING_TEXT_MODEL_CHARS", 2600)
    payload = FT.read_filings_text("AAA", as_of_utc=NOW, root=root)
    text = FT.as_model_text(IT.ToolResult(FT.TOOL_NAME, IT.STATUS_OK, payload=payload))
    body = json.loads(text.split("] ", 1)[1])
    assert body["rows_dropped_for_length"] == 1 and len(body["rows"]) == 1


# ------------------------------------------------------------ the full store

def test_cut_constant_matches_the_collector():
    import ast
    src = (Path(__file__).resolve().parents[2] / "scripts" / "news_pull.py").read_text("utf-8")
    vals = [n.value.value for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MAX_BODY"]
    assert vals == [CUT]


def test_fetch_writes_rows_then_read_prefers_full_text(root, tmp_path):
    receipt, calls = _run(root, tmp_path)
    # owed = cut bodies with a usable timestamp: AAA x2 (one is future-dated but public
    # by its own stamp is NOT assumed: it is filed "after now" only in the fixture), BBB, 333
    assert receipt["status"] == SX.OK and receipt["exit_code"] == 0
    assert receipt["counts"]["no_timestamp"] == 2 and receipt["fetched"] == len(calls) == 4
    assert Path(receipt["receipt_path"]).name == f"sec_exhibit_full_{receipt['run_id']}.json"
    stored = SX.read_full_store(SX.default_paths(root)["store"])
    row = stored["0001-26-000001:ex99-1.htm"]
    assert row["ticker"] == "AAA" and row["n_chars"] > CUT and row["prefix_matches_stored"] is True
    assert row["sha256"] == hashlib.sha256(_full_text("0001-26-000001").encode()).hexdigest()
    assert stored["0003-26-000001:ex99-1.htm"]["ticker"] is None
    month_files = sorted(p.name for p in SX.default_paths(root)["store"].glob("*.jsonl"))
    assert all(len(n) == len("2026-01.jsonl") for n in month_files)

    out = FT.read_filings_text("AAA", as_of_utc=NOW, root=root)
    full = [r for r in out["rows"] if r["accession"] == "0001-26-000001"][0]
    assert full["text_source"] == "full_exhibit" and full["truncated_at_source"] is False
    assert full["text_chars"] > CUT and full["outlook_offset"] >= CUT
    assert "$100 million to $110 million" in full["outlook_excerpt"]
    assert "warning" not in out


def test_resumable_and_nothing_owed_is_zero(root, tmp_path):
    first, calls = _run(root, tmp_path, max_docs=1)
    assert first["fetched"] == 1 and first["remaining_owed"] == 3
    assert "0001-26-000003" in calls[0].replace("000126", "0001-26-")  # newest filing first
    second, calls2 = _run(root, tmp_path)
    assert second["fetched"] == 3 and second["counts"]["already_fetched"] == 1
    assert not set(calls) & set(calls2)
    third, calls3 = _run(root, tmp_path)
    assert third["status"] == SX.NOTHING_OWED and third["exit_code"] == 0 and calls3 == []
    assert len({first["run_id"], second["run_id"], third["run_id"]}) >= 1
    assert len(list((SX.default_paths(root)["store"] / "receipts").glob("*.json"))) >= 1


@pytest.mark.parametrize("status", [403, 429])
def test_blocked_source_stops_at_first_refusal_non_zero(root, tmp_path, status):
    receipt, calls = _run(root, tmp_path, fail={2: status})
    assert receipt["status"] == SX.REFUSED and receipt["code"] == SX.SOURCE_BLOCKED
    assert receipt["exit_code"] == 2 and len(calls) == 2            # stopped, no retry
    assert receipt["fetched"] == 1                                   # the row before it is kept
    assert receipt["failures"][0]["http_status"] == status


def test_other_failures_are_non_zero_never_an_empty_success(root, tmp_path):
    receipt, calls = _run(root, tmp_path, fail={1: 404, 2: 500, 3: 404, 4: 500})
    assert receipt["status"] == SX.FAILED and receipt["exit_code"] == 3 and len(calls) == 4
    partial, _ = _run(root, tmp_path, fail={1: 404})
    assert partial["status"] == SX.PARTIAL and partial["exit_code"] == 3 and partial["fetched"] == 3


def test_default_scope_is_funnel_plus_open_event_nodes(root, tmp_path):
    refused, calls = _run(root, tmp_path, all_tickers=False)
    assert (refused["status"], refused["code"], refused["exit_code"]) == (
        SX.REFUSED, SX.SCOPE_MISSING, 2) and calls == []
    (tmp_path / "funnel.json").write_text(json.dumps({
        "generated_at": (NOW - timedelta(days=3)).isoformat(),
        "candidates": [{"ticker": "BBB"}]}), encoding="utf-8")
    nodes = root / C.EVENT_NODES_DIRNAME
    nodes.mkdir()
    (nodes / "event_nodes.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"row_kind": "node", "event_id": "e1", "primary_ticker": "AAA",
         "last_seen_utc": (NOW - timedelta(days=C.SEC_EXHIBIT_FULL_OPEN_NODE_DAYS + 2)).isoformat()},
        {"row_kind": "node", "event_id": "e2", "primary_ticker": "CCC",
         "last_seen_utc": (NOW - timedelta(hours=5)).isoformat()},
    ]) + "\n", encoding="utf-8")
    receipt, calls = _run(root, tmp_path, all_tickers=False)
    assert receipt["scope"]["sources"]["funnel"]["age_days"] == 3.0
    assert receipt["scope"]["sources"]["event_nodes"]["n"] == 1     # AAA's node is stale
    assert receipt["fetched"] == 1 and "/222/" in calls[0]
    assert receipt["counts"]["out_of_scope"] == 3


def test_missing_corpus_is_a_named_refusal(tmp_path):
    with pytest.raises(SX.SecExhibitFullRefused) as e:
        SX.check_inputs(SX.default_paths(tmp_path / "nowhere"))
    assert e.value.code == SX.CORPUS_MISSING
    receipt = SX.run(SX.default_paths(tmp_path / "nowhere"), http_get=lambda u: b"",
                     to_text=lambda b: "", now=NOW, out_dir=tmp_path / "out")
    assert receipt["exit_code"] == 2 and receipt["code"] == SX.CORPUS_MISSING


def test_urls_outside_edgar_archives_are_never_fetched(root, tmp_path):
    corpus = root / C.SEC_EXHIBIT_BODY_DIRNAME
    bad = _row("0009-26-000001")
    bad["url"] = "https://example.invalid/ex99.htm"
    with next(corpus.glob("*.jsonl")).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(bad) + "\n")
    receipt, calls = _run(root, tmp_path)
    assert receipt["counts"]["no_url"] == 1 and all(u.startswith(BASE) for u in calls)
