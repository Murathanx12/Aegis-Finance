"""Every LLM chat call site is either guarded, declared uncapped, or not DeepSeek.

Review #88 R2 (2026-11-11): the "$15/month" envelope binds only the calls that
go through `provider_budget.attempt()` -- `llm_analyzer`'s DeepSeek path. Other
modules call DeepSeek directly. Routing them is not a one-line change (tools,
multi-turn messages, `response_format`, raw HTTP), so they are DECLARED in
`provider_budget.UNCAPPED_DEEPSEEK_PATHS` and named on the status line. This
test fails when a NEW chat call site appears anywhere, or an existing file gains
one, until it is routed through `attempt()` or declared here on purpose.

A call site is a `<x>.chat.completions.create(...)` call, or a string constant
containing `chat/completions` (raw HTTP). Docstrings are skipped (CLAUDE.md
protocol item 10: a guard must not match the text that explains it).
"""
from __future__ import annotations

import ast
from pathlib import Path

from backend.services import provider_budget as PB

ROOT = Path(__file__).resolve().parents[2]
SCAN = ("backend", "scripts", "learner", "engine", "lab", "nn_lab", "ft_lab", "tools", "sdk",
        "desktop")

#: The guarded file: its DeepSeek create goes through `attempt()` on the PC
#: (`_budgeted_deepseek_create`); the others are the cloud branch of that same
#: function (no host envelope off Windows, by design), NVIDIA, and local.
GUARDED = {"backend/services/llm_analyzer.py": 4}

#: Chat call sites that never reach DeepSeek (local servers on 127.0.0.1).
NOT_DEEPSEEK = {
    "backend/services/beta_v1_news_runtime.py": 1,     # 127.0.0.1 passive local route
    "scripts/night_l4_qwen3_measure.py": 1,            # local qwen3 server
    "scripts/fiction_backtest.py": 1,                  # llm_analyzer._get_local_client()
}


def _docstring_ids(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def call_sites(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError):
        return 0
    docs = _docstring_ids(tree)
    n = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create" and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "completions"):
            n += 1
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and "chat/completions" in node.value and id(node) not in docs):
            n += 1
        elif isinstance(node, ast.JoinedStr) and any(
                isinstance(v, ast.Constant) and isinstance(v.value, str)
                and "chat/completions" in v.value for v in node.values):
            n += 1
    return n


def _scan() -> dict[str, int]:
    found = {}
    for top in SCAN:
        if not (ROOT / top).is_dir():
            continue
        for p in (ROOT / top).rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if ("/tests/" in f"/{rel}" or "__pycache__" in rel or "node_modules" in rel
                    or rel.startswith("backend/tests/")):
                continue
            n = call_sites(p)
            if n:
                found[rel] = n
    return found


#: Pinned site counts for the declared-uncapped files (count grows => red).
UNCAPPED_COUNTS = {
    "backend/services/architecture_arena.py": 1,
    "backend/services/copilot.py": 2,
    "backend/services/leakage_probe.py": 1,
    "backend/services/llm_research.py": 1,
    "backend/services/llm_swarm.py": 1,
    "backend/services/model_provider.py": 1,
    "backend/services/optimus_specialists.py": 1,
    "backend/services/why_moved.py": 1,
    "scripts/book_factory.py": 3,                  # incl. one local-server site
    "scripts/companyworld_extract.py": 1,
    "scripts/connection_check.py": 7,              # incl. HF/OpenAI probes
    "scripts/era_replay_v2.py": 2,
    "scripts/n6b_fantasy_exams_round2.py": 1,
    "scripts/recall_canary_positive_control.py": 1,
    "scripts/stack_health.py": 4,                  # incl. local-server probes
}


def test_no_unclassified_chat_call_site():
    found = _scan()
    declared = {**GUARDED, **NOT_DEEPSEEK, **UNCAPPED_COUNTS}
    new = {f: n for f, n in found.items() if f not in declared}
    grew = {f: (declared[f], n) for f, n in found.items() if f in declared and n > declared[f]}
    assert not new and not grew, (
        "new LLM chat call site(s) outside provider_budget.attempt(): route them through "
        f"attempt() or declare them in UNCAPPED_DEEPSEEK_PATHS. new={new} grew={grew}")


def test_uncapped_declaration_matches_the_module_constant():
    assert set(PB.UNCAPPED_DEEPSEEK_PATHS) == set(UNCAPPED_COUNTS)


def test_the_scanner_skips_docstrings_and_sees_raw_http(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""explains chat/completions and cli.chat.completions.create()"""\n'
                 'def g():\n    """also chat/completions"""\n    return 1\n', encoding="utf-8")
    assert call_sites(f) == 0
    f.write_text('import requests\nrequests.post("https://api.deepseek.com/chat/completions")\n'
                 'cli.chat.completions.create(model="m")\n', encoding="utf-8")
    assert call_sites(f) == 2
