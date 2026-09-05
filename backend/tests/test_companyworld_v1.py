"""Pins for COMPANYWORLD v1 -- the bought supply-chain edges.

What is pinned here is the part that fails SILENTLY. The extraction's cost, its
edge counts and its verdict all live in receipts and are read by a human. These
three do not:

1. **PIT.** `valid_from` is the filing date and `valid_to` is filing +
   `MAX_AGE_DAYS`. An edge visible before its filing date is a leak that no
   downstream number would reveal -- it would simply make the feature better.
2. **The resolver refuses rather than guesses.** A single generic token
   ("GENERAL", "UNION") must not resolve, and a counterparty must never resolve
   to its own subject. Both failures manufacture edges between the wrong pair of
   companies and neither raises.
3. **The parquet carries BOTH schemas.** The task's column names
   (`src_permno`/`dst_permno`/`edge_type`) and the ones
   `learner.features_graph.EDGE_COLUMNS` reads. If the second set goes missing
   the file still loads and the feature build produces an all-NaN join, which
   reads as a clean negative result.

Offline: no network, no vendor, no LLM. The parquet is skipped when absent
(it is data, not code, and CI has no copy) -- but its ABSENCE is reported, not
passed over in silence.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts import companyworld_extract as CW

EDGES = (Path(__file__).resolve().parents[2] / "backend" / "data" / "optimus"
         / "graph" / "companyworld_v1.parquet")


def _edges() -> pd.DataFrame:
    if not EDGES.exists():
        pytest.skip(f"companyworld_v1.parquet not on this machine ({EDGES}); "
                    "it is produced by scripts/companyworld_extract.py and is "
                    "not tracked as code")
    return pd.read_parquet(EDGES)


def test_valid_from_is_the_filing_date_and_valid_to_is_bounded():
    df = _edges()
    assert (df["valid_from"] == df["filing_date"]).all(), (
        "an edge whose valid_from precedes its filing_date is visible before it "
        "was public")
    span = (df["valid_to"] - df["valid_from"]).dt.days
    assert set(span.unique()) == {CW.MAX_AGE_DAYS}


def test_the_window_is_the_years_the_graph_did_not_have():
    df = _edges()
    yr = df["filing_date"].dt.year
    assert yr.min() >= CW.YEAR_LO and yr.max() <= CW.YEAR_HI, (
        f"this run buys {CW.YEAR_LO}-{CW.YEAR_HI}; MARKET-GRAPH-1 already "
        "covers 2014-2024 and a silent overlap would double-count")


def test_no_self_edges_and_both_ends_are_real_permnos():
    df = _edges()
    assert (df["src_permno"] != df["dst_permno"]).all()
    assert df["src_permno"].gt(0).all() and df["dst_permno"].gt(0).all()


def test_the_parquet_carries_both_schemas():
    df = _edges()
    for c in ("src_permno", "dst_permno", "edge_type", "graph_layer",
              "valid_from", "valid_to", "source", "confidence", "filing_date"):
        assert c in df.columns, f"task schema is missing {c}"
    from learner import features_graph as FG
    for c in FG.EDGE_COLUMNS:
        assert c in df.columns, (
            f"features_graph reads {c!r} and it is absent -- the feature build "
            "would join to all-NaN and read as a clean negative result")
    assert (df["graph_layer"] == "FACT").all()


def test_edge_types_are_the_frozen_taxonomy_and_confidence_is_a_probability():
    df = _edges()
    assert set(df["edge_type"]) <= set(CW.EDGE_TYPES)
    assert df["confidence"].between(0.0, 1.0).all()


def test_the_resolver_refuses_a_generic_single_token():
    idx = CW.NameIndex()
    d = pd.Timestamp("2005-06-30")
    for name in ("General", "Union", "Global", "ABC"):
        p, route = idx.resolve(name, None, d, subject=10107)
        assert p is None, f"{name!r} resolved to permno {p} via {route}"
        assert route in ("generic_single_token", "not_in_crsp_at_date",
                         "unusable_name")


def test_the_resolver_never_returns_the_subject_itself():
    idx = CW.NameIndex()
    d = pd.Timestamp("2005-06-30")
    # Microsoft's own permno is 10107; a filing that names itself must not
    # produce a self-edge through either the ticker or the name route.
    assert idx.resolve("Microsoft Corp", "MSFT", d, subject=10107)[0] is None


def test_normalize_name_folds_suffixes_and_punctuation():
    n = CW.normalize_name
    # The apostrophe is folded OUT, not turned into a space: without this,
    # "Lowe's" became the two-token key "LOWE S" and never matched CRSP's
    # "LOWES". Both sides go through the same function, which is the only
    # reason the two keys are comparable at all.
    assert n("Lowe's Companies, Inc.") == n("LOWES COMPANIES")
    assert n("Lowe's") == "LOWES"
    assert n("Apple Inc.") == n("APPLE")
    assert n("") == "" and n(None) == ""


def test_the_extractor_names_deepseek_and_only_deepseek():
    # CLAUDE.md: DeepSeek is the ONLY provisioned provider. A job that quietly
    # grew an Anthropic branch would spend money that does not exist.
    src = Path(CW.__file__).read_text(encoding="utf-8")
    assert CW.EXTRACT_MODEL == "deepseek-chat"
    assert "ANTHROPIC_API_KEY" not in src
    assert "api.anthropic.com" not in src


def test_the_money_ceiling_is_ten_dollars():
    assert CW.SESSION_MAX_USD == 10.00


def test_business_section_reports_how_it_found_the_span():
    # A section finder that silently returns the table of contents leaves every
    # downstream number looking fine, so the METHOD is part of the return value.
    text = ("Item 1. Business\n" + ("we rely on our supplier and our customer "
                                    "and our competitor and our distributor "
                                    "and our vendor and our partner. " * 120)
            + "\nItem 1A. Risk Factors\n" + "risk " * 500)
    exc, method, hits = CW.business_section(text)
    assert method.startswith("item1_business")
    assert hits >= CW.MIN_REL_HITS
    assert "Item 1A" not in exc


def test_item_15a1_does_not_match_item_1():
    # The `(?![0-9a])` guard: without it `Item 15(a)(1)` matched and the excerpt
    # came back as the auditor's report -- a wrong section produces a confident,
    # well-formed, EMPTY answer.
    assert CW._ITEM1_LOOSE.search("Item 15(a)(1) Exhibits") is None
    assert CW._ITEM1_LOOSE.search("Item 1A. Risk Factors") is None
    assert CW._ITEM1_LOOSE.search("Item 1. Business") is not None
