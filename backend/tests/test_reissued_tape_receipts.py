"""B1 task 4 -- the four re-issued tape receipts, and the rules they must obey.

WHY THIS FILE EXISTS
====================
On 2026-09-04 the panel was rebuilt on a point-in-time share basis: `ratio` had
been dividing the SPLIT-ADJUSTED IBES consensus (`ptgsum`) by the RAW CRSP close,
so `toxic_ge_5` was largely a future-reverse-split detector and every receipt
built on the old table measured a different set of names than it claimed. Four
receipts were re-issued on the clean panel.

Four rules govern that re-issue, and none of them is self-enforcing:

1. **A sealed receipt is never edited.** The correction is a NEW file plus a
   `<oldname>.SUPERSEDED_BY.json` sidecar. Repairing a tamper-evident artefact is
   the tampering, so the sidecar records BOTH sha256s and this test checks the
   sealed file still hashes to what the sidecar said it did.
2. **Every new receipt names what it supersedes**, or a reader six months from
   now has two receipts with the same shape and no way to tell which is void.
3. **The toxic cell is never reported without its $5 price floor and its era
   split.** It measures +40%/yr on ~7 names a month and FLIPS SIGN to -34%/yr
   once sub-$5 names are excluded; 84% of it trades under $5 at a median close of
   $3.08, where a 10bps round trip is fiction. A receipt that quotes the headline
   alone is misleading even though every number in it is arithmetically right
   (`docs/VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md` SS4).
4. **A family size and a family-correction STATUS travel with every p.** B4
   (CPCV / Deflated Sharpe / SPA) does not exist yet, so the honest statement is
   PENDING -- and "pending" has to be written down, because an uncorrected p in a
   104-cell family reads exactly like a corrected one.

The pure-function half of this file pins the arithmetic that carries those rules:
Reg-T capital (the denominator the void short receipt did not have), the
zero-cost diagnostic flag, the pinned scored window, and the hygiene-universe
selectors.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from learner import benchmark as bm

REPO = Path(__file__).resolve().parents[2]
RECEIPTS = REPO / "backend" / "data" / "optimus" / "tracker_backtest"

#: sealed (void) receipt -> the receipt that replaces it.
REISSUED: dict[str, str] = {
    "band_horizon_20260903.json": "band_horizon_20260905.json",
    "toxic_band_short_20260904.json": "toxic_band_short_20260905.json",
    "revision_6m_cohorts_20260904.json": "revision_6m_cohorts_20260905.json",
    "holding_period_policy_20260903.json": "holding_period_policy_20260905.json",
}

#: the two receipts whose SUBJECT is the toxic band, so the disclosure binds.
TOXIC_SUBJECT = ("band_horizon_20260905.json", "toxic_band_short_20260905.json")


def _load(name: str) -> dict:
    p = RECEIPTS / name
    if not p.exists():
        pytest.skip(f"{name} absent on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


# =========================================================== pure arithmetic

def test_regt_capital_is_the_denominator_the_void_receipt_lacked():
    """0.5 x short + 0.5 x long, and it GROWS with the hedge.

    The void receipt divided a beta-hedged P&L by $1 of short notional. A $1
    short against a 1.48x long index leg needs 1.24 of equity under Reg-T, so
    that headline was ~24% too large before the equity premium in the long leg is
    even discussed.
    """
    from scripts.toxic_band_short_run import regt_capital

    assert regt_capital(1.0, 0.0) == pytest.approx(0.50)
    assert regt_capital(1.0, 1.0) == pytest.approx(1.00)
    assert regt_capital(1.0, 1.48) == pytest.approx(1.24)
    # maintenance minima are LOWER, hence a bound on leverage and never a plan
    assert regt_capital(1.0, 1.48, maintenance=True) == pytest.approx(0.67)
    assert regt_capital(1.0, 1.48, maintenance=True) < regt_capital(1.0, 1.48)
    # monotone in the hedge, and never zero (a zero denominator is an infinity
    # dressed as a return)
    caps = [regt_capital(1.0, k) for k in (0.0, 0.5, 1.0, 2.0)]
    assert caps == sorted(caps) and all(c > 0 for c in caps)
    assert regt_capital(0.0, 0.0) > 0.0


def test_minus_resid_on_capital_charges_borrow_on_notional_not_on_capital():
    """The borrow fee is on the SHORT NOTIONAL, then divided by capital.

    Charging borrow on capital instead would shrink the fee by the leverage
    factor -- a real short account pays the lender on the shares it borrowed, not
    on the equity it posted.
    """
    from scripts.toxic_band_short_run import (borrow_cost_per_period,
                                             resid_net_on_capital)

    bk = pd.DataFrame({
        "minus_resid_net_of_trading": [0.02, -0.01],
        "regt_capital": [1.24, 1.24],
        "maint_capital": [0.67, 0.67],
    }, index=["2020-01", "2020-02"])
    free = resid_net_on_capital(bk, 0.0, 1)
    assert free.iloc[0] == pytest.approx(0.02 / 1.24)

    fee = borrow_cost_per_period(20.0, 1)          # 20%/yr for one month
    assert fee == pytest.approx(0.20 / 12.0)
    charged = resid_net_on_capital(bk, 20.0, 1)
    assert charged.iloc[0] == pytest.approx((0.02 - fee) / 1.24)
    # the fee must NOT have been divided before being charged
    assert charged.iloc[0] != pytest.approx((0.02 - fee / 1.24) / 1.24)


def _tiny_market(n_days: int = 400, n_perm: int = 3) -> dict:
    dates = pd.bdate_range("2015-01-01", periods=n_days)
    return {"dates": dates, "n_days": n_days, "n_perm": n_perm,
            "perms": np.arange(n_perm),
            "d_ix": {d: i for i, d in enumerate(dates)},
            "p_ix": {p: p for p in range(n_perm)},
            "R": np.zeros((n_days, n_perm), dtype=np.float32),
            "LIVE": np.ones((n_days, n_perm), dtype=bool),
            "mkt": np.zeros(n_days), "mkt_ew": np.zeros(n_days)}


def test_zero_cost_rows_carry_the_diagnostic_flag():
    """A 0bps arm is a DECOMPOSITION and the row says so.

    `portfolio_farm.Policy` refuses zero costs unless `zero_cost_diagnostic` is
    set; the same flag has to ride on every result row here, or a downstream
    reader quotes a gross number as a net one.
    """
    from scripts import holding_period_policy as hpp

    mkt = _tiny_market()
    book = np.linspace(1.0, 2.0, mkt["n_days"])
    traded = np.zeros(mkt["n_days"])
    free = hpp._score(mkt, book, traded, 30, 0.0)
    paid = hpp._score(mkt, book, traded, 30, 25.0)
    assert free["zero_cost_diagnostic"] is True
    assert paid["zero_cost_diagnostic"] is False
    assert paid["cost_bps_per_side"] == 25.0


def test_run_fixed_refuses_a_scored_window_that_starts_on_cash():
    """A pinned start day BEFORE the first rebalance would score an empty book.

    Two pools whose first vintage differs by a month must share one scored day,
    and the plumbing that pins it must refuse an impossible one rather than
    quietly report the return of cash.
    """
    from scripts import holding_period_policy as hpp

    mkt = _tiny_market()
    rb_dates = list(range(100, 100 + 40))
    members = [np.array([0, 1]) for _ in rb_dates]
    with pytest.raises(SystemExit) as e:
        hpp.run_fixed(mkt, rb_dates, members, 6, 25.0, start_day=50)
    assert "start_day" in str(e.value)
    # the default path still works and equals the historical convention
    out = hpp.run_fixed(mkt, rb_dates, members, 6, 25.0)
    assert out["start"] == str(mkt["dates"][rb_dates[hpp.WARMUP]].date())


def _tiny_panel() -> pd.DataFrame:
    rows = []
    for m in range(6):
        month = f"2020-{m + 1:02d}"
        for p in range(10):
            rows.append({
                "permno": p, "month": month,
                "entry_date": pd.Timestamp("2020-01-02") + pd.Timedelta(days=m),
                # only permnos 0-2 are inside the band prior admissible region;
                # 0-8 clear PIT hygiene. That gap IS the point of B1 task 4.
                "in_admissible": p < 3,
                "hygiene_ok": p < 9,
                "band": "b_3_5" if p < 3 else "lt_1_5",
                "ratio": 1.0 + p * 0.5, "consensus": 4.2, "coverage": 5,
                "close": 10.0, "market_cap": 1e9,
                "target_rev_1m": 0.01 * p,
                "net_rev_1m": float(9 - p),
            })
    return pd.DataFrame(rows)


def test_hygiene_selectors_use_the_wider_pit_universe_not_the_band_region():
    """`*_hygiene` selects on `hygiene_ok`; the legacy selectors on the band.

    The old revision receipt measured the mechanism inside `in_admissible` -- a
    RATIO threshold, and the ratio was the defect. A revision result measured in
    a pool carved by the broken quantity is not a revision result.
    """
    from scripts import holding_period_policy as hpp

    panel = _tiny_panel()
    d_ix = {d: i for i, d in enumerate(sorted(panel["entry_date"].unique()))}
    p_ix = {p: p for p in range(10)}

    _, legacy, _ = hpp.build_cohorts(panel, p_ix, d_ix, "rev_top50")
    _, wide, _ = hpp.build_cohorts(panel, p_ix, d_ix, "rev_top50_hygiene")
    _, net, _ = hpp.build_cohorts(panel, p_ix, d_ix, "netrev_top50_hygiene")

    assert all(len(c) == 3 for c in legacy), "legacy pool must stay inside the band"
    assert all(len(c) == 9 for c in wide), "hygiene pool must be the wider one"
    assert sum(len(c) for c in wide) > sum(len(c) for c in legacy)
    # net_rev_1m ranks the OPPOSITE way to target_rev_1m in this fixture, so a
    # selector that silently read the wrong column would be caught here.
    assert set(net[0].tolist()) == set(range(9))
    top_by_target = hpp.build_cohorts(panel, p_ix, d_ix, "rev_top50")[1][0]
    assert 2 in top_by_target


def test_hygiene_selector_refuses_a_schema_v1_panel_instead_of_falling_back():
    """No `hygiene_ok` column means REFUSE, not "use the band region instead".

    A silent fallback would produce a receipt that claims the wide universe and
    measures the narrow one -- the exact failure this whole re-issue exists to
    correct.
    """
    from scripts import holding_period_policy as hpp

    panel = _tiny_panel().drop(columns=["hygiene_ok"])
    d_ix = {d: i for i, d in enumerate(sorted(panel["entry_date"].unique()))}
    with pytest.raises(SystemExit) as e:
        hpp.build_cohorts(panel, {p: p for p in range(10)}, d_ix, "rev_top50_hygiene")
    assert "hygiene_ok" in str(e.value)


def test_selector_census_flags_a_sub_five_dollar_cohort_as_an_upper_bound():
    """A book of $3 names is not measurable at 10bps and the census says so."""
    from scripts import holding_period_policy as hpp

    cheap = _tiny_panel()
    cheap["close"] = 3.0
    verdict = hpp.selector_census(cheap, "rev_top50_hygiene")["cost_verdict"]
    assert "UPPER BOUND" in verdict

    rich = _tiny_panel()
    rich["close"] = 50.0
    assert "DEFENSIBLE" in hpp.selector_census(rich, "rev_top50_hygiene")["cost_verdict"]


def test_band_terminal_wealth_never_compounds_overlapping_windows():
    """The +740% error class, checked in the band engine rather than assumed away.

    A monthly-formed book held h months produces overlapping windows. Compounding
    them as if sequential multiplies the log return by about h -- measured at
    3.12x on 66 overlapping 3-month windows, which is how +96.7% was published as
    +740%. `phase_chains` must therefore slice `[p::h]` -- one non-overlapping
    chain per phase offset -- and NEVER take a product over the whole column.
    """
    from scripts.band_horizon_run import phase_chains

    # +10% every month for 12 months, held 3 months. A 3-phase non-overlapping
    # chain of 4 rebalances each terminates at 1.1**4 = 1.4641. A wrong
    # implementation that compounded all 12 overlapping rows would get 1.1**12.
    bk = pd.DataFrame({"fwd": [0.10] * 12},
                      index=[f"2020-{m:02d}" for m in range(1, 13)])
    out = phase_chains(bk, 3, "fwd")
    assert len(out["phases"]) == 3, "one chain per phase offset, h = 3"
    for ph in out["phases"]:
        assert ph["n_rebalances"] == 4
        assert ph["terminal_wealth"] == pytest.approx(1.1 ** 4, abs=1e-4)
    assert out["terminal_wealth_median"] == pytest.approx(1.1 ** 4, abs=1e-4)
    assert out["terminal_wealth_median"] < 1.1 ** 12

    # and the canonical ruler refuses the wrong arithmetic outright
    with pytest.raises(ValueError):
        bm.compound([0.10] * 12, overlapping=True)


def test_family_block_names_its_size_and_admits_the_correction_is_pending():
    """A p with no family size beside it is not a p."""
    from scripts.band_horizon_run import family_block

    fb = family_block({"a": 0.01, "b": 0.4}, {"c": 0.02}, extra_cells=64)
    assert fb["family_size_total"] == 67
    assert fb["family_max_p"] == pytest.approx(0.4)
    assert fb["family_min_p"] == pytest.approx(0.01)
    assert "PENDING" in fb["family_correction_status"]
    assert "B4" in fb["family_correction_status"]


# ============================================================ the receipts

@pytest.mark.parametrize("old,new", sorted(REISSUED.items()))
def test_every_reissued_receipt_names_what_it_supersedes(old, new):
    rec = _load(new)
    assert rec.get("supersedes") == old, (
        f"{new} must carry supersedes == {old!r} so a reader can tell which of two "
        f"same-shaped receipts is void; found {rec.get('supersedes')!r}")
    assert len(str(rec.get("supersedes_reason", ""))) > 200, (
        f"{new}: supersedes_reason must say WHAT was wrong, not merely that "
        "something was")


@pytest.mark.parametrize("old,new", sorted(REISSUED.items()))
def test_every_reissued_receipt_carries_a_canonical_benchmark_stamp(old, new):
    rec = _load(new)
    stamp = bm.find_stamp(rec)
    assert stamp is not None, f"{new} quotes market numbers with no stamp"
    ok, reason = bm.validate_stamp(stamp)
    assert ok, f"{new}: {reason}"
    assert stamp["benchmark_id"] in bm.REGISTRY


@pytest.mark.parametrize("old,new", sorted(REISSUED.items()))
def test_every_reissued_receipt_is_dated_on_the_clean_panel(old, new):
    """A receipt that does not name its panel cannot be told apart from a void one."""
    rec = _load(new)
    panel = rec.get("panel") or {}
    assert panel.get("schema_version") == "learner-train-table-2", (
        f"{new}: the whole point of the re-issue is the rebuilt panel, so the "
        "receipt must name the schema version it was computed on")
    assert "ptgsumu" in str(panel.get("numerator", "")), (
        f"{new}: the numerator must be the UNADJUSTED IBES consensus")
    assert len(str(panel.get("known_open_limitation", ""))) > 100, (
        f"{new}: `build_monthly` drops a dying name's final month. That is a known "
        "open limitation and every receipt built on this panel must quantify or at "
        "least name it, rather than absorbing it silently")


@pytest.mark.parametrize("old,new", sorted(REISSUED.items()))
def test_every_reissued_receipt_declares_its_family_and_that_b4_is_pending(old, new):
    rec = _load(new)
    fam = rec.get("family")
    assert isinstance(fam, dict), f"{new} carries no family block"
    size = fam.get("family_size_total") or fam.get("cells_examined")
    assert isinstance(size, int) and size > 0, f"{new}: family size missing"
    status = str(fam.get("family_correction_status", ""))
    assert "PENDING" in status, f"{new}: family correction status must say PENDING"
    # A >=64-draw model null either EXISTS and is quoted, or it cannot exist and
    # the receipt says why. Silence is the one answer that is not allowed:
    # `|shuffled-null t| < 2` was found to be mis-specified on 2026-09-03, and the
    # replacement bar is a percentile over >=64 draws -- so a receipt that mentions
    # no null at all leaves a reader unable to tell which regime it is in.
    mn = {k: v for k, v in fam.items() if k.startswith("model_null")}
    assert mn, (
        f"{new}: say whether a >=64-draw model null exists for this object, even "
        "when the answer is that it cannot exist")
    quoted = any(k.endswith(("percentile", "percentiles")) and v for k, v in mn.items())
    if not quoted:
        assert any(isinstance(v, str) and len(v) > 50 for v in mn.values()), (
            f"{new}: no model-null percentile is quoted, so the receipt must explain "
            f"why one cannot exist. Found only {sorted(mn)}")


@pytest.mark.parametrize("old,new", sorted(REISSUED.items()))
def test_every_reissued_receipt_marks_the_band_prior_columns_void(old, new):
    rec = _load(new)
    vc = rec.get("void_columns")
    assert isinstance(vc, dict), (
        f"{new}: the panel's `prior_*` / `resid_vw_*` columns are BAND_PRIOR v2 "
        "expectations fitted on the corrupted ratio. A receipt must say it does not "
        "read them as expectations")
    assert vc.get("status") == "VOID"


@pytest.mark.parametrize("name", TOXIC_SUBJECT)
def test_the_toxic_cell_is_never_reported_without_the_five_dollar_floor(name):
    """The single most important reporting rule of B1 task 4.

    +40%/yr on ~7 names a month, 84% of them under $5 at a median close of $3.08,
    and the sign FLIPS under a $5 floor. Reported alone it reads as a signal.
    """
    rec = _load(name)
    d = rec.get("MANDATORY_TOXIC_BAND_DISCLOSURE")
    assert isinstance(d, dict), f"{name}: no MANDATORY_TOXIC_BAND_DISCLOSURE block"
    blob = json.dumps(d)
    assert "close_ge_5" in blob or "close_ge_5_variant_1m" in blob, (
        f"{name}: the $5 price-floor variant must sit beside the headline")
    era = d.get("era_splits_no_floor_1m") or d.get("era_splits_no_floor")
    assert isinstance(era, dict) and "2022_2024" in era, (
        f"{name}: the era split must be reported beside the headline -- 2022-24 is "
        "where the cell is flat")
    pop = d.get("population_1m") or d.get("population") or {}
    assert pop.get("median_close") is not None, (
        f"{name}: report the population's median close, because the cost model "
        "depends on it")
    assert "NOT A SIGNAL" in d.get("verdict", "") or "REFUSAL" in d.get("verdict", "")


@pytest.mark.parametrize("old,new", sorted(REISSUED.items()))
def test_the_sealed_receipt_has_an_unedited_sidecar_pointing_at_its_replacement(old, new):
    side_p = RECEIPTS / (old + ".SUPERSEDED_BY.json")
    old_p = RECEIPTS / old
    if not old_p.exists():
        pytest.skip(f"{old} absent on this machine")
    assert side_p.exists(), (
        f"{old} is void and must carry {side_p.name}. The sealed file is never "
        "edited -- the sidecar is how a reader learns it was replaced")
    side = json.loads(side_p.read_text(encoding="utf-8"))
    assert side["sealed_receipt"] == old
    assert side["superseded_by"] == new
    assert side["status"].startswith("VOID")
    digest = hashlib.sha256(old_p.read_bytes()).hexdigest()
    assert side["sealed_receipt_sha256"] == digest, (
        f"{old} no longer hashes to what its sidecar recorded. Either the sealed "
        "receipt was EDITED (which is the tampering the sidecar exists to prevent) "
        "or the sidecar is stale. Do not repair by rewriting the hash.")
    new_p = RECEIPTS / new
    if new_p.exists():
        assert side["superseded_by_sha256"] == hashlib.sha256(
            new_p.read_bytes()).hexdigest(), (
            f"{new} changed after {side_p.name} was written -- regenerate the sidecar")


@pytest.mark.parametrize("old", sorted(REISSUED))
def test_a_sidecar_quotes_no_return_numbers_so_it_needs_no_stamp(old):
    """A sidecar that carried an old excess figure would need a canonical stamp
    for a number whose entire purpose is to be void."""
    p = RECEIPTS / (old + ".SUPERSEDED_BY.json")
    if not p.exists():
        pytest.skip(f"{p.name} absent")
    keys = bm.market_keys(json.loads(p.read_text(encoding="utf-8")))
    assert not keys, f"{p.name} quotes market fields {keys}; strip them"


@pytest.mark.parametrize("new", sorted(REISSUED.values()))
def test_the_reissued_receipts_are_not_grandfathered(new):
    """The exemption list only shrinks, and never covers a receipt written after
    the gate existed."""
    from backend.tests.test_benchmark_canonical import GRANDFATHERED
    assert new not in GRANDFATHERED


def test_the_holding_period_receipt_cites_its_sibling_by_a_hash_that_still_matches():
    """A cross-receipt reference is only worth its hash.

    The holding-period receipt used to EMBED the band receipt whole (0.6 MB) --
    a second copy of a sealed artefact, free to drift. It now cites it by path
    plus sha256, and this test is what makes the citation load-bearing: if the
    band receipt is re-run without re-running this one, the stored hash stops
    matching and the stale reference is visible instead of silent.
    """
    rec = _load("holding_period_policy_20260905.json")
    sib = rec.get("sibling_band_horizon_receipt")
    if sib is None:
        pytest.skip("sibling band receipt was absent when this receipt was written")
    assert "sha256" in sib and "path" in sib
    p = REPO / sib["path"]
    if not p.exists():
        pytest.skip(f"{sib['path']} absent on this machine")
    assert sib["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest(), (
        f"{sib['path']} has changed since holding_period_policy_20260905.json cited "
        "it. Re-run `python -m scripts.holding_period_policy` so the citation is "
        "true again -- do NOT edit the stored hash.")


def test_the_revision_receipt_measures_every_arm_against_one_market():
    """A benchmark that moves between two arms is not a benchmark.

    The first cut of this receipt scored each selection pool from its own 24th
    rebalance, so the two revision definitions came back against market terminal
    wealths of 3.2362 and 3.41 -- and the difference would have read as a result.
    """
    rec = _load("revision_6m_cohorts_20260905.json")
    sw = rec.get("scored_window") or {}
    assert sw.get("invariant_holds") is True, (
        "arms are measured against different market terminal wealths "
        f"{sw.get('market_terminal_wealth_observed')}; every cross-arm comparison "
        "in that receipt is a different-sample comparison")
    assert len(sw.get("market_terminal_wealth_observed") or []) == 1


def test_the_revision_receipt_reports_both_definitions_of_a_revision():
    """`target_rev_1m` is derived from the target LEVEL whose share basis was the
    defect; `net_rev_1m` counts up/down revisions and touches no price. One
    working without the other is itself the finding."""
    rec = _load("revision_6m_cohorts_20260905.json")
    block = rec.get("TWO_INDEPENDENT_REVISION_DEFINITIONS") or {}
    by_cost = block.get("by_cost") or {}
    assert by_cost, "no two-definition comparison in the revision receipt"
    for tag, cell in by_cost.items():
        assert "target_rev_1m" in cell and "net_rev_1m" in cell, tag
        for defn in ("target_rev_1m", "net_rev_1m"):
            assert cell[defn]["zero_cost_diagnostic"] is False, (
                f"{tag}/{defn}: the headline cells must be NET of costs")
    nulls = ((rec.get("null_vs_random_from_pool") or {}).get("by_pool") or {})
    assert {"hygiene_targetrev", "hygiene_netrev"} <= set(nulls), (
        "each pool needs its OWN permutation null -- a null drawn from a different "
        "pool is not a null for that arm")
    for tag, e in nulls.items():
        assert e["n_draws"] >= 64, f"{tag}: {e['n_draws']} draws < 64 (the DEV gate)"


def test_the_band_receipt_reports_zero_bh_fdr_survivors_or_says_which():
    """Not a result assertion -- a REPORTING assertion.

    The screen's survivor list is what the roadmap's B1 task 5 conditional reads,
    so it has to be present and it has to name its family size.
    """
    rec = _load("band_horizon_20260905.json")
    mult = rec["multiplicity"]
    assert "screen_BH_FDR" in mult and "export_Holm" in mult
    assert isinstance(mult["screen_BH_FDR"]["survivors"], list)
    assert mult["screen_BH_FDR"]["m"] == len(mult["screen_family"])
    assert rec["family"]["cells_examined_screen"] == mult["screen_BH_FDR"]["m"]


def test_the_short_receipt_never_headlines_hedged_gross():
    """The void receipt's '+76.6%/yr hedged gross' is the error being corrected;
    the replacement must label that line as decomposition-only and headline
    `-resid` on Reg-T capital instead."""
    rec = _load("toxic_band_short_20260905.json")
    for name, byh in rec["constructions"].items():
        for h, e in byh.items():
            if e.get("status"):
                continue
            hd = e.get("HEADLINE_minus_resid_on_regt_capital")
            assert isinstance(hd, dict), f"{name}@{h}: no -resid/Reg-T headline"
            assert hd["mean_regt_capital_per_dollar_short"] >= 0.5
            assert "beta_matched_benchmark" in e, (
                f"{name}@{h}: the beta_matched leg must be quoted beside the short")
            flag = e.get("hedged_gross_DECOMPOSITION_ONLY_NEVER_A_HEADLINE") or {}
            assert flag.get("status") == "DO NOT QUOTE"
