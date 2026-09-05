"""The frozen `nn_pre_causal` shadow: is it actually frozen, and is it actually zero-capital?

Three failures this file exists to make impossible:

1. **A freeze that isn't.** The contract snapshots `learner.neural_long`'s
   hyperparameters BY VALUE. If a later session edits that module, the contract
   file on disk is untouched and byte-identical while the recipe it names has
   changed. `verify_contract` must catch that, and the test proves it by moving
   a constant.
2. **A shadow that can spend.** SHADOW means zero capital. The registry
   validator must REFUSE a SHADOW row with `allowed_in_pm: true`, and it must
   refuse one with no `first_grade_date` and one with no `contract_sha256`.
   A rule enforced only by the YAML being written correctly is not enforced.
3. **A silent night.** The mandate is "receipt every night even when empty".
   The nightly builder must return a dict and write a file on a night with no
   book, no month and nothing to say — and it must NOT raise.

`ALL PASS` printed under a `__main__` guard is not a test run
([[reference-a-test-below-a-main-guard-never-runs]]); everything here is a
pytest function.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import signal_registry as SR      # noqa: E402
from learner import shadow_nn as SN                     # noqa: E402

REGISTRY_YAML = REPO / "backend" / "data" / "signal_registry.yaml"


# ───────────────────────────── the contract is frozen ─────────────────────────

def test_contract_file_exists_and_hashes_to_its_own_body():
    c = SN.load_contract()
    assert c["contract_id"] == SN.CONTRACT_ID
    assert c["sha256"] == SN.contract_sha256(c), (
        "the contract's stored hash does not match a re-hash of its body — it "
        "has been edited in place, which is how a forward record silently "
        "becomes a record of a different experiment")


def test_contract_carries_the_pre_declared_rule_hash():
    c = SN.load_contract()
    assert c["decision_rule_sha256"] == SN.DECISION_RULE_SHA256
    assert c["decision_rule_sha256"].startswith("428a7148"), (
        "the freeze is only meaningful because the rule was hashed BEFORE the "
        "first fit; if this hash moves, the ex-ante claim is gone")


def test_contract_freezes_all_eight_seeds_and_forbids_seed_selection():
    c = SN.load_contract()
    assert c["seeds"] == [20260906, 20260907, 20260908, 20260909,
                          20260910, 20260911, 20260912, 20260913]
    assert len(c["seeds"]) == len(set(c["seeds"])) == 8
    assert "FORBIDDEN" in c["seed_selection"]


def test_contract_declares_the_floored_training_universe():
    tu = SN.load_contract()["training_universe"]
    assert tu["dollar_volume_floor_usd_per_day"] == 3_000_000.0
    assert tu["min_close_usd"] == 5.0
    assert "TRAINING" in tu["applied_to"], (
        "the whole point of W3b was that the floor was applied to the TRAINING "
        "universe as well as the graded book")


def test_canonical_json_is_stable_under_key_order():
    a = {"b": 1, "a": {"d": 2, "c": 3}}
    b = {"a": {"c": 3, "d": 2}, "b": 1}
    assert SN.canonical_json(a) == SN.canonical_json(b)


def test_hash_ignores_the_stored_sha_field():
    c = SN.build_contract()
    h = SN.contract_sha256(c)
    c["sha256"] = h
    assert SN.contract_sha256(c) == h, (
        "a hash that changes when the hash is stored beside the body can never "
        "be verified")


def test_verify_contract_is_green_on_the_shipped_contract():
    v = SN.verify_contract()
    assert v["ok"] is True, v["drift"]
    assert v["checks"]["hash_matches_body"] is True
    assert v["checks"]["hyperparameters_unchanged"] is True


def test_verify_contract_goes_RED_when_the_module_drifts(monkeypatch):
    """PROVED RED. A gate that cannot go red is decorative.

    The contract file is untouched here — only `learner.neural_long`'s live
    constant moves. That is exactly the failure a file-hash check alone cannot
    see, and it is why `verify_contract` compares values and not just bytes.
    """
    from learner import neural_long as N
    monkeypatch.setattr(N, "DROPOUT", float(N.DROPOUT) + 0.05, raising=True)
    v = SN.verify_contract()
    assert v["ok"] is False
    assert v["checks"]["hyperparameters_unchanged"] is False
    assert "dropout" in v.get("hyperparameter_drift", {})
    assert any("neural_long" in d for d in v["drift"])


def test_freeze_refuses_to_overwrite_a_different_contract(tmp_path, monkeypatch):
    other = tmp_path / "contract.json"
    other.write_text(json.dumps({"contract_id": SN.CONTRACT_ID,
                                 "sha256": "0" * 64}), encoding="utf-8")
    monkeypatch.setattr(SN, "CONTRACT_PATH", other)
    monkeypatch.setattr(SN, "CONTRACT_DIR", tmp_path)
    with pytest.raises(SystemExit) as exc:
        SN.freeze()
    assert "REFUSED" in str(exc.value)


# ───────────────────────── the nightly receipt is never silent ────────────────

def test_nightly_receipt_is_written_on_an_empty_night(tmp_path, monkeypatch):
    monkeypatch.setattr(SN, "RECEIPT_DIR", tmp_path / "nn_shadow")
    monkeypatch.setattr(SN, "BOOK_DIR", tmp_path / "nn_shadow" / "books")
    rec = SN.build_nn_shadow_receipt(day="2026-09-05")
    assert rec["status"] == "PENDING_ARTEFACT"
    assert rec["books_to_date"] == 0
    assert rec["reasons"] and rec["how_to_produce_one"]
    path = SN.write_nn_shadow_receipt(rec)
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "PENDING_ARTEFACT"


def test_nightly_receipt_says_NO_NEW_MONTH_when_the_book_is_stale(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir(parents=True)
    (books / "nn_pre_causal_book_2026-08.json").write_text(
        json.dumps({"month": "2026-08", "k": 50, "weight": "vw",
                    "holdings": [{"permno": 1}]}), encoding="utf-8")
    monkeypatch.setattr(SN, "BOOK_DIR", books)
    monkeypatch.setattr(SN, "RECEIPT_DIR", tmp_path)
    rec = SN.build_nn_shadow_receipt(day="2026-09-05")
    assert rec["status"] == "NO_NEW_MONTH"
    assert rec["latest_book"]["month"] == "2026-08"
    assert rec["books_to_date"] == 1


def test_nightly_receipt_says_OK_on_the_month_the_book_covers(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir(parents=True)
    (books / "nn_pre_causal_book_2026-09.json").write_text(
        json.dumps({"month": "2026-09", "k": 50, "weight": "vw",
                    "holdings": [{"permno": 1}, {"permno": 2}]}), encoding="utf-8")
    monkeypatch.setattr(SN, "BOOK_DIR", books)
    monkeypatch.setattr(SN, "RECEIPT_DIR", tmp_path)
    rec = SN.build_nn_shadow_receipt(day="2026-09-30")
    assert rec["status"] == "OK"
    assert len(rec["holdings"]) == 2


def test_nightly_receipt_REFUSES_rather_than_grading_a_drifted_contract(monkeypatch):
    monkeypatch.setattr(SN, "verify_contract",
                        lambda: {"ok": False, "drift": ["planted drift"],
                                 "checks": {}, "stored_sha256": None})
    rec = SN.build_nn_shadow_receipt(day="2026-09-05")
    assert rec["status"] == "REFUSED"
    assert rec["reasons"] == ["planted drift"]


# ───────────────────────────── zero capital, enforced ─────────────────────────

def test_the_registry_row_exists_and_is_SHADOW_at_zero_capital():
    s = SR.load().get(SN.SIGNAL_ID)
    assert s.evidence_grade == "SHADOW"
    assert s.allowed_in_pm is False, "SHADOW means ZERO CAPITAL"
    assert s.usable_now is False
    assert s.queued is True, "a shadow is alive and not permitted — not a corpse"
    assert str(s.first_grade_date) == SN.FIRST_GRADE_DATE
    assert s.reliability_weight is None
    assert s.weight == SR.UNCALIBRATED, "uncalibrated is UNKNOWN, never 1.0"


def test_the_registry_row_pins_the_contract_hash_on_disk():
    s = SR.load().get(SN.SIGNAL_ID)
    c = SN.load_contract()
    assert s.contract_sha256 == c["sha256"], (
        "the registry names a contract hash that is not the contract on disk — "
        "the row and the experiment have come apart")
    assert (REPO / s.contract_path).exists()


def _row(**over) -> dict:
    base = {"signal_id": "planted_shadow", "evidence_grade": "SHADOW",
            "permitted_role": "PICKER", "allowed_in_pm": False,
            "first_grade_date": "2026-09-05", "contract_sha256": "a" * 64,
            "receipts": ["r"]}
    base.update(over)
    return base


def _load_planted(tmp_path, row) -> None:
    p = tmp_path / "signal_registry.yaml"
    p.write_text(yaml.safe_dump({"schema": "signal-registry-v1",
                                 "written": "2026-09-05", "signals": [row]}),
                 encoding="utf-8")
    SR.load.cache_clear()
    try:
        SR.load(str(p))
    finally:
        SR.load.cache_clear()


def test_registry_accepts_a_well_formed_shadow(tmp_path):
    _load_planted(tmp_path, _row())          # must not raise


@pytest.mark.parametrize("over,fragment", [
    ({"allowed_in_pm": True}, "ZERO CAPITAL"),
    ({"first_grade_date": None}, "first_grade_date"),
    ({"contract_sha256": None}, "contract_sha256"),
])
def test_registry_REFUSES_a_shadow_that_is_not_one(tmp_path, over, fragment):
    """PROVED RED, three ways. Each of these was a real way to write the row."""
    with pytest.raises(SR.RegistryError) as exc:
        _load_planted(tmp_path, _row(**over))
    assert fragment in str(exc.value)


def test_shadow_grade_is_not_in_NEVER_PICKS():
    """A shadow is alive. Grouping it with REJECTED/PERVERSE would make the
    graduation queue and the graveyard the same list — the distinction the
    registry's docstring says it exists to preserve."""
    assert SR.SHADOW_GRADE not in SR.NEVER_PICKS
    assert SR.SHADOW_GRADE in SR.GRADES


# ─────────────────────── the shadow cannot reach an order path ────────────────

def test_shadow_nn_imports_nothing_that_can_place_an_order():
    """The scan is over IMPORTS, not prose.

    The module's own docstring says the words "alpaca" and "execution repo"
    while promising it touches neither, so a substring scan over the whole file
    fails on the sentence that states the guarantee. What matters is what is
    imported.
    """
    import ast
    src = (REPO / "learner" / "shadow_nn.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"alpaca", "alpaca_trade_api", "requests", "httpx", "urllib",
                 "aiohttp", "socket"}
    assert not (imported & forbidden), (
        f"learner/shadow_nn.py imports {sorted(imported & forbidden)}; a "
        f"zero-capital shadow has no business anywhere near a network or an "
        f"order path")
    assert imported <= {"__future__", "hashlib", "json", "sys", "datetime",
                        "pathlib", "typing", "learner"}, sorted(imported)


def test_the_yaml_row_is_syntactically_a_shadow_row():
    raw = yaml.safe_load(REGISTRY_YAML.read_text(encoding="utf-8"))
    rows = [r for r in raw["signals"] if r.get("signal_id") == SN.SIGNAL_ID]
    assert len(rows) == 1, "the shadow is registered exactly once"
    r = rows[0]
    assert r["evidence_grade"] == "SHADOW"
    assert r["allowed_in_pm"] is False
    assert str(r["first_grade_date"]) == SN.FIRST_GRADE_DATE
    assert r["reliability_weight"] is None
