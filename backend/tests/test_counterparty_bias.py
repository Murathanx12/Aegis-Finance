"""Pins for `scripts/c6b_counterparty_bias.py` (item 5, 2026-09-06b mandate).

Four things are pinned, and each of them is a way the C5 receipt could go quietly
wrong rather than loudly wrong:

1. **within-month deciles are within month.**  The planted panel below is built
   so that a POOLED decile gives the opposite answer to a within-month one: caps
   grow tenfold across the window, so pooled deciles sort by DATE.  If the
   grouping is ever dropped the test fails on the planted answer, not on a
   subtle shift in a real number.
2. **the normaliser is idempotent and strips the declared suffixes**, and agrees
   with `scripts/companyworld_extract.normalize_name`, which is the function the
   graph was actually resolved with.  A drifted copy would silently re-classify
   the residue.
3. **the sample is reproducible under a fixed seed** and moves under a different
   one -- a "reproducible" sample that ignores the seed is worse than none.
4. **the receipt carries `_provenance` with a non-empty `_inputs_opened`** (the
   shared schema across this session's five agents; item 6 reads it).

Anything that needs CRSP or the 418 MB panel is marked `slow`.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts import c6b_counterparty_bias as C5


# ---------------------------------------------------------------- normaliser

def test_normaliser_is_idempotent_on_the_hard_cases():
    cases = ["Wal-Mart Stores, Inc.", "The Boeing Company", "Hewlett-Packard",
             "sanofi-aventis", "J&J", "CNH Global N.V.", "  Acme   Corp.  ",
             "Procter & Gamble Co", "Compagnie Générale S.A.", "", "3M Co"]
    for raw in cases:
        once = C5.normalise_company_name(raw)
        assert C5.normalise_company_name(once) == once, raw


def test_normaliser_strips_the_declared_suffix_list():
    assert C5.normalise_company_name("Acme Inc") == "ACME"
    assert C5.normalise_company_name("Acme Corporation") == "ACME"
    assert C5.normalise_company_name("Acme Co Ltd") == "ACME"
    assert C5.normalise_company_name("Acme Holdings PLC") == "ACME"
    assert C5.normalise_company_name("The Acme Company") == "ACME"
    assert C5.normalise_company_name("Acme, LLC") == "ACME"
    # A KNOWN ARTEFACT of the extractor's rule, pinned here rather than fixed:
    # the suffix list is matched TOKEN-wise, so a dotted foreign legal form
    # splits into two tokens and only the last one is stripped.  "Acme S.A."
    # therefore keeps a stray "S".  This is the extractor's own behaviour and
    # the graph was resolved under it; changing it here would make the residue
    # classification disagree with the file it is classifying.
    assert C5.normalise_company_name("Acme S.A.") == "ACME S"
    assert C5.normalise_company_name("Acme SA") == "ACME"
    # punctuation and apostrophes go; digits and & survive as tokens
    assert C5.normalise_company_name("Macy's, Inc.") == "MACYS"
    assert C5.normalise_company_name("3M Co") == "3M"
    # a name that is ONLY suffixes must not vanish into a crash
    assert C5.normalise_company_name("Inc.") == ""
    assert C5.normalise_company_name(None) == ""
    assert C5.normalise_company_name(42) == ""


def test_normaliser_agrees_with_the_extractor_that_built_the_graph():
    """The residue classification is only meaningful against the SAME keys the
    extractor used.  A drifted local copy would silently re-partition it."""
    ext = pytest.importorskip("scripts.companyworld_extract")
    for raw in ["Wal-Mart Stores, Inc.", "The Boeing Company", "IBM", "J&J",
                "Hewlett-Packard Company", "E M C Corp MA", "Acme Holdings PLC",
                "International Business Machs Cor", "sanofi-aventis"]:
        assert C5.normalise_company_name(raw) == ext.normalize_name(raw), raw


# ------------------------------------------------------------------ deciles

def _planted_panel() -> pd.DataFrame:
    """Caps rise tenfold per month, so POOLED deciles sort by DATE.

    Within each of the three months there are exactly 10 names with caps
    1..10 (times the month's factor), so the correct within-month answer is
    "name i is in decile i, in every month".  A pooled decile instead puts all
    of month 3 in the top deciles and all of month 1 in the bottom ones.
    """
    rows = []
    for k, d in enumerate(pd.to_datetime(["2005-01-21", "2005-02-18",
                                          "2005-03-18"])):
        for i in range(1, 11):
            rows.append({"permno": i, "entry_date": d,
                         "market_cap": i * (10.0 ** k)})
    return pd.DataFrame(rows)


def test_deciles_are_formed_within_month_not_pooled():
    out = C5.assign_within_month_deciles(_planted_panel(),
                                         value_col="market_cap",
                                         date_col="entry_date")
    # the planted answer: permno i sits in decile i in EVERY month
    for _, r in out.iterrows():
        assert int(r["decile"]) == int(r["permno"]), r.to_dict()
    # and the pooled answer would have been different: the largest name of
    # month 1 (cap 10) is smaller than the smallest name of month 3 (cap 100),
    # so a pooled decile would put it near the bottom rather than at 10.
    m1 = out[(out["entry_date"] == pd.Timestamp("2005-01-21")) & (out["permno"] == 10)]
    assert int(m1["decile"].iloc[0]) == 10
    pooled = pd.qcut(out["market_cap"], 10, labels=False) + 1
    assert int(pooled[m1.index[0]]) < 10, "the planted panel no longer separates the two"


def test_every_month_of_the_panel_is_uniform_by_construction():
    out = C5.assign_within_month_deciles(_planted_panel(),
                                         value_col="market_cap",
                                         date_col="entry_date")
    t = C5.decile_table(out["decile"], "planted")
    assert t["n"] == 30
    assert all(abs(s - 0.10) < 1e-9 for s in t["share_by_decile"].values())
    assert abs(t["mean_decile"] - 5.5) < 1e-9
    # ... which is exactly what makes a flat 10% the right null
    chi = C5.chi2_vs_uniform(t["count_by_decile"])
    assert chi["chi2"] == pytest.approx(0.0, abs=1e-9)


def test_deciles_survive_a_month_of_identical_caps():
    """A tie-collapsing rank would drop a whole month into one bucket."""
    df = pd.DataFrame({"permno": range(1, 21),
                       "entry_date": pd.Timestamp("2005-01-21"),
                       "market_cap": [7.0] * 20})
    out = C5.assign_within_month_deciles(df, value_col="market_cap",
                                         date_col="entry_date")
    assert sorted(out["decile"].unique().tolist()) == list(range(1, 11))


def test_nan_caps_do_not_become_a_decile():
    df = _planted_panel()
    df.loc[0, "market_cap"] = np.nan
    out = C5.assign_within_month_deciles(df, value_col="market_cap",
                                         date_col="entry_date")
    assert out["decile"].isna().sum() == 1


# ------------------------------------------------------------- reproducibility

def _draw(seed: int, n: int = 50, frame: int = 4656) -> list[int]:
    rng = np.random.default_rng(seed)
    return sorted(rng.choice(frame, size=n, replace=False).tolist())


def test_the_sample_is_reproducible_under_a_fixed_seed():
    assert _draw(C5.DEFAULT_SEED) == _draw(C5.DEFAULT_SEED)


def test_the_sample_actually_depends_on_the_seed():
    """A 'reproducible' draw that ignores its seed is worse than no seed."""
    assert _draw(C5.DEFAULT_SEED) != _draw(C5.DEFAULT_SEED + 1)


def test_the_sample_is_drawn_without_replacement():
    d = _draw(C5.DEFAULT_SEED)
    assert len(set(d)) == len(d) == 50


# ------------------------------------------------------------------- wilson

def test_wilson_interval_brackets_the_point_and_handles_the_edges():
    ci = C5.wilson(6, 50)
    assert ci["lo"] < ci["p_hat"] < ci["hi"]
    assert 0.0 < ci["lo"] and ci["hi"] < 1.0
    zero = C5.wilson(0, 50)
    assert zero["p_hat"] == 0.0 and zero["lo"] == 0.0 and zero["hi"] > 0.0
    assert C5.wilson(0, 0)["p_hat"] is None


# ---------------------------------------------------------------- provenance

def test_write_receipt_round_trips_a_provenance_block(tmp_path):
    out = tmp_path / "C5_probe.json"
    inputs = [{"path": str(tmp_path / "a.parquet"), "sha256": "ab" * 32,
               "bytes": 17}]
    prov = C5.provenance(["c6b_counterparty_bias.py"], {"seed": 1}, inputs)
    C5.write_receipt({"job": "probe", "_provenance": prov}, out)
    got = json.loads(out.read_text(encoding="utf-8"))
    assert set(got["_provenance"]) >= {"sys_argv", "resolved_config",
                                       "_inputs_opened", "git_commit",
                                       "generated_utc"}
    assert got["_provenance"]["_inputs_opened"], "inputs must not be empty"
    assert got["_provenance"]["git_commit"]


def test_sha256_of_matches_hashlib(tmp_path):
    import hashlib
    p = tmp_path / "x.bin"
    p.write_bytes(b"aegis" * 1000)
    got = C5.sha256_of(p)
    assert got["sha256"] == hashlib.sha256(b"aegis" * 1000).hexdigest()
    assert got["bytes"] == 5000


# ------------------------------------------------------------------ grading

class _FakeIndex:
    """A CrspNameIndex stand-in, so the grading rules are testable offline."""

    def __init__(self, mapping: dict[str, set[int]], names: dict[int, str]):
        self._m = mapping
        self.comnam = names

    def permnos_for_key(self, key):
        return self._m.get(key, set())

    def unique_prefix_match(self, key):
        hits = {k: v for k, v in self._m.items()
                if k == key or k.startswith(key + " ")}
        permnos = set().union(*hits.values()) if hits else set()
        if len(permnos) == 1:
            p = next(iter(permnos))
            return p, sorted(hits, key=len)[0], 1
        return None, None, len(permnos)

    def unique_leading_prefix(self, key, min_tokens=2):
        toks = key.split()
        if len(toks) < min_tokens + 1:
            return None, None, 0
        head = " ".join(toks[:min_tokens])
        hits = {k: v for k, v in self._m.items() if k.startswith(head)}
        permnos = set().union(*hits.values()) if hits else set()
        if len(permnos) == 1:
            return next(iter(permnos)), sorted(hits, key=len)[0], 1
        return None, None, len(permnos)

    def listing_kind(self, permno):
        return "us_common"


def _sample_row(name, key, foreign=False):
    return {"counterparty_name": name, "counterparty_ticker": None,
            "name_key": key, "filing_date": pd.Timestamp("2003-06-30"),
            "type": "customer", "direction": "out", "reason": "key_never_in_crsp",
            "foreign_form_token": foreign}


def test_grading_rules_produce_the_three_declared_verdicts():
    idx = _FakeIndex({"NOBLE DRILLING": {90537},
                      "WAL MART STORES": {55976},
                      "GENESIS HEALTH": {1}, "GENESIS ENERGY": {2},
                      "INTERNATIONAL BUSINESS MACHS COR": {12490}},
                     {90537: "NOBLE DRILLING CORP", 55976: "WAL MART STORES INC",
                      12490: "INTERNATIONAL BUSINESS MACHS COR"})
    sample = pd.DataFrame([
        _sample_row("Noble Drilling", "NOBLE DRILLING"),          # exact
        _sample_row("Wal-Mart", "WAL MART"),                      # unique prefix
        _sample_row("IBM", "IBM"),                                # declared rename
        _sample_row("Genesis", "GENESIS"),                        # multi-permno
        _sample_row("Sumitomo Corporation KK", "SUMITOMO KK", True),  # foreign
    ])
    got = C5.grade_sample(sample, idx,
                          renames={"IBM": "INTERNATIONAL BUSINESS MACHS COR"})
    by = {g["raw_name"]: g for g in got}
    assert by["Noble Drilling"]["verdict"] == "MATCHED_US_LISTED"
    assert by["Noble Drilling"]["match_route"] == "exact_name_key"
    assert by["Wal-Mart"]["verdict"] == "MATCHED_US_LISTED"
    assert by["Wal-Mart"]["matched_permno"] == 55976
    assert by["IBM"]["match_route"] == "declared_rename_table"
    assert by["IBM"]["verdict"] == "MATCHED_US_LISTED"
    assert by["Genesis"]["verdict"] == "AMBIGUOUS"
    assert by["Sumitomo Corporation KK"]["verdict"] == "PLAUSIBLY_FOREIGN_OR_PRIVATE"
    # every row carries the four hand-checkable fields the mandate asked for
    for g in got:
        assert set(g) >= {"raw_name", "best_alias_match", "matched_permno",
                          "match_score", "verdict"}


def test_an_ambiguous_name_is_never_forced_into_a_match():
    idx = _FakeIndex({"AMERICAN AIRLINES": {1}, "AMERICAN EXPRESS": {2}},
                     {1: "AMERICAN AIRLINES", 2: "AMERICAN EXPRESS"})
    got = C5.grade_sample(pd.DataFrame([_sample_row("American", "AMERICAN")]), idx)
    assert got[0]["verdict"] == "AMBIGUOUS"
    assert got[0]["matched_permno"] is None


# ------------------------------------------------------------ jsonl reader

def test_records_reader_survives_two_objects_on_one_line(tmp_path):
    """`records_run01.jsonl` really does carry a line with two objects on it.

    A per-line `json.loads` raises "Extra data" there, and a reader that
    swallowed the exception would silently lose edges and quietly shrink the
    denominator of the 31.05% rate.
    """
    p = tmp_path / "r.jsonl"
    p.write_text('{"a": 1}\n{"a": 2}{"a": 3}\n\n{"a": 4}\n', encoding="utf-8")
    assert [r["a"] for r in C5.read_records(p)] == [1, 2, 3, 4]


def test_mentions_frame_skips_non_ok_records():
    recs = [
        {"status": "ok", "permno": 1, "accession": "x", "filing_date": "2003-01-02",
         "edges": [{"counterparty_name": "A", "type": "customer",
                    "direction": "out", "quote_verified": True}]},
        {"status": "fetch_failed", "permno": 2, "accession": "y",
         "filing_date": "2003-01-03", "edges": []},
    ]
    m = C5.mentions_frame(recs)
    assert len(m) == 1 and m.loc[0, "counterparty_name"] == "A"


# --------------------------------------------------------------------- slow

@pytest.mark.slow
def test_the_real_receipt_carries_the_shared_provenance_schema():
    if not C5.OUT.exists():
        pytest.skip(f"{C5.OUT} not built yet -- run scripts.c6b_counterparty_bias")
    d = json.loads(C5.OUT.read_text(encoding="utf-8"))
    prov = d["_provenance"]
    assert set(prov) >= {"sys_argv", "resolved_config", "_inputs_opened",
                         "git_commit", "generated_utc"}
    assert len(prov["_inputs_opened"]) >= 5
    for row in prov["_inputs_opened"]:
        assert set(row) >= {"path", "sha256", "bytes"}
        assert len(row["sha256"]) == 64 and row["bytes"] > 0
    assert d["llm_spend_usd"] == 0.0
    assert d["resolution_audit"]["routes_reconcile"] is True
    assert d["resolution_audit"]["n_raw_mentions_recomputed"] == 6753
    assert d["verdict_direction"] in {"RESOLVED_SIDE_IS_SMALL",
                                      "RESOLVED_SIDE_IS_LARGE", "MIXED"}
    assert len(d["resolution_audit"]["sample_50"]["table"]) == 50


@pytest.mark.slow
def test_the_floored_panel_reproduces_the_w4b_training_universe():
    """The whole histogram is meaningless if it is drawn on a different universe."""
    if not C5.PANEL.exists():
        pytest.skip(f"{C5.PANEL} absent")
    p, full, rep = C5.load_floored_panel()
    assert rep["rows_before"] == 925757 and rep["names_before"] == 8981
    assert rep["rows_after"] == 530447 and rep["names_after"] == 6546
    assert len(full) == 925757
