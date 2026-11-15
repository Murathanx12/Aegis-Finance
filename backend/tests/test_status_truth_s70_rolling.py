"""S70: a None code_version is flagged on the rolling-cohort run row (fixtures shared with test_rolling_cohorts)."""
from backend.services.portfolio_intelligence import branch_population_rolling as R
from backend.tests.test_rolling_cohorts import (ANCHOR_I, DAYS, cfg, make_root, run,  # noqa: F401
                                                subset_specs, utc)


def test_a_none_code_version_is_flagged_on_the_run_row(tmp_path, monkeypatch):
    root, out, specs = make_root(tmp_path, ANCHOR_I + 1), tmp_path / "out", subset_specs(tmp_path)
    monkeypatch.setattr(R, "_CODE_VERSION", {"v": None})            # git unavailable, cached as None
    row = run("step", root, out, specs, utc(DAYS[ANCHOR_I]))
    assert row["code_version_warning"]
    monkeypatch.setattr(R, "_CODE_VERSION", {"v": "a" * 40})
    row2 = run("step", root, out, specs, utc(DAYS[ANCHOR_I + 1]))
    assert "code_version_warning" not in row2
