"""Chunk 20 T3 — the five variables and their nulls, on synthetic rows.

Offline throughout: the social rows, the typed rows, the price bars and the
model reader are all injected, and nothing under `backend/data` is read.

What is pinned, and each is a way a column could be computed and be wrong:

  1. velocity is computed PER SOURCE — pooling before the ratio hides which
     platform moved, which is the only thing the ratio is for;
  2. a zero baseline is `None`, not `inf` and not 1.0: "first ever mention" and
     "ten times its usual" are different facts;
  3. the shuffled-ticker null PRESERVES the day's volume and destroys the
     ticker — if it did not preserve volume it would be a different null;
  4. dispersion reports entropy AND variance, because entropy over three bins
     saturates and would read 40/30/30 as 34/33/33;
  5. the matched-day null is a DRAW, and it says when the count could not be
     matched instead of pretending it was;
  6. the trailing return ends STRICTLY BEFORE the feature date;
  7. the stance ENUM is in the literal wire text, not only in the validator;
  8. with no reader listening the job refuses PENDING_MODEL with the candidate
     list frozen and hashed, and starts no server;
  9. a variable that cannot be computed is NAMED as refused rather than
     silently absent — a family that declared five and reported three is a
     different family;
 10. RUN_DATE is derived, never a literal.
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from scripts import night_social_features as SF


def _utc(day: str, hour: int = 15) -> str:
    """A UTC stamp whose EASTERN date is `day` (15:00 UTC = 11:00 ET)."""
    return f"{day}T{hour:02d}:00:00+00:00"


def _row(day, kind="comment", rid="c1", tickers=("NVDA",), source="reddit",
         text="whatever", parent_id="t3_p1"):
    return {"source": source, "kind": kind, "first_seen_utc": _utc(day),
            "id": rid, "parent_id": parent_id, "channel": "r/x",
            "author_pseudonym": "u", "title": "", "text": text, "url": "",
            "created_utc_provider": "", "ticker_mentions": list(tickers),
            "ticker_rules": {t: "cashtag" for t in tickers},
            "engagement": {}, "pit_grade": "index_state"}


DAY = "2026-09-19"


def _baseline_rows(ticker="NVDA", per_day=1, days=60, source="reddit"):
    """One mention a day for `days` days before DAY."""
    end = date.fromisoformat(DAY)
    out = []
    for i in range(1, days + 1):
        d = (end - timedelta(days=i)).isoformat()
        for k in range(per_day):
            out.append(_row(d, kind="post", rid=f"t3_{ticker}{i}_{k}",
                            tickers=(ticker,), source=source))
    return out


# --------------------------------------------------------------------------
# dates and RUN_DATE


def test_the_feature_date_is_the_eastern_date_of_our_own_stamp():
    # 03:00 UTC on the 19th is still the 18th in New York.
    assert SF.row_date({"first_seen_utc": "2026-09-19T03:00:00+00:00"}) == "2026-09-18"
    assert SF.row_date({"first_seen_utc": "2026-09-19T15:00:00+00:00"}) == "2026-09-19"
    assert SF.row_date({}) == ""


def test_run_date_is_derived_and_never_a_literal():
    """2026-09-18: three idle-queue jobs dated their outputs by literal and
    overwrote committed receipts three nights running."""
    src = Path(SF.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "RUN_DATE" in names:
                assert not isinstance(node.value, ast.Constant), \
                    "RUN_DATE must be env-or-today, never a literal"
                assert "getenv" in ast.dump(node.value)


# --------------------------------------------------------------------------
# 1. mention velocity and its null


def test_velocity_is_the_count_over_its_own_sixty_day_baseline():
    rows = _baseline_rows(per_day=1) + [
        _row(DAY, kind="post", rid=f"t3_today{i}", tickers=("NVDA",))
        for i in range(10)]
    vel = SF.mention_velocity(SF.mention_table(rows), day=DAY)
    cell = vel[("reddit", "NVDA")]
    assert cell["n"] == 10
    assert cell["baseline_per_day"] == pytest.approx(1.0)
    assert cell["velocity"] == pytest.approx(10.0)


def test_a_zero_baseline_is_none_and_not_infinity():
    rows = [_row(DAY, kind="post", rid="t3_new", tickers=("ABCD",))]
    vel = SF.mention_velocity(SF.mention_table(rows), day=DAY)
    cell = vel[("reddit", "ABCD")]
    assert cell["n"] == 1
    assert cell["velocity"] is None, \
        "'first ever mention' and 'ten times its usual' are different facts"


def test_velocity_is_computed_separately_per_source():
    rows = (_baseline_rows(source="reddit") + _baseline_rows(source="youtube")
            + [_row(DAY, kind="post", rid="t3_r", source="reddit"),
               _row(DAY, kind="post", rid="t3_y1", source="youtube"),
               _row(DAY, kind="post", rid="t3_y2", source="youtube"),
               _row(DAY, kind="post", rid="t3_y3", source="youtube")])
    vel = SF.mention_velocity(SF.mention_table(rows), day=DAY)
    assert vel[("reddit", "NVDA")]["velocity"] == pytest.approx(1.0)
    assert vel[("youtube", "NVDA")]["velocity"] == pytest.approx(3.0)
    assert ("pooled", "NVDA") not in vel


def test_a_row_naming_three_tickers_is_three_mentions():
    rows = [_row(DAY, kind="post", rid="t3_x", tickers=("NVDA", "AMD", "INTC"))]
    assert len(SF.mention_table(rows)) == 3


def test_the_shuffled_null_preserves_the_days_volume_and_destroys_the_ticker():
    """THE DEFECT THIS TEST FOUND. The first implementation permuted the ticker
    LABELS of a day's mentions — which permutes a multiset, so twenty NVDA and
    ten AMD came back as twenty NVDA and ten AMD and the control equalled what
    it was controlling exactly. The null has to break the pairing between
    today's count and THAT NAME'S OWN history, so the day's distinct tickers
    are relabelled instead."""
    rows = (_baseline_rows("NVDA") + _baseline_rows("AMD")
            + [_row(DAY, kind="post", rid=f"t3_n{i}", tickers=("NVDA",))
               for i in range(20)]
            + [_row(DAY, kind="post", rid="t3_a", tickers=("AMD",))])
    mentions = SF.mention_table(rows)
    real = SF.mention_velocity(mentions, day=DAY)
    null = SF.shuffled_ticker_null(mentions, day=DAY, seed=7)
    assert sum(c["n"] for c in real.values()) == sum(c["n"] for c in null.values()), \
        "aggregate volume must survive the shuffle, or it is a different null"
    assert sorted(c["n"] for c in real.values()) == sorted(c["n"] for c in null.values()), \
        "the day's count VECTOR survives; only which name carries it changes"
    assert real[("reddit", "NVDA")]["n"] == 20
    # Over the seeds a real run draws, the 20 must sometimes land on AMD.
    landed = {SF.shuffled_ticker_null(mentions, day=DAY, seed=s
                                      )[("reddit", "NVDA")]["n"] for s in range(12)}
    assert landed != {20}, "the ticker-specific concentration must not always survive"


def test_the_shuffle_is_reproducible_from_its_declared_seed():
    rows = (_baseline_rows("NVDA") + _baseline_rows("AMD")
            + [_row(DAY, kind="post", rid=f"t3_n{i}",
                    tickers=("NVDA" if i % 3 else "AMD",)) for i in range(30)])
    m = SF.mention_table(rows)
    a = SF.shuffled_ticker_null(m, day=DAY, seed=11)
    b = SF.shuffled_ticker_null(m, day=DAY, seed=11)
    assert a == b
    # ...and a different seed draws a different control at least sometimes.
    assert any(SF.shuffled_ticker_null(m, day=DAY, seed=s) != a for s in range(12))


# --------------------------------------------------------------------------
# 2. stance dispersion


def test_dispersion_reports_both_entropy_and_variance():
    """Entropy over three bins saturates: 40/30/30 reads like 34/33/33. The
    variance is what keeps the spread of conviction."""
    a = SF.dispersion([-1] * 4 + [0] * 3 + [1] * 3)
    b = SF.dispersion([-1] * 34 + [0] * 33 + [1] * 33)
    assert abs(a["entropy"] - b["entropy"]) < 0.02, "entropy cannot tell them apart"
    c = SF.dispersion([-1] * 5 + [1] * 5)
    d = SF.dispersion([0] * 10)
    assert c["variance"] > d["variance"] == 0.0
    assert c["entropy"] < a["entropy_max"]


def test_dispersion_of_nothing_is_none_and_not_zero():
    got = SF.dispersion([])
    assert got["n"] == 0 and got["entropy"] is None and got["variance"] is None


def test_the_stance_enum_is_on_the_wire_not_only_in_the_validator():
    """2026-09-13: a prompt said 'matching the schema you have been given' and
    the enum lived only in the validator; 54% of the first flush came back with
    values the model had never been shown."""
    wire = SF.stance_wire_system()
    assert "-1, 0, 1" in wire
    assert '"enum"' in wire and "stance" in wire
    assert "bearish" in wire and "bullish" in wire
    assert SF.stance_prompt_hash() == SF.stance_prompt_hash()


def test_a_bad_reply_is_a_refusal_and_never_a_coerced_neutral():
    """A bad reply silently read as 0 would move the dispersion number it was
    supposed to be excluded from."""
    assert SF.parse_stance("")["refused"] == "REFUSED_UNPARSEABLE"
    assert SF.parse_stance("not json")["refused"] == "REFUSED_UNPARSEABLE"
    assert SF.parse_stance('{"stance": 2, "stance_confidence": 1}')["refused"] == "REFUSED_SCHEMA"
    assert SF.parse_stance('{"stance": "bullish", "stance_confidence": 1}')["refused"] == "REFUSED_SCHEMA"
    assert SF.parse_stance('{"stance": 1, "stance_confidence": 5}')["refused"] == "REFUSED_SCHEMA"
    good = SF.parse_stance('```json\n{"stance": -1, "stance_confidence": 0.8}\n```')
    assert good["stance"] == -1 and good["stance_confidence"] == 0.8


def test_the_matched_day_null_says_when_it_could_not_match():
    rows = [_row("2026-09-10", rid=f"c{i}") for i in range(3)]
    got = SF.matched_day_null(rows, day=DAY, counts={"NVDA": 10}, seed=3)
    assert got["NVDA"]["matched"] is False
    assert "fewer comments" in got["NVDA"]["why"]
    assert got["NVDA"]["available"] == 3


def test_the_matched_day_null_draws_another_day_of_the_same_ticker():
    rows = ([_row("2026-09-10", rid=f"a{i}") for i in range(6)]
            + [_row(DAY, rid=f"t{i}") for i in range(4)])
    got = SF.matched_day_null(rows, day=DAY, counts={"NVDA": 4}, seed=3)
    assert got["NVDA"]["matched"] is True
    assert got["NVDA"]["day"] != DAY, "the null must not be drawn from the day itself"
    assert len(got["NVDA"]["comment_ids"]) == 4


def test_a_ticker_with_no_other_day_is_named_rather_than_dropped():
    got = SF.matched_day_null([_row(DAY, rid="c1")], day=DAY,
                              counts={"NVDA": 2}, seed=3)
    assert got["NVDA"]["matched"] is False
    assert "no comment on any other day" in got["NVDA"]["why"]


def test_candidates_are_comments_only_and_frozen_reproducibly():
    rows = [_row(DAY, kind="post", rid="t3_p1"),
            _row(DAY, kind="comment", rid="t1_c2"),
            _row(DAY, kind="comment", rid="t1_c1")]
    units = SF.stance_candidates(rows, day=DAY)
    assert [u["id"] for u in units] == ["t1_c1", "t1_c2"], \
        "a post is the thing being debated, not a vote in the debate"
    assert SF.fingerprint(units)["sha256"] == SF.fingerprint(list(reversed(units)))["sha256"]


# --------------------------------------------------------------------------
# 3. hype lateness


def _bars(symbol="NVDA", n=40, start="2026-08-01", step=1.0):
    import pandas as pd
    d0 = datetime.fromisoformat(start)
    return pd.DataFrame({
        "symbol": [symbol] * n,
        "date": [d0 + timedelta(days=i) for i in range(n)],
        "close": [100.0 + i * step for i in range(n)],
        "open": [100.0 + i * step for i in range(n)],
        "volume": [1_000_000] * n,
    })


def test_the_trailing_window_ends_strictly_before_the_feature_date():
    """Defect #5 of 2026-09-10: a window that includes the day it describes has
    already seen the day it is describing."""
    import pandas as pd
    bars = _bars(n=40, start="2026-08-01")
    # A huge close ON the feature date must not move the trailing number.
    poisoned = pd.concat([bars, pd.DataFrame({
        "symbol": ["NVDA"], "date": [pd.Timestamp("2026-09-19")],
        "close": [10_000.0], "open": [10_000.0], "volume": [1]})])
    clean, _ = SF.trailing_returns("2026-09-19", ["NVDA"], bars=bars)
    dirty, _ = SF.trailing_returns("2026-09-19", ["NVDA"], bars=poisoned)
    assert clean["NVDA"] == dirty["NVDA"]


def test_absent_bars_refuse_by_name_with_the_path(tmp_path, monkeypatch):
    monkeypatch.setattr(SF, "_data_root", lambda: tmp_path)
    got, meta = SF.trailing_returns(DAY, ["NVDA"])
    assert got == {}
    assert meta["refused"] == "NO_BARS"
    assert "bars.parquet" in meta["path"]


def test_percentile_rank_is_cross_sectional_within_the_day():
    pct = SF.percentile_rank({"A": 1.0, "B": 2.0, "C": 3.0})
    assert pct["C"] == 1.0 and pct["A"] == pytest.approx(1 / 3)
    assert SF.percentile_rank({}) == {}


# --------------------------------------------------------------------------
# 4/5. the typed rows


def _typed(ticker="NVDA", source="sec_edgar_8k_ex99_body", supplier="",
           named_input="HBM supply", event=SF.CONSTRAINT_ID):
    return {"source": source, "event_type": event, "tickers": [ticker],
            "document_date": DAY, "first_seen_utc": _utc(DAY),
            "url": "https://example.invalid/x",
            "entities": ({"supplier": supplier, "named_input": named_input}
                         if supplier else {"named_input": named_input})}


def test_the_constraint_count_reads_what_l2_typed_and_calls_no_model():
    rows = [_typed(), _typed(), _typed("AMD"),
            _typed(event="earnings_report")]
    typed, _ = SF.load_typed_rows(rows=[r for r in rows
                                        if r["event_type"] == SF.CONSTRAINT_ID])
    assert SF.constraint_counts(typed) == {"NVDA": 2, "AMD": 1}


def test_the_constraint_id_is_read_from_the_vocabulary_not_retyped():
    from backend.services import event_vocabulary as vocab
    assert SF.CONSTRAINT_ID in {t.id for t in vocab.VOCABULARY_V3}
    assert SF.CONSTRAINT_ID in vocab.IDS_WITH_ENTITIES


def test_supplier_links_come_only_from_an_exhibit_body():
    """The Ex-99 FEED row carries no body and could never have produced a
    supplier mention; counting it would put rows in the denominator that had no
    chance to answer."""
    rows = [_typed(supplier="SK Hynix"),
            _typed(supplier="Also Hynix", source="sec_edgar_8k_current_atom"),
            _typed(supplier="", named_input="power")]
    got = SF.supplier_links(rows)
    assert list(got) == ["NVDA"]
    assert len(got["NVDA"]) == 1
    assert got["NVDA"][0]["supplier"] == "SK Hynix"
    assert got["NVDA"][0]["named_input"] == "HBM supply"


def test_absent_typed_rows_refuse_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(SF, "_data_root", lambda: tmp_path)
    rows, meta = SF.load_typed_rows()
    assert rows == [] and meta["refused"] == "NO_TYPED_ROWS"


# --------------------------------------------------------------------------
# the job


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(SF, "_data_root", lambda: tmp_path / "optimus")
    return tmp_path / "optimus" / "social"


def _complete(stances):
    """A fake reader returning the given stances in order."""
    seq = list(stances)
    seen: list[dict] = []

    class Reply:
        def __init__(self, text):
            self.text = text
            self.model = "fake-local"

    def complete(backend, prompt, system="", **kw):
        seen.append({"system": system, "prompt": prompt})
        s = seq[len(seen) - 1] if len(seen) <= len(seq) else 0
        return Reply(json.dumps({"stance": s, "stance_confidence": 0.7,
                                 "evidence_span": "x"}))
    complete.seen = seen
    return complete


def test_no_social_rows_refuses_every_variable_by_name(out):
    got = SF.S1_social_features(run_date=DAY)
    assert got["rows"] == 0
    assert set(got["variables"]) == set(SF.VARIABLES), \
        "a family that declared five and reported three is a different family"
    assert {v["refused"] for v in got["variables"].values()} == {"NO_SOCIAL_ROWS"}
    assert "NO_SOCIAL_ROWS" in got["headline"]


def test_pending_model_freezes_and_hashes_the_candidate_list(out, monkeypatch):
    monkeypatch.setattr(SF, "probe_reader", lambda backend="local_gguf":
                        "ProviderRefusal: nothing is listening on 8080")
    rows = _baseline_rows() + [_row(DAY, rid=f"t1_c{i}") for i in range(6)]
    got = SF.S1_social_features(run_date=DAY, social_rows=rows, typed_rows=[])
    block = got["variables"]["stance_dispersion"]
    assert block["refused"] == "PENDING_MODEL"
    assert block["candidates"]["n_units"] == 6
    assert len(block["candidates"]["sha256"]) == 16
    assert "nothing is listening" in block["why"]
    # ...and the four variables that need no model still computed.
    assert got["variables"]["mention_velocity"]["computed"] is True


def test_the_job_never_starts_a_server():
    """It probes and refuses. A job that started the server it found missing
    would take the GPU out from under whatever else is using it."""
    src = Path(SF.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"start", "stop", "ensure_model_server"}, \
                f"line {node.lineno}: this job may not own a server's lifetime"


def test_a_full_pass_writes_a_joinable_table(out):
    rows = (_baseline_rows()
            + [_row(DAY, kind="post", rid=f"t3_n{i}") for i in range(10)]
            + [_row(DAY, rid=f"t1_c{i}", text=f"comment {i}") for i in range(6)])
    got = SF.S1_social_features(
        run_date=DAY, social_rows=rows,
        typed_rows=[_typed(supplier="SK Hynix")],
        bars=_bars(n=40, start="2026-08-01"),
        complete=_complete([1, 1, -1, 0, -1, 1]))
    assert got["rows"] == 1
    assert got["variables"]["stance_dispersion"]["computed"] is True
    assert got["variables"]["stance_dispersion"]["typed"] == 6

    import pandas as pd
    frame = pd.read_parquet(SF.features_path(DAY))
    assert list(frame["ticker"]) == ["NVDA"]
    row = frame.iloc[0]
    assert row["date"] == DAY
    # 10 posts + 6 comments, all naming NVDA, over a 1.0/day baseline. A
    # COMMENT is a mention: the variable is "how much is this name being talked
    # about", not "how many threads were started about it".
    assert row["mention_velocity_reddit"] == pytest.approx(16.0)
    assert row["mention_velocity_null_reddit"] is not None
    assert row["stance_n"] == 6
    assert row["stance_entropy"] > 0 and row["stance_variance"] > 0
    assert row["growth_constraint_cited_n"] == 1
    assert row["supplier_link_n"] == 1
    assert row["supplier_named_inputs"] == "HBM supply"
    assert row["trailing_20d_return"] is not None


def test_every_variable_carries_its_null_on_the_receipt(out):
    rows = (_baseline_rows()
            + [_row(DAY, kind="post", rid=f"t3_n{i}") for i in range(10)]
            + [_row(DAY, rid=f"t1_c{i}") for i in range(6)])
    got = SF.S1_social_features(run_date=DAY, social_rows=rows,
                                typed_rows=[_typed(supplier="X")],
                                bars=_bars(n=40, start="2026-08-01"),
                                complete=_complete([1] * 6))
    for name in ("mention_velocity", "stance_dispersion", "hype_lateness",
                 "supplier_link"):
        assert "null" in got["variables"][name], f"{name} has no null beside it"
    assert got["variables"]["mention_velocity"]["null"]["name"] == "shuffled_ticker"
    assert got["variables"]["stance_dispersion"]["null"]["name"] == "matched_day_count"
    assert got["variables"]["supplier_link"]["null"]["name"] == "same_sector_non_supplier"
    assert "NOT COMPUTED" in got["variables"]["supplier_link"]["null"]["status"]


def test_the_receipt_says_this_is_not_a_claim(out):
    got = SF.S1_social_features(run_date=DAY)
    assert "TRIALS" in got["not_a_claim"] or "ranks nothing" in got["not_a_claim"]
    assert got["llm_spend_usd"] == 0.0
    assert got["stage"] == "signal"
    assert got["seed"] == SF.SEED


def test_the_enum_reaches_the_fake_reader(out):
    """The wire, not the intention: the enum has to be in the system message
    the reader actually received."""
    rows = _baseline_rows() + [_row(DAY, rid="t1_c1")]
    complete = _complete([1])
    SF.S1_social_features(run_date=DAY, social_rows=rows, typed_rows=[],
                          bars=_bars(), complete=complete)
    assert complete.seen, "the reader was never called"
    assert "-1, 0, 1" in complete.seen[0]["system"]


def test_the_job_is_registered_with_its_stage():
    from scripts import night_factory_jobs as J
    assert "S1_social_features" in J.JOBS
    assert J.JOB_STAGES["S1_social_features"] == "signal"
