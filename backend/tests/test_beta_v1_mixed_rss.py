"""Real Windows ordered probes, without altering shared ctypes signatures."""
import os
import subprocess
import sys
from pathlib import Path
import pytest


def test_projection_real_production_memory_cap_refuses_before_read(tmp_path, monkeypatch):
    from backend.services import beta_v1_replay as replay, beta_v1_decision_projection as projection
    source = tmp_path/"synthetic.jsonl"
    source.write_bytes(b"{}\n")
    monkeypatch.setattr(replay, "_rss_bytes", lambda: 256*1024*1024+1)
    import hashlib
    with pytest.raises(replay.ReplayLimitExceeded) as refused:
        projection.project_file(source, expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            cutoff="2026-10-11T00:00:00Z")
    assert refused.value.report["resource"] == "rss_bytes"
    assert refused.value.report["limit"] == 256*1024*1024


def test_rss_probe_unavailable_is_not_zero(monkeypatch):
    from backend.services import beta_v1_replay as replay
    def unavailable():
        raise RuntimeError("RSS monitor unavailable")
    monkeypatch.setattr(replay, "_rss_bytes", unavailable)
    with pytest.raises(RuntimeError, match="unavailable"):
        replay.RunBudget().check("fixture")


@pytest.mark.parametrize("rss", [0, -1, True, None, 1.0, float("nan"), float("inf")])
def test_invalid_rss_refuses_before_any_decision_source_read(tmp_path, monkeypatch, rss):
    from backend.services import beta_v1_replay as replay, beta_v1_decision_projection as projection
    monkeypatch.setattr(replay, "_rss_bytes", lambda: rss)
    reads = []
    monkeypatch.setattr(projection, "_hash", lambda path: reads.append(path))
    with pytest.raises(RuntimeError, match="RSS monitor invalid"):
        projection.project_file(tmp_path/"never-opened.jsonl", expected_sha256="a"*64,
            cutoff="2026-10-11T00:00:00Z")
    assert reads == []


def test_measured_resource_fields_cannot_be_overridden(monkeypatch):
    from backend.services import beta_v1_replay as replay
    monkeypatch.setattr(replay, "_rss_bytes", lambda: 32*1024*1024)
    with pytest.raises(ValueError, match="cannot be overridden"):
        replay.RunBudget().check("fixture", rss_bytes=0)


@pytest.mark.skipif(os.name != "nt", reason="Windows DLL interaction")
def test_legacy_beta_legacy_real_owned_child(tmp_path):
    # Select only the old RSS function AST: importing its CLI may load unrelated
    # analysis libraries. The exact function body runs against the real OS.
    source = Path(__file__).resolve().parents[2]/"scripts/survivorship_audit_bounded.py"
    script = tmp_path/"owned_rss_probe.py"
    script.write_text('''import ast, ctypes, json, os, sys
from pathlib import Path
source = Path(sys.argv[1])
tree = ast.parse(source.read_text(encoding="utf-8"))
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "peak_rss_bytes")
ns = dict(os=os, sys=sys, ctypes=ctypes)
exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), ns)
from backend.services.beta_v1_replay import _rss_bytes
values=[]
for _ in range(3):
    values += [ns["peak_rss_bytes"](), _rss_bytes(), ns["peak_rss_bytes"]()]
assert all(isinstance(v, int) and 0 < v < 256*1024*1024 for v in values), values
print(json.dumps({"finite_positive_probes":len(values)}))
''', encoding="utf-8")
    root = source.parent.parent
    env = dict(os.environ, PYTHONPATH=str(root)); env.pop("AEGIS_PERSONAL_MODE", None)
    result = subprocess.run([sys.executable, str(script), str(source)], cwd=root,
        env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
    assert '"finite_positive_probes": 9' in result.stdout
