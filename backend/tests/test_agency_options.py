"""Lane A2 — three options from one IPS, and the human who holds one.

Spec: `docs/research_notes/2026-09-12/spec_agency_intake.md` §2 and test T2.

Two properties carry the section. First, **the un-chosen options are created,
not discarded**: they become `shadow_of:<ips_hash>` books on the same clock
with their own twins, so "you would have done better with the other one" is a
measurement. Second, **a human holds**: `POST /agency/hold` is the only route
that mints `origin="human_text"`, and it refuses without the sentence.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import agency as A
from backend.services import book_cadence as BC
from backend.services import paper_books as PB
from backend.strategy.contract import loss_budget_worst_case
from backend.tests.book_helpers import seeded_db, synthetic_bars

client = TestClient(app)
ANSWERS = [3, 3, 2, 3, 2, 2, 1, 2]


@pytest.fixture()
def bars():
    return synthetic_bars(n=300)


@pytest.fixture()
def books_db(tmp_path, monkeypatch):
    from backend import db as DB
    from backend.db import get_connection, init_db
    path = tmp_path / "aegis_pi.db"
    conn = seeded_db(path)
    monkeypatch.setattr(DB, "DB_PATH", path)
    monkeypatch.setattr(
        PB, "_conn",
        lambda db_path=None: (init_db(db_path or path)
                              or get_connection(db_path or path)))
    yield path, conn
    conn.close()


@pytest.fixture()
def ips_store(tmp_path, monkeypatch):
    """Never the repo's own policy directory."""
    d = tmp_path / "ips"
    monkeypatch.setattr(A, "ips_dir", lambda: d)
    return d


@pytest.fixture(autouse=True)
def _ledger_to_tmp(tmp_path, monkeypatch):
    from backend.services import belief_state as BS
    monkeypatch.setattr(BS, "PREDICTIONS", tmp_path / "predictions.jsonl")
    monkeypatch.setattr(BS, "_migrate_once", lambda: None)


def make_ips(**kw):
    base = dict(capital=50_000.0, horizon_months=36, personality="balanced",
                constraints=[], liquidity_need=0.05, answers=list(ANSWERS),
                draft=False)
    base.update(kw)
    return A.intake(**base)


# ------------------------------------------------------------- the window


def test_three_options_never_two_and_never_four():
    opts = A.propose(make_ips(), bars=None)
    assert len(opts) == 3
    assert len({o.personality for o in opts}) == 3


@pytest.mark.parametrize("declared,expected", [
    ("preservation", ["preservation", "balanced", "aggressive"]),
    ("balanced", ["preservation", "balanced", "aggressive"]),
    ("aggressive", ["balanced", "aggressive", "extreme_growth"]),
    ("extreme_growth", ["balanced", "aggressive", "extreme_growth"]),
])
def test_the_window_slides_rather_than_inventing_a_fourth_bucket(declared, expected):
    assert A.neighbours(declared) == expected


def test_the_declared_choice_is_always_one_of_the_three():
    for p in A.PERSONALITIES:
        ips = make_ips(personality=p, liquidity_need=0.0)
        opts = A.propose(ips, bars=None)
        assert [o.personality for o in opts].count(p) == 1
        assert sum(o.is_declared_choice for o in opts) == 1


# --------------------------------------------------------------- the twins


def test_every_option_arrives_with_its_twins(bars):
    for opt in A.propose(make_ips(), bars=bars, asof=date.today()):
        kinds = {(t.strategy.engine_params["twin"] or {})["kind"]
                 for t in opt.twins}
        assert "random_universe" in kinds
        assert "beta_matched" in kinds, "a long-only book owes a beta twin"


def test_a_twin_is_built_before_the_option_has_a_number(bars):
    """B3, structurally: the twins exist on the Option object itself, so a
    payload cannot be assembled that shows a worst case without them."""
    row = A.propose(make_ips(), bars=bars)[0].as_row()
    assert row["twins"] and all(t["construction"] for t in row["twins"])


# ------------------------------------------------------- T2, the worst case


def test_the_worst_case_comes_from_the_one_function(bars):
    """Spec T2's SHAPE: the number is `loss_budget_worst_case`'s, not a
    re-derivation. If someone hand-codes the arithmetic for the agency, this
    fails."""
    opt = next(o for o in A.propose(make_ips(capital=100_000.0,
                                             personality="aggressive",
                                             liquidity_need=0.0), bars=bars)
               if o.personality == "aggressive")
    direct = loss_budget_worst_case(opt.strategy, n_names=12,
                                    notional_pct=1 / 12,
                                    equity_usd=100_000.0)
    assert direct["gross_over_equity"] == pytest.approx(1.0)
    assert opt.worst_case["worst_case_usd"] == pytest.approx(
        direct["worst_case_usd"] * (1 - opt.cash_floor_pct), rel=1e-9)


def test_the_aggressive_row_prints_its_own_arithmetic_not_the_specs_typo():
    """THE SPEC'S ONE SLIP, pinned so nobody 'fixes' it twice.

    §1.4 prints the aggressive row as `12 x 8.33% x 12% = 10.0%` and T2
    asserts -$10,000 on $100,000. 1.00x gross at a 12% stop is 12.0%. The
    other two rows are exact (8.0% and 10.0%), so the inputs are right and the
    printed output is the hand-edited one — and the spec's own note says the
    worst case is RECOMPUTED, never hand-edited. This test states both
    numbers so the next reader sees the choice rather than a mismatch.
    """
    ips = make_ips(capital=100_000.0, personality="aggressive",
                   liquidity_need=0.0)
    opt = next(o for o in A.propose(ips, bars=None)
               if o.personality == "aggressive")
    assert opt.strategy.hold.stop_loss == -0.12
    assert opt.worst_case["worst_case_pct_of_equity"] == pytest.approx(0.12)
    # ...of the INVESTED equity. The aggressive tier's own cash floor is 2%,
    # and the cash sleeve cannot be stopped out (§1.5), so $100,000 of IPS
    # capital puts $98,000 at risk: -$11,760, which is 11.76% of the capital
    # and 12.00% of the book. Both are printed; neither is the spec's $10,000.
    assert opt.worst_case["worst_case_usd"] == pytest.approx(-11_760.0)
    assert "invested" in opt.worst_case["equity_basis"].lower()
    assert "arithmetic" in A.TABLE["aggressive"].note.lower()


@pytest.mark.parametrize("personality,pct", [("preservation", 0.08),
                                             ("balanced", 0.10)])
def test_the_two_exact_rows_reproduce_the_specs_table(personality, pct):
    ips = make_ips(capital=100_000.0, personality=personality,
                   liquidity_need=0.0)
    opt = next(o for o in A.propose(ips, bars=None)
               if o.personality == personality)
    assert opt.worst_case["worst_case_pct_of_equity"] == pytest.approx(pct)
    assert opt.worst_case["gross_over_equity"] == pytest.approx(1.0)


def test_the_worked_example_reproduces(bars):
    """§2.4: $50,000 balanced at a 5% cash floor is -$4,750."""
    opt = next(o for o in A.propose(make_ips(), bars=bars)
               if o.personality == "balanced")
    assert opt.worst_case["worst_case_usd"] == pytest.approx(-4750.0, rel=1e-9)


def test_the_levered_tier_prints_its_gross_beside_its_stop():
    """Session protocol rule 4: never the stop alone."""
    ips = make_ips(personality="extreme_growth", liquidity_need=0.0)
    opt = next(o for o in A.propose(ips, bars=None)
               if o.personality == "extreme_growth")
    assert opt.worst_case["gross_over_equity"] == pytest.approx(1.5)
    assert "gross" in opt.worst_case["verdict"]
    assert opt.as_row()["extrapolated_tier"] is True


# ------------------------------------------------------------- the cost curve


def test_a_ticker_keyed_universe_declares_the_empirical_curve(bars):
    opt = A.propose(make_ips(), bars=bars)[0]
    assert opt.strategy.costs.curve == "taq_empirical"
    assert opt.strategy.engine_params["symbols"]


def test_a_screen_with_no_names_behind_it_declares_flat():
    opt = A.propose(make_ips(), bars=None)[0]
    assert opt.strategy.costs.curve == "flat"
    assert "symbols" not in opt.strategy.engine_params


def test_costs_are_never_zero_on_an_agency_book():
    for opt in A.propose(make_ips(), bars=None):
        assert opt.strategy.costs.zero_cost_diagnostic is False
        assert opt.strategy.costs.round_trip_bps > 0


# ----------------------------------------------------- the expected drawdown


def test_no_history_is_cannot_determine_not_zero(books_db, bars):
    opt = A.propose(make_ips(), bars=bars)[0]
    assert opt.expected_drawdown["verdict"] == "CANNOT DETERMINE"
    assert "no history" in opt.expected_drawdown["why"]


def test_a_marked_twin_gives_a_measured_drawdown(books_db, bars):
    path, conn = books_db
    ips = make_ips()
    opts = A.propose(ips, bars=bars, conn=conn)
    opt = opts[0]
    twin = opt.twins[0]
    PB.create(opt.strategy, cadence="monthly", origin="night_job",
              bars=bars, conn=conn)
    for i, nav in enumerate((100_000.0, 110_000.0, 99_000.0)):
        conn.execute("INSERT OR REPLACE INTO paper_nav VALUES (?,?,?,?,?)",
                     (twin.book_id, f"2026-01-0{i + 1}", nav, "cfg", "now"))
    conn.commit()
    again = A.expected_drawdown_at_budget(opt.strategy, opt.twins, conn=conn)
    assert again["verdict"] == "measured on the twins"
    assert again["worst_twin_drawdown"] == pytest.approx(-0.1, abs=1e-6)


# --------------------------------------------------------------- the signal


def test_the_signal_must_be_one_the_selector_can_compute():
    with pytest.raises(A.AgencyError, match="cannot be computed"):
        A.propose(make_ips(), bars=None, signal="agency_default_composite")


def test_the_default_signal_is_computable_by_the_cadence_pass():
    assert A.AGENCY_SIGNAL_DEFAULT in A.supported_signals()
    assert A.AGENCY_SIGNAL_DEFAULT in BC.SUPPORTED_SIGNALS


# ------------------------------------------------------------------ the hold


def test_a_hold_without_a_sentence_is_refused(books_db, bars):
    ips = make_ips()
    opts = A.propose(ips, bars=bars)
    with pytest.raises(A.AgencyError, match="sentence"):
        A.hold(ips, chosen_contract_hash=opts[0].contract_hash, sentence="   ",
               bars=bars)


def test_a_hold_on_a_contract_nobody_proposed_is_refused(books_db, bars):
    with pytest.raises(A.AgencyError, match="not one of the three"):
        A.hold(make_ips(), chosen_contract_hash="deadbeefdeadbeef",
               sentence="I want the balanced one, it matches my horizon.",
               bars=bars)


def test_the_chosen_book_is_human_text_and_the_others_are_shadows(books_db, bars):
    path, conn = books_db
    ips = make_ips()
    opts = A.propose(ips, bars=bars, conn=conn)
    chosen = next(o for o in opts if o.is_declared_choice)
    out = A.hold(ips, chosen_contract_hash=chosen.contract_hash,
                 sentence="Balanced matches my three-year horizon.",
                 bars=bars, conn=conn)
    books = {b["role"]: b for b in out["books"]}
    assert books["chosen"]["book"]["origin"] == "human_text"
    assert books["chosen"]["book"]["origin_text"] == \
        "Balanced matches my three-year horizon."
    assert books["chosen"]["book"]["ips_hash"] == ips.ips_hash
    assert books["chosen"]["book"]["shadow"] is False
    shadows = [b for b in out["books"] if b["role"] == "shadow"]
    assert len(shadows) == 2
    for s in shadows:
        assert s["book"]["origin"] == f"shadow_of:{ips.ips_hash}"
        assert s["book"]["shadow"] is True
        assert s["book"]["ips_hash"] == ips.ips_hash
        assert s["twins"], "a shadow is graded, so it owes a twin too"


def test_every_book_the_hold_creates_carries_the_ips_hash(books_db, bars):
    """A1's acceptance: the IPS hash is on every book the intake creates."""
    path, conn = books_db
    ips = make_ips()
    opts = A.propose(ips, bars=bars, conn=conn)
    A.hold(ips, chosen_contract_hash=opts[0].contract_hash,
           sentence="This is the one I want to run.", bars=bars, conn=conn)
    rows = PB.list_books(conn=conn, include_twins=False)
    assert len(rows) == 3
    assert all(b.ips_hash == ips.ips_hash for b in rows)


def test_a_shadow_cannot_be_created_as_a_primary(books_db, bars):
    from backend.services.paper_books import BookError
    path, conn = books_db
    opt = A.propose(make_ips(), bars=bars, conn=conn)[0]
    with pytest.raises(BookError, match="shadow"):
        PB.create(opt.strategy, cadence="monthly",
                  origin="shadow_of:aaaaaaaaaaaaaaaa", shadow=False,
                  bars=bars, conn=conn)


# --------------------------------------------------------------- the store


def test_the_ips_store_round_trips(ips_store):
    ips = make_ips()
    A.save_ips(ips)
    back = A.load_ips(ips.ips_hash)
    assert back.document == ips.document
    assert back.ips_hash == ips.ips_hash


def test_an_edited_policy_file_is_refused(ips_store):
    import json
    ips = make_ips()
    path = A.save_ips(ips)
    from pathlib import Path
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    blob["ips"]["client_facts"]["capital_usd"] = 999_999.0
    Path(path).write_text(json.dumps(blob), encoding="utf-8")
    with pytest.raises(A.AgencyError, match="hashes to"):
        A.load_ips(ips.ips_hash)


def test_an_unknown_hash_is_a_refusal_naming_the_directory(ips_store):
    with pytest.raises(A.AgencyError, match="no IPS with hash"):
        A.load_ips("0123456789abcdef")


# ---------------------------------------------------------------- the routes


def _enable(monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")


def test_the_questionnaire_route_is_a_read():
    body = client.get("/api/control/agency/questionnaire").json()
    assert len(body["questions"]) == 8
    assert body["limits"]
    assert set(body["personalities"]) == set(A.PERSONALITIES)


def test_intake_is_gated(monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    assert client.post("/api/control/agency/intake", json={}).status_code == 403


def test_hold_is_gated(monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    assert client.post("/api/control/agency/hold", json={}).status_code == 403


def test_the_intake_route_returns_a_hashed_policy(monkeypatch, ips_store):
    _enable(monkeypatch)
    r = client.post("/api/control/agency/intake",
                    json={"capital": 50_000, "horizon_months": 36,
                          "personality": "balanced", "constraints": [],
                          "liquidity_need": 0.05, "answers": ANSWERS,
                          "draft": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ips_hash"] == body["ips"]["ips_hash"]
    assert body["limits"]
    assert (ips_store / f"{body['ips_hash']}.json").is_file()


def test_the_intake_route_refuses_a_bad_questionnaire(monkeypatch, ips_store):
    _enable(monkeypatch)
    r = client.post("/api/control/agency/intake",
                    json={"capital": 50_000, "horizon_months": 36,
                          "personality": "balanced", "answers": [1, 2, 3]})
    assert r.status_code == 422


def test_the_propose_route_returns_three_with_hashes(monkeypatch, books_db,
                                                     bars, ips_store):
    _enable(monkeypatch)
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    ips = make_ips()
    A.save_ips(ips)
    r = client.post("/api/control/agency/propose", json={"ips_hash": ips.ips_hash})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_options"] == 3
    assert all(o["contract_hash"] for o in body["options"])
    assert body["limits"]


def test_the_propose_route_refuses_a_document_whose_hash_was_edited(
        monkeypatch, books_db, bars, ips_store):
    _enable(monkeypatch)
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    doc = dict(make_ips().document)
    doc["client_facts"] = dict(doc["client_facts"], capital_usd=1.0)
    r = client.post("/api/control/agency/propose", json={"ips": doc})
    assert r.status_code == 422
    assert "hashes to" in r.json()["detail"]


def test_the_hold_route_mints_the_only_human_text_book(monkeypatch, books_db,
                                                       bars, ips_store):
    _enable(monkeypatch)
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    ips = make_ips()
    A.save_ips(ips)
    proposed = client.post("/api/control/agency/propose",
                           json={"ips_hash": ips.ips_hash}).json()
    chosen = next(o for o in proposed["options"] if o["is_declared_choice"])
    r = client.post("/api/control/agency/hold",
                    json={"ips_hash": ips.ips_hash,
                          "chosen_contract_hash": chosen["contract_hash"],
                          "sentence": "Balanced fits the money I can lose."})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sentence"] == "Balanced fits the money I can lose."
    origins = {b["book"]["origin"] for b in body["books"]}
    assert "human_text" in origins
    assert any(o.startswith("shadow_of:") for o in origins)
    listed = client.get("/api/control/books").json()
    assert listed["n_books"] == 3
    assert all(b["twins"] for b in listed["books"])


def test_the_hold_route_refuses_without_a_sentence(monkeypatch, books_db, bars,
                                                   ips_store):
    _enable(monkeypatch)
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    ips = make_ips()
    A.save_ips(ips)
    proposed = client.post("/api/control/agency/propose",
                           json={"ips_hash": ips.ips_hash}).json()
    r = client.post("/api/control/agency/hold",
                    json={"ips_hash": ips.ips_hash,
                          "chosen_contract_hash":
                              proposed["options"][0]["contract_hash"],
                          "sentence": ""})
    assert r.status_code == 422
    assert "sentence" in r.json()["detail"]


def test_create_from_contract_still_refuses_human_text(monkeypatch, books_db):
    """The hold route is the ONLY one. This is the other half of that claim."""
    _enable(monkeypatch)
    from backend.tests.book_helpers import make_strategy
    r = client.post("/api/control/books/create-from-contract",
                    json={"strategy": make_strategy().as_dict(),
                          "cadence": "daily", "origin": "human_text"})
    assert r.status_code == 422
