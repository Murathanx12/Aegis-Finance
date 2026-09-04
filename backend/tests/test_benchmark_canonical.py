"""The ruler is one module, and every new receipt must prove it used it.

WHAT THIS FILE DEFENDS
======================
On 2026-09-04 the program found that "+740% market vs +250.9% strategy" -- its
most-copied public number -- was measured against `^GSPC` (a PRICE index, no
dividends) with 66 OVERLAPPING 3-month windows compounded as if sequential.
The true dividend-inclusive value-weighted market over that window is +96.7%.
The overlap arithmetic was fixed five months ago (`726c7bf`, 2026-04-15) and the
document was never regenerated, so the void figure propagated into nine files.

The root cause was not arithmetic. It was that **"the market" had no single
definition anywhere in the repo**, so there was nothing a test could pin. This
file pins it:

1. `learner.benchmark` reproduces the anchor number exactly (+96.67%).
2. `compound()` REFUSES an overlapping series -- the +740% line of code cannot
   be written again without the refusal firing.
3. Every receipt under `tracker_backtest/` dated on or after
   `STAMP_REQUIRED_FROM` that quotes a market-relative return must carry a
   valid `market_benchmark` stamp naming this module.

WHY THERE IS A GRANDFATHER LIST AND WHY IT IS NAMED, NOT DATED
==============================================================
Seventeen existing receipts quote a market number and predate the module.
Sealed receipts are immutable -- retro-stamping them would be tampering with a
tamper-evident artefact -- and a gate that can only ever be red teaches the
reader to skim red lines (CLAUDE.md, `monday_gate_check`). So the exemption is
an explicit dict of filenames, each with the reason it is exempt. Every one of
them is already on the S38 void list. A new receipt is not in that dict, so it
is gated. The list may only shrink: when B1 re-issues a receipt under a new
name, the new name is gated and the old row stays as history.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pandas as pd
import pytest

from learner import benchmark as bm

REPO = Path(__file__).resolve().parents[2]
RECEIPTS = REPO / "backend" / "data" / "optimus" / "tracker_backtest"

#: filename -> why it is exempt. Predates `learner.benchmark`; sealed; and every
#: one is on the void list in docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md §2.
GRANDFATHERED: dict[str, str] = {
    "band_horizon_20260903.json": "S38 void (corrupted ratio); superseded by B1",
    "exp_return_cross_section.json": "S38 void (BAND_PRIOR v2 constants); superseded by B1",
    "feature_ablation_20260903.json": "predates module; ratio-bearing feature set",
    "holder_h2_h3.json": "predates module; holder study, market leg unstamped",
    "holding_period_policy_20260903.json": "S38 void (admission column); superseded by B1",
    "ibes_status_rules_2013_2024.json": "S38 void (corrupted ratio); superseded by B1",
    "learner_v1.json": "predates module; ratio-bearing feature set",
    "learner_v2_20260903.json": "predates module; champion at noise max, ratio feature",
    "month_retro_20260902.json": "predates module; monthly retro narrative",
    "revision_6m_cohorts_20260904.json": "S38 void (contaminated pool); superseded by B1",
    "scenario_bridge_20260903.json": "predates module; exemplar excess_vw quoted from panel",
    "scenario_bridge_rerun_20260904.json": "predates module; same as its parent",
    "time_machine_arena.json": "S38 void (corrupted ratio); superseded by B1",
    "topn_concentration.json": "predates module; concentration study",
    "toxic_band_short_20260904.json": "S38 void (future-reverse-split label); superseded by B1",
    "unsupervised_states_20260903.json": "S38 void under its own persistent null; superseded by B4",
    "upside_band_decontamination.json": "S38 void (named the wrong cause); superseded by B1",
}

_PINNED_PRESENT = (REPO / "backend" / "data" / "ff_daily_pinned.csv.gz").exists()
_needs_pin = pytest.mark.skipif(
    not _PINNED_PRESENT, reason="pinned FF daily vintage absent on this machine")


# ------------------------------------------------------- the anchor number

@_needs_pin
def test_pinned_vw_market_reproduces_the_anchor():
    """+96.67% over 2020-01-02..2025-05-30. Re-derived twice on 2026-09-04.

    If this drifts, either the pinned vintage moved (its hash gate should have
    refused first) or the construction changed. Both are findings, not flakes.
    """
    m = bm.pinned_market_total_return("2020-01-02", "2025-05-30")
    assert m.benchmark_id == "vw_market_tr_pinned"
    assert m.provenance["dividends_included"] is True
    assert m.provenance["network"] is False
    assert m.total_return() == pytest.approx(0.9667, abs=0.0010)


@_needs_pin
def test_market_beats_cash_over_the_same_window_and_both_are_positive():
    """A floor that is above the thing it floors would mean the legs disagree."""
    m = bm.pinned_market_total_return("2020-01-02", "2025-05-30")
    c = bm.cash("2020-01-02", "2025-05-30")
    assert 0.0 < c.total_return() < m.total_return()
    # Same file, same span -> the two legs must be aligned day for day.
    assert len(c.returns) == len(m.returns)


@_needs_pin
def test_beta_matched_leg_explains_leverage():
    """A 1.48x book's beta leg is far above the market -- that is the point.

    The toxic-short receipt quoted "+76.6%/yr hedged gross" on a 1.48x long
    market leg. The beta-matched benchmark makes that premium visible instead of
    letting it read as alpha.
    """
    m = bm.pinned_market_total_return("2020-01-02", "2025-05-30")
    b = bm.beta_matched(m, 1.48)
    assert b.provenance["beta"] == 1.48
    assert b.provenance["market_benchmark_id"] == "vw_market_tr_pinned"
    assert b.total_return() > m.total_return()


# --------------------------------------------------- the +740% refusal

def test_compound_refuses_an_overlapping_series():
    """The one line of arithmetic that published +740% cannot be written again.

    There is deliberately no `force=` escape hatch: the remedy is
    `non_overlapping()` or calendar-time cohorts, not a flag with a comment.
    """
    monthly = pd.Series([0.0328] * 66)
    with pytest.raises(ValueError, match="overlapping"):
        bm.compound(monthly, overlapping=True)
    # And the inflation it prevents is real: ~3x in log space.
    all_66 = bm.compound(monthly)
    every_3rd = bm.compound(bm.non_overlapping(monthly, 3))
    import math
    assert math.log(all_66) / math.log(every_3rd) == pytest.approx(3.0, abs=0.05)


def test_non_overlapping_tiles_the_sample():
    s = pd.Series(range(10), dtype="float64")
    assert list(bm.non_overlapping(s, 3)) == [0.0, 3.0, 6.0, 9.0]
    assert list(bm.non_overlapping(s, 1)) == list(s)
    with pytest.raises(ValueError):
        bm.non_overlapping(s, 0)


def test_compound_of_empty_is_one_not_an_error():
    """An empty window is a measurement of nothing, not a crash."""
    assert bm.compound(pd.Series([], dtype="float64")) == 1.0


# ------------------------------------------------------ refuse, never sub

def test_unknown_benchmark_id_refuses_and_names_the_vocabulary():
    with pytest.raises(bm.BenchmarkUnavailable) as ei:
        bm.resolve("sp500_price_index")
    assert "known ids" in str(ei.value)
    assert "vw_market_tr_pinned" in str(ei.value)


def test_matched_requires_a_construction_string():
    """Bespoke is allowed; undocumented is not."""
    s = pd.Series([0.01, -0.02])
    with pytest.raises(ValueError):
        bm.matched(s, "sector_neutral", "")
    ok = bm.matched(s, "sector_neutral", "EW of same-SIC names, same months")
    assert ok.benchmark_id == "matched:sector_neutral"
    good, why = bm.validate_stamp(ok.stamp())
    assert good, why


def test_network_benchmarks_are_declared_so_the_fast_suite_can_avoid_them():
    """The fast suite is network-blocked; the module must say which ids need it."""
    assert bm.NETWORK_IDS == {"spy_tr_yf_adjclose", "qqq_tr_yf_adjclose"}
    for bid in bm.NETWORK_IDS:
        assert bid in bm.REGISTRY


# ------------------------------------------------------- the stamp itself

@_needs_pin
def test_stamp_round_trips_and_a_forged_module_is_rejected():
    m = bm.pinned_market_total_return("2024-01-02", "2024-12-31")
    stamp = m.stamp()
    good, why = bm.validate_stamp(stamp)
    assert good, why
    assert stamp["span"] == ["2024-01-02", "2024-12-31"]

    for mutate, expect in [
        ({"module": "scripts.my_own_market"}, "module"),
        ({"schema": 999}, "schema"),
        ({"benchmark_id": "^GSPC"}, "registry"),
        ({"provenance_sha256": ""}, "provenance_sha256"),
        ({"provenance": {"source": "vibes"}}, "construction"),
    ]:
        forged = dict(stamp)
        forged.update(mutate)
        ok, reason = bm.validate_stamp(forged)
        assert not ok, f"{mutate} should have been rejected"
        assert expect in reason


def test_market_key_detector_separates_returns_from_sizes_and_regimes():
    """Broad include, named exclusions. A false negative re-opens the hole."""
    for key in ("market", "cagr_market", "excess_vw_1m", "paired_t_vs_market",
                "adaptive12m_stop20_toxicexit_mktpark_10bps", "spy_return",
                "years_beating_benchmark", "vw_market", "primary_benchmark"):
        assert bm.is_market_key(key), f"{key} should be gated"
    for key in ("log_market_cap", "market_cap_musd", "by_market_state",
                "market_rows", "market_features", "market_states",
                "permno", "numest", "ratio", "prc", "cfacpr"):
        assert not bm.is_market_key(key), f"{key} is not a market return"


def test_buy_hold_keys_are_gated_because_the_first_version_missed_them():
    """Regression: the gate let its own first receipt through on 2026-09-04.

    `signal_engine_backtest_20260904.json` quotes `buy_hold_total_return` and
    `buy_hold_sharpe` -- market legs whose names contain no market word. The
    first regex matched only mkt/market/spy/qqq/bench/excess and reported ZERO
    market fields, so the receipt passed unstamped. A gate that misses the thing
    it guards is worse than no gate, because it is believed.
    """
    for key in ("buy_hold_total_return", "buy_hold_sharpe",
                "buy_and_hold_no_rebalance", "active_passive",
                "years_beating_top500_vw"):
        assert bm.is_market_key(key), f"{key} must be gated"


def test_ablation_and_fdr_keys_are_not_mistaken_for_benchmarks():
    """False friends, each one hand-checked against the real receipt corpus.

    `screen_BH_FDR` is Benjamini-Hochberg, not buy-and-hold. `beats_v1` and
    `H2_residual_arm_beats_raw_arm` compare two model arms to each other, which
    is an ablation; gating those would demand a market stamp on receipts that
    quote no market at all.
    """
    for key in ("screen_BH_FDR", "screen_survivors_BH_FDR", "beats_v1",
                "beats_incumbent", "beats_random_partition",
                "H2_residual_arm_beats_raw_arm"):
        assert not bm.is_market_key(key), f"{key} is not a market return"


def test_declare_keeps_one_producer_instead_of_widening_the_validator():
    """`backend.services.backtest` holds a price path, not a Benchmark object.

    It still must not hand-roll a stamp: the honest-looking repair would have
    been to let `validate_stamp` accept several modules, which ends the gate.
    `declare()` is the narrow alternative -- registry-checked, construction
    required, and `declared_only` recorded so the weaker path stays visible.
    """
    stamp = bm.declare(
        "spy_tr_yf_adjclose",
        construction="yfinance auto_adjust=True Close (total return)",
        span=["2019-12-31", "2025-09-02"], n_periods=22)
    ok, why = bm.validate_stamp(stamp)
    assert ok, why
    assert stamp["module"] == bm.CANONICAL_MODULE
    assert stamp["provenance"]["declared_only"] is True

    # It cannot be used to bless a price index or a bare assertion.
    with pytest.raises(bm.BenchmarkUnavailable):
        bm.declare("^GSPC", construction="S&P 500 price index")
    with pytest.raises(ValueError):
        bm.declare("spy_tr_yf_adjclose", construction="   ")


def test_market_keys_reports_paths_so_a_failure_is_actionable():
    receipt = {"book": {"cagr_market": 0.13, "permno": 10107},
               "arms": [{"excess_vw_1m": 0.02}]}
    paths = bm.market_keys(receipt)
    assert "book.cagr_market" in paths
    assert "arms[0].excess_vw_1m" in paths
    assert not any("permno" in p for p in paths)


# --------------------------------------------- the gate over real receipts

def _declared_date(payload: dict, path: Path) -> _dt.date:
    """The receipt's own date if it carries one, else the file's mtime.

    A receipt that declares its date is trusted about it; one that does not is
    dated by the filesystem. Deriving the input rather than assuming it is the
    house rule for guards.
    """
    for key in ("written_at_utc", "generated_at", "created", "created_utc",
                "date", "run_date", "as_of"):
        v = payload.get(key)
        if isinstance(v, str) and len(v) >= 10:
            try:
                return _dt.date.fromisoformat(v[:10])
            except ValueError:
                continue
    return _dt.date.fromtimestamp(path.stat().st_mtime)


@pytest.mark.skipif(not RECEIPTS.is_dir(), reason="tracker_backtest receipts absent")
def test_new_receipts_quoting_a_market_carry_the_canonical_stamp():
    """The gate. Every receipt from STAMP_REQUIRED_FROM onwards, or a named exemption."""
    offenders: list[str] = []
    for path in sorted(RECEIPTS.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # a receipt that cannot be read is its own finding
            offenders.append(f"{path.name}: UNREADABLE ({e})")
            continue
        if not isinstance(payload, dict):
            continue
        keys = bm.market_keys(payload)
        if not keys:
            continue
        if _declared_date(payload, path) < bm.STAMP_REQUIRED_FROM:
            continue
        if path.name in GRANDFATHERED:
            continue
        stamp = bm.find_stamp(payload)
        if stamp is None:
            offenders.append(
                f"{path.name}: quotes {len(keys)} market field(s) "
                f"(e.g. {keys[0]}) with no {bm.STAMP_KEY!r} stamp")
            continue
        ok, reason = bm.validate_stamp(stamp)
        if not ok:
            offenders.append(f"{path.name}: invalid stamp -- {reason}")

    assert not offenders, (
        "Receipts written on/after "
        f"{bm.STAMP_REQUIRED_FROM} must build their market leg with "
        f"{bm.CANONICAL_MODULE} and carry its stamp:\n  "
        + "\n  ".join(offenders)
        + "\n\nFix: build the benchmark via learner.benchmark.resolve(...) and "
          "write bm.stamp() under the 'market_benchmark' key. Do NOT add the "
          "file to GRANDFATHERED -- that list only shrinks."
    )


@pytest.mark.skipif(not RECEIPTS.is_dir(), reason="tracker_backtest receipts absent")
def test_the_grandfather_list_only_names_files_that_exist():
    """A stale exemption is a hole nobody can see. The list must stay honest."""
    missing = [n for n in GRANDFATHERED if not (RECEIPTS / n).exists()]
    assert not missing, (
        "GRANDFATHERED names receipts that are gone -- delete these rows so the "
        f"exemption cannot silently cover a future file with the same name: {missing}"
    )


@pytest.mark.skipif(not RECEIPTS.is_dir(), reason="tracker_backtest receipts absent")
def test_every_grandfathered_receipt_actually_quotes_a_market():
    """An exemption for a receipt the gate would not have caught is noise."""
    pointless = []
    for name in GRANDFATHERED:
        p = RECEIPTS / name
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and not bm.market_keys(payload):
            pointless.append(name)
    assert not pointless, f"exempted but not gated anyway: {pointless}"
