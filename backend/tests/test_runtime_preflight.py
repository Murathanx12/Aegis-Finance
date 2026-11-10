"""`scripts.runtime_preflight`: the per-task acceptance receipt for "the runtime is a commit".

The failures it encodes were all live on 2026-11-11: scheduled tasks imported an
untracked `provider_budget.py` (no commit held it), the checkout was 269 commits
behind main, and a clean clone pointed at the live data with `AEGIS_DATA_DIR`
alone still wrote through 77 modules' own `REPO/backend/data` paths into its
tracked copy. Every test builds a throwaway git repository under tmp_path; no
network, no real checkout is touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import runtime_preflight as RP


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "checkout"
    (r / "scripts").mkdir(parents=True)
    (r / "backend" / "services").mkdir(parents=True)
    (r / "backend" / "data" / "optimus").mkdir(parents=True)
    (r / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (r / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (r / "backend" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (r / "backend" / "services" / "budget.py").write_text("CAP = 1\n", encoding="utf-8")
    (r / "scripts" / "job.py").write_text(
        "from backend.services import budget\n"
        "def run():\n"
        "    from backend.services.budget import CAP  # an attribute, not a module\n"
        "    return CAP\n", encoding="utf-8")
    (r / "backend" / "data" / "optimus" / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
    _git(r.parent, "init", "-q", str(r))
    _git(r, "add", ".")
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return r


def _cfg(repo: Path, **kw) -> SimpleNamespace:
    base = dict(OPTIMUS_LEDGER_DIR=repo / "backend" / "data" / "optimus",
                DOTENV_PATH=repo / ".env",
                IC_FUNNEL_PATH=repo / "backend" / "data" / "funnel_night10.json")
    base.update(kw)
    return SimpleNamespace(**base)


def _check(rep: dict, name: str) -> dict:
    return next(r for r in rep["checks"] if r["check"] == name)


def _run(repo: Path, **kw) -> dict:
    args = dict(entries=["scripts.job"], expect_commit="HEAD",
                expect_optimus=repo / "backend" / "data" / "optimus", expect_funnel=None,
                cfg=_cfg(repo), environ={"AEGIS_IGNORE_DOTENV": "1"})
    args.update(kw)
    return RP.run_checks(repo, **args)


def test_a_clean_committed_checkout_passes(repo: Path) -> None:
    rep = _run(repo)
    assert rep["verdict"] == "PASS", rep
    assert _check(rep, "imports")["detail"]["n_modules"] >= 3


def test_an_untracked_module_on_the_import_path_fails_by_name(repo: Path) -> None:
    """The 10-15 `provider_budget.py` shape: the code runs, and no commit holds it."""
    (repo / "backend" / "services" / "shadow.py").write_text("X = 2\n", encoding="utf-8")
    (repo / "scripts" / "job.py").write_text(
        "from backend.services import budget, shadow\n", encoding="utf-8")
    _git(repo, "add", "scripts/job.py")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "import shadow")
    rep = _run(repo)
    imp = _check(rep, "imports")
    assert imp["status"] == "FAIL"
    assert imp["detail"]["untracked_modules"] == ["backend/services/shadow.py"]
    assert _check(rep, "code_clean")["status"] == "FAIL"   # the untracked file is code
    assert rep["verdict"] == "FAIL"


def test_a_module_that_does_not_exist_fails_as_missing(repo: Path) -> None:
    (repo / "scripts" / "job.py").write_text("from backend.services import earnings_deadline\n"
                                             "import backend.services.gone\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "gone")
    imp = _check(_run(repo), "imports")
    assert imp["status"] == "FAIL"
    assert "backend.services.gone" in imp["detail"]["missing"]
    # `from pkg import name` where name is neither a submodule nor bound in the package
    assert "backend.services.earnings_deadline" in imp["detail"]["missing"]


def test_modified_tracked_code_fails_but_data_does_not(repo: Path) -> None:
    (repo / "backend" / "data" / "optimus" / "ledger.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    (repo / "backend" / "data" / "optimus" / "new_receipt.json").write_text("{}", encoding="utf-8")
    assert _check(_run(repo), "code_clean")["status"] == "PASS"
    (repo / "backend" / "services" / "budget.py").write_text("CAP = 2\n", encoding="utf-8")
    cc = _check(_run(repo), "code_clean")
    assert cc["status"] == "FAIL" and cc["detail"]["n_dirty"] == 1


def test_the_wrong_commit_fails(repo: Path) -> None:
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "scripts" / "other.py").write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "second")
    assert _check(_run(repo, expect_commit=first), "commit")["status"] == "FAIL"
    assert _check(_run(repo, expect_commit="no-such-tag"), "commit")["status"] == "FAIL"
    _git(repo, "tag", "runtime-test")
    assert _check(_run(repo, expect_commit="runtime-test"), "commit")["status"] == "PASS"


def test_an_env_var_data_root_alone_is_a_split_brain(repo: Path, tmp_path: Path) -> None:
    """`AEGIS_DATA_DIR` moves config's paths; the checkout's own backend/data/optimus
    stays where it is, and 77 modules build that path themselves."""
    live = tmp_path / "live" / "optimus"
    live.mkdir(parents=True)
    rep = _run(repo, expect_optimus=live, cfg=_cfg(repo, OPTIMUS_LEDGER_DIR=live))
    dr = _check(rep, "data_root")
    assert dr["status"] == "FAIL"
    assert "SPLIT_BRAIN" in dr["detail"]["why"]


def test_config_pointing_elsewhere_fails(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    dr = _check(_run(repo, cfg=_cfg(repo, OPTIMUS_LEDGER_DIR=other)), "data_root")
    assert dr["status"] == "FAIL"


def test_a_missing_live_data_dir_fails(repo: Path, tmp_path: Path) -> None:
    dr = _check(_run(repo, expect_optimus=tmp_path / "absent"), "data_root")
    assert dr["status"] == "FAIL"
    assert dr["detail"]["expected_exists"] is False


def test_dotenv_must_exist_unless_ignored(repo: Path, tmp_path: Path) -> None:
    assert _check(_run(repo, environ={}), "dotenv")["status"] == "FAIL"
    assert _check(_run(repo), "dotenv")["status"] == "PASS"          # ignored
    keys = tmp_path / "keys.env"
    keys.write_text("A=1\n", encoding="utf-8")
    got = _check(_run(repo, environ={"AEGIS_DOTENV_PATH": str(keys)},
                      cfg=_cfg(repo, DOTENV_PATH=keys)), "dotenv")
    assert got["status"] == "PASS" and got["detail"]["declared_by"] == "AEGIS_DOTENV_PATH"
    assert "A=1" not in str(got), "the preflight must never carry .env contents"


def test_the_funnel_check_runs_only_when_declared(repo: Path, tmp_path: Path) -> None:
    rep = _run(repo)
    assert all(r["check"] != "funnel" for r in rep["checks"])
    shared = tmp_path / "funnel_night10.json"
    assert _check(_run(repo, expect_funnel=shared), "funnel")["status"] == "FAIL"
    assert _check(_run(repo, expect_funnel=shared, cfg=_cfg(repo, IC_FUNNEL_PATH=shared)),
                  "funnel")["status"] == "PASS"


def test_tracked_data_that_differs_is_a_warning_not_a_failure(repo: Path) -> None:
    (repo / "backend" / "data" / "optimus" / "ledger.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    rep = _run(repo)
    td = _check(rep, "tracked_data_through_junction")
    assert td["status"] == "WARN" and td["detail"]["n_tracked_differing"] == 1
    assert rep["verdict"] == "PASS" and rep["warned"] == ["tracked_data_through_junction"]


def test_main_exits_red_on_a_failure(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(RP, "REPO", repo)
    rc = RP.main(["--entry", "scripts.job", "--expect-commit", "no-such-tag",
                  "--expect-optimus", str(repo / "backend" / "data" / "optimus")])
    assert rc == 2
    assert "RUNTIME PREFLIGHT FAIL" in capsys.readouterr().err
