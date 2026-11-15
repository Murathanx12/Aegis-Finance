"""Source checks on the "Note to Claude" UI (review of PR #143: M2, M3, L4).

There is no frontend unit runner in CI, so these read the TSX. Each check reads a
specific JSX construct, not a comment: comments are stripped first, so a sentence
that explains the old behaviour cannot satisfy or break a check (protocol §10).
"""

from __future__ import annotations

import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _code(rel: str) -> str:
    """The file with // and /* */ comments (including {/* */} JSX comments) removed,
    whitespace collapsed."""
    s = (FRONT / rel).read_text(encoding="utf-8")
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"(?m)^\s*//.*$", "", s)
    s = re.sub(r"(?<![:\"'])//[^\n]*", "", s)
    return re.sub(r"\s+", " ", s)


NOTE = "components/desktop/owner-note.tsx"
ASK = "app/desktop/ask/page.tsx"


def test_the_saved_message_states_a_fact_not_a_promise():
    """M3: nothing makes a session read the note; the page says what is true."""
    code = _code(NOTE)
    assert "Claude reads this at the start of the next session" not in code
    assert ("Saved to the inbox file. Claude reads it when a session starts and runs the inbox "
            "command.") in code


def test_unreadable_lines_are_shown_when_non_zero():
    """M2: a torn line used to be counted by the API and never shown."""
    code = _code(NOTE)
    assert "d.unreadable_lines > 0 ?" in code and "{d.unreadable_lines} line" in code
    assert "{torn}" in code


def test_the_ask_page_box_uses_the_desktop_build_check():
    """L4: the inline box rendered on the public website's /desktop/ask."""
    code = _code(ASK)
    i = code.index("<OwnerNoteForm />")
    assert "{CONTROL_PLANE_BUILD ? (" in code[:i]
    assert code.index("{CONTROL_PLANE_BUILD ? (") < i < code.index(") : null}", i)


def test_the_floating_button_stays_off_the_page_with_the_inline_box():
    """L4: /desktop/ask showed the box twice."""
    code = _code(NOTE)
    assert 'const INLINE_FORM_PAGES = ["/desktop/ask"];' in code
    assert "if (!CONTROL_PLANE_BUILD || INLINE_FORM_PAGES.includes(here)) return null;" in code
