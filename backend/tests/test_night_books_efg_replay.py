"""T3 — Books E, F and G's replay job, on synthetic panels.

Three things are pinned here and each of them is a way the job could be
convincingly wrong while every number in it was arithmetically right:

  1. a PLANTED effect is found and its placebo is not. A replay that cannot
     find an effect it was handed is not evidence of anything, and a replay
     that finds one in a shuffled control is worse;
  2. the FLOOR moves the twin. TRIAL-H5's lesson, and `A_corner`'s: a
     corner-dependent control must be re-measured at every corner, and a $10M
     book against a $3M control is a different claim from the one being tested;
  3. the family Holm corrects against the DECLARED size of four, not against
     the three legs this job happens to compute. `C_v1` is the fourth and is
     read by another job; it is NAMED without a p-value, never dropped.

No test here reads the 1 GB JKP panel or any WRDS file. Every date is derived
from `today` — a literal month in a fixture is a fixture that fails the day
after it passes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import night_books_efg_replay as EFG
from scripts.night_first_books_replay import holm, run_monthly


# --------------------------------------------------------------------------
# fixtures


def _months(n: int):
    """`n` consecutive monthly periods ending with the month before this one."""
    end = pd.Period(pd.Timestamp.today(), freq="M") - 1
    return [end - i for i in range(n - 1, -1, -1)]


def _panel(n_months: int = 60, n_names: int = 90, *, small_from: int = 60,
           effect: float = 0.0, ranks=None):
    """A synthetic monthly CRSP panel.

    `effect` is the extra monthly return handed to the names whose `ranks` value
    is in the top tercile — the planted signal. Names from `small_from` on sit
    below the $10M floor and above the $3M one, so raising the floor removes a
    known set of names.
    """
    import numpy as np

    rng = np.random.default_rng(20260913)
    months = _months(n_months)
    ranks = ranks if ranks is not None else {i: float(i) for i in range(n_names)}
    cut = float(np.quantile(list(ranks.values()), 2.0 / 3.0))
    rows = []
    for ym in months:
        base = rng.normal(0.0, 0.02, size=n_names)
        for i in range(n_names):
            bonus = effect if ranks[i] >= cut else 0.0
            rows.append({
                "permno": 1000 + i,
                "ym": ym,
                "ret_m": float(base[i]) + bonus,
                "price": 50.0,
                "dv": 4_000_000.0 if i >= small_from else 25_000_000.0,
                "turnover_m": 0.05,
            })
    return pd.DataFrame(rows)


def _jkp_frames(panel, values: dict, *, column="qmj", extra=None):
    """{ym: frame} carrying `column` (and any `extra` columns) per permno."""
    frames = {}
    for ym, g in panel.groupby("ym", sort=False):
        rec = {"permno": [int(p) for p in g["permno"]],
               column: [values[int(p) - 1000] for p in g["permno"]]}
        for k, v in (extra or {}).items():
            rec[k] = [v[int(p) - 1000] for p in g["permno"]]
        frames[ym] = pd.DataFrame(rec)
    return frames


# --------------------------------------------------------------------------
# 1. the planted effect, and its placebo


def test_a_planted_effect_is_found_and_a_shuffled_placebo_is_not():
    """The same engine, the same twin, the same costs — the only difference is
    whether the column the book sorts on is the column the return was planted
    on."""
    ranks = {i: float(i) for i in range(90)}
    panel = _panel(effect=0.02, ranks=ranks)
    covered = {ym: set(range(1000, 1090)) for ym in panel["ym"].unique()}

    real = EFG.run_cell(panel, book="E", label="planted",
                        select=EFG.book_e_selector(
                            _jkp_frames(panel, [float(i) for i in range(90)])),
                        pool_filter=EFG._pool_filter(covered, set()),
                        floor_usd=None, seed=1)
    assert real["result"]["mean_excess_net_monthly"] > 0.01
    assert real["result"]["nw_lag2_t"] > 4.0

    # The placebo sorts on a column RESHUFFLED EVERY MONTH, which is the honest
    # "no relation" control. A column shuffled ONCE is not one: it picks a fixed
    # arbitrary subset, and a fixed subset of a panel that carries a planted
    # effect holds a fixed and generally wrong share of the names that earn it,
    # so it drifts away from a twin that re-draws. That version of this test
    # failed at t -3.28 on its first run, and the failure was the test's.
    import numpy as np

    rng = np.random.default_rng(7)
    placebo_frames = {}
    for ym, g in panel.groupby("ym", sort=False):
        placebo_frames[ym] = pd.DataFrame({
            "permno": [int(p) for p in g["permno"]],
            "qmj": rng.permutation(90).astype(float)})
    fake = EFG.run_cell(panel, book="E", label="placebo",
                        select=EFG.book_e_selector(placebo_frames),
                        pool_filter=EFG._pool_filter(covered, set()),
                        floor_usd=None, seed=1)
    assert abs(fake["result"]["mean_excess_net_monthly"]) < 0.005
    assert abs(fake["result"]["nw_lag2_t"]) < 2.0


def test_the_seasonality_placebo_reads_the_EARLIER_month_and_is_pit_safe():
    """TRIAL-DRAFT-F section 5 clause 2. The shifted read must select a
    DIFFERENT set from the unshifted one, and it must use strictly older
    information — a placebo that peeked would be the leak it exists to rule
    out."""
    panel = _panel(n_months=24)
    months = sorted(panel["ym"].unique())
    # A column whose ranking rotates every month, so the previous month's read
    # is a genuinely different cross-section.
    frames = {}
    for j, ym in enumerate(months):
        order = [(i + j) % 90 for i in range(90)]
        frames[ym] = pd.DataFrame({
            "permno": list(range(1000, 1090)),
            "seas_11_15an": [float(o) for o in order],
            "seas_16_20an": [float(o) for o in order]})
    pool = pd.DataFrame({"permno": list(range(1000, 1090)),
                         "dv": [25e6] * 90, "price": [50.0] * 90})
    now = EFG.book_f_selector(frames)(pool, months[5])
    then = EFG.book_f_selector(frames, shift_months=1)(pool, months[5])
    assert now and then
    assert set(now[:30]) != set(then[:30])
    # The shifted selector must return exactly what the unshifted one returned
    # one month earlier: it is the SAME read, moved back, and nothing else.
    assert then == EFG.book_f_selector(frames)(pool, months[4])


# --------------------------------------------------------------------------
# 2. the floor moves the twin


def test_the_floor_moves_the_band_the_BOOK_AND_THE_TWIN_are_drawn_from():
    """`run_monthly` hands the selector the very frame it draws the twin from,
    so recording what the selector saw records what the twin could hold."""
    panel = _panel(n_months=12, small_from=60)
    seen: dict = {}

    def recording(tag):
        def select(pool, ym):
            seen.setdefault(tag, []).append(
                {int(p) for p in pool["permno"]})
            return [int(p) for p in pool["permno"]][:30]
        return select

    run_monthly(panel, recording("3M"), k=30, seed=1, label="x", floor_usd=None)
    run_monthly(panel, recording("10M"), k=30, seed=1, label="x",
                floor_usd=EFG.SECONDARY_FLOOR_USD)

    big = set(range(1000, 1060))
    small = set(range(1060, 1090))
    assert all(s == big | small for s in seen["3M"])
    assert all(s == big for s in seen["10M"])
    # And the same for a pool_filter: the twin sees the FILTERED band, not the
    # raw eligible one, which is the whole reason `pool_filter` exists.
    covered = {ym: set(range(1000, 1040)) for ym in panel["ym"].unique()}
    seen.clear()
    run_monthly(panel, recording("covered"), k=30, seed=1, label="x",
                floor_usd=None, pool_filter=EFG._pool_filter(covered, set()))
    assert all(s == set(range(1000, 1040)) for s in seen["covered"])


def test_a_book_and_its_twin_never_see_a_name_the_characteristic_is_missing_on():
    """The coverage confound, in one assertion: with half the band uncovered,
    neither leg may reach it."""
    panel = _panel(n_months=12)
    covered = {ym: set(range(1000, 1045)) for ym in panel["ym"].unique()}
    cell = EFG.run_cell(
        panel, book="E", label="covered_only",
        select=EFG.book_e_selector(_jkp_frames(panel,
                                               [float(i) for i in range(90)])),
        pool_filter=EFG._pool_filter(covered, set()), floor_usd=None, seed=1)
    assert cell["result"]["pool_filtered_to_the_covered_band"] is True
    assert cell["result"]["n_blocks"] > 0


# --------------------------------------------------------------------------
# 3. the family Holm


def test_the_family_holm_corrects_against_the_DECLARED_size_of_four():
    assert len(EFG.DECLARED_FAMILY) == 4
    assert "disposition_overhang_conditioner_v1" in EFG.DECLARED_FAMILY
    pvals = {name: None for name in EFG.DECLARED_FAMILY}
    pvals["qmj_quality_tilt_v0"] = 0.01
    pvals["seasonality_11_20_v0"] = 0.02
    pvals["forecast_dispersion_v0"] = 0.30
    block = holm(pvals, family=EFG.FAMILY)
    assert block["family"] == EFG.FAMILY
    assert block["declared_family_size"] == 4
    assert block["legs_without"] == ["disposition_overhang_conditioner_v1"]
    # The smallest p is compared against 0.05/4, not 0.05/3: a leg that could
    # not run does not make the correction cheaper for the ones that did.
    assert block["per_leg"]["qmj_quality_tilt_v0"]["holm_alpha"] == pytest.approx(0.0125)


# --------------------------------------------------------------------------
# the clauses, the MDE and the liveness check


def test_the_contamination_clause_excludes_a_year_the_band_barely_covers():
    panel = _panel(n_months=36)
    months = sorted(panel["ym"].unique())
    thin_year = months[0].year
    covered = {ym: (set(range(1000, 1002)) if ym.year == thin_year
                    else set(range(1000, 1090))) for ym in months}
    cont = EFG.coverage_and_contamination(panel, covered, book="F",
                                          floor_usd=None)
    assert thin_year in cont["excluded_years"]
    assert cont["per_year"][str(thin_year)]["why"]


def test_recompute_mde_measures_the_books_own_series_not_the_registration():
    import numpy as np

    rng = np.random.default_rng(3)
    res = {"excess": list(rng.normal(0.0, 0.03, size=200))}
    got = EFG.recompute_mde(res)
    assert got["status"] == "MEASURED"
    assert got["n_blocks"] == 200
    assert 0.0 < got["mde_monthly"] < 0.02
    assert got["declared_mde_nominal"] == EFG.DECLARED_MDE_NOMINAL
    # Too short to measure an autocorrelation is CANNOT DETERMINE, not zero.
    assert EFG.recompute_mde({"excess": [0.01, 0.02]})["status"] == "CANNOT DETERMINE"


def test_a_control_that_was_never_alive_is_untestable_and_not_passed():
    """The 2026-09-13 lesson: Book C's momentum falsifier 'passed' with raw
    momentum at t 0.15, because nothing was alive to subsume."""
    dead = {"multivariate": {"x": {"nw_lag2_t": 0.2}},
            "univariate": {"x": {"nw_lag2_t": 0.15}}}
    got = EFG.survives(dead, "x")
    assert got["testable"] is False
    assert "could not run" in got["why"]
    alive = {"multivariate": {"x": {"nw_lag2_t": 3.0}},
             "univariate": {"x": {"nw_lag2_t": 4.0}}}
    assert EFG.survives(alive, "x")["testable"] is True
    assert EFG.survives(alive, "x")["survives"] is True


def test_an_untestable_falsifier_makes_the_verdict_cannot_determine():
    cell = {"result": {"mean_excess_net_monthly": 0.02, "nw_lag2_t": 3.0},
            "by_era": {"1990-1999": {"mean_excess_net_monthly": 0.01},
                       "2000-2009": {"mean_excess_net_monthly": 0.01},
                       "2010-2016": {"mean_excess_net_monthly": 0.01},
                       "2017-2024": {"mean_excess_net_monthly": 0.01}}}
    sec = {"result": {"mean_excess_net_monthly": 0.01}}
    ok = [{"falsifier": "a", "fires": False, "clause": "a"},
          {"falsifier": "b", "fires": False, "clause": "b"}]
    assert EFG.decide_cell("E", cell, ok, sec)["verdict"] == "PRODUCT_PROMISING"
    unknown = [{"falsifier": "a", "fires": False, "clause": "a"},
               {"falsifier": "b", "fires": None, "clause": "b"}]
    out = EFG.decide_cell("E", cell, unknown, sec)
    assert out["verdict"] == "CANNOT_DETERMINE"
    assert out["undetermined_falsifiers"] == ["b"]


def test_a_primary_at_or_below_zero_closes_the_book_whatever_the_falsifiers_did():
    cell = {"result": {"mean_excess_net_monthly": -0.001, "nw_lag2_t": -0.4},
            "by_era": {}}
    out = EFG.decide_cell("G", cell, [{"falsifier": "a", "fires": False,
                                       "clause": "a"}], None)
    assert out["verdict"] == "FAILED_VARIANT"
    assert "WRONG SIDE OF ZERO" in out["clauses_fired"][0]


def test_the_receipt_prints_its_own_construction():
    """Book C's run 1 said `confirm_slice 1995-2024` while warming a 60-month
    overhang at 24 months. A receipt that does not print its construction
    cannot be checked against the registration that licensed it."""
    cells = {"primary_floor": {"result": {"mean_excess_net_monthly": 0.001,
                                          "nw_lag2_t": 1.0, "n_blocks": 10},
                               "by_era": {}},
             "secondary_floor": {"result": {"mean_excess_net_monthly": 0.001,
                                            "nw_lag2_t": 1.0, "n_blocks": 10},
                                 "by_era": {}}}
    payload = EFG._book_payload(
        "E", "qmj_quality_tilt_v0", "TRIAL-DRAFT-E (UNSIGNED)", cells, [], {},
        {}, {"verdict": "CONDITIONAL", "reading": "x"}, smoke=False,
        construction={"column": "qmj"})
    rc = payload["registered_construction"]
    assert rc["honours_the_registration"] is True
    assert rc["cost_curve"] == "flat_25bps_pending_5c"
    assert rc["floors_usd"]["secondary"] == 10_000_000.0
    smoky = EFG._book_payload(
        "E", "qmj_quality_tilt_v0", "TRIAL-DRAFT-E (UNSIGNED)", cells, [], {},
        {}, {"verdict": "CONDITIONAL", "reading": "x"}, smoke=True,
        construction={"column": "qmj"})
    assert smoky["registered_construction"]["honours_the_registration"] is False


def test_jkp_files_pick_the_chunks_that_overlap_the_window(tmp_path,
                                                           monkeypatch):
    d = tmp_path / "wrds"
    (d / "jkp_full").mkdir(parents=True)
    for lo, hi in ((1986, 1987), (1990, 1991), (2010, 2011)):
        (d / "jkp_full" / f"jkp_usa_{lo}_{hi}.parquet").write_bytes(b"")
    (d / "jkp_global_factor_usa.parquet").write_bytes(b"")
    monkeypatch.setattr(EFG, "wrds_dir", lambda: d)
    got = [p.name for p in EFG.jkp_files(1990, 2012)]
    assert "jkp_usa_1990_1991.parquet" in got
    assert "jkp_usa_2010_2011.parquet" in got
    assert "jkp_usa_1986_1987.parquet" not in got
    # 1990-2012 does not reach the continuation file; 1990-2024 does.
    assert "jkp_global_factor_usa.parquet" not in got
    assert "jkp_global_factor_usa.parquet" in [p.name for p in
                                               EFG.jkp_files(1990, 2024)]


def test_the_big_half_filter_cuts_inside_the_covered_band():
    """A 'big half' cut against a control drawn from the whole band would
    compare two universes and call it a size check."""
    pool = pd.DataFrame({"permno": list(range(1000, 1010)),
                         "dv": [1e6 * (i + 1) for i in range(10)],
                         "price": [50.0] * 10})
    ym = _months(1)[0]
    covered = {ym: set(range(1000, 1008))}
    got = EFG._big_half_filter(covered, set())(pool, ym)
    # Median is taken over the COVERED eight, not the ten in the raw pool.
    assert set(got["permno"]) == {1004, 1005, 1006, 1007}


def test_the_dispersion_falsifier_refuses_when_the_si_panel_is_absent(tmp_path,
                                                                     monkeypatch):
    """A check that did not run is not a check that passed."""
    from backend.services import book_signals as BS

    monkeypatch.setattr(BS, "short_interest_panel_dir", lambda: tmp_path / "nope")
    panel = _panel(n_months=6)
    rows, status = EFG.dispersion_si_rows(panel, {}, {}, set(), floor_usd=None)
    assert rows == []
    assert "UNTESTABLE" in status


# --------------------------------------------------------------------------
# TRIAL-DRAFT-G Amendment 1 — the price-scaled read (chunk 15b)


def _ibes_frames(panel, *, stdev: dict, meanest: dict, numest: int = 5):
    frames = {}
    for ym, g in panel.groupby("ym", sort=False):
        frames[ym] = pd.DataFrame({
            "permno": [int(p) for p in g["permno"]],
            "stdev": [stdev[int(p) - 1000] for p in g["permno"]],
            "meanest": [meanest[int(p) - 1000] for p in g["permno"]],
            "numest": [numest] * len(g),
        })
    return frames


def test_the_default_scale_leaves_the_g_selector_byte_identical():
    """The amendment must not be able to change v0's selection by existing."""
    panel = _panel(n_months=24, n_names=90)
    frames = _ibes_frames(panel,
                          stdev={i: 0.01 * (i + 1) for i in range(90)},
                          meanest={i: 1.0 for i in range(90)})
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    v0 = EFG.book_g_selector(frames)(pool, ym)
    same = EFG.book_g_selector(frames, scale="meanest")(pool, ym)
    assert v0 == same and v0, "the default path is v0's, unchanged"


def test_the_price_scaled_selector_reads_price_off_the_POOL_not_the_ibes_frame():
    """The PIT price lives on the replay panel, which is where the $5 minimum
    and the dollar-volume floor are already computed from. A selector that
    needed a price column on the IBES frame would need a second source for a
    number the panel already carries at the right stamp."""
    panel = _panel(n_months=24, n_names=90)
    frames = _ibes_frames(panel,
                          stdev={i: 0.01 * (i + 1) for i in range(90)},
                          meanest={i: 1.0 for i in range(90)})
    assert "price" not in frames[sorted(frames)[0]].columns
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    picked = EFG.book_g_selector(frames, scale="price")(pool, ym)
    assert picked, "the selector carried price across from the pool"
    # Price is constant in this panel, so price-scaling is a positive rescaling
    # of v0's score and must not reorder anything.
    assert picked == EFG.book_g_selector(frames)(pool, ym)


def test_price_scaling_REORDERS_when_the_eps_channel_is_the_only_difference():
    """The amendment's point, at the selector: two names with identical
    uncertainty per dollar, one with near-zero consensus EPS. v0 avoids the
    near-zero-EPS name as if it were the most disagreed-about in the market."""
    panel = _panel(n_months=24, n_names=90)
    stdev = {i: 0.10 for i in range(90)}
    meanest = {i: 5.0 for i in range(90)}
    meanest[0] = 0.01                      # permno 1000: EPS near zero
    frames = _ibes_frames(panel, stdev=stdev, meanest=meanest)
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    v0 = EFG.book_g_selector(frames)(pool, ym)
    amended = EFG.book_g_selector(frames, scale="price")(pool, ym)
    assert 1000 not in v0, "v0 avoids it for its EPS LEVEL, not its disagreement"
    assert 1000 in amended, "the amendment ranks it with its identical peers"


def test_the_amended_book_carries_its_own_label_prereg_and_construction():
    """A receipt that could be mistaken for v0's is the failure this guards.

    Book C's run 1 printed `confirm_slice 1995-2024` while warming a 60-month
    overhang at 24 -- a receipt that does not print its own construction cannot
    be checked against the registration that licensed it.
    """
    panel = _panel(n_months=60, n_names=90)
    frames = _ibes_frames(panel,
                          stdev={i: 0.01 * (i + 1) for i in range(90)},
                          meanest={i: 1.0 for i in range(90)})
    book = EFG.replay_book_g(panel, frames, smoke=True, scale="price")
    c = book["registered_construction"]
    assert book["book"] == "forecast_dispersion_price_scaled_v1"
    assert "Amendment 1" in book["prereg"] and "UNSIGNED" in book["prereg"]
    assert c["dispersion_scale"] == "price"
    assert c["ratio"] == "|stdev / price|"
    assert "Amendment 1" in c["amendment"]
    # and the frozen fields the amendment does NOT touch are still v0's
    assert c["k"] == EFG.K and c["tercile"] == EFG.TERCILE
    assert c["filters"]["numest_min"] == 3
    assert c["declared_effect_size"] == EFG.DECLARED_EFFECT["G"]

    v0 = EFG.replay_book_g(panel, frames, smoke=True)
    assert v0["book"] == "forecast_dispersion_v0"
    assert v0["registered_construction"]["dispersion_scale"] == "meanest"
    assert v0["registered_construction"]["amendment"].startswith("none")


def test_an_unknown_scale_is_refused_at_the_replay_too():
    panel = _panel(n_months=24, n_names=90)
    frames = _ibes_frames(panel, stdev={i: 0.1 for i in range(90)},
                          meanest={i: 1.0 for i in range(90)})
    with pytest.raises(ValueError, match="unknown dispersion scale"):
        EFG.replay_book_g(panel, frames, smoke=True, scale="ebitda")


def test_the_amendment_is_its_OWN_family_and_does_not_join_the_spent_one():
    """A fifth leg added to `NIGHT_JOB_BOOKS_2026_09_13` after its four numbers
    were seen would be a family that grew to fit a result."""
    assert EFG.FAMILY_G_AMENDMENT != EFG.FAMILY
    assert "forecast_dispersion_price_scaled_v1" not in EFG.DECLARED_FAMILY
    assert len(EFG.DECLARED_FAMILY) == 4


def test_the_job_is_registered_and_reachable_by_name():
    from scripts.night_factory_jobs import JOB_STAGES, JOBS

    assert "G_price_scaled" in JOBS
    assert JOB_STAGES["G_price_scaled"] == "pnl"


def test_the_amendment_note_is_quoted_into_every_amended_receipt():
    """A number that travels without the reason it exists is a number that gets
    quoted as v0's next month."""
    assert "Amendment 1" in EFG.AMENDMENT_1_NOTE
    assert "0.79" in EFG.AMENDMENT_1_NOTE, "the published spread it exceeded"
    assert "UNSIGNED" in EFG.AMENDMENT_1_NOTE
