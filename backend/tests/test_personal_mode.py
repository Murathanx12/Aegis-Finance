"""PERSONAL MODE — the disclaimer moves, and nothing else does (chunk 17).

Spec: `docs/research_notes/2026-09-19/spec_decision_contract_and_path_audit.md` §5.

Aegis ships twice out of one codebase: a public tool other people run at their
own utility function, and Murat's own desktop build. The public one carries
"educational tool, not financial advice" on every surface. The personal one is
a man reading his own research, and a disclaimer addressed to himself is noise
that teaches him to skim whatever sits beside it.

FOUR THINGS ARE PINNED HERE, and each of them is a way this flag could go wrong:

* it is OFF unless the environment says otherwise — the deployed website, the
  public build and CI must never read it as on by accident;
* it hides DISCLAIMER sentences and nothing else. "paper only", "backtest, not
  the track record", "crash probabilities are model estimates, not guarantees"
  are findings about the numbers and stay in both builds;
* the three EXPORT artefacts (daily brief, tearsheet, portfolio guidance) are
  untouched: those files can leave the machine that made them, and whether they
  keep their disclaimer is Murat's call, not a session's (spec §5.2);
* the frontend reads the flag through ONE helper. Next.js inlines a
  `NEXT_PUBLIC_*` read only when it sees the full member expression at build
  time, so a second, computed spelling would evaluate to `undefined` in the
  browser bundle — a flag that reads OFF in exactly the build it was written
  for. The comment-stripped source of every listed file is checked, never the
  raw text: a guard that cannot tell an explanation from an instance is a
  broken guard (CLAUDE.md item 10).
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest

from backend import config as _config
from backend.services import copilot

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend" / "src"

#: Every frontend file the audit's §5.1 table names that renders a disclaimer
#: in code (as opposed to rendering the shared banner component).
GATED_FRONTEND_FILES = (
    "components/disclaimer-banner.tsx",
    "components/methodology-banner.tsx",
    "components/dashboard/model-vs-firms-card.tsx",
    "components/stock/factor-lens-card.tsx",
    "components/stock/two-sided-card.tsx",
    "components/sidebar.tsx",
    "app/screener/page.tsx",
    "app/risk/page.tsx",
    "app/portfolio/page.tsx",
    "app/news/page.tsx",
    "app/investment-committee/page.tsx",
    "app/copilot/page.tsx",
    "app/crash/page.tsx",
    "app/retirement/page.tsx",
    "app/about/page.tsx",
)

#: The three artefacts personal mode deliberately does NOT touch.
EXPORT_ARTEFACTS = (
    ("backend/services/daily_brief.py", "not financial advice"),
    ("backend/services/portfolio_intelligence/tearsheet.py", "not financial advice"),
    ("backend/services/portfolio_guidance.py", "not financial advice"),
)


def code_only(text: str) -> str:
    """TypeScript source with comments removed — the AST-walk's analogue.

    Three tests in this repository failed on their first run by matching the
    prose that EXPLAINS the thing they banned. Here the risk runs the other
    way: a file could "mention" the helper only in a comment about it, and a
    grep over raw text would call that an import.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.strip().startswith("//"))


# --------------------------------------------------------------------------
# the flag itself


@pytest.mark.skipif(os.getenv("AEGIS_PERSONAL_MODE") is not None,
                    reason="the operator has set the flag in this environment")
def test_personal_mode_is_off_unless_the_environment_says_otherwise():
    assert _config.PERSONAL_MODE is False


def test_the_flag_is_a_bool_and_not_a_string():
    """`os.getenv(...) in (...)` and not the raw string: a non-empty "0" is
    truthy, and this is exactly the shape of the `ANTHROPIC_API_KEY=` bug —
    a setting that reads as configured and is not."""
    assert isinstance(_config.PERSONAL_MODE, bool)


# --------------------------------------------------------------------------
# backend site 1 — the copilot system prompt


def test_the_public_prompt_ends_with_the_disclaimer_clause():
    assert copilot.system_prompt().endswith("is not financial advice.")
    assert copilot.SYSTEM_PROMPT == copilot.system_prompt()


def test_personal_mode_drops_the_prompts_disclaimer_clause(monkeypatch):
    monkeypatch.setattr(_config, "PERSONAL_MODE", True)
    prompt = copilot.system_prompt()
    assert "not financial advice" not in prompt
    assert prompt == copilot._SYSTEM_PROMPT_BASE


def test_the_rest_of_the_prompt_is_identical_in_both_builds(monkeypatch):
    """The copilot has no sizing authority in either build. Hiding a
    disclaimer must not quietly rewrite what it is told to do."""
    public = copilot.system_prompt()
    monkeypatch.setattr(_config, "PERSONAL_MODE", True)
    personal = copilot.system_prompt()
    assert public == personal + copilot._DISCLAIMER_CLAUSE
    for anchor in ("Always call tools before committing to numeric claims",
                   "Never invent tickers", "label them as 'Aegis data'"):
        assert anchor in personal


def test_every_prompt_call_site_reads_the_function_not_the_constant():
    """A call site that kept the constant would ship the public prompt into
    the personal build and nobody would see it — the prompt is not printed."""
    src = (REPO / "backend" / "services" / "copilot.py").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    for line in body.splitlines():
        if "SYSTEM_PROMPT" not in line:
            continue
        assert ("_SYSTEM_PROMPT_BASE" in line or "SYSTEM_PROMPT = " in line
                or "system_prompt()" in line), line


# --------------------------------------------------------------------------
# backend site 2 — the model-vs-firms framing


def _framing() -> dict:
    from backend.routers.market import get_model_vs_firms
    return asyncio.run(get_model_vs_firms())


def test_the_public_framing_carries_the_disclaimer():
    out = _framing()
    assert out["framing"].endswith("Educational comparison, not advice.")
    assert out["personal_mode"] is False


def test_personal_mode_drops_the_framings_disclaimer_but_keeps_the_finding(
        monkeypatch):
    """The firms' dispersion IS the finding — it is the honest margin of error
    on any long-run forecast, and it stays in both builds."""
    from backend.routers import market as market_router
    monkeypatch.setattr(market_router._cfg, "PERSONAL_MODE", True)
    out = _framing()
    assert "not advice" not in out["framing"]
    assert "disagree with each other by several percentage points" in out["framing"]
    assert out["personal_mode"] is True


# --------------------------------------------------------------------------
# the health surface


def test_the_copilot_status_route_declares_the_build(monkeypatch):
    from backend.routers.copilot import copilot_status
    assert asyncio.run(copilot_status())["personal_mode"] is False
    monkeypatch.setattr(_config, "PERSONAL_MODE", True)
    out = asyncio.run(copilot_status())
    assert out["personal_mode"] is True
    assert "available" in out, "the flag rides along; it does not replace"


# --------------------------------------------------------------------------
# what personal mode must NOT touch


@pytest.mark.parametrize("path,needle", EXPORT_ARTEFACTS)
def test_the_export_artefacts_keep_their_disclaimer(path, needle):
    """A saved tearsheet and a shared brief can leave the machine that made
    them. Spec §5.2 leaves them to Murat, and calls it out rather than
    silently deciding it."""
    src = (REPO / path).read_text(encoding="utf-8")
    assert needle in src
    assert "PERSONAL_MODE" not in src, (
        f"{path} is an export artefact; personal mode does not reach it "
        f"until Murat says so")


# --------------------------------------------------------------------------
# the frontend: one helper, one env read


def test_the_helper_exists_and_reads_the_env_var_literally():
    src = (FRONTEND / "lib" / "personal-mode.ts").read_text(encoding="utf-8")
    body = code_only(src)
    assert "process.env.NEXT_PUBLIC_AEGIS_PERSONAL_MODE" in body, (
        "Next.js inlines a NEXT_PUBLIC_* read only for the full member "
        "expression; a computed key is `undefined` in the browser bundle")
    assert 'export function isPersonalMode' in body


def test_only_the_exact_string_one_turns_it_on():
    body = code_only((FRONTEND / "lib" / "personal-mode.ts").read_text(
        encoding="utf-8"))
    assert '=== "1"' in body, (
        "a truthiness test would make AEGIS_PERSONAL_MODE=0 turn it ON")


@pytest.mark.parametrize("rel", GATED_FRONTEND_FILES)
def test_every_gated_frontend_file_goes_through_the_one_helper(rel):
    body = code_only((FRONTEND / rel).read_text(encoding="utf-8"))
    assert 'from "@/lib/personal-mode"' in body, f"{rel} does not import the helper"
    assert "isPersonalMode(" in body, f"{rel} imports the helper and never calls it"


def test_no_gated_file_reads_the_env_var_a_second_way():
    """One spelling, in one file. A second `process.env` read is a second
    place for the build-time inlining rule to be got wrong."""
    for rel in GATED_FRONTEND_FILES:
        body = code_only((FRONTEND / rel).read_text(encoding="utf-8"))
        assert "NEXT_PUBLIC_AEGIS_PERSONAL_MODE" not in body, rel


def test_the_shared_banner_is_the_only_one_that_disappears_whole():
    """Every other surface keeps its model statement and drops only the
    advice sentence; the two banners that ARE disclaimers go whole."""
    body = code_only((FRONTEND / "components" / "methodology-banner.tsx")
                     .read_text(encoding="utf-8"))
    assert "Backtest, not the track record" in body
    assert "no skill claims before 24 months" in body
    body = code_only((FRONTEND / "components" / "disclaimer-banner.tsx")
                     .read_text(encoding="utf-8"))
    assert "return null" in body
