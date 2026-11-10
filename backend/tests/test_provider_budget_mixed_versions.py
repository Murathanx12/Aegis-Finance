"""Old-code and new-code processes share ONE monthly DeepSeek envelope (review #88 R1).

The runtime checkout imports the 2026-10-15 `provider_budget.py` (a byte copy is
in `fixtures/provider_budget_legacy/`); it reads and writes only
`session_budget/deepseek_local.json` and checks `opening + sum(calls) <= cap`.
When this PR's code kept its own month file, the two versions each had a full
cap for the same month. These tests run both versions against one host
directory, interleaved in one process and concurrently in two, and assert that
the month's total held never exceeds the cap.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend import config as C
from backend.services import provider_budget as PB

ROOT = Path(__file__).resolve().parents[2]
LEGACY_SRC = (Path(__file__).parent / "fixtures" / "provider_budget_legacy"
              / "provider_budget_runtime_20261015.py")
REL = Path("aegis-finance/backend/data/optimus/session_budget")


def _load_legacy():
    spec = importlib.util.spec_from_file_location("provider_budget_runtime_20261015", LEGACY_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def host(monkeypatch, tmp_path):
    """Both versions resolve the same host directory under a tmp HOME."""
    monkeypatch.delenv("AEGIS_DEEPSEEK_BUDGET_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    d = tmp_path / REL
    monkeypatch.setattr(PB, "_default_dir", lambda: d)
    return d


def _reserve(mod):
    return mod.reserve("system", "user", 100, model="deepseek-chat",
                       base_url="https://api.deepseek.com", purpose="mixed-version fixture")


def _all_envelope_held(d: Path) -> int:
    """Units held across EVERY envelope file in the host dir (any version, any name)."""
    total = 0
    for f in d.glob("deepseek_local*.json"):
        s = json.loads(f.read_text(encoding="utf-8"))
        total += s["opening_units"] + sum(r["held_units"] for r in s["calls"].values())
    return total


def test_interleaved_old_and_new_code_share_one_cap(host, monkeypatch):
    legacy = _load_legacy()
    cap = 0.01                                   # ~23 reservations of ~$0.00043
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", cap)
    # the real order: the runtime's file was made by an attended initialize (11-10)
    legacy.initialize("od2-monthly-fixture", cap, opening_charge_usd=0,
                      opening_evidence="fixture: nothing spent yet")
    assert legacy.path() == host / "deepseek_local.json"
    n_old = n_new = 0
    old_open = new_open = True
    while old_open or new_open:
        if old_open:
            try:
                _reserve(legacy)
                n_old += 1
            except legacy.BudgetRefused:
                old_open = False
        if new_open:
            try:
                _reserve(PB)
                n_new += 1
            except PB.BudgetRefused:
                new_open = False
    assert n_old > 0 and n_new > 0
    assert _all_envelope_held(host) <= PB._units(cap)
    assert sorted(f.name for f in host.glob("deepseek_local*.json")) == ["deepseek_local.json"]


def test_old_code_spend_after_new_code_started_is_counted_by_new_code(host, monkeypatch):
    legacy = _load_legacy()
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 0.01)
    _reserve(PB)                                 # new code first: creates the envelope
    before = PB.snapshot()["held_usd"]
    t = _reserve(legacy)                         # old code spends afterwards
    assert PB.snapshot()["held_usd"] == pytest.approx(before + t["reserved_usd"])


def test_a_runtime_created_envelope_is_used_not_shadowed(host, monkeypatch):
    """The runtime's 2026-11-10 file (attended initialize, $15) is THE month envelope."""
    legacy = _load_legacy()
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 15.0)
    legacy.initialize("od2-monthly-fixture", 15, opening_charge_usd=0.63,
                      opening_evidence="fixture opening debit")
    s = PB.snapshot()
    assert s["held_usd"] == pytest.approx(0.63)
    _reserve(PB)
    raw = json.loads((host / "deepseek_local.json").read_text(encoding="utf-8"))
    assert len(raw["calls"]) == 1 and raw["session_id"] == "od2-monthly-fixture"
    legacy._load(host / "deepseek_local.json")   # the old reader still accepts the file


_WORKER = r"""
import importlib.util, json, sys, time
from pathlib import Path
which, start, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
if which == "old":
    spec = importlib.util.spec_from_file_location("legacy_pb", sys.argv[4])
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
else:
    from backend.services import provider_budget as mod
while not start.exists():
    time.sleep(0.01)
n = 0
while True:
    try:
        mod.reserve("system", "user", 100, model="deepseek-chat",
                    base_url="https://api.deepseek.com", purpose="concurrent " + which)
        n += 1
    except mod.BudgetRefused as exc:
        if "unreadable" in str(exc) or "UNREADABLE" in str(exc):
            raise
        break
    except Exception as exc:      # lock timeout etc.: report, never swallow
        out.write_text(json.dumps({"n": n, "error": type(exc).__name__ + ": " + str(exc)}))
        raise SystemExit(3)
    time.sleep(0.002)
out.write_text(json.dumps({"n": n}))
"""


def test_two_concurrent_processes_old_and_new_never_exceed_the_cap(host, tmp_path):
    env = {**os.environ, "USERPROFILE": str(tmp_path), "HOME": str(tmp_path),
           "AEGIS_IGNORE_DOTENV": "1", "AEGIS_PERSONAL_MODE": "0",
           "AEGIS_DEEPSEEK_MONTHLY_CAP_USD": "0.01", "PYTHONPATH": str(ROOT)}
    env.pop("AEGIS_DEEPSEEK_BUDGET_PATH", None)
    init = subprocess.run([sys.executable, "-m", "backend.services.provider_budget", "init"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert init.returncode == 0, init.stdout + init.stderr
    assert (host / "deepseek_local.json").exists()
    worker = tmp_path / "worker.py"
    worker.write_text(_WORKER, encoding="utf-8")
    start = tmp_path / "GO"
    procs = []
    for which in ("old", "new"):
        out = tmp_path / f"{which}.json"
        procs.append((which, out, subprocess.Popen(
            [sys.executable, str(worker), which, str(start), str(out), str(LEGACY_SRC)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))
    time.sleep(1.0)                              # both imported and waiting
    start.write_text("go", encoding="utf-8")
    counts = {}
    for which, out, p in procs:
        so, se = p.communicate(timeout=120)
        assert p.returncode == 0, (which, so, se)
        counts[which] = json.loads(out.read_text(encoding="utf-8"))["n"]
    assert counts["old"] > 0 and counts["new"] > 0, counts
    assert _all_envelope_held(host) <= PB._units(0.01), counts
