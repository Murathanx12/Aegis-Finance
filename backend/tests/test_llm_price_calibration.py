"""The price table is calibrated from the PROVIDER's balance, and the thesis-card
cap sums the SAME ruler its receipt prints (2026-09-27).

On 2026-09-27 the DeepSeek balance moved $0.05 for 4 OpenClaw quests + 2 synth
calls while OpenClaw's `costUsd` said ~$0.29 and the table said ~$0.22: both
rulers over-stated the provider 4-6x, and the one-day-old disagreement guard
(`REFUSED_CAP_READER_DISAGREES` at >10%) compared the two over-statements
against each other. These tests pin:

1. the fit recovers planted prices from synthetic (tokens, delta) windows --
   the level from one window, all three legs from three;
2. a delta below the balance's granularity threshold reports TOO_COARSE;
3. a card's `cost_usd` is the table's figure from the quest's tokens, OpenClaw's
   `costUsd` rides along as `reported_cost_usd`, and `card_spend` (the cap)
   sums the former -- so card sum and telemetry agree by construction;
4. the receipt's provider line WARNS (never refuses) above 25%.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from backend import config
from backend.services import llm_price_calibration as LPC
from backend.services import openclaw_client as OC
from backend.services import thesis_card as TC

PRIOR = {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835}


def _win(tin, cached, tout, prices, offset=0.0, jitter=0.0):
    cost = (tin * prices["in"] + cached * prices["cached_in"] + tout * prices["out"]) / 1e6
    return {"tokens_in": tin, "cached_tokens": cached, "tokens_out": tout,
            "delta_usd": round(cost + offset + jitter, 10), "offset_usd": offset}


# ── 1. the fit recovers planted prices ──────────────────────────────────────
def test_one_window_recovers_the_planted_level_on_the_prior_shape():
    """One route = one mix = one equation: the LEVEL. Planted at 0.2x the prior."""
    truth = {k: v * 0.2 for k, v in PRIOR.items()}
    w = _win(5_000_000, 160_000_000, 1_500_000, truth, offset=0.01)
    f = LPC.fit_prices([w], PRIOR)
    assert f["status"] == LPC.STATUS_OK and f["method"] == LPC.METHOD_SCALAR
    assert f["k_vs_prior"] == pytest.approx(0.2, rel=1e-6)
    for leg in LPC.LEGS:
        assert f["fitted_usd_per_mtok"][leg] == pytest.approx(truth[leg], rel=1e-5)
    # the bracket contains the truth and is +/- one cent of delta wide
    lo, hi = f["k_bracket"]
    assert lo < 0.2 < hi
    assert "NOT measured" in f["identified"]


def test_three_windows_of_different_mix_recover_all_three_legs():
    truth = {"in": 0.07, "cached_in": 0.0014, "out": 0.28}
    ws = [_win(20_000_000, 1_000_000, 500_000, truth),       # input heavy
          _win(1_000_000, 200_000_000, 300_000, truth),       # cache heavy
          _win(500_000, 1_000_000, 3_000_000, truth)]         # output heavy
    f = LPC.fit_prices(ws, PRIOR)
    assert f["method"] == LPC.METHOD_LEGS and f["status"] == LPC.STATUS_OK
    for leg in LPC.LEGS:
        assert f["fitted_usd_per_mtok"][leg] == pytest.approx(truth[leg], rel=1e-6)
        lo, hi = f["bracket_usd_per_mtok"][leg]
        assert lo <= truth[leg] <= hi


def test_a_different_planted_level_is_recovered_too():
    truth = {k: v * 1.7 for k, v in PRIOR.items()}
    f = LPC.fit_prices([_win(3_000_000, 50_000_000, 900_000, truth)], PRIOR)
    assert f["k_vs_prior"] == pytest.approx(1.7, rel=1e-6)


def test_the_offset_rows_are_not_fitted():
    """A synth call ledgered under another table row is subtracted, not fitted."""
    truth = {k: v * 0.3 for k, v in PRIOR.items()}
    a = LPC.fit_prices([_win(5_000_000, 100_000_000, 1_000_000, truth, offset=0.0)], PRIOR)
    b = LPC.fit_prices([_win(5_000_000, 100_000_000, 1_000_000, truth, offset=0.04)], PRIOR)
    assert a["k_vs_prior"] == pytest.approx(b["k_vs_prior"], rel=1e-9)


# ── 2. a delta below granularity is TOO_COARSE ──────────────────────────────
def test_a_delta_below_the_threshold_reports_too_coarse():
    truth = {k: v * 0.2 for k, v in PRIOR.items()}
    w = _win(300_000, 10_000_000, 90_000, truth)               # ~ $0.03
    assert w["delta_usd"] < 0.05
    f = LPC.fit_prices([w], PRIOR, granularity=0.01, min_delta=0.05)
    assert f["status"] == LPC.STATUS_TOO_COARSE
    assert f["adoptable"] is False
    assert "too coarse" in f["why"]
    assert f["relative_uncertainty"] > 0.2                    # one cent of ~3 cents


def test_refusals_are_statuses_not_numbers():
    assert LPC.fit_prices([], PRIOR)["status"] == LPC.STATUS_NO_WINDOW
    up = {"tokens_in": 1, "cached_tokens": 0, "tokens_out": 1, "delta_usd": -1.0}
    assert LPC.fit_prices([up], PRIOR)["status"] == LPC.STATUS_TOPUP_IN_WINDOW
    blind = {"tokens_in": 0, "cached_tokens": 0, "tokens_out": 0, "delta_usd": 0.2}
    f = LPC.fit_prices([blind], PRIOR)
    assert f["status"] == LPC.STATUS_NO_TOKENS and f["adoptable"] is False


def test_window_from_rows_splits_the_fitted_model_from_offsets(monkeypatch):
    rows = [{"provider": "deepseek", "model": "deepseek-flash", "tokens_in": 10,
             "cached_tokens": 100, "tokens_out": 5},
            {"provider": "deepseek", "model": "deepseek-flash", "tokens_in": 0,
             "cached_tokens": 0, "tokens_out": 0, "cost_usd": None},
            {"provider": "deepseek", "model": "deepseek-chat", "tokens_in": 1_000_000,
             "cached_tokens": 0, "tokens_out": 0}]
    w = LPC.window_from_rows(rows, delta_usd=0.2, model="deepseek-flash")
    assert (w["tokens_in"], w["cached_tokens"], w["tokens_out"]) == (10, 100, 5)
    assert w["n_calls"] == 2 and w["n_unpriced_calls"] == 1
    assert w["offset_usd"] == pytest.approx(config.LLM_PRICE_PER_MTOK["deepseek-chat"]["in"])


# ── 3. one ruler: card == telemetry, reported cost never summed ─────────────
def test_openclaw_priced_cost_is_the_telemetry_rows_arithmetic():
    usage = {"input": 80_000, "output": 30_000, "cache_read": 2_500_000}
    got = OC.priced_cost("deepseek/deepseek-flash", usage)
    p = config.LLM_PRICE_PER_MTOK["deepseek-flash"]
    assert got == pytest.approx((80_000 * p["in"] + 2_500_000 * p["cached_in"]
                                 + 30_000 * p["out"]) / 1e6)
    assert OC.priced_cost("deepseek/deepseek-flash", {}) is None     # UNKNOWN, not 0


def _meta(**kw):
    return {"openclaw_status": "OK", "openclaw_cost_usd": kw.get("reported"),
            "reported_cost_usd": kw.get("reported"), "quest_cost_usd": kw.get("priced"),
            "deepseek_cost_usd": kw.get("synth"), "quest_model": "deepseek/deepseek-flash"}


def test_the_card_carries_both_and_the_cap_sums_the_table_ruler(tmp_path):
    asof = date(2026, 9, 27)
    for t, (priced, reported, synth) in {"AAA": (0.012, 0.07, 0.001),
                                         "BBB": (0.010, 0.06, 0.001)}.items():
        c = TC.build_card(t, kind="personal", asof=asof, engine={}, web={"name": t},
                          synth={"synth_status": "OK", "verdict": "neutral"},
                          meta=_meta(priced=priced, reported=reported, synth=synth))
        assert c["cost_usd"] == pytest.approx(priced + synth)
        assert c["reported_cost_usd"] == reported and c["cost_ruler"] == "llm_price_table"
        TC.write_card(c, root=tmp_path)
    cs = TC.card_spend(asof, root=tmp_path)
    assert cs["spend_per_card_sum"] == pytest.approx(0.024)       # not 0.132
    assert cs["n_legacy_reported_ruler"] == 0
    # the ruler the receipt prints (telemetry at the same table) agrees
    assert TC.spend_disagreement(cs["spend_per_card_sum"], 0.024) == 0.0


def test_a_card_whose_tokens_never_came_back_is_unknown_not_zero(tmp_path):
    c = TC.build_card("CCC", kind="personal", asof="2026-09-27", engine={}, web={},
                      synth={"synth_status": "NOT_RUN"}, meta=_meta(priced=None, reported=0.07))
    assert c["cost_usd"] is None
    TC.write_card(c, root=tmp_path)
    assert TC.card_spend("2026-09-27", root=tmp_path)["n_quest_cost_unknown"] == 1


def test_legacy_cards_sum_the_repriced_sidecar_when_one_exists(tmp_path):
    day = "2026-09-27"
    old = TC.build_card("OLD", kind="personal", asof=day, engine={}, web={},
                        synth={"synth_status": "OK"},
                        meta={"openclaw_status": "OK", "openclaw_cost_usd": 0.07,
                              "deepseek_cost_usd": 0.001})
    assert "cost_usd" not in old
    TC.write_card(old, root=tmp_path)
    assert TC.card_spend(day, root=tmp_path)["n_legacy_reported_ruler"] == 1
    (tmp_path / day / TC.REPRICED_SIDECAR).write_text(json.dumps(
        {"cards": {"OLD": {"cost_usd_repriced": 0.015}}}), encoding="utf-8")
    cs = TC.card_spend(day, root=tmp_path)
    assert cs["spend_per_card_sum"] == pytest.approx(0.015)
    assert cs["n_from_repriced_sidecar"] == 1 and cs["n_legacy_reported_ruler"] == 0
    # and the sidecar is not read as a card
    assert [c["ticker"] for c in TC.read_cards(day, root=tmp_path)] == ["OLD"]


def test_the_run_caps_on_the_priced_cost_and_the_receipt_prints_the_same(tmp_path):
    """End to end through `scripts.thesis_cards.run`: OpenClaw reports 5x the
    priced cost; the cap and the receipt both read the priced one."""
    from scripts import thesis_cards as S
    asked = []

    def quest(ticker, prompt, *, model, timeout, log_dir):
        asked.append(ticker)
        return {"status": "OK", "reply": json.dumps({"name": ticker, "sources": ["u"]}),
                "elapsed_s": 1.0, "log_path": "", "cost_usd": 0.5, "priced_cost_usd": 0.1,
                "usage": {"input": 1, "output": 1, "cache_read": 1}}

    def synth(e, w, *, model):
        return {"verdict": "neutral", "confidence": "low", "synth_status": "OK"}

    from backend.tests.test_thesis_card import _fake_inputs as fake_inputs

    tel = lambda day: TC.card_spend(day, root=tmp_path)["spend_per_card_sum"]
    prov = []
    uni = [{"ticker": f"T{i}", "kind": "personal", "source": "s"} for i in range(6)]
    r = S.run(universe=uni, asof="2026-09-27", root=tmp_path, max_quests=6, cap_usd=5.0,
              parallel=1, model="m", inputs=fake_inputs(), quest_fn=quest, synth_fn=synth,
              spend_fn=tel, provider_fn=lambda a, b: prov.append((a, b)) or {
                  "status": "OK", "provider_delta_usd": 0.1, "telemetry_deepseek_usd": 0.6,
                  "balance_before_usd": 1.0, "balance_after_usd": 0.9,
                  "provider_disagreement": 0.8333, "warning": "WARNING provider ..."})
    assert r["state"] == "DONE" and len(asked) == 6
    assert r["spend_check"]["refused"] is False and r["spend_check"]["spend_disagreement"] == 0.0
    assert r["spend_per_card_sum"] == pytest.approx(0.6)          # 6 x 0.1, not 6 x 0.5
    rc = json.loads((tmp_path / "2026-09-27" / "_run_receipt.json").read_text(encoding="utf-8"))
    assert rc["spent_usd_today"] == pytest.approx(0.6)
    # provider disagreement is a WARNING on the receipt, and the run still finished
    assert rc["provider_delta"]["warning"].startswith("WARNING") and rc["state"] == "DONE"
    assert prov and prov[0][0] <= prov[0][1]


# ── 4. the provider line ────────────────────────────────────────────────────
def _row(ts, tin, cached, tout, model="deepseek-flash"):
    return {"provider": "deepseek", "model": model, "ts": ts, "tokens_in": tin,
            "cached_tokens": cached, "tokens_out": tout}


def test_provider_line_warns_above_25pct_and_names_the_calibration_age(monkeypatch):
    monkeypatch.setattr(config, "LLM_PRICE_CALIBRATION",
                        {"calibrated_on": "2026-09-20"}, raising=False)
    snaps = [{"read_at": "2026-09-27T01:00:00+00:00", "total_usd": 10.00},
             {"read_at": "2026-09-27T03:00:00+00:00", "total_usd": 9.90}]
    p = config.LLM_PRICE_PER_MTOK["deepseek-flash"]
    # tokens worth exactly $0.50 at the table: a 5x over-statement
    rows = [_row("2026-09-27T02:00:00+00:00", int(0.5e6 / p["in"]), 0, 0),
            _row("2026-09-27T05:00:00+00:00", 10**9, 0, 0)]            # outside: ignored
    out = LPC.provider_delta_line("2026-09-27T01:30:00+00:00", "2026-09-27T02:30:00+00:00",
                                  snaps=snaps, rows=rows, today=date(2026, 9, 27))
    assert out["status"] == "OK" and out["provider_delta_usd"] == pytest.approx(0.10)
    assert out["telemetry_deepseek_usd"] == pytest.approx(0.50, rel=1e-4)
    assert out["provider_disagreement"] == pytest.approx(0.8, abs=1e-3)
    assert out["warning"].startswith("WARNING") and "7 days old" in out["warning"]
    assert out["calibration_age_days"] == 7


def test_provider_line_agreeing_within_25pct_has_no_warning():
    snaps = [{"read_at": "2026-09-27T01:00:00+00:00", "total_usd": 10.00},
             {"read_at": "2026-09-27T03:00:00+00:00", "total_usd": 9.90}]
    p = config.LLM_PRICE_PER_MTOK["deepseek-flash"]
    rows = [_row("2026-09-27T02:00:00+00:00", int(0.11e6 / p["in"]), 0, 0)]
    out = LPC.provider_delta_line("2026-09-27T01:30:00+00:00", "2026-09-27T02:30:00+00:00",
                                  snaps=snaps, rows=rows)
    assert out["warning"] is None and out["provider_disagreement"] < 0.25


def test_provider_line_without_a_bracketing_pair_says_so():
    snaps = [{"read_at": "2026-09-27T01:00:00+00:00", "total_usd": 10.0}]
    out = LPC.provider_delta_line("2026-09-27T01:30:00+00:00", "2026-09-27T02:30:00+00:00",
                                  snaps=snaps, rows=[])
    assert out["status"] == "NO_BRACKETING_PAIR" and out["warning"] is None


# ── 5. the live row matches its recorded calibration ────────────────────────
def test_the_flash_row_is_the_recorded_calibration():
    cal = config.LLM_PRICE_CALIBRATION
    row = config.LLM_PRICE_PER_MTOK[cal["model"]]
    for leg in LPC.LEGS:
        assert row[leg] == pytest.approx(cal["fitted_usd_per_mtok"][leg], rel=1e-6)
        assert row[leg] == pytest.approx(cal["prior_row"][leg] * cal["k_vs_prior"], rel=1e-5)
    lo, hi = cal["k_bracket"]
    assert lo < cal["k_vs_prior"] < hi


def test_the_recorded_calibration_closes_its_own_arithmetic():
    """Re-fit the recorded window: a provenance block whose sums do not close is prose."""
    cal = config.LLM_PRICE_CALIBRATION
    w = {"delta_usd": cal["provider_delta_usd"], "offset_usd": cal["offset_usd_other_rows"],
         "tokens_in": cal["tokens_in"], "cached_tokens": cal["cached_tokens"],
         "tokens_out": cal["tokens_out"]}
    f = LPC.fit_prices([w], cal["prior_row"], granularity=cal["granularity_usd"])
    assert f["status"] == LPC.STATUS_OK
    assert f["k_vs_prior"] == pytest.approx(cal["k_vs_prior"], rel=1e-5)
    assert f["k_bracket"] == pytest.approx(cal["k_bracket"], rel=1e-5)
