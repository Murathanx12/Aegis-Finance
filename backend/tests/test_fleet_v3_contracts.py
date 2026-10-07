"""C20 / D2: the six-role fleet as frozen v3 contracts, PREPARED and NOT SEEDED.

The load-bearing test is `test_no_seed_path_can_read_a_prepared_contract`: the
contracts live in a folder no seed path reads, the fleet manager's load and
freeze REFUSE a PREPARED body even when it is copied into the live folder, and
no module outside the preparer names the prepared folder.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend import config
from backend.services import fleet_manager as FM
from backend.services import fleet_v3_contracts as V3

REPO = Path(__file__).resolve().parents[2]

REF = {
    "asof": "2026-10-06",
    "universe_sigma": {"p50": 0.025, "p75": 0.0366, "p90": 0.0492, "n": 3057},
    "spy_sigma": 0.007, "spy_worst_day": -0.0586,
    "candidate_sigma": {"thematic": 0.0671, "revision_snowball": 0.0504, "innovation": 0.1353},
    "quant": {"rule": V3.QUANT_RULE, "boards": {"fair": ["f.jsonl"], "sticky": ["s.jsonl"]},
              "eligible": ["r1", "r2"], "n_eligible": 2, "n_pure_selection_t2_both_twins": 2,
              "capital_candidate_eligible": [], "today": "HOLD_ELIGIBLE"},
    "kill_prior": {"sd_daily": 0.0119, "n_rows": 29, "source": "test"},
    "innovation_pool": {"n": 47, "n_sigma_eligible": 30},
    "lineage": {r: {"account": V3.ACCOUNT[r], "v2_policy_hash": "x"} for r in V3.ROLES},
}

REQUIRED = ("policy_hash", "frozen_utc", "rule_hash", "inputs", "costs", "objective",
            "selection", "exits", "stop_rule", "caps", "worst_case", "twin", "kill_rule",
            "status", "owner_action_required", "licence", "personality", "account")


@pytest.fixture()
def frozen(tmp_path) -> dict:
    return {r: V3.freeze_prepared(b, tmp_path) for r, b in V3.build_bodies(REF).items()}


def test_six_roles_each_frozen_with_every_declared_field(frozen):
    assert set(frozen) == {"thematic", "revision_snowball", "world_news", "quant_ensemble",
                           "innovation", "spy_control"}
    for role, c in frozen.items():
        missing = [k for k in REQUIRED if k not in c]
        assert not missing, (role, missing)
        assert c["status"] == config.FLEET_V3_STATUS_PREPARED == "PREPARED_NOT_SEEDED"
        assert c["licence"] == "PRODUCT_EXPERIMENT"
        assert c["costs"]["assumed_bps_per_side"] > 0 and "fill_convention" in c["costs"]
        assert c["policy_hash"] == FM.policy_hash(c) and c["rule_hash"] == V3.rule_hash(c)
        sr = c["stop_rule"]
        assert sr["quoted_in"] == "daily sigma" and sr["k_sigma"] > 0
        assert all("stop_pct" in e and e["stop_in_sigma"] for e in sr["examples"]), role
        wc = c["worst_case"]
        assert wc["equity_usd"] == config.FLEET_V3_WORST_CASE_EQUITY == 100_000.0
        assert wc["k_sigma_day_usd_after_cap"] >= -config.FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC * 1e5 - 1e-6
        assert wc["no_stop_ceiling_usd"] == pytest.approx(-wc["gross_over_equity"] * 1e5)
        assert any("broker UI" in s or "assign an account" in s for s in c["owner_action_required"])
        assert any(config.FLEET_V3_EARLIEST_SEED in s for s in c["owner_action_required"])
        assert "selection" in c and "horizon_sessions" in c["selection"] or \
            c["selection"]["kind"] == "quant_ensemble_or_cash"


def test_role_specific_rules(frozen):
    inn = frozen["innovation"]
    assert inn["caps"]["max_name_frac"] == 0.02, "a HARD 2% per name ceiling"
    assert inn["caps"]["gap_exposed_name_frac"] <= 0.01
    assert inn["caps"]["thin_coverage_multiplier"] == 0.5
    # review M7: the gap is the headline and stays inside the lane's own 10% line
    wc = inn["worst_case"]
    assert wc["binary_gap_usd"] == pytest.approx(-14 * 0.01 * 0.70 * 1e5)
    assert -wc["binary_gap_usd"] <= config.FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC * 1e5
    assert wc["no_stop_ceiling_usd"] >= -0.10 / 0.70 * 1e5 - 1e-6
    assert "binary_gap" in wc["headline"]
    # review M7: the 3-sigma stop is never clipped into a sub-3-sigma stop
    smax = inn["caps"]["max_daily_sigma"]
    assert 3 * smax <= inn["stop_rule"]["max_frac"] + 1e-12
    ex = {e["at"]: e for e in inn["stop_rule"]["examples"]}
    assert all(e["stop_in_sigma"] >= 3 - 1e-9 for e in ex.values())
    assert inn["account"] == "UNASSIGNED"
    rev = frozen["revision_snowball"]
    assert not any("reputation" in json.dumps(i).lower() for i in rev["inputs"]), \
        "reputation weights are NOT_PERSISTENT_OOS and are not an input"
    assert "NOT_PERSISTENT_OOS" in json.dumps(rev["excluded_inputs"])
    q = frozen["quant_ensemble"]
    # review H3: the PRODUCT_EXPERIMENT trades the two-twin survivors; the market line
    # is the CAPITAL_CANDIDATE promotion gate, never the entry gate
    assert q["selection"]["today"] == "HOLD_ELIGIBLE"
    assert q["selection"]["eligible_at_prepare"] == ["r1", "r2"]
    assert "net_minus_market" not in q["selection"]["rule"]
    assert q["capital_candidate_gate"]["licence"] == "CAPITAL_CANDIDATE"
    assert "net_minus_market" in q["capital_candidate_gate"]["rule"]
    for role in ("thematic", "revision_snowball", "world_news", "quant_ensemble", "innovation"):
        k = frozen[role]["kill_rule"]
        assert "z_21" in k["kill_if"] and "<= -2" in k["kill_if"], role
        assert k["P_kill_if_zero_edge_per_check"] == pytest.approx(0.02275)
        assert k["P_kill_if_zero_edge_63_sessions_3_checks"] < 0.07
        assert "MECHANISM_REJECTED" in k["never"]
        assert k["prior_for_scale"]["illustrative_line_21"] == pytest.approx(
            -2 * 0.0119 * 21 ** 0.5)
    assert "why_not_sticky" in frozen["world_news"]["twin"]
    ctl = frozen["spy_control"]
    assert ctl["selection"]["symbol"] == "SPY" and ctl["kill_rule"].startswith("never killed")
    assert "trust" in frozen["world_news"]["selection"]["rule"]


def test_write_once_and_tamper_evident(tmp_path, frozen):
    body = V3.build_bodies(REF)["thematic"]
    assert V3.freeze_prepared(body, tmp_path)["policy_hash"] == frozen["thematic"]["policy_hash"]
    changed = dict(body, caps={**body["caps"], "max_name_frac": 0.2})
    with pytest.raises(V3.PreparedRefusal, match="new version"):
        V3.freeze_prepared(changed, tmp_path)
    p = V3.contract_path("thematic", tmp_path)
    c = json.loads(p.read_text(encoding="utf-8"))
    c["kill_rule"] = "never"
    p.write_text(json.dumps(c), encoding="utf-8")
    with pytest.raises(V3.PreparedRefusal, match="edited after freeze"):
        V3.load_prepared("thematic", tmp_path)
    with pytest.raises(V3.PreparedRefusal, match="only a"):
        V3.freeze_prepared(dict(body, status="LIVE"), tmp_path / "x")


def test_a_prepared_contract_can_be_superseded_and_the_old_one_is_kept(tmp_path, frozen):
    body = V3.build_bodies(REF)["innovation"]
    old_hash = frozen["innovation"]["policy_hash"]
    changed = dict(body, caps={**body["caps"], "max_names": 13})
    new = V3.freeze_prepared(changed, tmp_path, supersede=True)
    assert new["supersedes"] == [old_hash] and new["policy_hash"] != old_hash
    assert (tmp_path / "superseded" / f"innovation_v3_{old_hash}.json").exists()
    assert V3.load_prepared("innovation", tmp_path)["policy_hash"] == new["policy_hash"]
    # idempotent: the same body again returns the superseding contract unchanged
    assert V3.freeze_prepared(changed, tmp_path, supersede=True)["policy_hash"] == new["policy_hash"]


def test_activation_may_change_only_the_status_fields(frozen):
    prep = frozen["world_news"]
    act = dict(prep, status="ACTIVE", owner_action_required=[], seed={"t": "later"})
    assert V3.activation_diff(prep, act) == {"same_rule": True, "changed_rule_fields": []}
    sneaky = dict(act, caps={**prep["caps"], "max_gross_frac": 1.0})
    d = V3.activation_diff(prep, sneaky)
    assert d["same_rule"] is False and d["changed_rule_fields"] == ["caps"]


def test_no_seed_path_can_read_a_prepared_contract(tmp_path, frozen):
    live = tmp_path / "fm"
    # 1. the fleet manager looks only in contracts/, where no v3 exists
    with pytest.raises(FM.FleetRefusal, match="no frozen contract"):
        FM.load_contract("hack1", "v3", live)
    # 2. a hand copy of a PREPARED body into the live folder is refused on load
    src = V3.contract_path("thematic", tmp_path)
    dst = FM.contract_file("hack1", "v3", live)
    dst.parent.mkdir(parents=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    c = json.loads(dst.read_text(encoding="utf-8"))
    assert FM.policy_hash(c) == c["policy_hash"], "the copy is intact; only the status refuses"
    with pytest.raises(FM.FleetRefusal, match="PREPARED_NOT_SEEDED"):
        FM.load_contract("hack1", "v3", live)
    # 3. freezing a PREPARED body through the fleet manager is refused
    body = {k: v for k, v in frozen["spy_control"].items() if k not in ("policy_hash", "frozen_utc")}
    body["role"], body["version"] = "hack5", "v3"
    with pytest.raises(FM.FleetRefusal, match="PREPARED_NOT_SEEDED"):
        FM.freeze_contract(body, tmp_path / "fm2")
    # 4. nothing outside the preparer names the prepared folder (AST, docstrings skipped)
    allowed = {"backend/config.py", "backend/services/fleet_v3_contracts.py",
               "scripts/fleet_v3_prepare.py"}
    offenders = []
    for root in ("backend", "scripts"):
        for f in (REPO / root).rglob("*.py"):
            rel = f.relative_to(REPO).as_posix()
            if rel in allowed or "/tests/" in rel or "__pycache__" in rel:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8-sig"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            docs = {id(n.body[0].value) for n in ast.walk(tree)
                    if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and n.body and isinstance(n.body[0], ast.Expr)
                    and isinstance(n.body[0].value, ast.Constant)}
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                        and "contracts_v3" in n.value:
                    offenders.append(rel)
                if isinstance(n, (ast.Name, ast.Attribute)) and \
                        getattr(n, "attr", getattr(n, "id", None)) == "FLEET_V3_CONTRACTS_DIR":
                    offenders.append(rel)
    assert not offenders, sorted(set(offenders))


def test_the_live_runner_resolves_only_v1_and_v2():
    """Pinned so the owner trap stays visible: modes.json contract='v3' would
    fall back to v1 terms until the runner is taught a v3 path."""
    src = (REPO / "scripts" / "fleet_manager_run.py").read_text(encoding="utf-8")
    assert 'contract = c2 if (active == "v2" and c2) else c1' in src


def _board(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def _row(rule: str, ps: float, nmm: float) -> dict:
    return {"rule": rule, "status": "OK", "pure_selection": {"full": {"t_blocks": ps}},
            "net_minus_market": {"validate": {"t_blocks": nmm}}}


def test_quant_entry_needs_both_twins_and_the_market_line_only_promotes(tmp_path):
    ft = _board(tmp_path / "f.jsonl", [_row("a", 2.5, 0), _row("b", 2.5, 0), _row("c", 1.0, 0)])
    st = _board(tmp_path / "s.jsonl", [_row("a", 2.1, 2.4), _row("b", 2.2, 1.0), _row("c", 3.0, 3.0)])
    q = V3.quant_eligibility([ft], [st])
    assert q["pure_selection_t2_both_twins"] == ["a", "b"]
    assert q["eligible"] == ["a", "b"] and q["today"] == "HOLD_ELIGIBLE"
    assert q["capital_candidate_eligible"] == ["a"], "the market line is the promotion gate"
    st2 = _board(tmp_path / "s2.jsonl", [_row("a", 1.9, 3.0)])
    assert V3.quant_eligibility([ft], [st2])["today"] == "HOLD_CASH"
    with pytest.raises(V3.PreparedRefusal):
        V3.quant_eligibility([tmp_path / "missing.jsonl"], [st])


def test_archive_copies_never_moves(tmp_path):
    base = tmp_path / "fm"
    (base / "state").mkdir(parents=True)
    (base / "state" / "hack1.json").write_text('{"a": 1}', encoding="utf-8")
    (base / "decisions.jsonl").write_text('{"d": 1}\n', encoding="utf-8")
    res = V3.archive_snapshot(tmp_path / "arch", base)
    assert res["n_files"] == 2
    assert (base / "state" / "hack1.json").exists() and (base / "decisions.jsonl").exists()
    man = json.loads((Path(res["dest"]) / "MANIFEST.json").read_text(encoding="utf-8"))
    assert {m["path"] for m in man["files"] if "sha256" in m} == {"state/hack1.json",
                                                                  "decisions.jsonl"}


def test_the_frozen_repo_contracts_verify_when_present():
    d = Path(config.FLEET_V3_CONTRACTS_DIR)
    present = [r for r in V3.ROLES if V3.contract_path(r).exists()]
    if not present:
        pytest.skip(f"no prepared v3 contracts under {d.name}")
    for r in present:
        c = V3.load_prepared(r)
        assert c["status"] == config.FLEET_V3_STATUS_PREPARED
