"""The price table must be DERIVABLE from the provider balance, and the
derivation must be able to REFUSE.

WHY THIS FILE EXISTS
====================
On 2026-08-12 someone corrected `LLM_PRICE_PER_MTOK` carefully, wrote a long
comment explaining why, and got the output leg wrong by 4.6x. Nothing failed for
24 days, because every test in the suite read the table it was checking. The
ledger priced 55.8% of what DeepSeek actually charged, and `research_budget`'s
DOLLAR ceilings — which gate on that same table — were quietly advisory: a $10
gate stopped near $17.90 of real money.

So this file pins the table to a MEASUREMENT rather than to a number, and it
pins the measurement machinery to a planted truth.

THE HARD HALF IS THE REFUSAL
----------------------------
A gate that cannot go red is a broken gate. `scripts/c6b_deepseek_price_
derivation.py` is allowed to answer only when the inputs can support an answer,
and three cases must come back as named refusals rather than as a number:

  * one balance reading — a number, not a window;
  * a window with no tokens — the provider charged for calls the ledger never
    saw, and no rate divides into that;
  * a singular system — two windows with the same in/out mix, where the
    "solution" is floating-point noise amplified by the inverse.

Each is exercised below, and each asserts the REASON CODE, not merely that
something raised.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.config import (LLM_PRICE_AS_OF, LLM_PRICE_DERIVATION,
                            LLM_PRICE_PER_MTOK)
from scripts import c6b_deepseek_price_derivation as der

UTC = timezone.utc
T0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


# ── synthetic fixtures ──────────────────────────────────────────────────────
def _write_ledger(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows),
                    encoding="utf-8")
    return path


def _call(ts: datetime, tin: int, tout: int, cached: int = 0,
          model: str = "deepseek-chat") -> dict:
    return {"call_id": f"{ts.isoformat()}-{tin}-{tout}-{cached}",
            "ts": ts.isoformat(), "provider": "deepseek", "model": model,
            "purpose": "synthetic", "tokens_in": tin, "tokens_out": tout,
            "cached_tokens": cached, "cost_usd": 0.0, "row_type": "call"}


def _write_balance(path: Path, readings: list[tuple[datetime, float]]) -> Path:
    path.write_text("".join(
        json.dumps({"granted_usd": 0.0, "is_available": True,
                    "label": "synthetic", "read_at": t.isoformat(),
                    "topped_up_usd": v, "total_usd": v}) + "\n"
        for t, v in readings), encoding="utf-8")
    return path


def _plant(tmp_path: Path, in_rate: float, out_rate: float, *,
           cache_rate: float | None = None) -> tuple[Path, Path]:
    """A ledger and a balance file that are EXACTLY consistent at these rates.

    Two windows with deliberately opposite in/out mixes — an output-heavy one
    and an input-heavy one — because that is what makes the 2x2 solvable at all.
    """
    cache_rate = (in_rate * 0.02) if cache_rate is None else cache_rate
    # window 1: output heavy. window 2: input heavy.
    spec = [  # (tokens_in, cached, tokens_out) per window
        (2_000_000, 500_000, 8_000_000),
        (12_000_000, 6_000_000, 1_000_000),
    ]
    marks = [T0, T0 + timedelta(days=5), T0 + timedelta(days=6)]
    rows: list[dict] = []
    balances: list[tuple[datetime, float]] = []
    total = 100.0
    balances.append((marks[0], total))
    for i, (tin, cach, tout) in enumerate(spec):
        mid = marks[i] + (marks[i + 1] - marks[i]) / 2
        # split across three rows so the aggregation is doing real work
        rows.append(_call(mid, tin // 2, tout // 2, cach // 2))
        rows.append(_call(mid + timedelta(seconds=1), tin - tin // 2,
                          tout - tout // 2, cach - cach // 2,
                          model="deepseek-v4-flash"))
        # a non-DeepSeek row that must be ignored: it bills a different vendor
        rows.append({**_call(mid + timedelta(seconds=2), 9_000_000, 9_000_000),
                     "model": "gpt-5-nano", "provider": "openai"})
        cost = (tin * in_rate + cach * cache_rate + tout * out_rate) / 1e6
        total -= cost
        balances.append((marks[i + 1], round(total, 10)))
    return (_write_ledger(tmp_path / "ledger.jsonl", rows),
            _write_balance(tmp_path / "balance.jsonl", balances))


def _windows(ledger: Path, balance: Path) -> list[der.Window]:
    return der.windows_from_readings(der.read_balance_readings(balance),
                                     der.read_ledger(ledger))


# ── it recovers a planted rate ──────────────────────────────────────────────
def test_it_recovers_the_planted_rates_to_a_tight_tolerance(tmp_path):
    """The whole claim in one assertion: plant a price, get it back."""
    ledger, balance = _plant(tmp_path, in_rate=0.169413, out_rate=1.284835)
    got = der.solve_two_rate(_windows(ledger, balance))
    # rel=1e-5, not tighter: `Window.spend_usd` rounds the balance delta to six
    # decimals (real balances are quoted to the cent, and the rounding also
    # kills 10.629999999999999-style subtraction litter). That floor propagates
    # into the solve, and a tolerance below it would be testing float noise.
    assert got["in_usd_per_mtok"] == pytest.approx(0.169413, rel=1e-5)
    assert got["out_usd_per_mtok"] == pytest.approx(1.284835, rel=1e-5)
    assert got["max_abs_residual_usd"] < 1e-9
    assert got["economically_sensible"] is True


def test_it_recovers_a_DIFFERENT_planted_rate(tmp_path):
    """Drawn twice, deliberately. One recovery could be the fixture agreeing
    with itself; a second, unrelated rate is the test actually measuring."""
    ledger, balance = _plant(tmp_path, in_rate=0.55, out_rate=2.19)
    got = der.solve_two_rate(_windows(ledger, balance))
    assert got["in_usd_per_mtok"] == pytest.approx(0.55, rel=1e-5)
    assert got["out_usd_per_mtok"] == pytest.approx(2.19, rel=1e-5)


def test_the_scalar_multiple_recovers_the_planted_level(tmp_path):
    """Cross-check (b): a table that is uniformly Nx low reports N in BOTH
    windows. If it ever reported one number for a shape error, the multiple
    would be a false reassurance — which is exactly what happened on 09-05."""
    base = der.BASELINE_TABLE_2026_08_12
    ledger, balance = _plant(tmp_path, in_rate=base["in"] * 3.0,
                             out_rate=base["out"] * 3.0,
                             cache_rate=base["cached_in"] * 3.0)
    got = der.scalar_multiple(_windows(ledger, balance))
    assert got["pooled"] == pytest.approx(3.0, rel=1e-6)
    for v in got["per_window"].values():
        assert v == pytest.approx(3.0, rel=1e-6)
    assert got["spread_max_over_min"] == pytest.approx(1.0, abs=1e-4)


def test_a_shape_error_makes_the_scalar_multiple_disagree(tmp_path):
    """The 2026-09-05 finding, reproduced synthetically: when only the OUTPUT
    leg is wrong, the per-window multiples must NOT agree. A derivation that
    reported a single tidy multiple here would have hidden the real error."""
    base = der.BASELINE_TABLE_2026_08_12
    ledger, balance = _plant(tmp_path, in_rate=base["in"],
                             out_rate=base["out"] * 4.6,
                             cache_rate=base["cached_in"])
    got = der.scalar_multiple(_windows(ledger, balance))
    assert got["spread_max_over_min"] > 1.5


def test_the_gap_attribution_fingers_the_output_leg(tmp_path):
    """The number that separates 'the table is wrong' from 'rows are missing'.

    Here the ledger is COMPLETE and only the output rate is wrong, so the gap
    must look most nearly constant per output token.
    """
    base = der.BASELINE_TABLE_2026_08_12
    ledger, balance = _plant(tmp_path, in_rate=base["in"],
                             out_rate=base["out"] * 4.6,
                             cache_rate=base["cached_in"])
    got = der.attribute_the_gap(_windows(ledger, balance))
    assert got["tightest_denominator"] == "gap_per_mtok_out_usd"
    spreads = dict(got["ranking_by_spread"])
    assert spreads["gap_per_mtok_out_usd"] == pytest.approx(1.0, abs=1e-4)
    assert spreads["gap_per_call_usd"] > 1.5


def test_a_missing_row_inflates_the_implied_rate(tmp_path):
    """The confound the mandate names: the key is shared, so a real call that
    wrote no row looks like a higher price. Prove the direction and the size."""
    ledger, balance = _plant(tmp_path, in_rate=0.14, out_rate=0.28)
    honest = der.solve_two_rate(_windows(ledger, balance))
    assert honest["out_usd_per_mtok"] == pytest.approx(0.28, rel=1e-5)
    # drop ONE of the two DeepSeek rows inside the first window — not all of
    # them, which would empty the window and (correctly) refuse instead. The
    # provider still charged for the deleted call, so the solve has to hand
    # that money to the surviving tokens.
    rows = [json.loads(x) for x in
            ledger.read_text(encoding="utf-8").splitlines()]
    cut = der.read_balance_readings(balance)[1][0]
    dropped = False
    kept = []
    for r in rows:
        if (not dropped and der._dt(r["ts"]) < cut
                and r["model"] in der.DEEPSEEK_MODELS):
            dropped = True
            continue
        kept.append(r)
    assert dropped
    _write_ledger(ledger, kept)
    inflated = der.solve_two_rate(_windows(ledger, balance))
    assert inflated["out_usd_per_mtok"] > honest["out_usd_per_mtok"]


# ── the refusals: prove the gate goes red ───────────────────────────────────
def test_one_balance_reading_is_refused_by_name(tmp_path):
    ledger, _ = _plant(tmp_path, 0.14, 0.28)
    balance = _write_balance(tmp_path / "one.jsonl", [(T0, 100.0)])
    with pytest.raises(der.PriceDerivationRefused) as exc:
        der.windows_from_readings(der.read_balance_readings(balance),
                                  der.read_ledger(ledger))
    assert exc.value.reason == der.REFUSE_INSUFFICIENT_READINGS


def test_a_window_with_no_tokens_is_refused_by_name(tmp_path):
    """The provider charged and the ledger saw nothing. That is a FINDING —
    unledgered spend — and it must not be laundered into a price."""
    ledger, balance = _plant(tmp_path, 0.14, 0.28)
    rows = [json.loads(x) for x in
            ledger.read_text(encoding="utf-8").splitlines()]
    cut = der.read_balance_readings(balance)[1][0]
    _write_ledger(ledger, [r for r in rows if der._dt(r["ts"]) >= cut])
    with pytest.raises(der.PriceDerivationRefused) as exc:
        der.solve_two_rate(_windows(ledger, balance))
    assert exc.value.reason == der.REFUSE_EMPTY_WINDOW
    assert "no tokens" in str(exc.value) or "never saw" in str(exc.value)


def test_two_windows_with_the_same_mix_are_refused_as_singular(tmp_path):
    """Two windows of identical in/out mix carry ONE equation, not two. The
    inverse still returns a pair of numbers; they are noise."""
    mix = (5_000_000, 1_000_000, 5_000_000)
    marks = [T0, T0 + timedelta(days=1), T0 + timedelta(days=2)]
    rows, bal, total = [], [(marks[0], 100.0)], 100.0
    for i in range(2):
        rows.append(_call(marks[i] + timedelta(hours=1), *[mix[0], mix[2],
                                                           mix[1]][:3]))
        total -= (mix[0] * 0.14 + mix[1] * 0.0028 + mix[2] * 0.28) / 1e6
        bal.append((marks[i + 1], round(total, 10)))
    ledger = _write_ledger(tmp_path / "l.jsonl", rows)
    balance = _write_balance(tmp_path / "b.jsonl", bal)
    with pytest.raises(der.PriceDerivationRefused) as exc:
        der.solve_two_rate(_windows(ledger, balance))
    assert exc.value.reason == der.REFUSE_SINGULAR
    assert "condition number" in str(exc.value)


def test_a_single_window_cannot_yield_two_rates(tmp_path):
    ledger, balance = _plant(tmp_path, 0.14, 0.28)
    one = _windows(ledger, balance)[:1]
    with pytest.raises(der.PriceDerivationRefused) as exc:
        der.solve_two_rate(one)
    assert exc.value.reason == der.REFUSE_INSUFFICIENT_READINGS


# ── the table must still match its own derivation ───────────────────────────
def test_the_live_table_matches_the_recorded_derivation():
    """The pin the 2026-08-12 edit did not have.

    `LLM_PRICE_DERIVATION` is the machine-readable claim about where these
    numbers came from. If someone edits the table without re-deriving, this
    fails and names the receipt they need to update.
    """
    measured = LLM_PRICE_DERIVATION["measured_usd_per_mtok"]
    for name in LLM_PRICE_DERIVATION["measured_entries"]:
        row = LLM_PRICE_PER_MTOK[name]
        assert row["in"] == pytest.approx(measured["in"]), name
        assert row["out"] == pytest.approx(measured["out"]), name
        # cached_in is SCALED, not measured — the 50x discount is carried.
        assert row["cached_in"] == pytest.approx(row["in"] * 0.02, rel=1e-6)
    assert LLM_PRICE_AS_OF == LLM_PRICE_DERIVATION["derived_on"]


def test_the_derivation_reproduces_the_windows_it_claims():
    """Recompute the provider spend from the recorded tokens at the recorded
    rates. A derivation block whose own arithmetic does not close is prose."""
    m = LLM_PRICE_DERIVATION["measured_usd_per_mtok"]
    cached_rate = m["in"] * 0.02
    for w in LLM_PRICE_DERIVATION["windows"]:
        pred = (w["tokens_in"] * m["in"] + w["tokens_cached"] * cached_rate
                + w["tokens_out"] * m["out"]) / 1e6
        assert pred == pytest.approx(w["provider_spend_usd"], abs=0.01), (
            f"{w['label']}: derivation predicts ${pred:.4f} against a measured "
            f"balance delta of ${w['provider_spend_usd']:.2f}")


def test_v4_pro_is_declared_propagated_and_stays_above_flash():
    """It is NOT measured — no v4-pro call has ever been made — and the file
    has to say so. It must also not price below flash, which is what leaving
    the old 0.87 would have done once flash's output leg moved to 1.28."""
    assert "deepseek-v4-pro" in LLM_PRICE_DERIVATION["scaled_not_measured"]
    assert "deepseek-v4-pro" not in LLM_PRICE_DERIVATION["measured_entries"]
    pro = LLM_PRICE_PER_MTOK["deepseek-v4-pro"]
    flash = LLM_PRICE_PER_MTOK["deepseek-v4-flash"]
    assert pro["out"] > flash["out"] and pro["in"] > flash["in"]


def test_the_dollar_gate_now_bins_at_the_corrected_prices(tmp_path):
    """The point of the whole exercise: `research_budget` gates on DOLLARS read
    through `llm_telemetry.spend()`, which reprices stored TOKENS at the CURRENT
    table. So the correction has to reach the gate with no further change.

    Historical rows keep their written `cost_usd` in the file — repairing an
    append-only accounting ledger is the tampering — and the gate deliberately
    does not read it.
    """
    from backend.services import llm_telemetry as tel

    led = _write_ledger(tmp_path / "gate.jsonl", [
        {**_call(T0, 1_000_000, 1_000_000),
         # what the OLD table wrote into the row, left untouched on disk
         "cost_usd": 0.42},
    ])
    got = tel.spend(path=led)
    p = LLM_PRICE_PER_MTOK["deepseek-chat"]
    assert got["total_cost_usd"] == pytest.approx(p["in"] + p["out"], rel=1e-6)
    assert got["total_cost_usd"] > 0.42, (
        "the gate must not be measuring the stale dollars on disk")
    # and the file itself is unchanged
    assert json.loads(led.read_text(encoding="utf-8").strip())["cost_usd"] == 0.42


def test_the_real_ledger_and_balance_still_derive_the_adopted_rates():
    """End to end on the REAL files, offline. This is the receipt's claim, and
    it fails loudly if either input is edited under it."""
    if not der.LEDGER.exists() or not der.BALANCE.exists():
        pytest.skip("real ledger/balance not present in this checkout")
    wins = der.windows_from_readings(der.read_balance_readings(der.BALANCE),
                                     der.read_ledger(der.LEDGER))
    got = der.solve_two_rate(wins)
    m = LLM_PRICE_DERIVATION["measured_usd_per_mtok"]
    assert got["in_usd_per_mtok"] == pytest.approx(m["in"], rel=1e-4)
    assert got["out_usd_per_mtok"] == pytest.approx(m["out"], rel=1e-4)
    assert got["condition_number"] < 10, "the windows must differ in mix"
