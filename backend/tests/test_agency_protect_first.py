"""Lane A4 — protect first: the breach, the flip, the human reversal.

Spec: `docs/research_notes/2026-09-12/spec_agency_intake.md` §4 and test T3.

Three properties, each of which would be invisible if it broke:

* **the peak never resets** — not at the flip and not at the reversal, so a
  book cannot avoid a second breach by having flipped once;
* **a breach on the TWIN does not flip the book** — the twin is a grading
  control, and a control that can change the thing it controls is not one;
* **the engine flips, only a human unflips**, and the reversal writes onto the
  SAME log row rather than a second one that could be read on its own.
"""

from __future__ import annotations

import pytest

from backend.services import agency as A
from backend.services import book_cadence as BC
from backend.services import paper_books as PB
from backend.tests.book_helpers import make_strategy, seeded_db, synthetic_bars


@pytest.fixture()
def bars():
    return synthetic_bars(n=300)


@pytest.fixture()
def flips(tmp_path, monkeypatch):
    p = tmp_path / "protect_first.jsonl"
    monkeypatch.setattr(A, "FLIPS_PATH", p)
    return p


@pytest.fixture()
def db(tmp_path, monkeypatch):
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


@pytest.fixture(autouse=True)
def _ledger_to_tmp(tmp_path, monkeypatch):
    from backend.services import belief_state as BS
    monkeypatch.setattr(BS, "PREDICTIONS", tmp_path / "predictions.jsonl")
    monkeypatch.setattr(BS, "_migrate_once", lambda: None)


def seed_book(conn, bars, *, budget=-0.20, ips_hash="a" * 16):
    """A book at a declared budget, created the way the agency creates one."""
    from backend.strategy.contract import Objective
    strategy = make_strategy().with_(
        objective=Objective(name="terminal_wealth_at_drawdown_budget",
                            drawdown_budget=budget))
    asof = BC.latest_bar_date(bars)
    return PB.create(strategy, cadence="daily", origin="human_text",
                     origin_text="a sentence a human typed here",
                     ips_hash=ips_hash, bars=bars, asof=asof, conn=conn)


def mark(conn, book_id, rows):
    for d, nav in rows:
        conn.execute("INSERT OR REPLACE INTO paper_nav VALUES (?,?,?,?,?)",
                     (book_id, d, nav, "cfg", "now"))
    conn.commit()


#: A path that peaks at 120k and falls to 94.8k — 21% from the peak, one point
#: past a -20% budget. Derived from the budget in the test, never a literal
#: calendar or a literal NAV nobody can re-derive.
def path_to(peak: float, drawdown: float) -> list[tuple[str, float]]:
    return [("2026-01-01", 100_000.0), ("2026-01-02", peak),
            ("2026-01-03", round(peak * (1.0 + drawdown), 2))]


# --------------------------------------------------------------- the breach


def test_a_book_inside_its_budget_does_not_breach(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.10))
    state = A.breach_check(book, conn=conn, path=flips)
    assert state["breach"] is False
    assert state["distance_to_budget"] == pytest.approx(0.10, abs=1e-6)


def test_a_book_past_its_budget_breaches(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    state = A.breach_check(book, conn=conn, path=flips)
    assert state["breach"] is True
    assert state["drawdown"] == pytest.approx(-0.21, abs=1e-6)
    assert state["peak_nav"] == 120_000.0


def test_a_book_with_no_budget_never_fires(db, bars, flips):
    from backend.strategy.contract import Objective
    path, conn = db
    strategy = make_strategy().with_(objective=Objective(name="alpha_intercept"))
    asof = BC.latest_bar_date(bars)
    book, _t = PB.create(strategy, cadence="daily", origin="night_job",
                         bars=bars, asof=asof, conn=conn)
    mark(conn, book.book_id, path_to(120_000.0, -0.90))
    state = A.breach_check(book, conn=conn, path=flips)
    assert state["breach"] is False
    assert "no drawdown budget" in state["why"]


def test_a_breach_on_the_twin_does_not_flip_the_book(db, bars, flips):
    """The control is a control. A twin in freefall is information about the
    construction, not an instruction to the book."""
    path, conn = db
    book, twins = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.02))
    mark(conn, twins[0].book_id, path_to(120_000.0, -0.55))
    out = A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars,
                               conn=conn, path=flips)
    assert out["n_flipped"] == 0
    entry = next(b for b in out["books"] if b["book_id"] == book.book_id)
    assert entry["breach"] is False
    assert A.read_flips(flips) == []
    assert PB.get(book.book_id, conn=conn).status == "holding"


# ----------------------------------------------------------------- the flip


def test_a_breach_flips_to_the_preservation_construction(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    out = A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars,
                               conn=conn, path=flips)
    assert out["n_flipped"] == 1
    row = out["books"][0]["flip"]
    new = PB.get(row["to_book_id"], conn=conn)
    pres = A.TABLE["preservation"]
    assert new.strategy.construction.k == pres.k
    assert new.strategy.construction.max_single_name == pres.max_single_name
    assert new.strategy.hold.stop_loss == pres.stop_loss
    assert new.strategy.objective.drawdown_budget == pres.drawdown_budget
    assert new.origin == "mutation"
    assert new.ips_hash == book.ips_hash


def test_the_flip_target_is_the_personality_row_and_not_a_twin(db, bars, flips):
    """§4.2: 'preservation twin's construction' means the preservation
    PERSONALITY's construction. Flipping into the control would put a breached
    book into a random portfolio."""
    path, conn = db
    book, twins = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    row = A.read_flips(flips)[0]
    twin_prints = {t.strategy.fingerprint for t in twins}
    assert row["to_strategy_fingerprint"] not in twin_prints
    assert row["to_construction"] == "preservation"
    new = PB.get(row["to_book_id"], conn=conn)
    assert new.strategy.signal.name == book.strategy.signal.name


def test_the_original_is_retained_unmutated_and_both_are_shown(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    before = book.strategy.fingerprint
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    old = PB.get(book.book_id, conn=conn)
    assert old.status == "flipped"
    assert old.strategy.fingerprint == before, "a mutation is a NEW strategy"
    listed = {b.book_id for b in PB.list_books(conn=conn, include_twins=False)}
    assert book.book_id in listed
    assert A.read_flips(flips)[0]["to_book_id"] in listed


def test_the_flip_row_carries_the_from_and_to_fingerprints(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    row = A.read_flips(flips)[0]
    assert row["event"] == A.FLIP_EVENT
    assert row["from_strategy_fingerprint"] == book.strategy.fingerprint
    assert row["to_strategy_fingerprint"] != row["from_strategy_fingerprint"]
    assert row["flip_seq"] == 1
    assert row["reversible"] is True and row["reversed_utc"] is None
    assert row["drawdown_at_trigger"] == pytest.approx(-0.21, abs=1e-6)


def test_a_book_already_at_preservation_is_not_flipped_again(db, bars, flips):
    path, conn = db
    from backend.strategy.contract import Construction, Objective
    pres = A.TABLE["preservation"]
    strategy = make_strategy().with_(
        construction=Construction(rule="top_k", k=pres.k, weighting="ew",
                                  max_single_name=pres.max_single_name),
        objective=Objective(name="terminal_wealth_at_drawdown_budget",
                            drawdown_budget=pres.drawdown_budget))
    asof = BC.latest_bar_date(bars)
    book, _t = PB.create(strategy, cadence="daily", origin="human_text",
                         origin_text="already the careful one", ips_hash="b" * 16,
                         bars=bars, asof=asof, conn=conn)
    mark(conn, book.book_id, path_to(120_000.0, -0.30))
    out = A.protect_first_pass(asof=asof, bars=bars, conn=conn, path=flips)
    entry = out["books"][0]
    assert entry["breach"] is True
    assert entry["flipped"] is False
    assert "no more conservative row" in entry["reason"]


def test_a_breach_with_no_bars_is_recorded_and_not_flipped(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    out = A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=None,
                               conn=conn, path=flips)
    entry = out["books"][0]
    assert entry["breach"] is True and entry["flipped"] is False
    assert "REFUSED" in entry["reason"]


# ------------------------------------------------- T3: the peak never resets


def test_the_flip_and_the_reversal_both_preserve_the_peak(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    before = A.read_flips(flips)[0]["peak_nav"]
    assert before == 120_000.0
    A.unflip(book_id=book.book_id, by="murat", path=flips, conn=conn)
    after = A.read_flips(flips)[0]
    assert after["peak_nav"] == before
    assert after["reversed_utc"] is not None
    assert after["reversed_by"] == "murat"


def test_the_new_book_inherits_the_peak_rather_than_starting_fresh(db, bars,
                                                                   flips):
    """§4.1: a book that breaches, flips and recovers is still measured
    against its ORIGINAL peak."""
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    new_id = A.read_flips(flips)[0]["to_book_id"]
    new = PB.get(new_id, conn=conn)
    mark(conn, new_id, [("2026-01-04", 100_000.0)])
    state = A.breach_check(new, conn=conn, path=flips)
    assert state["peak_nav"] == 120_000.0, "the peak came with the book"
    assert "carried" in state["peak_carried_from"]
    assert state["drawdown"] == pytest.approx(-1 / 6, abs=1e-6)


def test_the_reversal_writes_onto_the_same_row_not_a_second_one(db, bars,
                                                                flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    A.unflip(book_id=book.book_id, path=flips, conn=conn)
    rows = A.read_flips(flips)
    assert len(rows) == 1, "a reversal is not a second event"
    assert rows[0]["flip_seq"] == 1


def test_the_reversal_restores_the_pre_flip_book(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    new_id = A.read_flips(flips)[0]["to_book_id"]
    A.unflip(book_id=book.book_id, path=flips, conn=conn)
    assert PB.get(book.book_id, conn=conn).status == "holding"
    assert PB.get(new_id, conn=conn).status == "retired"


def test_reversing_a_flip_that_did_not_happen_is_refused(flips, db):
    with pytest.raises(A.AgencyError, match="no un-reversed"):
        A.unflip(book_id="book:deadbeef", path=flips)


def test_the_engine_never_reverses_its_own_flip(db, bars, flips):
    """A second pass over a reversed flip must not re-flip silently — and
    `protect_first_pass` contains no call to `unflip` at all."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(A.protect_first_pass).lstrip())
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "unflip" not in called


# ------------------------------------------------------- the base-rate control


def test_a_flip_is_never_reported_without_its_base_rate(db, bars, flips):
    path, conn = db
    book, twins = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    mark(conn, twins[0].book_id, path_to(110_000.0, -0.05))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    row = A.read_flips(flips)[0]
    ctl = row["base_rate_control"]
    assert ctl["verdict"] == "measured on the twin"
    assert 0.0 <= ctl["twin_breach_rate"] <= 1.0
    assert 0.0 <= ctl["random_threshold_fire_rate"] <= 1.0
    assert "not informative" in ctl["reading"]


def test_a_twin_with_no_history_is_cannot_determine_not_zero(db, bars, flips):
    path, conn = db
    book, _t = seed_book(conn, bars)
    ctl = A.base_rate_on_twin(book, conn=conn)
    assert ctl["verdict"] == "CANNOT DETERMINE"
    assert "false-positive rate" in ctl["why"]


def test_a_noisy_twin_raises_the_base_rate(db, bars, flips):
    path, conn = db
    book, twins = seed_book(conn, bars)
    mark(conn, twins[0].book_id, path_to(120_000.0, -0.40))
    ctl = A.base_rate_on_twin(book, conn=conn)
    assert ctl["twin_worst_drawdown"] == pytest.approx(-0.40, abs=1e-6)
    assert ctl["random_threshold_fire_rate"] == 1.0, (
        "a twin 40% off its peak crosses every threshold in a band around -20%")


# ------------------------------------------------------------- the surfaces


def test_the_morning_step_carries_the_protect_first_block(db, bars, flips,
                                                          tmp_path, monkeypatch):
    from backend.services import morning as M
    path, conn = db
    book, _t = seed_book(conn, bars)
    # The peak is set high enough that the mark THIS MORNING writes (the book
    # holds nothing, so it marks at inception value) is itself past the budget.
    # Writing a breach and then letting the same morning mark over it is how a
    # fixture ends up testing the fixture.
    mark(conn, book.book_id, path_to(130_000.0, -0.21))
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    receipt = M.run_morning(today=BC.latest_bar_date(bars), do_network=False,
                            predictions_path=tmp_path / "p.jsonl",
                            out_dir=tmp_path / "m")
    row = next(s for s in receipt["steps"] if s["step"] == "agency_review")
    assert row["protect_first"]["n_flipped"] == 1
    assert row["protect_first"]["books"][0]["base_rate_control"]


def test_the_flip_route_is_a_read_and_the_unflip_is_gated(db, bars, flips,
                                                          monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    client = TestClient(app)
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    assert client.post("/api/control/agency/unflip", json={}).status_code == 403
    body = client.get("/api/control/agency/protect-first").json()
    assert body["n_flips"] == 0
    assert "base_rate_control" in body["reading"]


def test_the_unflip_route_reverses_one_flip(db, bars, flips, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    path, conn = db
    book, _t = seed_book(conn, bars)
    mark(conn, book.book_id, path_to(120_000.0, -0.21))
    A.protect_first_pass(asof=BC.latest_bar_date(bars), bars=bars, conn=conn,
                         path=flips)
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = TestClient(app).post("/api/control/agency/unflip",
                             json={"book_id": book.book_id, "by": "murat"})
    assert r.status_code == 200, r.text
    assert r.json()["flip"]["reversed_by"] == "murat"
    assert A.read_flips(flips)[0]["reversed_utc"]
