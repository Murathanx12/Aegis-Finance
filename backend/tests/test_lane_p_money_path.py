"""Lane P (2026-09-28): the paper money path, after the adversarial review.

P1 -- the decision contract printed `MANDATE REFUSED` and the plan receipt printed
no mandate at all. The mandate is a reconciliation that gates no order (by
design); the defect was two surfaces printing two things. Both now print the
contract's block verbatim through `decision_contract.mandate_view`.

P2 -- GOOGL and GOOG were two PROBE names at 2% each: one issuer at 4%.
`investment_committee.collapse_share_classes` keeps one line per issuer (the
more liquid by the funnel's bar-measured dollar volume) and names the dropped
line on the receipt.

Every broker call is faked on the module; synthetic funnels, contracts and
ledgers live in tmp_path; dates derive from TODAY (protocol item 5); no network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config
from backend.services import decision_contract as DC
from backend.services import investment_committee as IC
from backend.services import pc_broker as PB
from scripts import sim_run as S

EQUITY = 1_000_000.0
PRICE = 50.0
TODAY = datetime.now(timezone.utc).date()
ASOF = TODAY.isoformat()


# ─────────────────────────────── fixtures ───────────────────────────────────

def _funnel(tmp: Path, cands: list[tuple[str, float | None]]) -> Path:
    """cands: (ticker, median_dollar_vol) in score order, best first."""
    stamp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    payload = {"generated_at": stamp,
               "evidence_basis": {"ranked_by": ["profitability_small"]},
               "candidates": [{"ticker": t, "score": 1.0 - i / 100.0,
                               "median_dollar_vol": mdv, "vol_annual": 0.30,
                               "why": [f"reason for {t}"]}
                              for i, (t, mdv) in enumerate(cands)]}
    p = tmp / "funnel.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _ranking(out: Path, net: float = -0.2) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps({
        "asof": ASOF, "top20_net_rel_21d": net, "model_version": "test",
        "top": [{"rank": i + 1, "symbol": f"RK{i:02d}", "decile": 9,
                 "expected_relative_return_21d_net": -0.004} for i in range(18)]}),
        encoding="utf-8")


def _contract(tmp: Path, mandate: dict | None) -> Path:
    d = tmp / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    blob = {"date": ASOF, "rows": []}
    if mandate is not None:
        blob["mandate"] = mandate
    p = d / f"{ASOF}.json"
    p.write_text(json.dumps(blob), encoding="utf-8")
    return p


class FakeBroker:
    """Records every call. `forbid_submit=True` FAILS the test on any submit."""

    def __init__(self, *, forbid_submit: bool = False, held: dict | None = None):
        self.forbid_submit = forbid_submit
        self.held = held or {}
        self.submitted: list[PB.PlannedOrder] = []
        self.open_orders: list[dict] = []

    def install(self, mp: pytest.MonkeyPatch) -> "FakeBroker":
        mp.setattr(PB, "snapshot", lambda **kw: {
            "equity": EQUITY, "cash": EQUITY, "n_positions": len(self.held),
            "positions": [{"symbol": s, "qty": q} for s, q in self.held.items()]})
        mp.setattr(PB, "last_prices", lambda syms: {s: PRICE for s in syms})
        mp.setattr(PB, "clock", lambda: {"is_open": True})
        mp.setattr(PB, "orders", lambda **kw: list(self.open_orders))

        def _submit(plan, **kw):
            if self.forbid_submit:
                pytest.fail(f"pc_broker.submit reached for {plan.symbol} when it must not be")
            self.submitted.append(plan)
            self.open_orders.append({"symbol": plan.symbol})
            return {"status": "submitted", "symbol": plan.symbol, "side": plan.side,
                    "qty": plan.qty, "notional": plan.notional}
        mp.setattr(PB, "submit", _submit)
        return self


def _run(tmp: Path, mode: str = "paper_profit") -> dict:
    return S.u_plan(tmp / "out", mode, asof=ASOF, funnel_path=tmp / "funnel.json",
                    ledger_path=tmp / "ledger.jsonl",
                    contracts_dir=tmp / "decisions" / "pc_plan")


def _receipt(tmp: Path) -> dict:
    return json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8"))


#: An OLD receipt (written before 2026-09-28) carries the old word REFUSED.
REFUSED_BLOCK = {
    "status": "REFUSED",
    "refusals": ["CAPITAL_BASES_DISAGREE: a", "PER_NAME_CAPS_DISAGREE: b"],
    "line": "MANDATE REFUSED: capital $40,000; synthetic line for the test",
}


# ─────────────────────────────── P2: one issuer, one line ───────────────────

def _rows(pairs):
    return [{"ticker": t, "score": 1.0 - i / 100.0, "median_dollar_vol": m,
             "source": "t", "reasons": []} for i, (t, m) in enumerate(pairs)]


def test_the_more_liquid_class_is_kept_and_the_other_is_named():
    out = IC.collapse_share_classes(_rows([("AAA", 1e9), ("GOOG", 5.8e9),
                                           ("GOOGL", 8.8e9), ("BBB", 1e8)]))
    assert [r["ticker"] for r in out] == ["AAA", "GOOGL", "BBB"]
    kept = out[1]
    d = kept["share_class_dropped"]
    assert [(x["ticker"], x["kept"]) for x in d] == [("GOOG", "GOOGL")]
    assert "Alphabet" in d[0]["issuer"] and "CIK 1652044" in d[0]["issuer"]
    assert "dollar volume" in kept["share_class_dropped"][0]["basis"]


def test_liquidity_not_score_decides_and_order_is_preserved():
    out = IC.collapse_share_classes(_rows([("GOOGL", 1e9), ("X", 1e9), ("GOOG", 9e9)]))
    assert [r["ticker"] for r in out] == ["X", "GOOG"]


def test_missing_dollar_volume_keeps_the_best_scored_line_and_says_so():
    out = IC.collapse_share_classes(_rows([("FOX", None), ("FOXA", 3e8)]))
    assert [r["ticker"] for r in out] == ["FOX"]
    assert "missing for FOX" in out[0]["share_class_dropped"][0]["basis"]


def test_a_three_line_issuer_collapses_to_one_and_unmapped_names_pass():
    rows = _rows([("LBTYA", 1e8), ("ZZZ", 1e6), ("LBTYK", 3e8), ("LBTYB", 1e5)])
    out = IC.collapse_share_classes(rows)
    assert [r["ticker"] for r in out] == ["ZZZ", "LBTYK"]
    assert sorted(d["ticker"] for d in out[1]["share_class_dropped"]) == ["LBTYA", "LBTYB"]
    plain = _rows([("A", 1.0), ("B", 2.0)])
    assert IC.collapse_share_classes(plain) == plain


# ── the issuer map is DERIVED from SEC CIK (review 2026-09-28 F4 / F6) ──────
# The old test here passed on an EMPTY map. These derive the expected groups
# from a CIK file and fail on any multi-class issuer the collapse misses.

def _sec_file(tmp: Path, rows: list[tuple[int, str, str]]) -> Path:
    p = tmp / "company_tickers.json"
    p.write_text(json.dumps({str(i): {"cik_str": c, "ticker": t, "title": n}
                             for i, (c, t, n) in enumerate(rows)}), encoding="utf-8")
    return p


SYNTH_SEC = [
    (1, "GOOGL", "Alphabet"), (1, "GOOG", "Alphabet"), (1, "GOOGM", "Alphabet"),
    (2, "BELFA", "Bel Fuse"), (2, "BELFB", "Bel Fuse"),
    (3, "BRK-B", "Berkshire"), (3, "BRK-A", "Berkshire"),
    (4, "MSTR", "Strategy"), (4, "STRC", "Strategy"), (4, "STRK", "Strategy"),
    (5, "SMCI", "Super Micro"), (5, "SMCIP", "Super Micro"),
    (6, "VIXM", "ETF Trust"), (6, "VIXY", "ETF Trust"),
    (7, "NVDA", "NVIDIA"),
    (8, "LBTYA", "Liberty Global"), (8, "LBTYB", "Liberty Global"), (8, "LBTYK", "Liberty Global"),
]


def _cik_groups_in(universe: list[str], sec_rows) -> list[set[str]]:
    """The EXPECTED groups, computed independently of the code under test:
    same CIK, common lines only (no preferred/note by suffix, no ETF-trust
    siblings) -- here listed by construction for the synthetic file."""
    by = {}
    for c, t, _n in sec_rows:
        by.setdefault(c, set()).add(t)
    common = {1: {"GOOGL", "GOOG"}, 2: {"BELFA", "BELFB"}, 3: {"BRK-B", "BRK-A"},
              8: {"LBTYA", "LBTYB", "LBTYK"}}
    return [g & set(universe) for g in common.values() if len(g & set(universe)) > 1]


def test_every_cik_group_in_a_synthetic_universe_collapses_to_one_line(tmp_path):
    sec = _sec_file(tmp_path, SYNTH_SEC)
    uni = ["GOOGL", "GOOG", "BELFA", "BELFB", "BRK.B", "BRK-A", "MSTR", "STRC",
           "SMCI", "SMCIP", "VIXM", "VIXY", "NVDA", "LBTYA", "LBTYK", "LBTYB"]
    m, st = IC.issuer_map(sec, overrides={})
    assert st["error"] is None
    out = IC.collapse_share_classes(_rows([(t, 1e9 - i) for i, t in enumerate(uni)]),
                                    issuer_of=m)
    kept = {r["ticker"] for r in out}
    for g in _cik_groups_in([t.replace(".", "-") for t in uni], SYNTH_SEC):
        assert len({t for t in kept if t.replace(".", "-") in g}) == 1, g
    # a preferred, a note and an ETF-trust sibling are NOT merged with the common
    for t in ("MSTR", "STRC", "SMCI", "SMCIP", "VIXM", "VIXY", "NVDA"):
        assert t in kept, t
    assert "GOOGM" not in m


def test_the_override_covers_lines_sec_lacks_and_joins_known_groups(tmp_path):
    sec = _sec_file(tmp_path, SYNTH_SEC)
    m, st = IC.issuer_map(sec, overrides={"Carnival": ("CCL", "CUK"),
                                          "Alphabet extra": ("GOOG", "GOOGX")})
    assert m["CCL"] == m["CUK"] and "override" in m["CUK"]
    assert m["GOOGX"] == m["GOOGL"]                       # joined the CIK group
    assert st["n_override_only_issuers"] == 1


def test_a_missing_sec_file_is_degraded_by_name_not_silent(tmp_path):
    m, st = IC.issuer_map(tmp_path / "absent.json", overrides={"Carnival": ("CCL", "CUK")})
    assert st["source"].startswith("OVERRIDE ONLY") and st["error"]
    assert m == {"CCL": m["CCL"], "CUK": m["CCL"]}


def test_the_tracked_sec_file_finds_all_22_multiclass_issuers_the_review_counted():
    """The 22 CIK groups the review found in the 2026-09-24 5,339-name universe,
    as a SYNTHETIC universe (the list, not the untracked universe cache), against
    the SEC file tracked in git. The first hand map held 14 of them."""
    groups = [("GOOG", "GOOGL"), ("BATRA", "BATRK"), ("BBD", "BBDO"), ("BELFA", "BELFB"),
              ("CENT", "CENTA"), ("DGICA", "DGICB"), ("FOX", "FOXA"), ("WLY", "WLYB"),
              ("KELYA", "KELYB"), ("GLIBA", "GLIBK"), ("LBTYA", "LBTYB", "LBTYK"),
              ("LILA", "LILAK"), ("LLYVA", "LLYVK"), ("FWONA", "FWONK"), ("NWS", "NWSA"),
              ("RDI", "RDIB"), ("RUSHA", "RUSHB"), ("METC", "METCB"), ("SENEA", "SENEB"),
              ("UONE", "UONEK"), ("UA", "UAA"), ("Z", "ZG")]
    if not IC.SEC_COMPANY_TICKERS.exists():
        pytest.skip("SEC company_tickers.json is not on disk")
    m, st = IC.issuer_map()
    missing = [g for g in groups if len({m.get(t) for t in g}) != 1 or m.get(g[0]) is None]
    assert missing == [], missing
    # and the three third classes the hand map omitted
    for a, b in (("BATRB", "BATRA"), ("FWONB", "FWONA"), ("LILAB", "LILA")):
        assert m.get(a) is not None and m.get(a) == m.get(b), a


def test_shortlist_applies_the_collapse(tmp_path):
    f = _funnel(tmp_path, [("NVDA", 2.5e10), ("GOOGL", 8.8e9), ("GOOG", 5.8e9), ("JAZZ", 1.7e8)])
    rows = IC.shortlist(ASOF, funnel_path=f)
    assert [r["ticker"] for r in rows] == ["NVDA", "GOOGL", "JAZZ"]


def test_u_plan_never_sends_two_classes_of_one_issuer(tmp_path, monkeypatch):
    fb = FakeBroker().install(monkeypatch)
    names = [f"SL{i:02d}" for i in range(12)]
    cands = [(t, 5e9) for t in names[:7]] + [("GOOGL", 8.8e9), ("GOOG", 5.8e9)] \
        + [(t, 5e9) for t in names[7:]]
    _funnel(tmp_path, cands)
    _ranking(tmp_path / "out")
    res = _run(tmp_path)

    sent = [p.symbol for p in fb.submitted]
    assert "GOOGL" in sent and "GOOG" not in sent
    assert res["share_class_dropped"] == ["GOOG"]
    rec = _receipt(tmp_path)
    assert rec["share_class_dropped"][0]["ticker"] == "GOOG"
    assert rec["share_class_dropped"][0]["kept"] == "GOOGL"
    # the worst case did not rise: still n x PROBE_MAX_WEIGHT inside PROBE_GROSS_CAP
    assert len(sent) <= config.PROBE_MAX_NAMES
    assert all(p.notional <= config.PROBE_MAX_WEIGHT * EQUITY + 1e-6 for p in fb.submitted)
    assert sum(p.notional for p in fb.submitted) <= config.PROBE_GROSS_CAP * EQUITY + 1e-6


# ─────────────────────────────── P1: one mandate status ─────────────────────

def test_account_mandate_says_on_its_face_that_it_gates_nothing():
    m = DC.account_mandate(40_000.0, equity=None)
    assert m["gates_orders"] is False
    assert "RECONCILIATION ONLY" in m["gates_orders_note"]
    assert "ONE capital base" in m["what_makes_it_green"]


def test_POLICY_PIN_probe_acts_under_an_unreconciled_mandate(tmp_path, monkeypatch):
    """A POLICY PIN, not a regression guard: the mandate gates no order by the
    2026-09-25 C3 design. Whoever makes it bind must change this test ON
    PURPOSE. It also reads an OLD receipt carrying the old word REFUSED."""
    FakeBroker().install(monkeypatch)
    _funnel(tmp_path, [(f"SL{i:02d}", 5e9) for i in range(12)])
    _ranking(tmp_path / "out")
    _contract(tmp_path, REFUSED_BLOCK)
    res = _run(tmp_path)

    rec = _receipt(tmp_path)
    assert res["mandate_status"] == rec["mandate"]["status"] == "UNRECONCILED"
    assert rec["mandate"]["status_as_written"] == "REFUSED"
    assert rec["mandate_line"] == REFUSED_BLOCK["line"].replace(
        "MANDATE REFUSED", "MANDATE UNRECONCILED", 1)
    assert rec["mandate"]["disagreements"] == REFUSED_BLOCK["refusals"]
    assert rec["mandate"]["gates_orders"] is False
    assert "ONE capital base" in rec["mandate"]["what_makes_it_green"]
    assert res["probe_acting"] is True


def test_the_new_word_is_written_and_old_receipts_still_parse():
    assert DC.normalise_mandate_status("REFUSED") == "UNRECONCILED"
    assert DC.normalise_mandate_status("OK") == "OK"
    m = DC.account_mandate(40_000.0, equity={"equity_usd": 999_054.41, "as_of": ASOF})
    assert m["status"] == "UNRECONCILED" and "REFUSED" not in m["line"]
    # the committee's tilt budget is not compared to the account's gross (F2)
    assert not any(d.startswith("GROSS_CAPS_DISAGREE") for d in m["disagreements"])
    assert any("IC_TOTAL_TILT_BUDGET" in k for k in m["sleeve_caps_seen"])
    assert not any("IC_TOTAL_TILT_BUDGET" in k for k in m["gross_caps_seen"])
    v = DC.mandate_view(REFUSED_BLOCK, contract_status="present", contract_path="old.json")
    assert v["status"] == "UNRECONCILED" and v["status_as_written"] == "REFUSED"
    assert "old receipt" in v["source"]


def test_the_same_function_reads_a_real_contract_block():
    block = DC.account_mandate(40_000.0, equity={"equity_usd": 999_054.41, "as_of": ASOF})
    v = DC.mandate_view(block, contract_status="present", contract_path="x.json")
    assert (v["status"], v["line"], v["refusals"]) == (
        block["status"], block["line"], block["refusals"])


@pytest.mark.parametrize("mandate,why", [(None, "no mandate block"),
                                         ("absent", "contract absent")])
def test_no_contract_mandate_is_cannot_determine_never_ok(tmp_path, monkeypatch, mandate, why):
    FakeBroker().install(monkeypatch)
    _funnel(tmp_path, [(f"SL{i:02d}", 5e9) for i in range(12)])
    _ranking(tmp_path / "out")
    if mandate is None:
        _contract(tmp_path, None)
    res = _run(tmp_path)
    rec = _receipt(tmp_path)
    assert res["mandate_status"] == "CANNOT DETERMINE"
    assert rec["mandate"]["status"] == "CANNOT DETERMINE"
    assert "ONE capital base" in rec["mandate"]["what_makes_it_green"]


def test_observe_mode_never_reaches_submit_under_a_refused_mandate(tmp_path, monkeypatch):
    FakeBroker(forbid_submit=True).install(monkeypatch)
    _funnel(tmp_path, [("GOOGL", 8.8e9), ("GOOG", 5.8e9)] + [(f"SL{i:02d}", 5e9) for i in range(10)])
    _ranking(tmp_path / "out")
    _contract(tmp_path, REFUSED_BLOCK)
    res = _run(tmp_path, mode="observe")
    assert res["probe_acting"] is False and res["n_sent"] == 0
    assert res["mandate_status"] == "UNRECONCILED"


# ─────────────────────────────── F5: the version is bumped ──────────────────

def test_the_probe_policy_is_a_new_version_with_a_dated_boundary():
    vs = [v["version"] for v in S.PROBE_POLICY_VERSIONS]
    assert vs[:2] == ["c3-v0", "c3-v1"]                   # c3-v0 is kept, not edited
    assert S.PROBE_POLICY_VERSION == "c3-v1"
    assert S.PROBE_POLICY_VERSION_FROM == "2026-09-28"
    assert "share-class collapse" in S.PROBE_POLICY_VERSIONS[-1]["what"]


def test_the_version_change_is_journaled_once(tmp_path):
    j = tmp_path / "policy_journal.jsonl"
    row = S._record_probe_version(j)
    assert row["key"] == f"policy_version:{S.PROBE_POLICY_ID}"
    assert (row["old"], row["new"], row["effective_asof"]) == ("c3-v0", "c3-v1", "2026-09-28")
    assert row["kind"] == "code_version" and "share-class collapse" in row["reason"]
    assert S._record_probe_version(j) is None             # idempotent
    assert len(j.read_text(encoding="utf-8").splitlines()) == 1


def test_a_held_dropped_class_exits_as_a_policy_change_not_a_view(tmp_path, monkeypatch):
    fb = FakeBroker(held={"GOOG": 400}).install(monkeypatch)
    # GOOG was bought as a PROBE name under c3-v0 on an earlier asof
    plan_dir = tmp_path / "decisions" / "pc_plan"
    plan_dir.mkdir(parents=True)
    earlier = (TODAY - timedelta(days=3)).isoformat()
    (plan_dir / f"{earlier}.json").write_text(json.dumps({"rows": [
        {"ticker": "GOOG", "direction": "PROBE", "acting": True,
         "policy_version": "c3-v0"}]}), encoding="utf-8")
    names = [f"SL{i:02d}" for i in range(10)]
    _funnel(tmp_path, [("GOOGL", 8.8e9), ("GOOG", 5.8e9)] + [(t, 5e9) for t in names])
    _ranking(tmp_path / "out")
    res = _run(tmp_path)

    goog = [p for p in fb.submitted if p.symbol == "GOOG"]
    assert goog and goog[0].side == "sell"
    assert goog[0].reason.startswith("POLICY CHANGE (share-class collapse)")
    assert "c3-v0->c3-v1" in goog[0].reason and "Not a change of view" in goog[0].reason
    assert "not in the ranked book" not in goog[0].reason
    rec = _receipt(tmp_path)
    assert rec["policy_version"] == "c3-v1"
    assert rec["policy_version_from_asof"] == "2026-09-28"
    assert rec["policy_change_exits"][0]["symbol"] == "GOOG"
    assert res["policy_change_exits"] == ["GOOG"]
    # a sandbox caller never writes the machine's journal
    assert rec["policy_version_journal"] == "sandbox: not journaled"
    # the plan's own PROBE rows carry the new version
    rows = json.loads((plan_dir / f"{ASOF}.json").read_text(encoding="utf-8"))["rows"]
    assert rows and {r["policy_version"] for r in rows} == {"c3-v1"}
