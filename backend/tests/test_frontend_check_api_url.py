"""Q18, 2026-10-07: the Vercel CLI's redaction placeholder, inlined.

The live site's console printed, on every page:
`[aegis] NEXT_PUBLIC_API_URL is not an absolute http(s) URL (got 11 chars
starting "[")`. `vercel env ls` showed the Project variable set to the real
Railway URL -- but `vercel pull` REDACTS a variable marked "Sensitive" to the
literal 11-character string "[SENSITIVE]", and because `NEXT_PUBLIC_*` is
inlined by webpack at build time, `vercel build` compiled that placeholder
straight into the browser bundle. The site stayed up only because
`frontend/src/lib/api.ts`'s `resolveApiBase` (C4, 2026-10-06) refused the bad
value and fell back to `PUBLIC_API_FALLBACK`.

These tests pin the GUARD's logic against a fixture bundle directory --
deterministic, offline, no real `next build` or `vercel build` -- and pin the
three places that must name the same host (the workflow's Build-step env var,
`PUBLIC_API_FALLBACK` in api.ts, and this guard's own `EXPECTED_API_HOST`/
`EXPECTED_API_URL`) so they cannot drift apart silently.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts import frontend_check as FC

REPO = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------- the pure guard

def test_placeholder_present_is_red_even_with_no_host(tmp_path: Path):
    _write(tmp_path / "chunks" / "a.js", 'const u="[SENSITIVE]";fetch(u+"/api/x")')
    _write(tmp_path / "chunks" / "b.js", 'console.log("unrelated")')
    r = FC.guard_bundle_for_redacted_api_url(tmp_path)
    assert r["ok"] is False and r["verdict"] == "RED"
    assert r["placeholder_hits"] == [str(Path("chunks") / "a.js")]
    assert r["host_found"] is False
    assert r["files_scanned"] == 2
    assert "[SENSITIVE]" in r["reason"]


def test_host_present_and_no_placeholder_is_green(tmp_path: Path):
    _write(tmp_path / "chunks" / "a.js",
           'fetch("https://aegis-finance-production.up.railway.app/api/x")')
    _write(tmp_path / "chunks" / "b.js", 'console.log("unrelated")')
    r = FC.guard_bundle_for_redacted_api_url(tmp_path)
    assert r["ok"] is True and r["verdict"] == "GREEN"
    assert r["placeholder_hits"] == []
    assert r["host_found"] is True


def test_host_present_but_placeholder_also_present_is_still_red(tmp_path: Path):
    """A stale chunk carrying the placeholder fails the whole bundle even if
    some other chunk has the right host -- a real build would never emit the
    env var two different ways, so seeing both means something is wrong."""
    _write(tmp_path / "a.js",
           'fetch("https://aegis-finance-production.up.railway.app/api/x")')
    _write(tmp_path / "b.js", 'const u="[SENSITIVE]"')
    r = FC.guard_bundle_for_redacted_api_url(tmp_path)
    assert r["ok"] is False and r["verdict"] == "RED"
    assert r["host_found"] is True
    assert r["placeholder_hits"] == ["b.js"]


def test_host_missing_entirely_is_red_not_cannot_determine(tmp_path: Path):
    _write(tmp_path / "a.js", 'console.log("no api url inlined at all")')
    r = FC.guard_bundle_for_redacted_api_url(tmp_path)
    assert r["ok"] is False and r["verdict"] == "RED"
    assert r["host_found"] is False
    assert "Railway host" in r["reason"]


def test_missing_directory_is_cannot_determine(tmp_path: Path):
    r = FC.guard_bundle_for_redacted_api_url(tmp_path / "does-not-exist")
    assert r["ok"] is None and r["verdict"] == "CANNOT DETERMINE"
    assert r["files_scanned"] == 0


def test_directory_with_no_js_files_is_cannot_determine(tmp_path: Path):
    _write(tmp_path / "style.css", "body{}")
    r = FC.guard_bundle_for_redacted_api_url(tmp_path)
    assert r["ok"] is None and r["verdict"] == "CANNOT DETERMINE"
    assert r["files_scanned"] == 0


# ------------------------------------------------------------------- the CLI

def test_cli_exits_nonzero_and_prints_hits_on_red(tmp_path: Path, capsys):
    _write(tmp_path / "a.js", 'const u="[SENSITIVE]"')
    rc = FC.main(["--guard-api-url-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "RED" in out
    assert "PLACEHOLDER FOUND: a.js" in out


def test_cli_exits_zero_on_green(tmp_path: Path, capsys):
    _write(tmp_path / "a.js",
           'fetch("https://aegis-finance-production.up.railway.app/api/x")')
    rc = FC.main(["--guard-api-url-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GREEN" in out


def test_guard_api_url_dir_skips_the_three_builds_entirely(tmp_path: Path, monkeypatch):
    """A caller passing --guard-api-url-dir must never trigger tsc/site/desktop --
    those cost minutes and need Node; the whole point is a fast, isolated check."""
    def boom(*a, **k):
        raise AssertionError("check() must not run when --guard-api-url-dir is given")
    monkeypatch.setattr(FC, "check", boom)
    _write(tmp_path / "a.js", "console.log('fine')")
    FC.main(["--guard-api-url-dir", str(tmp_path)])


# -------------------------------------------- the three literals must agree

def test_the_guard_constants_agree_with_each_other():
    assert FC.EXPECTED_API_URL == f"https://{FC.EXPECTED_API_HOST}"


def test_api_ts_fallback_matches_the_guards_expected_url():
    src = (REPO / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    m = re.search(r'PUBLIC_API_FALLBACK\s*=\s*"([^"]+)"', src)
    assert m, "PUBLIC_API_FALLBACK not found in frontend/src/lib/api.ts"
    assert m.group(1) == FC.EXPECTED_API_URL


def test_workflow_build_step_sets_the_same_url_explicitly():
    wf = (REPO / ".github" / "workflows" / "deploy-frontend-vercel.yml").read_text(encoding="utf-8")
    hits = re.findall(r"NEXT_PUBLIC_API_URL:\s*(\S+)", wf)
    assert hits, "deploy-frontend-vercel.yml no longer sets NEXT_PUBLIC_API_URL explicitly"
    assert all(h == FC.EXPECTED_API_URL for h in hits), hits


def test_workflow_has_the_post_build_guard_step_before_deploy():
    wf = (REPO / ".github" / "workflows" / "deploy-frontend-vercel.yml").read_text(encoding="utf-8")
    guard_idx = wf.index("guard-api-url-dir")
    build_idx = wf.index("vercel build --prod")
    deploy_idx = wf.index("vercel deploy --prebuilt")
    assert build_idx < guard_idx < deploy_idx, (
        "the guard must run after Build and before Deploy to production"
    )
