"""The three consumers of L2's typed rows: E1's head, X3's grader, X2's mapping.

The point of all three is that the CHANGED VARIABLE is how an event was typed and
nothing else. So the head's feature table must have the same shape from typed
rows as from the proxy (only the values differ), the grader must key on the same
`event_type` the extractor emits, and X2's C1 mapping must refuse the kinds it
cannot type rather than forcing them.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend.services import event_vocabulary as vocab
from backend.services import scenario_forecasts as sf
import learner.event_head as eh
from scripts import night_x2_elasticity as x2


# ------------------------------------------------------------------ E1's head

@pytest.fixture
def panel():
    dates = pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]).normalize()
    rows = []
    for d in dates:
        for sym in ("ACME", "WIDGET"):
            rows.append({"symbol": sym, "entry_date": d,
                         "text": "Acme board authorizes new $1B share buyback program",
                         "pit_dv_21": 1e7, "mom_21": 0.01, "mom_5": 0.0})
    return pd.DataFrame(rows)


def _typed_file(tmp_path, rows):
    d = tmp_path / "typed_events"
    d.mkdir(exist_ok=True)
    (d / "2026-09-13.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return d


def _typed_row(symbol="ACME", date="2026-09-01", event_type="stock_buyback",
               direction=1, bucket="SMALL", conf=0.85):
    return {"source": "alpaca_benzinga_news", "raw_id": f"{symbol}{date}",
            "first_seen_utc": f"{date}T12:00:00+00:00", "document_date": date,
            "scope": symbol, "scope_kind": "ticker", "tickers": [symbol],
            "event_type": event_type, "direction": direction,
            "magnitude_bucket": bucket, "confidence": conf,
            "evidence_span": "board authorizes", "prompt_hash": "a" * 64,
            "vocabulary_hash": vocab.VOCABULARY_HASH}


def test_the_feature_table_has_the_same_shape_from_typed_rows_and_from_the_proxy(panel, tmp_path):
    """The only variable E1 may change between the arms is HOW the events were
    typed. A different column set would make the comparison a comparison of two
    models."""
    proxy = eh.extract_events(panel[["symbol", "entry_date", "text"]])
    typed_dir = _typed_file(tmp_path, [_typed_row(sym, d) for sym in ("ACME", "WIDGET")
                                       for d in ("2026-09-01", "2026-09-02")])
    typed, meta = eh.typed_events(panel, typed_dir)
    assert meta["event_source"] == eh.TYPED_L2
    assert list(proxy.columns) == list(typed.columns)

    Xp, mp = eh.build_features(panel, proxy, min_occurrences=1)
    Xt, mt = eh.build_features(panel, typed, min_occurrences=1)
    assert list(Xp.columns) == list(Xt.columns)
    assert Xp.shape == Xt.shape
    assert Xp.index.equals(Xt.index)


def test_events_for_panel_prefers_l2_and_names_which_ran(panel, tmp_path):
    ev, meta = eh.events_for_panel(panel, directory=tmp_path / "nothing_here")
    assert meta["event_source"] == eh.KEYWORD_PROXY
    assert "proxy_note" in meta and len(ev) > 0

    typed_dir = _typed_file(tmp_path, [_typed_row("ACME", "2026-09-01")])
    ev2, meta2 = eh.events_for_panel(panel, directory=typed_dir)
    assert meta2["event_source"] == eh.TYPED_L2
    assert set(ev2["basis"]) == {eh.TYPED_L2}


def test_a_typed_row_lands_on_the_first_session_strictly_after_its_own_date(panel, tmp_path):
    typed_dir = _typed_file(tmp_path, [_typed_row("ACME", "2026-09-01")])
    ev, _ = eh.typed_events(panel, typed_dir)
    assert len(ev) == 1
    assert ev.iloc[0]["entry_date"] == pd.Timestamp("2026-09-02")


def test_a_typed_row_after_the_panel_is_dropped_and_counted(panel, tmp_path):
    typed_dir = _typed_file(tmp_path, [_typed_row("ACME", "2026-09-03"),
                                       _typed_row("NOTINPANEL", "2026-09-01")])
    ev, meta = eh.typed_events(panel, typed_dir)
    assert len(ev) == 0
    assert meta["dropped_date_after_panel"] == 1
    assert meta["dropped_symbol_not_in_panel"] == 1


def test_a_multi_ticker_typed_row_is_not_fanned_out(panel, tmp_path):
    row = _typed_row("ACME", "2026-09-01")
    row["tickers"] = ["ACME", "WIDGET"]
    typed_dir = _typed_file(tmp_path, [row])
    ev, meta = eh.typed_events(panel, typed_dir)
    assert list(ev["symbol"]) == ["ACME"]
    assert meta["tickers_seen_but_not_emitted"] == 1


def test_refusal_rows_are_not_read_as_types(panel, tmp_path):
    d = _typed_file(tmp_path, [_typed_row("ACME", "2026-09-01")])
    (d / "2026-09-13_refusals.jsonl").write_text(
        json.dumps({"source": "x", "reason": "REFUSED_SCHEMA", "scope": "ACME"}) + "\n",
        encoding="utf-8")
    ev, _ = eh.typed_events(panel, d)
    assert len(ev) == 1


# ------------------------------------------------------------------ X3's grader

def test_the_grader_matches_a_planted_scenario_from_a_typed_row():
    scenarios = [
        {"headline": "Acme raises guidance", "probability": 0.5,
         "event_type": "guidance_change", "direction": 1, "magnitude_bucket": "MODERATE"},
        {"headline": "Acme announces a buyback", "probability": 0.3,
         "event_type": "stock_buyback", "direction": 1, "magnitude_bucket": "SMALL"},
        {"headline": "nothing happens", "probability": 0.2,
         "event_type": "no_event", "direction": 0, "magnitude_bucket": "NEGLIGIBLE"},
    ]
    sset = {"symbol": "ACME", "as_of": "2026-09-01", "scenarios": scenarios}
    typed = [_typed_row("ACME", "2026-09-01", "stock_buyback", 1, "SMALL", 0.85),
             _typed_row("WIDGET", "2026-09-01", "guidance_change", 1, "MODERATE", 0.9),
             _typed_row("ACME", "2026-09-02", "guidance_change", 1, "MODERATE", 0.9)]
    realised = sf.realised_from_typed_rows(typed, symbol="ACME", as_of="2026-09-01")
    assert [r["event_type"] for r in realised] == ["stock_buyback"], (
        "another symbol's row and another day's row must not reach the grade")
    graded = sf.grade_set(sset, realised)
    assert graded["realised_event_type"] == "stock_buyback"
    assert graded["matched_index"] == 1
    assert graded["brier"] == pytest.approx(
        (0.5 - 0) ** 2 + (0.3 - 1) ** 2 + (0.2 - 0) ** 2)


def test_the_grader_reads_the_dominant_row_when_a_day_has_two():
    typed = [_typed_row("ACME", "2026-09-01", "litigation_filed", -1, "SMALL", 0.8),
             _typed_row("ACME", "2026-09-01", "bankruptcy_or_going_concern", -1,
                        "EXTREME", 0.6)]
    realised = sf.realised_from_typed_rows(typed, symbol="ACME", as_of="2026-09-01")
    assert len(realised) == 2
    assert sf.dominant_event(realised)["event_type"] == "bankruptcy_or_going_concern"


def test_a_typed_row_outside_the_vocabulary_never_reaches_the_grader():
    row = _typed_row("ACME", "2026-09-01")
    row["event_type"] = "short_interest_squeeze"        # in no vocabulary version
    assert sf.realised_from_typed_rows([row], symbol="ACME", as_of="2026-09-01") == []


def test_the_grader_and_the_extractor_share_one_vocabulary():
    from backend.services import event_extraction as ex
    assert sf.EVENT_TYPES is vocab.EVENT_TYPES
    assert ex.SCHEMA["properties"]["event_type"]["enum"] == list(sf.EVENT_TYPES)


# ------------------------------------------------------------- X2's C1 mapping

def _c1(kind, direction="POSITIVE", magnitude="MEDIUM"):
    return {"uid": "u", "event_type": kind, "direction": direction,
            "magnitude": magnitude, "counterfactuals": []}


def test_only_the_kinds_whose_mapping_is_a_function_are_mapped():
    rows = [_c1("EARNINGS"), _c1("GUIDANCE"), _c1("M&A"), _c1("PRODUCT"),
            _c1("ANALYST"), _c1("LEGAL"), _c1(None)]
    out = x2.c1_vocabulary_mapping(rows)
    assert out["mapped_by_vocabulary_id"] == {"earnings_report": 1,
                                              "mergers_acquisitions": 1,
                                              "guidance_change": 1}
    assert set(out["unmapped_kinds"]) == {"PRODUCT", "LEGAL"}
    assert out["rows_with_no_kind"] == 1
    assert all(v in vocab.EVENT_TYPES for v in out["mapped_by_vocabulary_id"])


def test_analyst_maps_to_the_v2_FAMILY_and_is_counted_separately():
    """v1 could type none of C1's largest kind. v2 can type it at the mechanism
    level -- and family coverage is NOT id coverage, so the two counts stay
    apart rather than being added into one flattering number."""
    rows = [_c1("EARNINGS")] + [_c1("ANALYST") for _ in range(4)]
    out = x2.c1_vocabulary_mapping(rows)
    assert out["vocabulary_version"] == vocab.VOCABULARY_VERSION == 2
    assert out["mapped_rows"] == 1
    assert out["family_mapped_rows"] == 4
    assert out["family_mapped_kinds"] == {"ANALYST": 4}
    assert out["covered_rows"] == 5 and out["covered_share"] == 1.0
    assert "ANALYST" not in out["unmapped_kinds"]
    assert all(v in vocab.EVENT_TYPES
               for v in out["family_members"]["ANALYST"])


def test_a_family_may_not_span_opposite_direction_priors():
    """The rule that keeps PRODUCT and FINANCING out of the family map: a family
    that spans opposite priors is a mapping pretending to be a coverage number."""
    for kind, ids in x2.C1_KIND_TO_FAMILY.items():
        priors = {vocab.by_id(i).direction_prior for i in ids}
        assert priors == {None}, (kind, priors)


def test_an_unclear_direction_is_not_coerced_to_zero():
    """0 means "real event, no directional implication by itself" in L2's
    contract. "The reader could not tell" is a different claim."""
    out = x2.c1_vocabulary_mapping([_c1("EARNINGS", direction="UNCLEAR"),
                                    _c1("EARNINGS", direction="NEGATIVE")])
    assert out["direction"] == {"signed": 1, "unclear": 1, "missing": 0}


def test_c1_medium_is_the_vocabularys_moderate():
    assert x2.C1_MAGNITUDE_TO_BUCKET["MEDIUM"] == "MODERATE"
    assert set(x2.C1_MAGNITUDE_TO_BUCKET.values()) <= set(vocab.MAGNITUDE_BUCKETS)
    out = x2.c1_vocabulary_mapping([_c1("EARNINGS", magnitude="MEDIUM"),
                                    _c1("EARNINGS", magnitude=None)])
    assert out["magnitude_buckets"]["MODERATE"] == 1
    assert out["magnitude_buckets"]["unmapped"] == 1


def test_every_mapped_id_and_every_named_candidate_is_a_real_vocabulary_id():
    named = set()
    for reason in x2.C1_KIND_UNMAPPED.values():
        for token in reason.replace("/", " ").split():
            if token.strip(",.") in vocab.EVENT_TYPES:
                named.add(token.strip(",."))
    # every candidate the reasons name must exist; a typo would quietly widen a
    # mapping nobody can find
    assert named, "the unmapped reasons name no vocabulary id at all"
    assert named <= set(vocab.EVENT_TYPES)
    assert np.all([v in vocab.EVENT_TYPES for v in x2.C1_KIND_TO_VOCABULARY.values()])
