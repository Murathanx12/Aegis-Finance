"""H5 -- the terminal-state mirror, and the proof it can never write back.

`TestReadOnly` is the point of this file. The execution repo is the process that
holds the broker client; a sync that could write into it is a write path into
the thing that can place orders. "Read-only" is asserted three independent ways
here, so that no single future edit can quietly make the docstring false.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from backend.services import terminal_state_reader as tsr

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "backend" / "services" / "terminal_state_reader.py"


@pytest.fixture()
def fake_state(tmp_path: Path) -> Path:
    """A miniature `state/` with one file per whitelisted family."""
    src = tmp_path / "state"
    (src / "predictions").mkdir(parents=True)
    (src / "predictions" / "seals.jsonl").write_text(
        '{"day": "2026-09-02", "content_sha256": "abc"}\n', encoding="utf-8")
    (src / "autopsy").mkdir()
    (src / "autopsy" / "2026-09-04.json").write_text('{"day": "2026-09-04"}',
                                                     encoding="utf-8")
    (src / "autopsy" / "2026-08-28.json").write_text('{"day": "2026-08-28"}',
                                                     encoding="utf-8")
    (src / "learning_report").mkdir()
    (src / "learning_report" / "2026-09-04.json").write_text('{"n": 1}',
                                                             encoding="utf-8")
    (src / "opportunity_recall").mkdir()
    (src / "opportunity_recall" / "2026-09-04.jsonl").write_text(
        '{"symbol": "AAA", "recall_kind": "missed_winner"}\n', encoding="utf-8")
    (src / "contracts").mkdir()
    (src / "contracts" / "passive_beta_v1.json").write_text('{"beta": 1.0}',
                                                            encoding="utf-8")
    (src / "refusal_regret.json").write_text('{"n": 0}', encoding="utf-8")
    (src / "fills.jsonl").write_text('{"symbol": "AAA", "qty": 1}\n',
                                     encoding="utf-8")
    #: NOT whitelisted. It must still be here, byte for byte, afterwards.
    (src / "decisions.jsonl").write_text('{"secret": true}\n', encoding="utf-8")
    (src / "loop_dev.log").write_text("noise\n", encoding="utf-8")
    return src


def _fingerprint(root: Path) -> dict:
    return {str(p.relative_to(root)): (p.stat().st_size,
                                       hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(root.rglob("*")) if p.is_file()}


class TestReadOnly:
    """Three independent mechanisms, because one is a docstring with a test."""

    def test_the_source_tree_is_byte_identical_after_a_sync(self, fake_state, tmp_path):
        """MECHANISM 3, and the decisive one: fingerprint before, fingerprint
        after. This is the assertion that fails if a future edit makes the
        module write upstream, and it does not depend on anyone reading a
        docstring or maintaining a list of banned verbs."""
        before = _fingerprint(fake_state)
        assert before, "the fixture planted nothing; this test proves nothing"
        tsr.sync(source=fake_state, mirror=tmp_path / "mirror")
        after = _fingerprint(fake_state)
        assert after == before, (
            "the execution repo's tree CHANGED during a sync. Files added: "
            f"{sorted(set(after) - set(before))}; removed: "
            f"{sorted(set(before) - set(after))}; altered: "
            f"{sorted(k for k in set(before) & set(after) if before[k] != after[k])}")

    def test_no_source_path_is_ever_opened_for_write(self):
        """MECHANISM 1: AST scan. Every `open()` in this module must be a read,
        and the write verbs that exist must be reachable only on a destination
        built by `_dest_for`."""
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", getattr(fn, "id", ""))
            if name == "open":
                modes = [a.value for a in node.args[1:] if isinstance(a, ast.Constant)]
                modes += [k.value.value for k in node.keywords
                          if k.arg == "mode" and isinstance(k.value, ast.Constant)]
                if any("w" in m or "a" in m or "+" in m for m in modes):
                    bad.append(f"open(mode={modes})")
            if name in ("unlink", "rmdir", "rmtree", "replace", "move", "chmod",
                        "truncate", "rename", "system", "popen"):
                bad.append(name)
        assert not bad, f"destructive or write calls in the mirror module: {bad}"

    def test_the_only_write_targets_are_inside_the_mirror(self):
        """The write verbs that DO exist -- `write_bytes`, `write_text`,
        `mkdir` -- must be called on `dst`, `dst_root` or `dst.parent`, never on
        anything derived from the source."""
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        allowed_receivers = {"dst", "dst_root", "p"}
        offenders = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") in ("write_bytes",
                                                           "write_text", "mkdir")):
                recv = node.func.value
                root = recv
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.BinOp):
                    root = root.left
                    while isinstance(root, ast.Attribute):
                        root = root.value
                nm = getattr(root, "id", None)
                if nm not in allowed_receivers:
                    offenders.append(f"{node.func.attr} on {nm!r}")
        assert not offenders, (
            f"a write verb targets something other than the mirror: {offenders}")

    def test_the_module_imports_nothing_that_can_place_an_order(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods.add(n.module.split(".")[0])
        assert not (mods & {"alpha", "alpaca", "requests", "httpx", "urllib",
                            "subprocess", "shutil", "socket"})

    def test_a_traversal_name_cannot_escape_the_mirror(self, tmp_path):
        """MECHANISM 2: containment. The one shape in which a copy could ever
        have walked back toward the source tree."""
        with pytest.raises(tsr.MirrorRefused):
            tsr._dest_for(tmp_path / "mirror", "autopsies", "../../escaped.json")
        with pytest.raises(tsr.MirrorRefused):
            tsr.read("autopsies", "../secret.json", mirror=tmp_path / "mirror")

    def test_a_sync_onto_itself_is_refused(self, fake_state):
        with pytest.raises(tsr.MirrorRefused) as e:
            tsr.sync(source=fake_state, mirror=fake_state)
        assert "itself" in str(e.value)

    def test_nothing_outside_the_whitelist_is_copied(self, fake_state, tmp_path):
        mirror = tmp_path / "mirror"
        tsr.sync(source=fake_state, mirror=mirror)
        copied = {p.name for p in mirror.rglob("*") if p.is_file()}
        assert "decisions.jsonl" not in copied
        assert "loop_dev.log" not in copied
        assert "seals.jsonl" in copied and "fills.jsonl" in copied


class TestSyncReceipt:
    def test_the_receipt_counts_files_and_kinds(self, fake_state, tmp_path):
        r = tsr.sync(source=fake_state, mirror=tmp_path / "m")
        assert r["n_files"] == 8, r["kinds"]
        assert r["kinds"]["autopsies"] == 2
        assert r["kinds"]["seals"] == 1
        assert "READ_ONLY, ONE DIRECTION" in r["authority"]

    def test_an_absent_artefact_is_a_named_skip_not_a_silent_zero(self, tmp_path):
        src = tmp_path / "state"
        (src / "autopsy").mkdir(parents=True)
        (src / "autopsy" / "2026-09-04.json").write_text("{}", encoding="utf-8")
        r = tsr.sync(source=src, mirror=tmp_path / "m")
        reasons = {s["artefact"]: s["reason"] for s in r["skipped"]}
        assert "fills.jsonl" in reasons and "absent" in reasons["fills.jsonl"]

    def test_a_missing_execution_repo_refuses(self, tmp_path):
        with pytest.raises(tsr.MirrorRefused) as e:
            tsr.sync(source=tmp_path / "nope", mirror=tmp_path / "m")
        assert "UNREACHABLE" in str(e.value)

    def test_an_oversized_jsonl_is_tail_truncated_and_says_so(self, fake_state, tmp_path):
        big = fake_state / "fills.jsonl"
        big.write_text("".join(f'{{"i": {i}}}\n' for i in range(2000)),
                       encoding="utf-8")
        r = tsr.sync(source=fake_state, mirror=tmp_path / "m", max_bytes=200)
        row = [x for x in r["artefacts"]["fills"]][0]
        assert row["truncated_from_tail"] is True
        assert row["bytes"] <= 200 and row["source_bytes"] > 200
        rows = tsr.read("fills", "fills.jsonl", mirror=tmp_path / "m")["rows"]
        assert rows[-1]["i"] == 1999, "the tail (newest) was not what survived"

    def test_an_oversized_json_blob_is_skipped_not_halved(self, fake_state, tmp_path):
        (fake_state / "refusal_regret.json").write_text(
            json.dumps({"x": ["y"] * 500}), encoding="utf-8")
        r = tsr.sync(source=fake_state, mirror=tmp_path / "m", max_bytes=200)
        row = r["artefacts"]["refusals"][0]
        assert row["copied"] is False
        assert "half a JSON document" in row["reason"]


class TestInventoryAndRead:
    def test_never_synced_is_not_an_empty_mirror(self, tmp_path):
        inv = tsr.inventory(mirror=tmp_path / "never")
        assert inv["status"] == "NEVER_SYNCED"
        assert "NOT" in inv["reason"] and inv["how_to_refresh"]

    def test_inventory_after_a_sync_lists_the_kinds(self, fake_state, tmp_path):
        m = tmp_path / "m"
        tsr.sync(source=fake_state, mirror=m)
        inv = tsr.inventory(mirror=m)
        assert inv["status"] in ("OK", "SOURCE_UNREACHABLE")
        assert {f["file"] for f in inv["kinds"]["autopsies"]} == {
            "2026-09-04.json", "2026-08-28.json"}
        assert inv["n_files"] == 8

    def test_reading_a_jsonl_returns_rows(self, fake_state, tmp_path):
        m = tmp_path / "m"
        tsr.sync(source=fake_state, mirror=m)
        out = tsr.read("opportunity_recall", "2026-09-04.jsonl", mirror=m)
        assert out["format"] == "jsonl" and out["n_rows"] == 1
        assert out["rows"][0]["recall_kind"] == "missed_winner"

    def test_reading_a_json_returns_content(self, fake_state, tmp_path):
        m = tmp_path / "m"
        tsr.sync(source=fake_state, mirror=m)
        assert tsr.read("autopsies", "2026-09-04.json",
                        mirror=m)["content"]["day"] == "2026-09-04"

    def test_an_unknown_kind_is_refused(self, tmp_path):
        with pytest.raises(tsr.MirrorRefused):
            tsr.read("whatever", "x.json", mirror=tmp_path)

    def test_a_missing_file_is_refused_with_the_next_step(self, fake_state, tmp_path):
        m = tmp_path / "m"
        tsr.sync(source=fake_state, mirror=m)
        with pytest.raises(tsr.MirrorRefused) as e:
            tsr.read("autopsies", "1999-01-01.json", mirror=m)
        assert "inventory()" in str(e.value)

    def test_the_kinds_are_derived_from_the_whitelist(self):
        from backend.config import TERMINAL_MIRROR_ARTEFACTS
        assert set(tsr.KINDS) == {k for _, k, _ in TERMINAL_MIRROR_ARTEFACTS}
