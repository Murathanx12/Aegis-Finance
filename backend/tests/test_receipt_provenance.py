"""The provenance rule, and the proof that it can go RED.

A gate that cannot go green is a broken gate, and its twin -- a gate that cannot
go red -- is worse, because it reads as evidence. So the centre of this file is
`test_the_w4b_bug_in_miniature_is_rejected`: the actual 2026-09-05 defect,
rebuilt at fixture scale, with the assertion that the checker names it. If that
one cannot fail, everything else here is decorative.

The last test is the session sweep. It SKIPS when the directory is empty or a
receipt is absent -- four sibling agents are writing into it while this runs,
and a suite that goes red because a peer has not finished teaches people to
ignore it -- but it FAILS on a receipt that exists and lacks the block.
"""

from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path

import pytest

from backend.services.receipt_provenance import (CHUNK_BYTES, InputTracker,
                                                 argv_mentions, check_receipt,
                                                 hard_failures, normalise,
                                                 provenance_block,
                                                 resolve_config, sha256_of,
                                                 stamped_input_paths)

REPO = Path(__file__).resolve().parents[2]
SWEEP_DIR = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"


# ────────────────────────────────────────────────────────────── round trip

def test_tracker_hashes_match_hashlib(tmp_path):
    a = tmp_path / "edges.parquet"
    b = tmp_path / "panel.csv"
    a.write_bytes(b"alpha-edges\n" * 11)
    b.write_text("permno,ret\n1,0.01\n", encoding="utf-8")

    tr = InputTracker()
    tr.opened(a)
    tr.opened(b)
    block = provenance_block(["prog", "--edges", str(a)], {}, tr)

    got = {e["path"]: e for e in block["_inputs_opened"]}
    assert set(got) == {normalise(a), normalise(b)}
    for p in (a, b):
        e = got[normalise(p)]
        assert e["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
        assert e["bytes"] == p.stat().st_size
    assert block["sys_argv"] == ["prog", "--edges", str(a)]
    assert set(block) == {"sys_argv", "resolved_config", "_inputs_opened",
                          "git_commit", "generated_utc"}


def test_a_file_opened_five_times_is_hashed_once(tmp_path, monkeypatch):
    f = tmp_path / "panel.parquet"
    f.write_bytes(b"x" * 4096)
    calls = {"n": 0}
    import backend.services.receipt_provenance as RP
    real = RP.sha256_of

    def counted(path, **kw):
        calls["n"] += 1
        return real(path, **kw)

    monkeypatch.setattr(RP, "sha256_of", counted)
    tr = InputTracker()
    for _ in range(5):
        tr.opened(f)
    # ...and the same file under a different spelling of the same path.
    tr.opened(str(f).replace("\\", "/"))
    assert calls["n"] == 1
    assert len(tr) == 1


def test_hashing_is_chunked_and_streamed(tmp_path):
    """>1 MB is hashed in more than one read, and the chunk size is the reason.

    Memory is not observable from here; the number of reads is. The file is
    deliberately larger than CHUNK_BYTES so a whole-file read and a streamed
    read give different call counts.
    """
    big = tmp_path / "big.parquet"
    big.write_bytes(b"z" * (CHUNK_BYTES + 4096))
    assert CHUNK_BYTES == 1 << 20

    reads = {"n": 0}
    import builtins
    real_open = builtins.open

    class CountingFile:
        def __init__(self, fh):
            self._fh = fh

        def read(self, n=-1):
            reads["n"] += 1
            return self._fh.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()
            return False

    def fake_open(path, mode="r", *a, **kw):
        fh = real_open(path, mode, *a, **kw)
        return CountingFile(fh) if "b" in mode else fh

    builtins.open = fake_open
    try:
        digest = sha256_of(big)
    finally:
        builtins.open = real_open

    assert digest == hashlib.sha256(big.read_bytes()).hexdigest()
    # ceil(1MB+4096 / 1MB) = 2 chunks, plus the empty read that ends the loop.
    assert reads["n"] == 3, reads


def test_a_missing_input_is_recorded_not_raised(tmp_path):
    tr = InputTracker()
    entry = tr.opened(tmp_path / "never_written.parquet")
    assert entry["error"] == "MISSING"
    assert "sha256" not in entry
    block = provenance_block(["prog"], {}, tr)
    assert block["_inputs_opened"][0]["error"] == "MISSING"


# ──────────────────────────────────────── THE PROVED-RED ASSERTION (W4b)

def _w4b_fixture(tmp_path) -> tuple[dict, Path, Path]:
    """The 2026-09-05 defect at fixture scale.

    The job was HANDED `companyworld_v1.parquet` and opened it. The receipt
    stamped `edge_instances.parquet` -- the module-level default -- because the
    describing line and the opening line were written separately. Only
    `source_rows` disagreed, and nothing compared it to the path beside it.
    """
    module_default = tmp_path / "MARKET-GRAPH-1" / "edge_instances.parquet"
    module_default.parent.mkdir(parents=True, exist_ok=True)
    module_default.write_bytes(b"the 2014-2024 file the arm was tested against")

    the_argument = tmp_path / "graph" / "companyworld_v1.parquet"
    the_argument.parent.mkdir(parents=True, exist_ok=True)
    the_argument.write_bytes(b"the never-seen 1999-2013 tape")

    tr = InputTracker()
    tr.opened(the_argument)                      # what the loader ACTUALLY read
    receipt = {
        "job": "W4b_companyworld_rerun",
        "graph_receipt": {
            "edges_path": str(module_default),   # <-- the module default
            "source_rows": 2020,                 # <-- the only line that told
        },
        "verdict": "PRODUCT_EXPERIMENT",
    }
    receipt["_provenance"] = provenance_block(
        ["companyworld_extract.py", "--edges", str(the_argument)],
        resolve_config(Namespace(edges=str(the_argument)),
                       {"edges": str(module_default)},
                       argv=["--edges", str(the_argument)]),
        tr)
    return receipt, module_default, the_argument


def test_the_w4b_bug_in_miniature_is_rejected(tmp_path):
    """THE RED PROOF. A stamped module default beside a differently-opened file.

    If this assertion cannot fail, the checker is decorative and the class is
    not closed -- so it is written against the real defect rather than against
    a synthetic one.
    """
    receipt, module_default, the_argument = _w4b_fixture(tmp_path)

    findings = check_receipt(receipt)
    named = [f for f in findings if f.startswith("UNOPENED_PATH_STAMPED")]
    assert named, f"the W4b defect went UNDETECTED. findings={findings}"
    assert "graph_receipt.edges_path" in named[0]
    assert module_default.name in named[0]
    assert hard_failures(findings), "a stamped default must be a HARD failure"

    # ...and the same receipt with the argument stamped is clean. Without this
    # half, a checker that always fails would pass the half above.
    receipt["graph_receipt"]["edges_path"] = str(the_argument)
    assert check_receipt(receipt) == []


def test_the_stamped_path_scan_finds_the_field_it_is_meant_to():
    receipt = {"graph_receipt": {"edges_path": "a/b/edge_instances.parquet"},
               "out_path": "results/out.json",
               "source": "IBES",
               "_provenance": {"_inputs_opened": []}}
    found = dict(stamped_input_paths(receipt))
    assert "graph_receipt.edges_path" in found
    # an OUTPUT path was never opened for reading and must not be compared
    assert "out_path" not in found
    # a vendor name is not a path
    assert "source" not in found


# ─────────────────────────────────────────────────── the other rejections

def test_a_receipt_with_no_provenance_is_rejected():
    findings = check_receipt({"job": "W9", "verdict": "NOISE"})
    assert findings and findings[0].startswith("MISSING_PROVENANCE")
    assert hard_failures(findings)


def test_a_default_stamp_on_a_passed_key_is_rejected():
    receipt = {
        "_provenance": {
            "sys_argv": ["prog", "--edges", "graph/companyworld_v1.parquet"],
            "resolved_config": {"edges": {"value": "MARKET-GRAPH-1/edges.parquet",
                                          "source": "default"}},
            "_inputs_opened": [{"path": normalise("graph/companyworld_v1.parquet"),
                                "sha256": "0" * 64, "bytes": 1}],
        }}
    findings = check_receipt(receipt)
    assert any(f.startswith("DEFAULT_SOURCE_BUT_PASSED") for f in findings), findings
    assert hard_failures(findings)


def test_resolve_config_marks_arg_env_and_default(monkeypatch):
    monkeypatch.setenv("AEGIS_EDGES", "from/the/env.parquet")
    ns = Namespace(edges="passed/on/the/cli.parquet", k=50, cost_bps=10.0)
    cfg = resolve_config(
        ns, {"edges": "module/default.parquet", "k": 50, "cost_bps": 10.0},
        argv=["prog", "--edges", "passed/on/the/cli.parquet", "--k", "50"],
        env_overrides={"cost_bps": "AEGIS_EDGES"})
    assert cfg["edges"]["source"] == "arg"
    assert cfg["k"]["source"] == "arg"          # on the command line, though equal
    assert cfg["cost_bps"]["source"] == "env"
    assert cfg["edges"]["value"] == "passed/on/the/cli.parquet"


def test_a_value_equal_to_the_default_but_never_passed_is_default():
    cfg = resolve_config(Namespace(k=50), {"k": 50}, argv=["prog"])
    assert cfg["k"]["source"] == "default"
    # ...and a receipt carrying that is clean, because `--k` is not in argv.
    receipt = {"_provenance": {"sys_argv": ["prog"], "resolved_config": cfg,
                               "_inputs_opened": []}}
    assert not any(f.startswith("DEFAULT_SOURCE_BUT_PASSED")
                   for f in check_receipt(receipt, require_inputs=False))


def test_argv_mentions_matches_both_spellings():
    assert argv_mentions("cost_bps", ["prog", "--cost-bps", "10"])
    assert argv_mentions("cost_bps", ["prog", "--cost_bps=10"])
    assert not argv_mentions("cost_bps", ["prog", "cost_bps"])
    assert not argv_mentions("k", ["prog", "--kind", "lgbm"])


def test_empty_inputs_is_a_finding_only_when_inputs_were_required():
    receipt = {"_provenance": {"sys_argv": ["prog"], "resolved_config": {},
                               "_inputs_opened": []}}
    assert any(f.startswith("EMPTY_INPUTS") for f in check_receipt(receipt))
    assert check_receipt(receipt, require_inputs=False) == []


def test_a_changed_input_is_soft_not_hard(tmp_path):
    f = tmp_path / "panel.parquet"
    f.write_bytes(b"first")
    tr = InputTracker()
    tr.opened(f)
    receipt = {"_provenance": provenance_block(["prog"], {}, tr)}
    assert check_receipt(receipt, verify_hashes=True) == []

    f.write_bytes(b"second, and legitimately so")
    findings = check_receipt(receipt, verify_hashes=True)
    assert any(f.startswith("STALE_OR_CHANGED") for f in findings), findings
    assert hard_failures(findings) == [], "a changed input is not a bad receipt"


# ────────────────────────────────────────── the writer this rule was applied to

def test_weekend_lab_jobs_stamps_provenance_at_one_place():
    """The choke point exists and the block is written there, not per job."""
    import scripts.weekend_lab_jobs as WLJ
    src = Path(WLJ.__file__).read_text(encoding="utf-8")
    assert src.count("attach(payload") == 1, (
        "provenance must be written at ONE place -- the W4b bug is what "
        "per-call-site provenance looks like")
    assert "RUN_INPUTS" in src and isinstance(WLJ.RUN_INPUTS, InputTracker)
    # `era_sign_table` is imported READ-ONLY by scripts/w3_neural_floored.py.
    assert callable(WLJ.era_sign_table)


def test_weekend_lab_jobs_writes_a_checkable_receipt(tmp_path, monkeypatch):
    """Run the real choke point over a stub job and check its own receipt."""
    import scripts.weekend_lab_jobs as WLJ
    probe = tmp_path / "probe.parquet"
    probe.write_bytes(b"an input the job opened")

    def _stub(variant: int = 0) -> dict:
        WLJ.RUN_INPUTS.opened(probe)
        return {"verdict": "INVENTORY", "headline": "stub", "source": str(probe)}

    monkeypatch.setitem(WLJ.JOBS, "W1_long_panel_inventory", _stub)
    monkeypatch.setattr(WLJ, "RUN_INPUTS", InputTracker())
    out = tmp_path / "receipt.json"
    rc = WLJ.main(["W1_long_panel_inventory", "--out", str(out), "--variant", "3"])
    assert rc == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    prov = payload["_provenance"]
    assert [e["path"] for e in prov["_inputs_opened"]] == [normalise(probe)]
    assert prov["resolved_config"]["variant"]["source"] == "arg"
    assert prov["resolved_config"]["run"]["source"] == "default"
    assert prov["resolved_config"]["job"]["source"] == "arg"
    assert check_receipt(payload) == [], check_receipt(payload)


# ───────────────────────────────────────────────────────── the session sweep

def _is_a_frozen_declaration(path: Path, payload: dict) -> bool:
    """A pre-run DECLARATION is not a receipt of a computation.

    `C4_hold_rule_declaration.json` and `W3b_neural_floored_run01_declaration
    .json` are the shape: a rule hashed and timestamped BEFORE the run, opening
    no input and producing no number. Provenance of an open it never performed
    would be an empty block asserting nothing.

    The exemption is not the filename alone -- that would be a free pass to
    anyone who names a file `..._declaration.json`. It must ALSO carry its own
    freeze stamp, which is the tamper-evidence a declaration owes instead.
    """
    if not path.name.endswith("_declaration.json"):
        return False
    if not isinstance(payload, dict):
        return False
    has_stamp = any(k.endswith("_sha256") or k.endswith("_hash")
                    for k in payload) or "declared_utc" in payload
    return has_stamp and "_inputs_opened" not in json.dumps(payload)[:200000]


def _sweep_receipts() -> list[Path]:
    if not SWEEP_DIR.is_dir():
        return []
    return sorted(p for p in SWEEP_DIR.glob("*.json") if p.is_file())


def test_every_continuation_receipt_carries_provenance():
    """Every receipt in this session's directory passes `check_receipt`.

    SKIPS when the directory is empty -- four agents are writing into it while
    this runs and a red suite for work that has not landed yet is a red suite
    people learn to ignore. FAILS on a receipt that exists and lacks the block,
    which is the case the rule is about.

    `require_inputs=False`: a receipt whose job opened no file is legitimate
    (a pure re-derivation from numbers already in another receipt). The W4b
    check still binds on those, because a receipt that stamps an input path it
    never opened is caught either way.
    """
    receipts = _sweep_receipts()
    if not receipts:
        pytest.skip(f"no receipts under {SWEEP_DIR} yet — nothing to sweep")

    bad: dict[str, list[str]] = {}
    exempt: dict[str, str] = {}
    for p in receipts:
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # A peer agent mid-write leaves a truncated file; that is a race,
            # not a provenance defect.
            bad.setdefault(p.name, []).append(f"UNREADABLE: {exc}")
            continue
        if _is_a_frozen_declaration(p, payload):
            exempt[p.name] = "declaration frozen before the run"
            continue
        findings = hard_failures(check_receipt(payload, require_inputs=False))
        if findings:
            bad[p.name] = findings
    assert not bad, json.dumps(bad, indent=1)[:4000]
    # An exemption that costs nothing becomes the default. This one costs the
    # file its own freeze stamp, and the names are printed rather than skipped
    # quietly -- a silent skip is this repository's house failure mode.
    print(f"provenance sweep: {len(receipts)} receipt(s), "
          f"{len(exempt)} declaration(s) exempt: {sorted(exempt)}")


def test_the_declaration_exemption_is_not_a_free_pass(tmp_path):
    """The sweep's own escape hatch, made to refuse.

    The sweep went RED for real at 22:34 on 2026-09-05, on a peer's
    `C4_hold_rule_declaration.json`, which is how the exemption came to exist.
    An exemption keyed on the filename alone would have been a way to opt out
    of the rule by renaming, so it is keyed on the freeze stamp as well.
    """
    named = tmp_path / "X_hold_rule_declaration.json"
    payload_no_stamp = {"job": "X", "hold_rule": "keep the prior month"}
    named.write_text(json.dumps(payload_no_stamp), encoding="utf-8")
    assert not _is_a_frozen_declaration(named, payload_no_stamp)

    payload_stamped = dict(payload_no_stamp, hold_rule_sha256="ab" * 32)
    assert _is_a_frozen_declaration(named, payload_stamped)

    # a receipt is never exempt, however it is stamped
    other = tmp_path / "X_run01.json"
    assert not _is_a_frozen_declaration(other, payload_stamped)


def test_my_own_receipt_carries_valid_provenance():
    """A provenance rule whose own receipt lacks provenance is a joke."""
    mine = SWEEP_DIR / "C6_receipt_provenance_rule_run01.json"
    if not mine.is_file():
        pytest.skip(f"{mine.name} not written yet")
    payload = json.loads(mine.read_text(encoding="utf-8"))
    assert hard_failures(check_receipt(payload)) == [], check_receipt(payload)
    assert payload["_provenance"]["_inputs_opened"], (
        "this receipt reports a survey of files it read; it must name them")
