"""The parent tab must carry Murat's marker (2026-09-27).

The `user` attach reaches every profile of the running Chrome and the tab list
does not name a tab's profile. "By host" twice opened pages in the main account.
With the marker set, only a tab Murat opened by hand in the MuratClaw window is
an admissible parent; without one the reader refuses.
"""
import pytest

from backend.services import web_reader as WR
from scripts import dowjones_pull as DJ


def _tab(n: int, url: str) -> dict:
    return {"targetId": f"chrome-mcp:abc:{n}", "tabId": f"t{n}", "url": url, "type": "page"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(DJ, "PARENT_MARKER", None)


@pytest.fixture
def marker(monkeypatch):
    monkeypatch.setattr(DJ, "PARENT_MARKER", DJ.MARKER_DEFAULT)


def test_marker_tab_wins_over_an_older_tab_on_the_same_host(marker):
    tabs = [_tab(2, "https://www.wsj.com/"), _tab(9, "https://www.wsj.com/?aegis=muratclaw")]
    out = DJ.resolve_parent_tabs(["wsj", "barrons", "marketwatch"], tabs)
    assert {v["url"] for v in out.values()} == {"https://www.wsj.com/?aegis=muratclaw"}


def test_no_marker_tab_refuses_by_name(marker):
    tabs = [_tab(2, "https://www.wsj.com/"), _tab(3, "https://www.barrons.com/")]
    with pytest.raises(WR.ReaderRefused, match="REFUSED_NO_MARKER_TAB"):
        DJ.resolve_parent_tabs(["wsj"], tabs)


def test_an_explicit_parent_without_the_marker_refuses(marker):
    tabs = [_tab(2, "https://www.wsj.com/"), _tab(9, "https://www.wsj.com/?aegis=muratclaw")]
    with pytest.raises(WR.ReaderRefused, match="REFUSED_PARENT_TAB"):
        DJ.resolve_parent_tabs(["wsj"], tabs, explicit={"wsj": "t2"})


def test_without_the_marker_setting_the_old_rule_stands():
    assert DJ.PARENT_MARKER is None
    out = DJ.resolve_parent_tabs(["wsj"], [_tab(2, "https://www.wsj.com/")])
    assert out["wsj"]["how"].startswith("by_host")


def test_main_sets_the_marker_for_operator_profiles_only():
    import ast, inspect
    src = inspect.getsource(DJ.main)
    tree = ast.parse(src)
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and any(getattr(t, "id", "") == "PARENT_MARKER" for t in n.targets)]
    assert assigns, "main() no longer sets PARENT_MARKER"
    assert "is_operator_profile" in src
