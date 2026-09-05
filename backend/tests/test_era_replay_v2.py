"""Tests for `scripts/era_replay_v2.py` -- the L10 era-replay decide step.

Every test here pins a PROPERTY, never a calendar moment and never a live
vendor. The suite is network-blocked (`backend/tests/conftest.py`), so nothing
below touches OpenAI or DeepSeek: the wire functions are exercised only through
their parsers and their gates.

The four things worth pinning, in the order they cost the pilot money:

1. **The two naming arms must carry identical information.** If `render_bundle`
   ever lets a number differ between fantasy and real-anon, the whole
   memorisation contrast is measuring the renderer.
2. **The sealed side table must never reach a prompt.** Forward returns live on
   keys beginning `_`; a card containing one is a leak of the answer.
3. **`normalise_rank` must map "A" to "Company A" and still refuse garbage.**
   The pilot lost every real-anon window because `deepseek-chat` abbreviates,
   and it failed SILENTLY as "not a permutation".
4. **`magnitudes_preserved` must score a faithful rewrite as faithful.** Its
   first version regexed the whole card and counted "12-1 momentum" and
   "4 weeks" as data, scoring a perfect rewrite at 0%.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts import era_replay_v2 as er


# ── fixtures: a window built by PROPERTY, not by a pinned date ──────────────

def _win(n: int = 4, month: str = "2017-06") -> dict:
    rng = np.random.default_rng(4)
    sectors = ["Manufacturing", "Services", "Mining", "Retail"]
    names = []
    for i in range(n):
        names.append({
            "slot": i,
            "permno": 10000 + i,
            "sector": sectors[i % len(sectors)],
            "size_bucket": "mid",
            "facts": {k: float(rng.normal()) for k in
                      ("ret_1m", "ret_3m", "ret_12m", "mom_12_1", "vol_60d",
                       "drawdown_60d", "coverage", "consensus", "ratio",
                       "dispersion", "net_rev_4w", "target_rev_3m",
                       "consensus_rev_1m")},
            # SENTINELS, far outside any plausible feature range. A realistic
            # forward return renders at 1dp as "21.0" and collides with some
            # feature on almost every seed, so a string-match leak test built on
            # realistic values is a coincidence lottery rather than a test.
            # These values cannot collide, so a hit is a real leak.
            "_fwd_1m": 7654.321 + i,
            "_mkt_ew_1m": 8765.432,
            "_dollar_vol": 9876.543,
        })
    return {"window_id": f"t0_{month}", "thread": 0, "month": month,
            "trailing_mkt_1m": -0.02, "names": names}


# ── 1. the arms carry the same information ─────────────────────────────────

def test_the_two_naming_arms_carry_identical_numbers():
    """Fantasy and real-anon differ in LABELS only. If a number differs, the
    memorisation contrast is measuring the renderer instead of the model."""
    w = _win(6)
    _, lab_f, val_f = er.render_bundle(w, "fantasy")
    _, lab_r, val_r = er.render_bundle(w, "realanon")
    assert val_f == val_r, "the arms would not be comparable"
    assert lab_f != lab_r, "the arms would not be distinguishable"


def test_the_sector_map_is_a_bijection():
    """A many-to-one fantasy map would DESTROY the information about which
    names share a sector, which is information the real-anon arm still has."""
    targets = [er.FANTASY_SECTOR[k] for k in er.FANTASY_SECTOR
               if k not in ("_UNKNOWN",)]
    # "Unclassified" and "_UNKNOWN" are the same real bucket and legitimately
    # share one image; everything else must be distinct.
    assert len(set(targets)) == len(set(
        k for k in er.FANTASY_SECTOR if k != "_UNKNOWN"))


# ── 2. the sealed side table never reaches a prompt ────────────────────────

@pytest.mark.parametrize("naming", ["fantasy", "realanon"])
def test_the_card_never_contains_the_answer(naming):
    """`_fwd_1m` is the grader's column. A card that carries it is a backtest
    of a model that was shown the outcome."""
    w = _win(5)
    card, _labels, _values = er.render_bundle(w, naming)
    for n in w["names"]:
        for sealed_key, v in n.items():
            if not sealed_key.startswith("_") or v is None:
                continue
            # The formats the renderer actually emits. A 2-decimal form is
            # excluded on purpose: the card legitimately prints ratios at 2dp,
            # so "0.18" can collide with a sealed 0.176543 by arithmetic rather
            # than by leak, and a test that fails on a coincidence teaches the
            # reader to skim it.
            for rendered in (f"{float(v):.1f}", f"{float(v):.4f}",
                             f"{float(v) * 100:.1f}"):
                assert rendered not in card, (
                    f"{sealed_key} reached the prompt as {rendered!r}")
    assert "fwd" not in card.lower()


def test_the_card_never_names_a_real_year_or_the_month():
    """The era is what the canary is FOR. Printing the month on the card would
    make the canary measure our renderer, not the model's memory."""
    w = _win(4, month="2018-11")
    for naming in ("fantasy", "realanon"):
        card, _l, _v = er.render_bundle(w, naming)
        assert "2018" not in card
        assert "2018-11" not in card


# ── 3. rank normalisation: tolerant, but never a guess ────────────────────

def test_normalise_rank_accepts_the_abbreviation_deepseek_actually_returns():
    labels = er.REAL_LABELS[:4]                       # Company A .. Company D
    got = er.normalise_rank(["D", "A", "C", "B"], labels)
    assert got == ["Company D", "Company A", "Company C", "Company B"]


def test_normalise_rank_accepts_the_canonical_form_unchanged():
    labels = er.FANTASY_FIRMS[:3]
    assert er.normalise_rank(list(labels), labels) == list(labels)


@pytest.mark.parametrize("bad", [
    ["A", "B", "C"],                    # short -- not a permutation
    ["A", "A", "B", "C"],               # a repeat
    ["A", "B", "C", "Z"],               # an unknown label
    "ABCD",                             # not a list at all
    None,
])
def test_normalise_rank_refuses_rather_than_guesses(bad):
    """A rank we cannot read is a refusal. Guessing at the ordering would put
    fabricated decisions into the ledger, which is worse than a missing window."""
    assert er.normalise_rank(bad, er.REAL_LABELS[:4]) is None


# ── 4. the preservation gate scores a faithful rewrite as faithful ─────────

def test_magnitudes_preserved_ignores_field_names():
    """The first version regexed the whole card, counted "12-1 momentum" and
    "4 weeks" as data, and scored a perfect rewrite 0%. Pin the fix."""
    expected = ["-20.2", "3.33", "1.32"]
    faithful = ("Over 12 months and on a 12-1 basis the trend is soft: the 1m "
                "return was -20.2%, 12 analysts rate it 3.33 of 5, and the "
                "target sits at 1.32x over the last 4 weeks.")
    out = er.magnitudes_preserved(expected, faithful)
    assert out["ok"] is True
    assert out["share_preserved"] == 1.0


def test_magnitudes_preserved_catches_a_real_drop():
    out = er.magnitudes_preserved(["-20.2", "3.33", "1.32"],
                                  "the 1m return was -20.2% and the rating 3.33")
    assert out["ok"] is False
    assert "1.32" in out["dropped"]
    assert out["share_preserved"] == pytest.approx(2 / 3, abs=1e-3)


def test_leak_check_catches_a_year_and_a_cross_arm_label():
    bad = er.leak_check("In 2018 Company A rallied.", ["Company A"])
    assert bad["ok"] is False
    assert 2018 in bad["years_mentioned"]
    assert "Company A" in bad["cross_arm_labels"]
    assert er.leak_check("Aureon rallied on soft revisions.", ["Company A"])["ok"]


# ── 5. grading: code prices, and the benchmark is the same names ───────────

def test_grade_uses_the_same_names_as_its_benchmark():
    """The vision's 'better than what?': the EW basket of the SAME anonymised
    names in the SAME month, not SPY and not the whole universe."""
    w = _win(4)
    labels = er.REAL_LABELS[:4]
    decisions = {(w["window_id"], "realanon_nodiary"): {
        "rank": list(labels), "guess_year": None, "guess_company": None}}
    g = er.grade_arm([w], decisions, "realanon_nodiary", cost_bps=10.0)
    assert g["n_windows"] == 1
    fwd = [n["_fwd_1m"] for n in w["names"]]
    # the receipt rounds to 5dp; the equality is what is being pinned
    assert g["terminal_wealth_ew_same_names"] == pytest.approx(
        1.0 + float(np.mean(fwd)), abs=1e-5)


def test_costs_are_charged_and_cannot_be_silently_zero():
    """`portfolio_farm.Policy` refuses zero costs; so does this. A first
    rebalance is 100% turnover and must cost something."""
    w = _win(4)
    labels = er.REAL_LABELS[:4]
    decisions = {(w["window_id"], "realanon_nodiary"): {
        "rank": list(labels), "guess_year": None, "guess_company": None}}
    g = er.grade_arm([w], decisions, "realanon_nodiary", cost_bps=10.0)
    assert g["mean_turnover"] == pytest.approx(1.0)
    assert g["mean_net_top_minus_ew_pct"] < g["mean_top_minus_ew_pct"]


def test_the_canary_counts_an_exact_year_hit():
    w = _win(3, month="2019-04")
    labels = er.REAL_LABELS[:3]
    decisions = {(w["window_id"], "realanon_nodiary"): {
        "rank": list(labels), "guess_year": 2019, "guess_company": "Acme Corp"}}
    g = er.grade_arm([w], decisions, "realanon_nodiary", cost_bps=10.0)
    assert g["canary"]["exact_year_hits"] == 1
    assert g["canary"]["company_named_rate"] == 1.0


def test_the_canary_does_not_count_a_null_company_as_an_identification():
    w = _win(3, month="2019-04")
    labels = er.REAL_LABELS[:3]
    for empty in (None, "null", "", "unknown", "N/A"):
        decisions = {(w["window_id"], "realanon_nodiary"): {
            "rank": list(labels), "guess_year": 2016, "guess_company": empty}}
        g = er.grade_arm([w], decisions, "realanon_nodiary", cost_bps=10.0)
        assert g["canary"]["company_named_rate"] == 0.0
        assert g["canary"]["exact_year_hits"] == 0


# ── 6. the nulls ──────────────────────────────────────────────────────────

def test_null_3_is_exactly_zero_when_the_rank_is_uninformative():
    """Same-day paired on a bundle whose forward returns are all equal must be
    0 -- the month effect cancels by construction."""
    rows = [{"thread": 0, "month": "2017-0%d" % (i + 1),
             "ranks": [0, 1, 2, 3, 4, 5, 6, 7], "fwd": [0.02] * 8,
             "cost": 0.002, "paired_net_top_minus_ew": 0.0,
             "paired_top_minus_bottom": 0.0} for i in range(5)]
    out = er.nulls({"_rows": rows}, n_draws=50, seed=3)
    assert out["null_3_same_day_paired"]["mean_top_minus_bottom_pct"] == 0.0


def test_null_1_is_centred_near_zero_for_a_random_rank():
    """Shuffling the bundle must not systematically pay. A null that is not
    centred is a bug in the null, not a finding."""
    rng = np.random.default_rng(1)
    rows = []
    for i in range(30):
        fwd = list(rng.normal(0.01, 0.06, 8))
        ranks = list(rng.permutation(8).astype(float))
        top = float(np.mean([fwd[j] for j in range(8) if ranks[j] < er.TOP_N]))
        rows.append({"thread": 0, "month": "2017-%02d" % (i % 12 + 1),
                     "ranks": ranks, "fwd": fwd, "cost": 0.0,
                     "paired_net_top_minus_ew": top - float(np.mean(fwd)),
                     "paired_top_minus_bottom": 0.0})
    out = er.nulls({"_rows": rows}, n_draws=300, seed=5)
    n1 = out["null_1_shuffled_companies"]
    assert abs(n1["mean_pct"]) < 0.5, "the shuffled-company null is not centred"
    assert 0.0 <= n1["p_one_sided"] <= 1.0


# ── 7. the budget gate is real ────────────────────────────────────────────

def test_the_hard_cap_refuses_rather_than_warns(monkeypatch):
    """A cap that logs and continues is not a cap. It must raise, so a caller
    cannot mistake an exhausted budget for an empty result."""
    monkeypatch.setattr(er.SPEND, "nano_out", 10**12, raising=False)
    with pytest.raises(er.HardCapReached):
        er._gate(er.REWRITER_MODEL)


def test_the_local_cap_sits_below_the_mandate():
    assert er.HARD_CAP_USD < 5.00


def test_the_decider_prompt_pins_english_and_asks_the_canary_last():
    """DeepSeek code-switches to Chinese without a language pin, and a canary
    asked BEFORE the rank would anchor the rank."""
    sys_prompt = er.DECIDER_SYSTEM
    assert "English only" in sys_prompt
    assert sys_prompt.index('"rank"') < sys_prompt.index('"guess_year"')
    assert sys_prompt.index('"rank"') < sys_prompt.index('"guess_company"')


def test_the_rewriter_is_never_sent_a_temperature():
    """`temperature` is a 400 on gpt-5-nano. Pin the fact in the source so a
    later 'consistency' edit cannot reintroduce it."""
    import inspect
    src = inspect.getsource(er.call_rewriter)
    # the KWARG, not the word -- the source comment explaining the 400 is
    # exactly the documentation we want to keep
    assert "temperature=" not in src
    assert 'reasoning_effort="minimal"' in src


def test_the_8k_tape_is_refused_with_a_stated_reason():
    """A silent omission is indistinguishable from an oversight. The refusal
    and its reason must travel in the built window record."""
    import json
    if not er.WINDOWS_PATH.exists():
        pytest.skip("windows not built on this machine")
    rec = json.loads(er.WINDOWS_PATH.read_text(encoding="utf-8"))
    reason = rec["excluded_source"]["edgar_8k_items"]
    assert "REFUSED" in reason
    assert "company_tickers.json" in reason
