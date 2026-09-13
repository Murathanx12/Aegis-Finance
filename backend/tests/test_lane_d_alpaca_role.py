"""Lane D's own Alpaca paper role (chunk 12, T6) — the refusal and the name line.

WHY LANE D NEEDS ITS OWN ACCOUNT, STATED ONCE
=============================================
Lane D's D2 deliverable is "every paper fill vs the IEX quote and vs the SIP
NBBO", and it is the only thing that can turn `cost_curve.retail_paper` from a
DECLARED band into a measured rate. A fill receipt collected on the default or
the arena account is a receipt about a DIFFERENT book's order flow, and the cost
number it produced would be attributed to lane D. So the role is its own key
pair and there is NO FALLBACK.

What is pinned here:

* `ALPACA_LANE_D_API_KEY_ID` and `ALPACA_LANE_D_API_SECRET_KEY`, both halves,
  read in exactly one place (`backend/config.py`);
* the refusal TEXT, verbatim, because a consumer that invents its own wording
  leaves an operator grepping for a sentence that does not exist;
* **no fallback**, by AST: neither the config helpers nor the lane D consumer
  may mention the default or arena names in executable source;
* **names only, never values**: `lane_d_role_status()` returns the NAMES and
  `configured`/`absent`, and a test fails if a key's value can reach the
  payload.

`backend.config` is never reloaded in-process (house rule); every test sets the
env vars with `monkeypatch` and calls the helpers, which read `os.getenv` at
call time for exactly that reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend import config as C

REPO = Path(__file__).resolve().parents[2]
SECRET = "sk-lane-d-this-value-must-never-appear-anywhere"


def executable_source(path: Path) -> str:
    """Source with comments AND docstrings removed (protocol item 10).

    Three guards failed on their first run this month by matching the docstring
    that EXPLAINS the banned pattern. The docstrings here deliberately name
    `ALPACA_API_KEY_ID` in order to say it is never read.
    """
    src = path.read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            first = body[0] if body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return "\n".join(line for i, line in enumerate(src.splitlines(), 1)
                     if i not in drop and not line.strip().startswith("#"))


@pytest.fixture
def absent(monkeypatch):
    monkeypatch.delenv(C.LANE_D_KEY_ID_ENV, raising=False)
    monkeypatch.delenv(C.LANE_D_SECRET_ENV, raising=False)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv(C.LANE_D_KEY_ID_ENV, "PKLANED0000000000000")
    monkeypatch.setenv(C.LANE_D_SECRET_ENV, SECRET)


# --------------------------------------------------------------------------
# the names


def test_the_names_follow_the_repos_existing_pattern():
    assert C.LANE_D_KEY_ID_ENV == "ALPACA_LANE_D_API_KEY_ID"
    assert C.LANE_D_SECRET_ENV == "ALPACA_LANE_D_API_SECRET_KEY"


def test_both_halves_are_required(monkeypatch):
    """A key id with no secret is an account nobody can reach; reporting it as
    configured moves the failure to the first request."""
    monkeypatch.setenv(C.LANE_D_KEY_ID_ENV, "PKLANED")
    monkeypatch.delenv(C.LANE_D_SECRET_ENV, raising=False)
    assert C.lane_d_role_configured() is False
    st = C.lane_d_role_status()
    assert st["lane_d_role"] == "absent"
    assert st["names_present"] == [C.LANE_D_KEY_ID_ENV]
    assert st["names_absent"] == [C.LANE_D_SECRET_ENV]


def test_whitespace_is_not_a_credential(monkeypatch):
    monkeypatch.setenv(C.LANE_D_KEY_ID_ENV, "   ")
    monkeypatch.setenv(C.LANE_D_SECRET_ENV, "  ")
    assert C.lane_d_role_configured() is False


def test_the_configured_status_names_both_and_carries_no_refusal(configured):
    st = C.lane_d_role_status()
    assert st["lane_d_role"] == "configured"
    assert st["names_present"] == [C.LANE_D_KEY_ID_ENV, C.LANE_D_SECRET_ENV]
    assert st["names_absent"] == []
    assert st["refusal"] is None


# --------------------------------------------------------------------------
# the refusal text, verbatim


def test_the_refusal_is_the_declared_sentence(absent):
    want = ("lane D's paper role is not configured: set "
            "ALPACA_LANE_D_API_KEY_ID and ALPACA_LANE_D_API_SECRET_KEY")
    assert C.LANE_D_ROLE_REFUSAL == want
    assert C.lane_d_role_status()["refusal"] == want


def test_the_lane_d_consumer_refuses_by_name_and_does_not_crash(absent):
    from scripts import monday_night as MN

    step = MN.fill_quality_step(MN.lane_d_role())
    assert step["status"] == "refused"
    assert step["refusal"] == C.LANE_D_ROLE_REFUSAL
    assert step["names_absent"] == [C.LANE_D_KEY_ID_ENV, C.LANE_D_SECRET_ENV]
    assert "retail_paper" in step["consequence"]


def test_a_configured_role_does_not_claim_a_receipt_it_did_not_write(configured):
    """A step that reported `ok` because the credential existed would be a gate
    on the credential, not on the fill-quality receipt."""
    from scripts import monday_night as MN

    step = MN.fill_quality_step(MN.lane_d_role())
    assert step["status"] == "pending_writer"
    assert step["role"] == "configured"
    assert "does not exist yet" in step["blocked_on"]


def test_the_pass_receipt_carries_the_role_and_the_step(absent):
    from datetime import datetime, timezone

    from scripts import monday_night as MN

    payload = MN.one_pass(dry_run=True, now=datetime.now(timezone.utc), index=0)
    assert payload["lane_d_role"]["lane_d_role"] == "absent"
    assert payload["fill_quality"]["status"] == "refused"


# --------------------------------------------------------------------------
# no fallback, and no values


def test_no_fallback_to_the_default_or_arena_account():
    """A fallback would trade lane D on the wrong book, and the failure would
    look like a working system."""
    assert C.LANE_D_FORBIDDEN_FALLBACKS == (
        "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY",
        "ALPACA_ARENA_API_KEY_ID", "ALPACA_ARENA_API_SECRET_KEY")
    src = executable_source(REPO / "scripts" / "monday_night.py")
    for name in C.LANE_D_FORBIDDEN_FALLBACKS:
        assert name not in src, (
            f"{name} appears in monday_night.py's executable source. Lane D has "
            f"no fallback account: a fill receipt collected elsewhere is a "
            f"receipt about another book's order flow.")


def test_the_config_helpers_read_only_lane_ds_own_two_names():
    """The forbidden names may appear in the DECLARED tuple and in prose, and
    nowhere else — so the check is on `os.getenv` calls, not on the text."""
    src = (REPO / "backend" / "config.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = {n.name: n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef)
           and n.name in ("lane_d_role_configured", "lane_d_role_status")}
    assert set(fns) == {"lane_d_role_configured", "lane_d_role_status"}
    for name, fn in fns.items():
        read: list[str] = []
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "getenv"):
                arg = node.args[0] if node.args else None
                read.append(getattr(arg, "id", None)
                            or getattr(arg, "value", None))
        assert read, f"{name} reads no environment variable"
        assert set(read) <= {"LANE_D_KEY_ID_ENV", "LANE_D_SECRET_ENV"}, (
            f"{name} reads {sorted(set(read))}; lane D has its own two names "
            f"and no fallback")


def test_the_status_payload_never_carries_a_value(configured):
    import json

    blob = json.dumps(C.lane_d_role_status())
    assert SECRET not in blob
    assert "PKLANED0000000000000" not in blob
    # it carries the NAMES, which is the whole point of the line
    assert C.LANE_D_KEY_ID_ENV in blob and C.LANE_D_SECRET_ENV in blob


def test_the_monday_night_receipt_never_carries_a_value(configured):
    import json
    from datetime import datetime, timezone

    from scripts import monday_night as MN

    payload = MN.one_pass(dry_run=True, now=datetime.now(timezone.utc), index=0)
    assert SECRET not in json.dumps(payload, default=str)


# --------------------------------------------------------------------------
# the board's status line


def test_the_coverage_card_shows_the_role_by_name(absent):
    from backend.routers import control

    row = control._lane_d_role()
    assert row["lane_d_role"] == "absent"
    assert row["names_required"] == [C.LANE_D_KEY_ID_ENV, C.LANE_D_SECRET_ENV]


def test_the_coverage_card_says_configured_when_it_is(configured):
    from backend.routers import control

    assert control._lane_d_role()["lane_d_role"] == "configured"


def test_the_card_degrades_to_a_report_rather_than_a_500(monkeypatch):
    """A read degrades to a report, never a 500 — the rule the rest of
    `/coverage` already follows."""
    import backend.config as CFG
    from backend.routers import control

    def _boom():
        raise RuntimeError("config is unreadable")

    monkeypatch.setattr(CFG, "lane_d_role_status", _boom)
    row = control._lane_d_role()
    assert row["lane_d_role"] == "CANNOT DETERMINE"
    assert "config is unreadable" in row["error"]


def test_the_coverage_route_carries_the_key(absent):
    from backend.routers import control

    cov = control.coverage()
    # the route degrades to `available: False` on a machine with no registry;
    # the lane D line is only promised on the available path
    if cov.get("available"):
        assert cov["lane_d_role"]["lane_d_role"] == "absent"
    else:
        pytest.skip("no news registry on this checkout; the card is unavailable")
