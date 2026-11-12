"""A mention is not a pick (CH-12 / CH-35): page type decides whether a named
ticker may become a directional `source:*` forecast.

Offline, synthetic pages and claims under tmp_path; no live data, no LLM, no
calendar-moment literals (every stamp is derived from now).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import dowjones_claims as DC


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    return tmp_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _claim(t: str, d: str = "up", para: str = "", quote: str = "") -> dict:
    return {"ticker": t, "direction": d, "horizon_days_stated": 63,
            "magnitude_bucket": "unstated", "quote": quote or f"{t} quote",
            "paraphrase": para or f"The author expects {t} to keep rising."}


def _write(ledger: Path, art: dict, claims: list[dict]) -> dict:
    return DC.write_forecasts(art, claims, ledger_path=ledger / "p.jsonl",
                              claims_path=ledger / "c.jsonl", local_path=ledger / "local.jsonl")


def _rows(ledger: Path) -> list[dict]:
    p = ledger / "p.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


MENTION_PAGES = [
    ("https://www.barrons.com/articles/stock-movers-8b39c82b?mod=x",
     "Nvidia, Micron, and More Stocks That Explain Today's Market - Barron's"),
    ("https://www.barrons.com/articles/stock-market-things-to-know-today-tesla-fed-1ca91096",
     "Even Tesla's Flying Car Can't Lift the Tech Stock Gloom"),
    ("https://www.wsj.com/finance/stocks/stocks-to-watch-today-abc12345", "Stocks to Watch"),
    ("https://www.barrons.com/articles/a-1234", "These Stocks Are Today's Movers: Nvidia, AMD"),
]


@pytest.mark.parametrize("url,title", MENTION_PAGES)
def test_a_mention_page_emits_no_directional_forecast(ledger, url, title):
    # labelled barrons_stock_picks the way the nav bar labelled it on the live pages
    art = {"url": url, "title": title, "first_seen_utc": _now(), "sha": "s1",
           "column": "barrons_stock_picks"}
    assert C.DOWJONES_MENTION_NO_FORECAST is True          # the default
    r = _write(ledger, art, [_claim("NVDA"), _claim("AVGO")])
    assert r["status"] == "MENTION_NO_FORECAST" and r["n_rows_written"] == 0
    assert r["page_class"] == "MENTION"
    assert _rows(ledger) == [] and not (ledger / "c.jsonl").exists()
    local = [json.loads(x) for x in (ledger / "local.jsonl").read_text("utf-8").splitlines()]
    assert len(local) == 2 and all(x["page_class"] == "MENTION" and x["forecast_written"] is False
                                   for x in local)


def test_a_pick_page_emits_as_before(ledger):
    art = {"url": "https://www.barrons.com/articles/buy-citigroup-stock-3da35db6",
           "title": "Citigroup Can Lift the Stock by 30%. It's Time to Buy.",
           "first_seen_utc": _now(), "sha": "s2", "column": "barrons_stock_picks"}
    assert DC.page_class(DC.page_type_of(art["url"], art["title"], art["column"])) == "PICK"
    r = _write(ledger, art, [_claim("C"), _claim("JPM", "down", "JPM should lag")])
    rows = _rows(ledger)
    assert r["status"] == "OK" and r["n_rows_written"] == 6 == len(rows)
    assert {(x["ticker"], x["probability"]) for x in rows} == {("C", 0.6), ("JPM", 0.4)}
    assert {x["specialist"] for x in rows} == {"source:barrons_stock_picks"}
    # the local record of a written page is byte-identical to before (no tag)
    local = [json.loads(x) for x in (ledger / "local.jsonl").read_text("utf-8").splitlines()]
    assert all("page_class" not in x for x in local)


def test_mention_flag_off_restores_the_old_rows(ledger, monkeypatch):
    monkeypatch.setattr(C, "DOWJONES_MENTION_NO_FORECAST", False)
    url, title = MENTION_PAGES[0]
    r = _write(ledger, {"url": url, "title": title, "first_seen_utc": _now(), "sha": "s",
                        "column": "barrons_other"}, [_claim("NVDA")])
    assert r["n_rows_written"] == 3


def test_stance_required_emits_only_with_a_stance_and_its_direction(ledger, monkeypatch):
    art = {"url": "https://www.barrons.com/articles/nvidia-stock-chips-ai-1ba0b84a",
           "title": "Why Nvidia Is Rising While Chip Stocks Keep Falling",
           "first_seen_utc": _now(), "sha": "s3", "column": "barrons_stock_picks"}
    # nav-bar label, no pick marker -> STANCE_REQUIRED
    assert DC.page_type_of(art["url"], art["title"], art["column"]) == "barrons_stock_picks_nav"
    claims = [_claim("NVDA", "up", "Nvidia is holding up and rising while chips slump."),
              _claim("AMD", "up", "AMD looks cheap and could rebound."),
              {**_claim("INTC", "up", "Intel is in the news."), "stance": "bearish"}]
    # flag OFF (default): rows as before, every up claim at 0.60
    r0 = DC.write_forecasts(art, claims, ledger_path=ledger / "off.jsonl",
                            claims_path=ledger / "off_c.jsonl", local_path=ledger / "off_l.jsonl")
    assert r0["n_rows_written"] == 9
    monkeypatch.setattr(C, "DOWJONES_STANCE_REQUIRED_ENFORCE", True)
    r = _write(ledger, art, claims)
    rows = _rows(ledger)
    assert r["n_no_stance"] == 1                               # NVDA: a description, counted
    assert {(x["ticker"], x["probability"]) for x in rows} == {("AMD", 0.6), ("INTC", 0.4)}
    assert "NVDA" not in {x["ticker"] for x in rows}


def test_the_stock_pick_hint_reaches_only_a_real_pick_page():
    seen: list[str] = []
    nav = {"url": "https://www.barrons.com/articles/nvidia-stock-chips-ai-1ba0b84a",
           "title": "Why Nvidia Is Rising", "text": "x " * 400, "column": "barrons_stock_picks",
           "first_seen_utc": _now()}
    pick = {**nav, "url": "https://www.barrons.com/articles/buy-citigroup-stock-3da35db6",
            "title": "Citigroup: Time to Buy"}
    DC.extract_claims(nav, llm_fn=lambda s, u: seen.append(u) or '{"claims": []}')
    DC.extract_claims(pick, llm_fn=lambda s, u: seen.append(u) or '{"claims": []}')
    assert "Column note" not in seen[0] and "Column note" in seen[1]


def test_new_rows_take_their_column_from_url_and_title(ledger):
    nav = {"url": "https://www.barrons.com/articles/nvidia-stock-chips-ai-1ba0b84a",
           "title": "Why Nvidia Is Rising", "first_seen_utc": _now(), "sha": "n1",
           "column": "barrons_stock_picks"}
    hots = {"url": "https://www.wsj.com/tech/ai/ai-is-disrupting-software-a380443a",
            "title": "AI Is Disrupting Software", "first_seen_utc": _now(), "sha": "n2",
            "column": "wsj_heard_on_the_street"}
    assert DC.page_type_of(hots["url"], hots["title"], hots["column"]) == \
        "wsj_heard_on_the_street_text_only"
    _write(ledger, nav, [_claim("NVDA")])
    _write(ledger, hots, [_claim("ORCL")])
    assert {x["specialist"] for x in _rows(ledger)} == {"source:barrons_other", "source:wsj_other"}
    hots2 = {**hots, "url": "https://www.wsj.com/finance/heard-on-the-street-x-1a2b3c4d",
             "sha": "n3"}
    assert DC.effective_column(hots2["url"], "", hots2["column"]) == "wsj_heard_on_the_street"


@pytest.mark.parametrize("url,title,col,status", [
    ("https://www.barrons.com/articles/stock-movers-8b39c82b", "Movers", "barrons_other",
     "SKIPPED_MENTION_NO_FORECAST"),
    ("https://www.barrons.com/articles/buy-frontline-stock-3415119d", "Buy This", "barrons_stock_picks",
     "SKIPPED_STALE_NO_FORECAST"),
    ("https://www.barrons.com/articles/x-1", "x", "barrons_lane_nobody_classified",
     "REFUSED_UNKNOWN_PAGE_TYPE"),
])
def test_no_extraction_is_paid_for_a_page_that_will_write_nothing(url, title, col, status):
    old = (datetime.now(timezone.utc) - timedelta(days=27)).isoformat(timespec="seconds")
    art = {"url": url, "title": title, "text": "x " * 400, "column": col,
           "first_seen_utc": old if "STALE" in status else _now()}
    pc = DC.precheck(art)
    assert pc["forecast"] is False
    r = DC.extract_claims(art, llm_fn=lambda s, u: pytest.fail("paid for a page that writes nothing"))
    assert r["status"] == status and r["claims"] == []
    assert (status in DC.RETRY_STATUSES) == (status == "REFUSED_UNKNOWN_PAGE_TYPE")


def test_a_fresh_pick_page_passes_the_precheck():
    pc = DC.precheck({"url": "https://www.barrons.com/articles/buy-citigroup-stock-3da35db6",
                      "title": "Buy", "column": "barrons_stock_picks", "first_seen_utc": _now()})
    assert pc["forecast"] is True and pc["page_class"] == "PICK"


def test_status_census_makes_an_all_zero_backlog_visible():
    per = [{"status": "SKIPPED_STALE_NO_FORECAST", "forecast_rows": 0},
           {"status": "REFUSED_UNKNOWN_PAGE_TYPE", "forecast_rows": 0},
           {"status": "OK", "write_status": "STALE_NO_FORECAST", "forecast_rows": 0}]
    c = DC.status_census(per)
    assert c["all_articles_wrote_zero_rows"] is True and c["n_retry"] == 1
    assert c["extract_status"]["SKIPPED_STALE_NO_FORECAST"] == 1
    assert c["write_status"] == {"STALE_NO_FORECAST": 1}


def test_duplicates_collapse_to_one_row_per_article_ticker_horizon(ledger, monkeypatch):
    monkeypatch.setattr(C, "DOWJONES_DEDUPE_ARTICLE_TICKER_HORIZON", True)
    base = "https://www.barrons.com/articles/ionq-stock-quantum-computing-buy-ce5e2fde"
    seen = datetime.now(timezone.utc)
    a1 = {"url": base + "?mod=hp_1", "title": "IonQ Is a Buy", "sha": "x1",
          "first_seen_utc": seen.isoformat(timespec="seconds"), "column": "barrons_stock_picks"}
    # the same article reached by another link, stored again, paraphrased again
    a2 = {**a1, "url": base + "?mod=mw_latestnews", "sha": "x2",
          "first_seen_utc": (seen + timedelta(minutes=3)).isoformat(timespec="seconds")}
    r1 = _write(ledger, a1, [_claim("IONQ"), _claim("IONQ", "down", "IonQ could fall")])
    r2 = _write(ledger, a2, [_claim("IONQ", para="IonQ will climb, says the column.")])
    rows = _rows(ledger)
    keys = [(x["ticker"], x["horizon_days"]) for x in rows]
    assert len(keys) == len(set(keys)) == 3
    assert r1["n_duplicate_article_ticker"] == 1 and r2["n_duplicate_article_ticker"] == 1
    assert r2["n_rows_written"] == 0


def test_dedupe_off_keeps_the_old_behaviour(ledger, monkeypatch):
    monkeypatch.setattr(C, "DOWJONES_DEDUPE_ARTICLE_TICKER_HORIZON", False)
    base = "https://www.barrons.com/articles/ionq-stock-quantum-computing-buy-ce5e2fde"
    seen = datetime.now(timezone.utc)
    a1 = {"url": base, "title": "IonQ Is a Buy", "sha": "x1",
          "first_seen_utc": seen.isoformat(timespec="seconds"), "column": "barrons_stock_picks"}
    a2 = {**a1, "first_seen_utc": (seen + timedelta(minutes=3)).isoformat(timespec="seconds")}
    _write(ledger, a1, [_claim("IONQ")])
    _write(ledger, a2, [_claim("IONQ", para="IonQ will climb, says the column.")])
    assert len(_rows(ledger)) == 6                            # the measured live defect


def test_an_unknown_page_type_is_refused_by_name_never_a_pick(ledger):
    art = {"url": "https://www.barrons.com/articles/some-story-abc123", "title": "Some story",
           "first_seen_utc": _now(), "sha": "s4", "column": "barrons_new_lane_nobody_classified"}
    with pytest.raises(DC.PageTypeRefused, match="barrons_new_lane_nobody_classified"):
        DC.page_class(DC.page_type_of(art["url"], art["title"], art["column"]))
    r = _write(ledger, art, [_claim("NVDA")])
    assert r["status"] == "REFUSED_UNKNOWN_PAGE_TYPE" and r["n_rows_written"] == 0
    assert "barrons_new_lane_nobody_classified" in r["refused"]
    assert _rows(ledger) == []


def test_every_column_the_code_can_produce_is_classified():
    cols = {sid for sid, _, _ in DC.COLUMN_RULES} | {f"{p}_other" for p in DC.PUBLISHERS}
    cols |= {"dowjones_other", "barrons_stock_picks_nav", "wsj_heard_on_the_street_text_only"}
    cols |= set(C.DOWJONES_COLUMN_RELABEL.values())
    cols |= {ptype for ptype, _ in C.DOWJONES_PAGE_TYPE_RULES}
    for c in cols:
        assert DC.page_class(c) in DC.PAGE_CLASSES


def _ledger_row(i: int, sp: str, t: str, h: int, p: float, day: str, outcome, url: str) -> dict:
    return {"prediction_id": f"id{i}", "ticker": t, "specialist": sp,
            "observable": "beats_benchmark", "horizon_days": h, "probability": p,
            "made_at": f"{day}T00:00:00+00:00", "decision_date": day, "thesis": f"[{sp}] x",
            "next_observable": url, "outcome": outcome, "void_reason": None,
            "inputs_used": {"post_url": url, "claim_utc": f"{day}T00:00:00+00:00"}}


def test_the_grader_reads_only_through_the_layer_reconciles_and_refuses(tmp_path, capsys):
    from scripts import source_picks_grade as G
    root, out = tmp_path / "optimus", tmp_path / "out"
    root.mkdir()
    rng_days = [(datetime.now(timezone.utc) - timedelta(days=40 - k)).date().isoformat()
                for k in range(12)]
    rows, i = [], 0
    for k, day in enumerate(rng_days):
        for t in ("AAA", "BBB", "CCC"):
            for h in (1, 5, 20):
                i += 1
                rows.append(_ledger_row(i, "source:barrons_stock_picks", t, h, 0.6, day,
                                        (i + k) % 2,
                                        f"https://www.barrons.com/articles/stock-movers-{k}{t}"))
    rows.append({"prediction_id": "other", "specialist": "investigator", "ticker": "AAA"})
    (root / "predictions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    before = sorted(x.name for x in root.iterdir())
    assert G.main(["--data-root", str(root), "--out", str(out), "--run-id", "t1"]) == 0
    assert sorted(x.name for x in root.iterdir()) == before          # nothing written there
    rec = json.loads((out / "source_picks_grade_t1.json").read_text(encoding="utf-8"))
    sp = rec["per_specialist"]["source:barrons_stock_picks"]
    assert rec["reconciles"] and sp["n_rows"] == sp["ledger_regex_count"] == len(rows) - 1
    assert sp["date_blocks"] == 12 and sp["tickers"] == 3
    c5 = sp["by_horizon"]["5"]
    assert c5["mde"] is not None and sp["verdict"] in (
        "SUPPORTED_IN_SCOPE", "CANNOT_DISTINGUISH", "NOT_SUPPORTED_IN_SCOPE")
    assert rec["mention_rows"]["n"] == len(rows) - 1                 # every page is a mover page
    # refusals are red, never rc 0
    assert G.main(["--data-root", str(tmp_path / "missing"), "--out", str(out)]) == 2
    assert G.main(["--data-root", str(root), "--out", str(root / "x")]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert G.main(["--data-root", str(empty), "--out", str(out)]) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_a_verdict_never_comes_without_an_mde():
    from scripts import source_picks_grade as G
    assert G.verdict({"mde": None, "n_resolved": 500, "date_blocks_resolved": 50,
                      "t": 9.0, "hit_rate": 0.9}) == "CANNOT_DISTINGUISH"


def test_a_stale_page_writes_zero_rows_by_default_and_says_so_locally(ledger, monkeypatch):
    assert C.DOWJONES_MAX_EXTRACTION_LAG_DAYS == 3                 # the default since review 1
    assert C.DOWJONES_DEDUPE_ARTICLE_TICKER_HORIZON is True
    old = (datetime.now(timezone.utc) - timedelta(days=27)).isoformat(timespec="seconds")
    art = {"url": "https://www.barrons.com/articles/buy-frontline-stock-3415119d",
           "title": "Buy This Tanker Stock", "first_seen_utc": old, "sha": "s5",
           "column": "barrons_stock_picks"}
    r = _write(ledger, art, [_claim("FRO"), _claim("EURN")])
    assert r["status"] == "STALE_NO_FORECAST" and r["n_rows_written"] == 0
    assert r["extraction_lag_days"] > 3
    assert _rows(ledger) == [] and not (ledger / "c.jsonl").exists()
    local = [json.loads(x) for x in (ledger / "local.jsonl").read_text("utf-8").splitlines()]
    assert len(local) == 2 and all(x["forecast_written"] is False
                                   and x["no_forecast_why"] == "STALE_NO_FORECAST" for x in local)
    # None switches the gate off
    monkeypatch.setattr(C, "DOWJONES_MAX_EXTRACTION_LAG_DAYS", None)
    assert _write(ledger, {**art, "sha": "s6"}, [_claim("FRO")])["n_rows_written"] == 3
