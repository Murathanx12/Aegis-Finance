"""N-D — the entity resolver, on twenty hand-written titles.

Including the two that matter most: a DENIAL (which still names the issuer and
must resolve — typing the denial is L2's job, not a string matcher's) and a
FALSE FRIEND (a company name that is also an ordinary English word, which must
NOT resolve without a corporate cue nearby).
"""

from __future__ import annotations

import pytest

from backend.services import news_entities as ne


@pytest.fixture(scope="module")
def tbl(tmp_path_factory):
    """A small, fully-controlled table. The shipped CSVs are tested separately."""
    d = tmp_path_factory.mktemp("names")
    (d / "issuers.csv").write_text(
        "symbol,primary_name,aliases,country,is_adr\n"
        'NVDA,"NVIDIA Corporation",NVDA|NVIDIA,US,\n'
        'A,"Agilent Technologies, Inc.",A|Agilent Technologies,US,\n'
        'V,"Visa Inc.",V|Visa,US,\n'
        'AAPL,"Apple Inc.",AAPL|Apple,US,\n'
        'KR,"The Kroger Co.",KR|Kroger,US,\n'
        'F,"Ford Motor Company",F|Ford,US,\n'
        'AMD,"Advanced Micro Devices, Inc.",AMD|Advanced Micro Devices,US,\n'
        'INTC,"Intel Corporation",INTC|Intel,US,\n'
        'TSLA,"Tesla, Inc.",TSLA|Tesla,US,\n'
        'EXEL,"Exelixis, Inc.",EXEL|Exelixis,US,\n',
        encoding="utf-8",
    )
    (d / "asia_adrs.csv").write_text(
        "us_symbol,local_symbol,local_exchange,source_country,us_short_name_yfinance,us_exchange_yfinance,verified,notes\n"
        "BABA,9988.HK,HKEX,CN,Alibaba Group Holding Limited,NYQ,YES,dual primary\n"
        "TM,7203.T,TSE,JP,Toyota Motor Corporation,NYQ,YES,Tokyo primary\n"
        "LPL,034220.KS,KRX,KR,LG Display Co. Ltd.,NYQ,YES,LG Display not LG Corp\n"
        "TSM,2330.TW,TWSE,TW,Taiwan Semiconductor Manufacturing,NYQ,YES,Taiwan primary\n",
        encoding="utf-8",
    )
    return ne._Tables(d / "issuers.csv", d / "asia_adrs.csv")


def r(text, tbl):
    return list(ne.resolve(text, tbl=tbl).tickers)


# ------------------------------------------------- the twenty hand-written ones

CASES: list[tuple[str, list[str]]] = [
    # 1 — a DENIAL still names the issuer. Resolving this to [] would hide the
    #     row from the panel; whether the denial is bullish is L2's problem.
    ("Nvidia denies report that it cancelled a Blackwell order", ["NVDA"]),
    # 2 — the plain positive case
    ("NVIDIA Corporation raises its data centre outlook", ["NVDA"]),
    # 3 — FALSE FRIEND: "Visa" the word, not the company
    ("Visa applications surge in Singapore as students arrive", []),
    # 4 — same word, licensed by a corporate cue
    ("Visa Inc. beat on earnings; shares rose 4%", ["V"]),
    # 5 — FALSE FRIEND: apples, not Apple
    ("Apple orchards in Washington report a bumper crop", []),
    # 6 — licensed
    ("Apple shares slipped after the foldable launch", ["AAPL"]),
    # 7 — the single-letter symbol must NOT match a bare English word
    ("A record heatwave hits Texas", []),
    # 8 — but its full name does
    ("Agilent Technologies, Inc. names a new CFO", ["A"]),
    # 9 — an explicit cashtag reaches a name the table has no long form for
    ("$AMD and $INTC both fell today", ["AMD", "INTC"]),
    # 10 — venue-prefixed ticker
    ("NASDAQ: TSLA closed at a two-month high", ["TSLA"]),
    # 11 — parenthesised ticker, the EDGAR/press-release convention
    ("Exelixis, Inc. (EXEL) files an 8-K", ["EXEL"]),
    # 12 — an Asian local code maps to its US ADR leg
    ("Alibaba posts record cloud revenue; 9988.HK climbs 6%", ["BABA"]),
    # 13 — the ADR short name itself
    ("Toyota Motor Corporation lifts full-year guidance", ["TM"]),
    # 14 — the local Tokyo code
    ("7203.T rose in Tokyo trade", ["TM"]),
    # 15 — the 09-11 probe's ADR fix: LPL is LG DISPLAY, not LG Corp
    ("034220.KS swings to a quarterly profit", ["LPL"]),
    # 16 — a long name that needs suffix stripping to match
    ("Taiwan Semiconductor Manufacturing lifts capex", ["TSM"]),
    # 17 — two issuers in one headline, in order of appearance
    ("Kroger and Ford Motor Company both raised guidance", ["KR", "F"]),
    # 18 — "Ford" alone is in the ambiguous set and needs a cue; "Motor Company" gives it
    ("Ford drove to the meeting", []),
    # 19 — a macro headline with generic business vocabulary resolves to nothing
    ("Energy and materials led the index higher on capital inflows", []),
    # 20 — an empty string is not an error
    ("", []),
]


@pytest.mark.parametrize("text,expected", CASES, ids=[c[0][:40] or "empty" for c in CASES])
def test_resolver_cases(text, expected, tbl):
    assert r(text, tbl) == expected


def test_a_denial_is_resolved_not_suppressed(tbl):
    """Stated once more on its own, because it is a decision, not an accident."""
    res = ne.resolve("Nvidia denies the report", tbl=tbl)
    assert res.tickers == ("NVDA",)
    assert res.how["NVDA"] == "name"


def test_the_rule_that_fired_is_recorded(tbl):
    res = ne.resolve("Alibaba climbs; 9988.HK up 6%", tbl=tbl)
    assert res.how["BABA"] == "adr_local_code"
    assert ne.resolve("$AMD", tbl=tbl).how["AMD"] == "cashtag"


def test_the_length_floor_drops_short_aliases(tbl):
    """`A`, `V`, `F` are reachable by ticker token and never by bare word."""
    assert all(len(k) >= ne.MIN_ALIAS_CHARS for k in tbl.name_to_symbol)
    for one_letter in ("a", "v", "f"):
        assert one_letter not in tbl.name_to_symbol
    assert tbl.n_aliases_dropped_short > 0, "the floor never fired — it is not being exercised"


def test_generic_business_words_are_not_aliases(tbl):
    for word in ("group", "holdings", "technologies", "energy", "capital"):
        assert word not in tbl.name_to_symbol


def test_limit_caps_the_ticker_list(tbl):
    text = " ".join(f"${s}" for s in ("NVDA", "AMD", "INTC", "TSLA", "KR", "F", "V", "AAPL", "EXEL"))
    assert len(ne.resolve(text, tbl=tbl, limit=3).tickers) == 3


# ------------------------------------------------------- the SHIPPED name table


def test_the_shipped_tables_load_and_report_their_gap():
    s = ne.stats()
    assert s["issuer_rows"] >= 3000, "issuers.csv lost rows"
    assert s["adr_rows"] >= 25, "asia_adrs.csv lost rows"
    # The known 2026-09-11 gap, stated as a number rather than a feeling.
    assert s["named_symbols"] < s["issuer_rows"]
    assert "name-table gap" in s["note"]


def test_the_shipped_adr_fixes_survive():
    """The four ADR corrections the probe made, pinned in the shipped CSV."""
    t = ne.tables()
    assert t.local_to_us.get("9988.HK") == "BABA"
    assert t.local_to_us.get("8306.T") == "MUFG", "MUFG is 8306.T, Mizuho/MFG is 8411.T"
    assert t.local_to_us.get("8411.T") == "MFG"
    assert t.local_to_us.get("034220.KS") == "LPL", "LPL is LG Display's ADR, not LG Corp"
