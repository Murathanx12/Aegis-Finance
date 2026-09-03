"""The null bar, tested against the defect it was built because of.

The load-bearing test is the S36 pin: a model that holds ONE persistent random
tilt over a panel with persistent cross-sectional structure PASSES the old
`|shuffled-ranking null t| < 2` bar (the re-randomising null is near-N(0,1),
so its one draw reads clean) while the tilt's own naive t clears 2 -- a false
positive -- and the model-null percentile reads the same statistic as
unremarkable (the fitted-on-noise null's t has sd ~22 on this panel). A bar
that cannot refuse the design it replaced has not been shown to do anything.

Everything here is OFFLINE and synthetic, runs in well under a second, and
uses `np.random.default_rng(seed)` throughout -- never `np.random.seed`.
"""

from __future__ import annotations

import numpy as np
import pytest

from learner import nullbar as NB


# ------------------------------------------------------------- the fixture

N_MONTHS = 60
N_NAMES = 50


def _panel(seed: int = 11) -> dict:
    """A panel whose target has a PERSISTENT cross-sectional component.

    y[t, i] = a[i] + 0.3 * e[t, i]. The name effects `a` are the reason the
    S36 defect exists: any FIXED ranking correlates with `a` at ~N(0, 1/n)
    and then repeats that correlation every month, so its monthly ICs are a
    near-constant series and the naive across-months t explodes.
    """
    rng = np.random.default_rng(seed)
    a = rng.normal(size=N_NAMES)
    e = rng.normal(size=(N_MONTHS, N_NAMES))
    return {"y": a[None, :] + 0.3 * e}


def _rank(x: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(x)).astype("float64")


def _naive_t_of_monthly_ics(scores: np.ndarray, y: np.ndarray) -> float:
    """Spearman IC per month, then the naive t that assumes the months are
    independent draws -- the exact statistic the old bar was applied to.

    `scores` is (n_months, n_names): a FIXED ranking repeats one row.
    """
    ics = []
    for t in range(y.shape[0]):
        rs, ry = _rank(scores[t]), _rank(y[t])
        ics.append(float(np.corrcoef(rs, ry)[0, 1]))
    ics = np.asarray(ics)
    return float(ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics))))


def _fit_fixed_tilt(panel: dict, seed: int, shuffle_target: bool) -> dict:
    """The S36 offender as a five-line pipeline.

    A 'model' that emits ONE score vector and holds it for the whole window --
    which is what any fitted model does out of sample. `shuffle_target` is
    accepted for the FitFn contract; a model fitted on a shuffled target locks
    onto noise exactly as a random fixed vector does, so the draw is the seed's
    random tilt either way. What matters is PERSISTENCE, and both branches
    have it -- that is the point.
    """
    rng = np.random.default_rng(seed)
    s = rng.normal(size=N_NAMES)
    scores = np.tile(s, (N_MONTHS, 1))
    return {"t_naive": _naive_t_of_monthly_ics(scores, panel["y"])}


# ------------------------------------------- (a) the refusal below 64 draws

def test_model_null_percentile_refuses_below_64_draws():
    with pytest.raises(NB.InsufficientDrawsError, match="REFUSED: 32 draws < 64"):
        NB.model_null_percentile(_fit_fixed_tilt, _panel(), n_draws=32,
                                 metrics=("t_naive",), seed=0)


def test_the_refusal_quotes_the_capital_authoritative_floor():
    """The error is where the reader learns the right number, so it must say 256."""
    with pytest.raises(NB.InsufficientDrawsError, match="256"):
        NB.model_null_percentile(_fit_fixed_tilt, _panel(), n_draws=8)


def test_verdict_returns_explicit_cannot_determine_below_the_floor():
    v = NB.verdict(3.0, list(range(20)))
    assert v["verdict"].startswith(NB.CANNOT_DETERMINE)
    assert "20 < 64" in v["verdict"]          # says why, inline
    assert v["p_one_sided"] is None           # never a number it cannot back


def test_p_helpers_refuse_an_empty_null():
    with pytest.raises(NB.InsufficientDrawsError):
        NB.p_one_sided(1.0, [])
    with pytest.raises(NB.InsufficientDrawsError):
        NB.percentile_of(1.0, [np.nan, np.nan])


# ------------------------- (b) the S36 defect: red under the old bar, caught

def test_a_persistent_tilt_passes_the_old_shuffled_ranking_bar_and_fails_the_model_null():
    """The pin. Three facts, asserted in order:

    1. The OLD bar as written -- ONE draw of a ranking re-randomised every
       month, require |t| < 2 -- reads 'clean', because re-randomising washes
       the tilt out monthly and leaves an ~N(0,1) statistic. (Across 64 such
       draws the share over |t| 2 stays near the nominal ~5%: the wash-out is
       structural, not one lucky seed.)
    2. The 'real' model (one persistent tilt, ZERO skill by construction)
       posts naive |t| > 2 anyway -- so the old bar calls skill on a model
       that has none. That is the S36 false positive.
    3. The MODEL null -- the same persistent-tilt pipeline refitted on 64
       seeds -- reproduces the fat t distribution (a third or more of draws
       beyond |t| 2) and places the real statistic inside its bulk: p > 0.05.
    """
    panel = _panel()

    # 1. the old bar: re-randomising ranking nulls. Tilts wash out monthly.
    rng = np.random.default_rng(20260903)
    old_null_ts = []
    for _ in range(64):
        scores = rng.normal(size=(N_MONTHS, N_NAMES))   # fresh ranking each month
        old_null_ts.append(_naive_t_of_monthly_ics(scores, panel["y"]))
    assert abs(old_null_ts[0]) < 2.0, "the old bar's single draw reads 'clean'"
    share_old = float(np.mean(np.abs(old_null_ts) > 2.0))
    assert share_old < 0.20, (
        f"the re-randomising null crosses |t| 2 in {share_old:.0%} of draws -- "
        "it is supposed to be near-N(0,1) (measured sd ~1.1), which is WHY "
        "it cannot catch a tilt")

    # 2. a skill-free persistent tilt that the old bar would call significant.
    #    Deterministic seed scan, so the test never depends on one lucky draw.
    real_seed = next(s for s in range(1000, 1400)
                     if 2.0 < _fit_fixed_tilt(panel, s, False)["t_naive"] < 3.0)
    real_t = _fit_fixed_tilt(panel, real_seed, False)["t_naive"]
    assert real_t > 2.0     # old bar: null clean + |t| > 2  =>  'skill'. Wrong.

    # 3. the model null reads the same number as noise.
    res = NB.model_null_percentile(
        _fit_fixed_tilt, panel, n_draws=64, metrics=("t_naive",),
        seed=500, observed={"t_naive": real_t})
    m = res["metrics"]["t_naive"]
    assert res["null_bar"] == NB.MODEL_NULL_BAR
    assert m["n_draws"] == 64
    # the mis-specification, made visible: the model null crosses 2 freely,
    # at MANY times the re-randomising null's rate
    null_ts = [_fit_fixed_tilt(panel, 500 + 1 + i, True)["t_naive"] for i in range(64)]
    share_model = float(np.mean(np.abs(null_ts) > 2.0))
    assert share_model > 0.50                       # measured: ~92%, sd ~22
    assert share_model > 3 * max(share_old, 0.05)
    # and the 'significant' real t sits inside the null's bulk
    assert m["p_one_sided"] > 0.05
    v = NB.verdict(real_t, null_ts)
    assert v["verdict"] == "WITHIN_MODEL_NULL"


# ---------------------------------- (c) percentile arithmetic, known answers

def test_percentile_and_p_on_a_known_distribution():
    null = np.arange(1.0, 100.0)                        # 1..99, n = 99
    # 10 draws are >= 90, add-one: (10 + 1) / (99 + 1)
    assert NB.p_one_sided(90.0, null) == pytest.approx(11 / 100)
    assert NB.percentile_of(90.0, null) == pytest.approx(89 / 99)
    # above every draw: never zero, exactly 1/(n+1)
    assert NB.p_one_sided(1000.0, null) == pytest.approx(1 / 100)
    # below every draw
    assert NB.p_one_sided(-5.0, null) == pytest.approx(1.0)
    assert NB.percentile_of(-5.0, null) == 0.0


def test_verdict_clears_and_stays_within_on_known_p():
    null = list(np.arange(1.0, 100.0))
    assert NB.verdict(1000.0, null)["verdict"] == "CLEARS_MODEL_NULL"    # p = .01
    assert NB.verdict(50.0, null)["verdict"] == "WITHIN_MODEL_NULL"      # p = .51


def test_summarise_null_reports_the_five_numbers():
    s = NB.summarise_null(np.arange(1.0, 101.0))
    assert s["n_draws"] == 100
    assert s["p50"] == pytest.approx(50.5)
    assert s["min"] == 1.0 and s["max"] == 100.0
    assert s["sd"] == pytest.approx(29.011, abs=0.001)


def test_nan_draws_are_dropped_not_counted():
    """A draw that failed to produce the metric shrinks the null; it must
    never inflate the denominator and flatter the p."""
    null = list(np.arange(1.0, 100.0)) + [np.nan] * 50
    assert NB.p_one_sided(90.0, null) == pytest.approx(11 / 100)


def test_a_metric_short_of_the_floor_is_cannot_determine_not_a_number():
    def fit(panel, seed, shuffle):
        if shuffle and seed % 2:
            return {"m": float("nan")}          # half the draws fail
        return {"m": float(seed)}
    res = NB.model_null_percentile(fit, None, n_draws=64, metrics=("m",),
                                   seed=0, observed={"m": 3.0})
    blk = res["metrics"]["m"]
    assert "p_one_sided" not in blk
    assert blk["verdict"].startswith(NB.CANNOT_DETERMINE)
    assert blk["n_draws"] == 32


# -------------------------------------------------- the family correction

def test_family_max_p_scores_the_best_arm_against_the_per_draw_max():
    observed = {"a": 3.0, "b": 1.0}
    draws = [{"a": i / 64.0, "b": 2.0 - i / 64.0} for i in range(64)]
    out = NB.family_max_p(observed, draws)
    assert out["best_arm"] == "a"
    # per-draw max = max(i/64, 2 - i/64) <= 2 always, so nothing reaches 3.0
    assert out["p_one_sided_family"] == pytest.approx(1 / 65, abs=1e-4)
    assert out["n_draws"] == 64


def test_family_max_p_refuses_below_the_floor():
    out = NB.family_max_p({"a": 3.0}, [{"a": 0.0}] * 10)
    assert out["verdict"].startswith(NB.CANNOT_DETERMINE)


# ------------------------------------------------------- the legacy stamp

def test_the_legacy_annotation_is_greppable_and_names_this_module():
    """Every un-migrated gate stamps this exact string; if it drifts, the
    grep story (`grep -r LEGACY_SHUFFLED_RANKING`) silently breaks."""
    assert "LEGACY_SHUFFLED_RANKING" in NB.LEGACY_SHUFFLED_RANKING
    assert "learner/nullbar.py" in NB.LEGACY_SHUFFLED_RANKING


def test_states_shuffled_null_carries_the_legacy_stamp():
    """`learner.states.shuffled_null` re-randomises every draw, so it cannot
    catch a persistent random partition; its output must say so itself."""
    pd = pytest.importorskip("pandas")
    sklearn = pytest.importorskip("sklearn")  # noqa: F841  states imports it
    from learner import states as S
    rng = np.random.default_rng(3)
    months = [f"2020-{m:02d}" for m in range(1, 13)]
    df = pd.DataFrame({
        "month": np.repeat(months, 20),
        "state_k2": rng.integers(0, 2, size=12 * 20),
        "excess_vw_1m": rng.normal(size=12 * 20),
    })
    out = S.shuffled_null(df, "state_k2", "excess_vw_1m", n_shuffles=20, seed=1)
    assert out["null_bar"] == NB.LEGACY_SHUFFLED_RANKING
