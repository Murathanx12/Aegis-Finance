"""H2 -- the journal → thesis bridge.

The tests that matter here are the REFUSALS. A bridge that accepts everything
turns an ungradeable journal row into an ungradeable thesis row and calls it
progress, so every refusal the execution repo's schema owns is exercised
through THIS module -- proving the inheritance is live and not decorative.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.config import LOSS_BUDGETS
from backend.services import human_thesis as ht

REPO = Path(__file__).resolve().parents[2]
UPSTREAM = Path.home() / "aegis-alpha-terminal"


def _future(days: int = 30) -> str:
    """A catalyst date derived from `today` -- never a literal (CLAUDE.md §5)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(
        timespec="seconds")


def _ok(**over):
    kw = dict(symbol="NVDA", direction="up", expected_move=0.06,
              catalyst="Q3 FY27 print", catalyst_at_utc=_future(30),
              reason="AI demand accelerating faster than the guide implies",
              falsifier="Q4 revenue guide at or below $104bn, or GM guide below 74%",
              horizon_sessions=21, min_normal_hold_sessions=5,
              loss_budget_ref="human_v1")
    kw.update(over)
    return kw


# ── the schema is the execution repo's, verbatim ────────────────────────────
class TestSchemaIsVerbatim:
    """One schema, not two. Drift is a failing test, never a surprise."""

    MIRRORED = ("alpha/human.py", "alpha/brains/base.py")

    @pytest.mark.parametrize("rel", MIRRORED)
    def test_mirror_is_byte_identical_to_the_execution_repo(self, rel):
        up = UPSTREAM / rel
        if not up.is_file():
            pytest.skip(
                f"{up} is not on this machine, so byte-identity CANNOT BE "
                "DETERMINED here. This is a SKIP and not a pass: the mirror may "
                "have drifted and this run did not check.")
        mine = REPO / "backend" / "vendor" / "aat" / rel
        assert hashlib.sha256(mine.read_bytes()).hexdigest() == \
            hashlib.sha256(up.read_bytes()).hexdigest(), (
                f"{rel} has drifted from the execution repo. Re-copy it; do NOT "
                "hand-merge, and do NOT re-implement the rules locally -- two "
                "copies of a validation rule is how two repos start refusing "
                "different things while both claim one contract.")

    def test_the_loaded_schema_is_the_mirror_not_the_execution_repo(self):
        prov = ht.schema_provenance()
        assert prov["is_vendored_mirror"] is True
        assert "vendor" in prov["file"], (
            "the schema resolved outside backend/vendor. If `alpha` ever binds "
            "to the execution repo, a web request handler is one import away "
            "from `alpha.brains` -- the package that owns the broker client.")

    def test_the_brains_stub_imports_nothing(self):
        """The one deliberate difference from upstream, asserted rather than
        described. The real `alpha/brains/__init__.py` imports the whole fleet."""
        src = (REPO / "backend" / "vendor" / "aat" / "alpha" / "brains"
               / "__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        assert not [n for n in ast.walk(tree)
                    if isinstance(n, (ast.Import, ast.ImportFrom))]

    def test_no_broker_package_entered_sys_modules(self):
        import sys
        assert "alpha.brains.post_event_drift" not in sys.modules
        base = sys.modules.get("alpha.brains.base")
        assert base is not None and "vendor" in str(base.__file__)


# ── the inherited refusals, exercised through THIS module ───────────────────
class TestInheritedRefusals:
    def test_a_thesis_after_its_own_catalyst_is_refused(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with pytest.raises(ht.ThesisRefusal) as e:
            ht.build(**_ok(catalyst_at_utc=past))
        assert "memory" in str(e.value).lower()

    def test_a_short_falsifier_is_refused(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(falsifier="it goes down"))

    @pytest.mark.parametrize("n", [0, 14])
    def test_the_falsifier_boundary_is_15_chars(self, n):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(falsifier="x" * n))
        assert ht.build(**_ok(falsifier="y" * 15)).falsifier == "y" * 15

    def test_a_short_reason_is_refused(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(reason="cheap"))

    def test_direction_without_expected_move_is_refused(self):
        with pytest.raises(ht.ThesisRefusal) as e:
            ht.build(**_ok(expected_move=None))
        assert "expected-move" in str(e.value) or "expected_move" in str(e.value)

    def test_a_sign_disagreement_is_refused(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(direction="up", expected_move=-0.06))

    def test_no_direction_and_no_width_claim_is_not_a_thesis(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(direction="none", expected_move=None, magnitude="unknown"))

    def test_conviction_out_of_range_is_refused(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(conviction=2.0))


# ── the three fields this bridge adds ───────────────────────────────────────
class TestTheThreeHoldFields:
    def test_all_three_land_on_the_row(self):
        t = ht.build(**_ok())
        assert (t.horizon_sessions, t.min_normal_hold_sessions,
                t.loss_budget_ref) == (21, 5, "human_v1")

    def test_an_undeclared_loss_budget_is_refused(self):
        with pytest.raises(ht.ThesisRefusal) as e:
            ht.build(**_ok(loss_budget_ref="whatever"))
        assert "invariant 19" in str(e.value).lower()

    def test_zero_min_hold_is_refused_outside_an_event_budget(self):
        with pytest.raises(ht.ThesisRefusal) as e:
            ht.build(**_ok(min_normal_hold_sessions=0))
        assert "event" in str(e.value).lower()

    def test_zero_min_hold_is_ALLOWED_under_the_event_budget(self):
        """min hold 0 must be a CHOICE with a name on it, not a default. The
        gate that only ever refuses is a gate that cannot go green."""
        t = ht.build(**_ok(loss_budget_ref="event_v1",
                           min_normal_hold_sessions=0, horizon_sessions=3))
        assert t.min_normal_hold_sessions == 0
        assert t.loss_budget["book"] == "hack2"

    def test_min_hold_over_the_horizon_is_refused(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(horizon_sessions=5, min_normal_hold_sessions=6))

    def test_a_non_positive_horizon_is_refused(self):
        with pytest.raises(ht.ThesisRefusal):
            ht.build(**_ok(horizon_sessions=0))

    def test_the_defaults_are_stamped_as_defaults(self):
        t = ht.build(**{k: v for k, v in _ok().items()
                        if k not in ("horizon_sessions", "min_normal_hold_sessions",
                                     "loss_budget_ref")})
        assert t.evidence["horizon_source"] == "config_default"
        assert t.evidence["min_hold_source"] == "config_default"
        declared = ht.build(**_ok())
        assert declared.evidence["horizon_source"] == "declared"

    def test_every_declared_budget_is_usable(self):
        """A budget nobody can name is a row in a dict, not a policy."""
        for ref, spec in LOSS_BUDGETS.items():
            hold = 0 if ref == "event_v1" else 1
            t = ht.build(**_ok(loss_budget_ref=ref, horizon_sessions=5,
                               min_normal_hold_sessions=hold))
            assert t.loss_budget["book"] == spec["book"]
            assert t.loss_budget["expected_losers"] <= t.loss_budget["positions_judged"]

    def test_review_cadence_never_outruns_the_horizon(self):
        t = ht.build(**_ok(horizon_sessions=3, min_normal_hold_sessions=1))
        assert t.review_cadence_sessions == 3


# ── the book row ────────────────────────────────────────────────────────────
class TestBookEntry:
    def test_the_row_is_under_the_human_brain(self):
        row = ht.book_entry(ht.build(**_ok()), day="2026-09-08")
        assert row["generator"] == "human:murat" and row["brain"] == "human:murat"
        assert row["schema"] == "prediction-book-3"

    def test_the_three_fields_travel_onto_the_row(self):
        row = ht.book_entry(ht.build(**_ok()), day="2026-09-08")
        assert row["horizon_sessions"] == 21
        assert row["min_normal_hold_sessions"] == 5
        assert row["loss_budget_ref"] == "human_v1"
        assert row["loss_budget"]["positions_judged"] == 20

    def test_the_hash_covers_the_content(self):
        row = ht.book_entry(ht.build(**_ok()), day="2026-09-08")
        assert ht.verify_book_entry(row)
        row["exp_return"] = 0.99
        assert not ht.verify_book_entry(row), (
            "the content hash did not move when a number did; it is decoration")

    def test_the_row_declares_it_is_not_self_executing(self):
        row = ht.book_entry(ht.build(**_ok()), day="2026-09-08")
        assert "NOT SELF-EXECUTING" in row["authority"]

    def test_export_for_seal_does_not_seal(self):
        """The function that would be the tempting place to write upstream."""
        out = ht.export_for_seal(ht.build(**_ok()))
        assert out["seal_is_attended"] is True
        assert "READ_ONLY" in out["authority"]
        src = (REPO / "backend" / "services" / "human_thesis.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "export_for_seal")
        calls = {getattr(c.func, "attr", getattr(c.func, "id", ""))
                 for c in ast.walk(fn) if isinstance(c, ast.Call)}
        assert not (calls & {"write_text", "write_bytes", "open", "_append"})

    def test_a_bare_thesis_cannot_produce_a_book_row(self):
        t = ht.Thesis(author="murat", symbol="NVDA", direction="up",
                      magnitude="unknown", catalyst="x", catalyst_at_utc=_future(9),
                      horizon_days=30.0, reason="a reason long enough",
                      falsifier="a falsifier that is long enough to check",
                      expected_move=0.05)
        with pytest.raises(ht.ThesisRefusal):
            ht.book_entry(t)


# ── storage ─────────────────────────────────────────────────────────────────
class TestStorage:
    def test_record_is_append_only_and_round_trips(self, tmp_path: Path):
        tp, bp = tmp_path / "t.jsonl", tmp_path / "b.jsonl"
        a = ht.build(**_ok())
        b = ht.build(**_ok(symbol="AMD", falsifier="MI400 slips past H2 CY27 guide"))
        ht.record(a, thesis_path=tp, book_path=bp)
        ht.record(b, thesis_path=tp, book_path=bp)
        assert len(tp.read_text(encoding="utf-8").strip().splitlines()) == 2
        rep = ht.load_report(tp)
        assert rep["n"] == 2 and rep["n_rejected"] == 0
        assert {t.symbol for t in rep["theses"]} == {"NVDA", "AMD"}

    def test_a_row_that_no_longer_validates_is_counted_not_repaired(self, tmp_path):
        tp = tmp_path / "t.jsonl"
        ht.record(ht.build(**_ok()), thesis_path=tp, book_path=tmp_path / "b.jsonl")
        bad = json.loads(tp.read_text(encoding="utf-8").splitlines()[0])
        bad["falsifier"] = "short"
        with tp.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(bad) + "\n")
        rep = ht.load_report(tp)
        assert rep["n"] == 1 and rep["n_rejected"] == 1
        assert "falsifier" in rep["rejected"][0]["reason"]

    def test_the_thesis_id_covers_the_three_new_fields(self):
        a = ht.build(**_ok())
        b = ht.build(**_ok(horizon_sessions=63, stated_at_utc=a.stated_at_utc))
        assert a.thesis_id() != b.thesis_id(), (
            "two theses differing only in horizon hash the same; the id does "
            "not cover the fields the grader uses")


class TestReachabilityClassification:
    """`backend.vendor.aat.alpha.human` has a real RUNTIME consumer and no
    static import edge, and both halves of that sentence are asserted here.

    It cannot be given an ordinary caller: the mirrored file keeps its own
    `from alpha.brains.base import Forecast` line byte-identical (that is what
    "verbatim" means), so it is only importable under the top-level name
    `alpha`, and a static `from backend.vendor.aat.alpha import human` would
    fail at import time. Editing the line to make the audit happy would break
    the one property H2 asked for. So it is CLASSIFIED, and these two tests
    stop the classification from becoming an excuse for dead code.
    """

    def test_the_vendor_subtree_is_classified_by_name(self):
        from backend.services.signal_reachability import _classification

        for m in ("backend.vendor", "backend.vendor.aat.alpha.human",
                  "backend.vendor.aat.alpha.brains.base"):
            reason = _classification(m)
            assert reason and "VERBATIM" in reason, (
                f"{m} is not classified. A prefix rename under backend/vendor/ "
                "must fail here rather than turning the reachability audit red "
                "for a future session to rediscover.")

    def test_the_mirror_is_actually_LOADED_not_merely_present(self):
        """The half a classification cannot prove: that the file runs.

        `signal_reachability` can only say nothing IMPORTS it. This says the
        running service DID import it, by path, and is using the class from it.
        Without this the classification would be indistinguishable from an
        excuse for a directory of dead code.
        """
        import sys

        assert "alpha.human" in sys.modules
        assert ht.HumanThesis.__mro__[1] is sys.modules["alpha.human"].Thesis
        assert "vendor" in ht.schema_provenance()["file"]
