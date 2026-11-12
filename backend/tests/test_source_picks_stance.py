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


def test_the_stock_pick_hint_is_withheld_from_a_non_pick_page_under_enforce(monkeypatch):
    seen: list[str] = []
    art = {"url": "https://www.barrons.com/articles/nvidia-stock-chips-ai-1ba0b84a",
           "title": "Why Nvidia Is Rising", "text": "x " * 400, "column": "barrons_stock_picks"}
    DC.extract_claims(art, llm_fn=lambda s, u: seen.append(u) or '{"claims": []}')
    monkeypatch.setattr(C, "DOWJONES_STANCE_REQUIRED_ENFORCE", True)
    DC.extract_claims(art, llm_fn=lambda s, u: seen.append(u) or '{"claims": []}')
    assert "Column note" in seen[0] and "Column note" not in seen[1]


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


def test_dedupe_off_keeps_the_old_behaviour(ledger):
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
    cols |= {"dowjones_other", "barrons_stock_picks_nav"}
    cols |= {ptype for ptype, _ in C.DOWJONES_PAGE_TYPE_RULES}
    for c in cols:
        assert DC.page_class(c) in DC.PAGE_CLASSES


def test_a_stale_extraction_writes_no_forecast_only_when_the_lag_flag_is_on(ledger, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=27)).isoformat(timespec="seconds")
    art = {"url": "https://www.barrons.com/articles/buy-frontline-stock-3415119d",
           "title": "Buy This Tanker Stock", "first_seen_utc": old, "sha": "s5",
           "column": "barrons_stock_picks"}
    assert _write(ledger, art, [_claim("FRO")])["n_rows_written"] == 3     # default: off
    monkeypatch.setattr(C, "DOWJONES_MAX_EXTRACTION_LAG_DAYS", 3.0)
    art2 = {**art, "url": art["url"].replace("frontline", "euronav"), "sha": "s6"}
    r = DC.write_forecasts(art2, [_claim("EURN")], ledger_path=ledger / "p2.jsonl",
                           claims_path=ledger / "c2.jsonl", local_path=ledger / "l2.jsonl")
    assert r["status"] == "STALE_NO_FORECAST" and r["extraction_lag_days"] > 3
