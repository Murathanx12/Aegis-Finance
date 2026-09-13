"""T3 — Books H and I's replay job, on synthetic panels.

No test here reads a parquet, a WRDS file or a receipt on disk. Every month is
derived from `today`, because a literal quarter in a fixture is a fixture that
fails the day after it passes.

What is pinned, and each is a way the job could be convincingly wrong while
every number in it was arithmetically right:

  1. a PLANTED effect is found and its placebo is not — for BOTH books. A
     replay that cannot find an effect it was handed is not evidence of
     anything, and one that finds an effect in a shuffled control is worse;
  2. the FLOOR moves the band the BOOK AND THE TWIN are drawn from. TRIAL-H5's
     lesson: a $10M book against a $3M control is a different claim;
  3. the grant windows are MARKET-ADJUSTED and refuse a short tape rather than
     imputing one;
  4. no grant classifies itself, and an UNCLASSIFIABLE pair is in NEITHER leg
     of the scheduled/unscheduled falsifier;
  5. a name with no insider sale scores ZERO intensity and is in the book — the
     distinction between "nobody sold" and "we could not tell";
  6. the family Holm corrects against the DECLARED size of two;
  7. the receipt prints its own construction, and a smoke run says so.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import night_books_hi_replay as HI
from scripts.night_first_books_replay import holm, run_monthly


# --------------------------------------------------------------------------
# fixtures


def _months(n: int):
    """`n` consecutive monthly periods ending with the month before this one."""
    end = pd.Period(pd.Timestamp.today(), freq="M") - 1
    return [end - i for i in range(n - 1, -1, -1)]


def _panel(n_months: int = 48, n_names: int = 90, *, small_from: int = 60,
           effect: float = 0.0, winners=frozenset(), months=None):
    """A synthetic monthly CRSP panel.

    Names from `small_from` on sit below the $10M floor and above the $3M one,
    so raising the floor removes a known set of names. `winners` earn `effect`
    extra every month — the planted signal.
    """
    rng = np.random.default_rng(20260914)
    months = list(months) if months is not None else _months(n_months)
    rows = []
    for ym in months:
        base = rng.normal(0.0, 0.02, size=n_names)
        for i in range(n_names):
            rows.append({
                "permno": 1000 + i, "ym": ym,
                "ret_m": float(base[i]) + (effect if (1000 + i) in winners
                                           else 0.0),
                "price": 50.0,
                "dv": 4_000_000.0 if i >= small_from else 25_000_000.0,
                "turnover_m": 0.05,
            })
    return pd.DataFrame(rows)


def _pair_frames(months, stats: dict, *, grant_class="opportunistic",
                 n_prior=4):
    """{ym: pair-level frame} where each permno's ONE insider carries `stats`."""
    out = {}
    for ym in months:
        out[ym] = pd.DataFrame({
            "permno": list(stats),
            "owner_cik": [f"{p}|x" for p in stats],
            # A qualifying pair: pre NEGATIVE, post POSITIVE, statistic
            # post - pre = the planted value.
            "mean_pre": [-0.5 * v for v in stats.values()],
            "mean_post": [0.5 * v for v in stats.values()],
            "n_prior_grants": [n_prior] * len(stats),
            "grant_class": [grant_class] * len(stats),
        })
    return out


def _band_frames(quarters, *, low_sellers, buyback=frozenset(), n_names=90):
    """{q: per-name frame} for Book I over a fixed covered band."""
    out = {}
    for q in quarters:
        permnos = [1000 + i for i in range(n_names)]
        out[q] = pd.DataFrame({
            "permno": permnos,
            "buyback_flag": [p in buyback for p in permnos],
            "buyback_intensity": [0.01 + 0.0001 * (p - 1000) for p in permnos],
            "sell_intensity": [0.0 if p in low_sellers else 0.5
                               for p in permnos],
        })
    return out


# --------------------------------------------------------------------------
# 1. the planted effect, and its placebo


def test_book_h_finds_a_planted_effect_and_a_shuffled_placebo_does_not():
    months = _months(48)
    winners = set(range(1000, 1030))
    panel = _panel(effect=0.02, winners=winners, months=months)
    stats = {p: (10.0 if p in winners else 1.0) for p in range(1000, 1090)}
    covered = {ym: set(stats) for ym in months}

    real = HI.run_cell(panel, book="H", label="planted",
                       select=HI.book_h_selector(_pair_frames(months, stats)),
                       pool_filter=HI._pool_filter(covered, set()),
                       floor_usd=None, seed=1)
    assert real["result"]["mean_excess_net_monthly"] > 0.01
    assert real["result"]["nw_lag2_t"] > 4.0

    # The placebo re-shuffles the statistic EVERY month, which is the honest
    # "no relation" control. A column shuffled ONCE picks a fixed arbitrary
    # subset, and a fixed subset of a panel carrying a planted effect holds a
    # fixed and generally wrong share of the names that earn it — it drifts
    # away from a twin that re-draws, and the failure would be the test's.
    rng = np.random.default_rng(7)
    placebo = {ym: _pair_frames(
        [ym], {p: float(v) for p, v in
               zip(range(1000, 1090), rng.permutation(90))})[ym]
        for ym in months}
    fake = HI.run_cell(panel, book="H", label="placebo",
                       select=HI.book_h_selector(placebo),
                       pool_filter=HI._pool_filter(covered, set()),
                       floor_usd=None, seed=1)
    assert abs(fake["result"]["nw_lag2_t"]) < 2.0


def test_book_i_finds_a_planted_divergence_and_a_shuffled_placebo_does_not():
    months = _months(60)
    winners = set(range(1000, 1030))
    panel = _panel(effect=0.02, winners=winners, months=months)
    qpanel = HI.to_quarterly(panel)
    quarters = sorted(qpanel["ym"].unique())
    frames = _band_frames(quarters, low_sellers=winners,
                          buyback=set(range(1000, 1090)))
    covered = {q: set(range(1000, 1090)) for q in quarters}

    real = HI.run_cell(qpanel, book="I", label="planted",
                       select=HI.book_i_selector(frames, leg="divergence"),
                       pool_filter=HI._pool_filter(covered, set()),
                       floor_usd=None, seed=1)
    assert real["result"]["mean_excess_net_monthly"] > 0.01

    rng = np.random.default_rng(11)
    shuffled = {}
    for q in quarters:
        g = frames[q].copy()
        g["sell_intensity"] = rng.permutation(g["sell_intensity"].to_numpy())
        shuffled[q] = g
    fake = HI.run_cell(qpanel, book="I", label="placebo",
                       select=HI.book_i_selector(shuffled, leg="divergence"),
                       pool_filter=HI._pool_filter(covered, set()),
                       floor_usd=None, seed=1)
    assert abs(fake["result"]["nw_lag2_t"] or 0.0) < 2.5
    assert (fake["result"]["mean_excess_net_monthly"]
            < real["result"]["mean_excess_net_monthly"])


# --------------------------------------------------------------------------
# 2. the floor


def test_the_floor_moves_the_band_the_BOOK_AND_THE_TWIN_are_drawn_from():
    """`run_monthly` hands the selector the very frame it draws the twin from,
    so recording what the selector saw records what the twin could hold."""
    panel = _panel(n_months=12, small_from=60)
    seen: dict = {}

    def recording(tag):
        def select(pool, ym):
            seen.setdefault(tag, []).append({int(p) for p in pool["permno"]})
            return [int(p) for p in pool["permno"]][:HI.K]
        return select

    run_monthly(panel, recording("3M"), k=HI.K, seed=1, label="x",
                floor_usd=None)
    run_monthly(panel, recording("10M"), k=HI.K, seed=1, label="x",
                floor_usd=HI.SECONDARY_FLOOR_USD)
    big, small = set(range(1000, 1060)), set(range(1060, 1090))
    assert all(s == big | small for s in seen["3M"])
    assert all(s == big for s in seen["10M"])


def test_the_floor_moves_the_QUARTERLY_band_too():
    """Book I is graded on quarterly buckets and the corner re-measurement has
    to survive the change of period type, not just the change of floor."""
    qpanel = HI.to_quarterly(_panel(n_months=24, small_from=60))
    seen: dict = {}

    def recording(tag):
        def select(pool, ym):
            seen.setdefault(tag, []).append({int(p) for p in pool["permno"]})
            return [int(p) for p in pool["permno"]][:HI.K]
        return select

    run_monthly(qpanel, recording("3M"), k=HI.K, seed=1, label="x",
                floor_usd=None)
    run_monthly(qpanel, recording("10M"), k=HI.K, seed=1, label="x",
                floor_usd=HI.SECONDARY_FLOOR_USD)
    assert all(s == set(range(1000, 1090)) for s in seen["3M"])
    assert all(s == set(range(1000, 1060)) for s in seen["10M"])


# --------------------------------------------------------------------------
# 3. Book H's grant windows


def _tape(n_sessions=200, names=(1, 2, 3)):
    days = pd.bdate_range(pd.Timestamp.today().normalize()
                          - pd.Timedelta(days=int(n_sessions * 1.6)),
                          periods=n_sessions)
    rows = [{"permno": p, "date": d, "ret": 0.0} for p in names for d in days]
    return pd.DataFrame(rows), days


def test_the_grant_windows_are_MARKET_ADJUSTED_and_refuse_a_short_tape():
    d, days = _tape()
    grant_day = days[100]
    d.loc[(d.permno == 1) & d.date.isin(days[80:100]), "ret"] = -0.01
    d.loc[(d.permno == 1) & d.date.isin(days[101:121]), "ret"] = +0.01
    daily = HI.daily_from_frame(d)
    pre, post = HI.grant_windows(
        daily, np.array([1, 2, 1]),
        np.array([grant_day, grant_day, days[3]], dtype="datetime64[ns]"))

    assert pre[0] < -0.10 and post[0] > 0.10, (
        "the name that fell into its own grant and rose out of it is the "
        "qualifying pattern")
    # The FLAT name is market-adjusted POSITIVE before the grant and negative
    # after, precisely because the market moved and it did not. Without the
    # adjustment both of its numbers would be exactly zero.
    assert pre[1] > 0.0 and post[1] < 0.0
    assert np.isnan(pre[2]) and np.isnan(post[2]), (
        "a grant without twenty sessions of tape behind it yields NaN and is "
        "dropped; an imputed window is a return nobody earned")


def test_no_grant_classifies_itself_and_unclassifiable_is_neither_leg():
    """Three January grants in three consecutive prior years make the FOURTH
    January grant ROUTINE — and the first three cannot be, because the rule
    only ever sees strictly-prior rows."""
    rows = []
    base = pd.Timestamp.today().normalize().year - 6
    for k in range(4):
        rows.append({"pair": "iss|own", "owner_cik": "0000001",
                     "trans_date": pd.Timestamp(f"{base + k}-01-15")})
    # A second pair that grants in a DIFFERENT month each year: opportunistic
    # once it has three prior years, never routine.
    for k, m in enumerate((1, 5, 9, 2)):
        rows.append({"pair": "iss|two", "owner_cik": "0000002",
                     "trans_date": pd.Timestamp(f"{base + k}-{m:02d}-10")})
    g = pd.DataFrame(rows)
    v = HI.classify_scheduled(g)
    one = list(v[g["pair"] == "iss|own"])
    two = list(v[g["pair"] == "iss|two"])
    assert one[:3] == ["unclassifiable"] * 3
    assert one[3] == "routine"
    assert two[:3] == ["unclassifiable"] * 3
    assert two[3] == "opportunistic"


def test_the_scheduled_split_puts_an_unclassifiable_pair_in_NEITHER_leg():
    """Twenty pairs of each class, because a tercile over fewer than twenty
    names is a cut of the survivors and the signal refuses it — which is also
    why this test needs sixty names to say one thing about three."""
    months = _months(6)
    classes = (["routine"] * 20 + ["opportunistic"] * 20
               + ["unclassifiable"] * 20)
    permnos = list(range(1, 61))
    routine = {p for p, c in zip(permnos, classes) if c == "routine"}
    opportunistic = {p for p, c in zip(permnos, classes)
                     if c == "opportunistic"}
    unclassifiable = {p for p, c in zip(permnos, classes)
                      if c == "unclassifiable"}
    frames = {ym: pd.DataFrame({
        "permno": permnos,
        "owner_cik": [f"o{p}" for p in permnos],
        "mean_pre": [-0.1] * 60,
        "mean_post": [0.01 * p for p in permnos],
        "n_prior_grants": [4] * 60,
        "grant_class": classes,
    }) for ym in months}
    pool = pd.DataFrame({"permno": permnos})
    sched = set(HI.book_h_selector(frames, subset="scheduled")(pool, months[0]))
    unsched = set(HI.book_h_selector(frames, subset="unscheduled")(pool,
                                                                   months[0]))
    assert sched and unsched
    assert sched <= routine and unsched <= opportunistic
    assert not (sched & unclassifiable) and not (unsched & unclassifiable), (
        "a pair the CMP rule could not classify is not evidence that its "
        "grants were unscheduled")


# --------------------------------------------------------------------------
# 4. the expanding history


def test_the_pair_state_is_an_EXPANDING_mean_over_grants_already_FILED():
    base = pd.Timestamp.today().normalize() - pd.Timedelta(days=900)
    rows = []
    for k, (pre, post) in enumerate([(-0.1, 0.1), (-0.2, 0.2), (-0.3, 0.3),
                                     (-0.4, 0.4)]):
        rows.append({"pair": "p", "permno": 10, "pre": pre, "post": post,
                     "filing_date": base + pd.Timedelta(days=90 * k),
                     "grant_class": "opportunistic"})
    st = HI.pair_state_rows(pd.DataFrame(rows))
    assert list(st["n_prior_grants"]) == [3, 4], (
        "a pair is scoreable from its third grant, and only then")
    assert st["mean_pre"].iloc[0] == pytest.approx(-0.2)
    assert st["mean_post"].iloc[1] == pytest.approx(0.25)
    # The state is readable in the FILING month of the grant that made it: a
    # Form-4 filed in month m is public at 22:00 ET that day.
    assert st["ym"].iloc[0] == pd.Period(rows[2]["filing_date"], freq="M")


def test_a_state_is_carried_forward_until_the_next_one_and_no_further():
    months = _months(6)
    st = pd.DataFrame({
        "pair": ["p", "p"], "permno": [10, 10],
        "ym": [months[1], months[4]],
        "n_prior_grants": [3, 4], "mean_pre": [-0.2, -0.25],
        "mean_post": [0.2, 0.25], "grant_class": ["opportunistic"] * 2})
    frames = HI.expand_pair_months(st, months)
    assert months[0] not in frames, "a state may not be read before it existed"
    assert set(frames) == set(months[1:])
    assert frames[months[3]]["n_prior_grants"].iloc[0] == 3
    assert frames[months[4]]["n_prior_grants"].iloc[0] == 4
    assert frames[months[5]]["mean_post"].iloc[0] == pytest.approx(0.25)


# --------------------------------------------------------------------------
# 5. Book I's quarterly panel and sale intensity


def test_to_quarterly_COMPOUNDS_and_keeps_the_floor_comparable():
    months = _months(6)
    rows = [{"permno": 1, "ym": ym, "ret_m": 0.10, "price": 20.0,
             "dv": 5_000_000.0, "turnover_m": 0.02} for ym in months]
    q = HI.to_quarterly(pd.DataFrame(rows))
    assert len(q) == 2
    assert q["ret_m"].iloc[0] == pytest.approx(1.10 ** 3 - 1.0)
    assert q["dv"].iloc[0] == 5_000_000.0, (
        "dollar volume is the MEDIAN of the quarter's months, so the floor "
        "means the same thing it means monthly")
    assert str(q["ym"].iloc[0]).endswith(("Q1", "Q2", "Q3", "Q4"))


def _sales(rows):
    return pd.DataFrame(rows).sort_values("filing_date",
                                          kind="mergesort").reset_index(drop=True)


def test_sell_intensity_is_a_bounded_share_of_HOLDINGS_and_zero_is_a_signal():
    end = pd.Timestamp.today().normalize()
    s = _sales([
        {"permno": 1, "owner_cik": "a", "shares": 300.0,
         "shares_owned_following": 700.0,
         "filing_date": end - pd.Timedelta(days=10), "plan_10b5_1": "NO"},
        {"permno": 2, "owner_cik": "b", "shares": 10.0,
         "shares_owned_following": 990.0,
         "filing_date": end - pd.Timedelta(days=10), "plan_10b5_1": "NO"},
        # Outside the 90-day window: it may not touch either name.
        {"permno": 1, "owner_cik": "a", "shares": 9999.0,
         "shares_owned_following": 0.0,
         "filing_date": end - pd.Timedelta(days=400), "plan_10b5_1": "NO"},
    ])
    out = HI.sell_intensity(s, end)
    assert out[1] == pytest.approx(0.30)
    assert out[2] == pytest.approx(0.01)
    assert 3 not in out, (
        "a name with no sale is ABSENT here and the caller supplies the zero; "
        "the frame builder is where 'nobody sold' becomes a score")
    assert all(0.0 <= v <= 1.0 for v in out.values())


def test_the_10b5_1_exclusion_and_the_large_sale_split_change_the_intensity():
    end = pd.Timestamp.today().normalize()
    s = _sales([
        {"permno": 1, "owner_cik": "a", "shares": 300.0,
         "shares_owned_following": 700.0,
         "filing_date": end - pd.Timedelta(days=5), "plan_10b5_1": "YES"},
        {"permno": 2, "owner_cik": "b", "shares": 10.0,
         "shares_owned_following": 990.0,
         "filing_date": end - pd.Timedelta(days=5), "plan_10b5_1": "NO"},
    ])
    assert 1 in HI.sell_intensity(s, end)
    assert 1 not in HI.sell_intensity(s, end, exclude_10b5_1=True), (
        "a pre-scheduled sale carries no discretionary information and the "
        "reported leg is what shows how much of the signal it was")
    big = HI.sell_intensity(s, end, large_only=True)
    small = HI.sell_intensity(s, end, small_only=True)
    assert set(big) == {1} and set(small) == {2}, (
        "the FAJ 2004 cut is 10% of pre-sale holdings; 300/1000 is large and "
        "10/1000 is not")


# --------------------------------------------------------------------------
# 6. the clauses and the verdict


def test_a_primary_at_or_below_zero_closes_the_book_whatever_the_falsifiers_did():
    cell = {"result": {"mean_excess_net_monthly": -0.001, "nw_lag2_t": -0.4},
            "by_era": {}}
    for book in ("H", "I"):
        out = HI.decide_cell(book, cell, [{"falsifier": "a", "fires": False,
                                           "clause": "a"}], None)
        assert out["verdict"] == "FAILED_VARIANT"
        assert "WRONG SIDE OF ZERO" in out["clauses_fired"][0]


def test_an_untestable_falsifier_makes_the_verdict_cannot_determine():
    cell = {"result": {"mean_excess_net_monthly": 0.02, "nw_lag2_t": 3.0},
            "by_era": {}}
    out = HI.decide_cell("I", cell, [{"falsifier": "legs", "fires": None,
                                      "clause": "x"}], None)
    assert out["verdict"] == "CANNOT_DETERMINE"
    assert "could not run is not a falsifier that passed" in out["reading"]


def test_the_verdict_quotes_each_books_OWN_unit():
    cell = {"result": {"mean_excess_net_monthly": -0.001, "nw_lag2_t": -0.4},
            "by_era": {}}
    assert "/month" in HI.decide_cell("H", cell, [], None)["reading"]
    assert "/quarter" in HI.decide_cell("I", cell, [], None)["reading"]
    assert HI.DECLARED_UNIT == {"H": "month", "I": "quarter"}
    assert HI.DECLARED_EFFECT["I"] == pytest.approx(3 * 0.005), (
        "Book I's declared effect is stated per QUARTER — the unit it earns — "
        "and equals three times the 0.50%/month haircut prior")


# --------------------------------------------------------------------------
# 7. the family, the receipt, the registration


def test_the_family_holm_corrects_against_the_DECLARED_size_of_two():
    assert len(HI.DECLARED_FAMILY) == 2
    pvals = {n: None for n in HI.DECLARED_FAMILY}
    pvals["option_grant_timing_v0"] = 0.01
    block = holm(pvals, family=HI.FAMILY)
    assert block["family"] == HI.FAMILY
    assert block["declared_family_size"] == 2
    assert block["legs_without"] == ["buyback_insider_divergence_v0"]
    assert block["per_leg"]["option_grant_timing_v0"]["holm_alpha"] == \
        pytest.approx(0.025), (
        "a leg that could not run does not make the correction cheaper for "
        "the one that did")


def test_the_receipt_prints_its_own_construction_and_a_smoke_run_says_so():
    cells = {k: {"result": {"mean_excess_net_monthly": 0.001, "nw_lag2_t": 1.0,
                            "n_blocks": 10}, "by_era": {}}
             for k in ("primary_floor", "secondary_floor")}
    payload = HI._book_payload(
        "H", "option_grant_timing_v0", "TRIAL-DRAFT-H (UNSIGNED)", cells, [],
        {}, {}, {"verdict": "CONDITIONAL", "reading": "x"}, smoke=False,
        construction={"cut": "top tercile"}, panel_stats={})
    rc = payload["registered_construction"]
    assert rc["honours_the_registration"] is True
    assert rc["cost_curve"] == "flat_25bps_pending_5c"
    assert rc["floors_usd"]["secondary"] == 10_000_000.0
    assert rc["declared_effect_size"] == HI.DECLARED_EFFECT["H"]
    assert rc["block_unit"] == "month"
    assert payload["signed"] is False
    smoky = HI._book_payload(
        "H", "option_grant_timing_v0", "TRIAL-DRAFT-H (UNSIGNED)", cells, [],
        {}, {}, {"verdict": "CONDITIONAL", "reading": "x"}, smoke=True,
        construction={"cut": "top tercile"}, panel_stats={})
    assert smoky["registered_construction"]["honours_the_registration"] is False


def test_the_job_is_registered_and_reachable_by_name():
    from scripts.night_factory_jobs import JOBS, JOB_STAGES
    assert HI.JOB in JOBS
    assert JOB_STAGES[HI.JOB] == "pnl"


def test_the_contamination_clause_excludes_a_year_the_band_barely_covers():
    panel = _panel(n_months=36)
    months = sorted(panel["ym"].unique())
    thin = months[0].year
    covered = {ym: (set(range(1000, 1002)) if ym.year == thin
                    else set(range(1000, 1090))) for ym in months}
    cont = HI.coverage_and_contamination(panel, covered, book="H",
                                         floor_usd=None)
    assert thin in cont["excluded_years"]
    assert cont["per_year"][str(thin)]["why"]


def test_recompute_mde_measures_the_books_OWN_series_not_the_registration():
    res = {"excess": list(np.random.default_rng(3).normal(0.0, 0.05, 120))}
    out = HI.recompute_mde(res, nominal=0.009, deflated=0.010)
    assert out["status"] == "MEASURED"
    assert out["n_blocks"] == 120
    assert out["declared_mde_nominal"] == 0.009
    assert out["mde_per_block"] > 0
    thin = HI.recompute_mde({"excess": [0.01, 0.02]}, nominal=0.009,
                            deflated=0.010)
    assert thin["status"] == "CANNOT DETERMINE"
