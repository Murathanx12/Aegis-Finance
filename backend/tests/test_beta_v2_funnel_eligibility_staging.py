"""Compare the original stage1 code in an isolated test namespace, offline."""
from copy import deepcopy
import io
import json
from types import FunctionType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend.services import funnel_eligibility_staging as E
from backend.services import funnel_price_bridge as B
from backend.services import funnel_staging as S
from backend.services import opportunity_funnel as F
from backend.tests import test_beta_v2_funnel_price_bridge as P


@pytest.fixture
def bundle():
    return P.bundle.__wrapped__()


def oracle(close, volume, keep=F.STAGE1_KEEP):
    """Use original code, private globals/failure ledger, and injected test prices."""
    original_fetch = F._batch_history
    original_failures = deepcopy(F.STAGE_FAILURES)
    namespace = dict(F.stage1.__globals__)
    namespace.update(_batch_history=lambda tickers: {"close": close, "volume": volume},
                     STAGE_FAILURES={}, logger=SimpleNamespace(info=lambda *args: None))
    original = FunctionType(F.stage1.__code__, namespace, F.stage1.__name__,
                            F.stage1.__defaults__, F.stage1.__closure__)
    original.__kwdefaults__ = deepcopy(F.stage1.__kwdefaults__)
    result = original(list(close.columns), keep=keep)
    assert F._batch_history is original_fetch
    assert F.STAGE_FAILURES == original_failures
    return [c.to_dict() for c in result], namespace["STAGE_FAILURES"]


def frames(count=13, rows=251, *, tied=False):
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=rows)
    # Reverse column order exercises stable ties rather than accidental sorting.
    names = [f"T{i:02d}" for i in reversed(range(count))]
    close = pd.DataFrame({s: np.linspace(10, 11, rows) for s in names}, index=idx)
    volume = pd.DataFrame({s: 300000 if tied else 300000 + i * 100000
                           for i, s in enumerate(names)}, index=idx)
    return close, volume


@pytest.mark.parametrize("keep", [1, 4, 5, 6, 7, 12, F.STAGE1_KEEP])
@pytest.mark.parametrize("tied", [False, True])
def test_exact_candidate_fields_order_and_original_stratification_warning(keep, tied):
    close, volume = frames(tied=tied)
    expected, warning = oracle(close, volume, keep)
    selected, decisions, actual_warning = E._original_stage1(close, volume, keep)
    assert [c.to_dict() for c in selected] == expected
    assert actual_warning == warning
    assert [r["ticker"] for r in decisions] == list(close.columns)
    assert sum(r["status"] == "eligible_kept" for r in decisions) == len(selected)
    if keep < len(close.columns):
        assert any(r["status"] == "eligible_not_scored" for r in decisions)
        assert "never scored" in actual_warning["stage1_truncated"]
        if keep == 5:
            # The same size-band sample includes less-liquid survivors.
            assert {c.ticker for c in selected} != set(volume.iloc[-1].nlargest(keep).index)


@pytest.mark.parametrize("rows", [199, 200, 249, 250])
def test_original_history_and_display_momentum_boundaries(rows):
    close, volume = frames(count=2, rows=rows)
    expected, warning = oracle(close, volume)
    selected, decisions, actual_warning = E._original_stage1(close, volume, F.STAGE1_KEEP)
    assert [c.to_dict() for c in selected] == expected
    assert actual_warning == warning
    if rows < F.MIN_HISTORY_DAYS:
        assert all(r["reason"] == "insufficient_history" for r in decisions)
    elif rows < 250:
        assert all(c.mom_12_1 is None for c in selected)
    else:
        assert all(c.mom_12_1 is not None for c in selected)


def test_original_price_liquidity_and_alignment_boundaries():
    close, volume = frames(count=9)
    names = list(close.columns)
    for name, price, vol in zip(names[:6], [3, 2000, 2.999, 2000.001, 10, 10],
                                [1000000, 100000, 1000000, 100000, 199999, 200000]):
        close[name] = price
        volume[name] = vol
    del volume[names[6]]
    volume.loc[volume.index[-40:], names[7]] = np.nan
    close.loc[close.index[:60], names[8]] = np.nan
    expected, warning = oracle(close, volume)
    selected, decisions, actual_warning = E._original_stage1(close, volume, F.STAGE1_KEEP)
    assert [c.to_dict() for c in selected] == expected
    assert actual_warning == warning
    by_name = {r["ticker"]: r for r in decisions}
    assert by_name[names[0]]["status"] == by_name[names[1]]["status"] == "eligible_kept"
    assert by_name[names[4]]["status"] == "filtered"
    assert by_name[names[5]]["status"] == "eligible_kept"
    assert by_name[names[6]]["reason"] == "volume_missing"


def test_public_adapter_keeps_full_parent_and_immutable_private_receipt(bundle):
    m, files = bundle
    old = deepcopy((m, files, F.STAGE_FAILURES))
    result = E.stage_original_eligibility(manifest=m, artifacts=files, keep=1)
    report = result.report
    assert report["accounting_complete"] and report["eligibility_complete"]
    assert report["universe"] == m["universe"]
    assert report["eligible_count"] == 2 and report["selected_count"] == 1
    assert {r["ticker"] for r in report["outcomes"]} == {"AAA", "BBB"}
    assert {r["status"] for r in report["outcomes"]} == {"eligible_kept", "eligible_not_scored"}
    assert not report["promotion_eligible"] and not report["full_funnel_complete"]
    assert set(report["downstream"].values()) == {"not_evaluated"}
    assert report["price_stage_sha256"] == P.sha(B.stage_verified_prices(manifest=m, artifacts=files).payload)
    assert (m, files, F.STAGE_FAILURES) == old
    report["candidates"].clear()
    m["universe"]["tickers"].clear()
    assert len(result.report["candidates"]) == 1
    assert len(result.report["universe"]["tickers"]) == 2


def change_closes(m, files, values):
    raw = json.loads(files["history-B000001.json"])
    frame = raw["AAA"]
    position = frame["columns"].index("Close")
    for row, value in zip(frame["data"], values):
        row[position] = value
    files["history-B000001.json"] = P.encode(raw)
    coverage = json.loads(files["funnel-price-staging/price.json"])
    last = frame["data"][-1]
    cv = pd.DataFrame({"Close": [last[position]],
                       "Volume": [last[frame["columns"].index("Volume")]]},
                      index=pd.to_datetime([frame["original_session_dates"][-1]]))
    summary = S._frame(cv, cv.index[0].date(), cv.index[0].date(), 1)
    coverage["outcomes"][0].update(summary)
    files["funnel-price-staging/price.json"] = P.encode(coverage)
    P.reseal(m, files)


def test_public_adapter_records_price_exclusion_without_shrinking_domain(bundle):
    m, files = bundle
    change_closes(m, files, [2.0] * len(m["required_sessions"]))
    report = E.stage_original_eligibility(manifest=m, artifacts=files).report
    assert report["eligibility_complete"]
    assert report["universe"]["n"] == 2
    assert report["selected_count"] == report["eligible_count"] == 1
    assert report["outcomes"][0] == {"ticker": "AAA", "status": "filtered",
                                         "reason": "price_outside_original_range_or_nonfinite"}


@pytest.mark.parametrize("change", ["missing_symbol", "short_history", "malformed_json", "partial"])
def test_price_unknowns_refuse_eligibility_without_removing_any_parent_name(bundle, change):
    m, files = bundle
    if change in ("missing_symbol", "short_history"):
        raw = json.loads(files["history-B000001.json"])
        if change == "missing_symbol":
            del raw["AAA"]
        else:
            for field in ("data", "index", "original_session_dates"):
                del raw["AAA"][field][0]
        files["history-B000001.json"] = P.encode(raw)
        P.reseal(m, files)
    elif change == "malformed_json":
        files["plan.json"] = b'[' * 2000 + b'0' + b']' * 2000
        P.reseal(m, files)
    else:
        acq = json.loads(files["acquisition.json"])
        acq["status"] = "REFUSED"
        P.reseal(m, files, acquisition=acq)
    with pytest.raises(E.EligibilityRefused) as caught:
        E.stage_original_eligibility(manifest=m, artifacts=files)
    report = caught.value.report
    assert not report["eligibility_complete"]
    assert not report["promotion_eligible"]
    assert not report["candidates"]
    assert {r["ticker"] for r in report["outcomes"]} == {"AAA", "BBB"}
    assert "ineligible" not in {r["status"] for r in report["outcomes"]}


def test_finite_raw_prices_cannot_produce_nonfinite_candidate_receipt(bundle):
    m, files = bundle
    change_closes(m, files, [1e-300, 1e300] + [11.0] * (len(m["required_sessions"]) - 2))
    assert B.stage_verified_prices(manifest=m, artifacts=files).report["complete"]
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        with pytest.raises(E.EligibilityRefused) as caught:
            E.stage_original_eligibility(manifest=m, artifacts=files)
    report = caught.value.report
    assert not report["eligibility_complete"]
    assert report["candidates"] == []
    json.dumps(report, allow_nan=False)  # The refusal itself remains serializable.


@pytest.mark.parametrize("keep", [0, -1, True, 1.5])
def test_invalid_keep_is_an_explicit_refusal(bundle, keep):
    m, files = bundle
    with pytest.raises(E.EligibilityRefused):
        E.stage_original_eligibility(manifest=m, artifacts=files, keep=keep)


def test_missing_contract_and_verified_execution_have_zero_external_calls(bundle, monkeypatch):
    import builtins
    from pathlib import Path
    import subprocess

    m, files = bundle
    original_fetch, original_run = F._batch_history, F.run
    failures = deepcopy(F.STAGE_FAILURES)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("unexpected I/O")

    with monkeypatch.context() as patch:
        for target, name in [(builtins, "open"), (io, "open"), (Path, "open"), (subprocess, "Popen")]:
            patch.setattr(target, name, forbidden)
        try:
            with pytest.raises(E.EligibilityRefused):
                E.stage_original_eligibility(manifest={}, artifacts={})
            assert E.stage_original_eligibility(manifest=m, artifacts=files).report["eligibility_complete"]
        finally:
            assert calls == []
    assert F._batch_history is original_fetch and F.run is original_run
    assert F.STAGE_FAILURES == failures
