"""`--to-registry`: what the memory knows, written where the PM can see it.

FOUR PROPERTIES, EACH ONE A FAILURE SOMEBODY HAS ALREADY PAID FOR HERE.

1. INERT. The block is read-only for the PM until B9, and that has to be a
   structural fact rather than a promise. `signal_registry.load()` builds its
   `Registry` from exactly five top-level keys and `Registry` has no field for
   anything else, so a sixth block cannot reach `permits()`, `weight()` or
   `check_closed()`. This file greps the repo for consumers and asserts the
   loaded object cannot see it -- because "nobody reads it" is the kind of claim
   that stops being true in a commit nobody remembers making.

2. IDEMPOTENT, TO THE BYTE. A generated block carrying a wall clock rewrites the
   registry on every run and turns a real change into noise nobody reads. The
   provenance here is a content hash and the newest observation on file, both
   functions of the input.

3. IT DISTURBS NOTHING. The registry is 56 lines of reasoned comment before its
   first key. `yaml.safe_load` -> `yaml.safe_dump` would delete every one of
   them, so the file is edited as TEXT between two markers and everything
   outside them is asserted byte-identical.

4. THE VOCABULARY BINDS, AND A SCREEN CANNOT REACH NOVEL. `screen_verdict`'s own
   docstring counts the damage the last time it did not: "25 of 92 committed
   verdicts said NOVEL and not one of them had cleared the bar".
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from learner import evidence_memory as EM

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "backend" / "data" / "signal_registry.yaml"


# ------------------------------------------------------------------- fixtures

def _book_row(**kw):
    r = {
        "utc": "2026-09-01T00:00:00+00:00", "version": EM.VERSION,
        "family_id": "fam", "cell": "arm|10bps", "job": "T", "run": 1,
        "variant": "a", "n_months": 240, "sharpe": None,
        "dsr": 0.99, "spa_p": 0.01, "pbo": 0.1, "verdict": None,
        "powered": True, "years_needed_for_t2": 4.0, "years_observed": 20.0,
        "eras": {"eras_with_a_positive_mean": 3, "eras_measured": 3,
                 "holds_in_2_of_3": True, "same_sign_in_2_of_3": True,
                 "1999-2007": {"months": 48, "mean_pct": 1.0, "t": 2.4},
                 "2008-2015": {"months": 96, "mean_pct": 1.1, "t": 2.6},
                 "2016-2024": {"months": 96, "mean_pct": 1.2, "t": 0.4}},
        "gross_beats_market": True, "net_beats_market": True,
        "screen_cleared": None, "controlled_t": None, "holm_p": None,
        "note": "",
    }
    r.update(kw)
    return r


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(EM, "STORE_DIR", tmp_path)
    monkeypatch.setattr(EM, "STORE", tmp_path / "evidence_memory.jsonl")
    monkeypatch.setattr(EM, "SUPERSESSIONS", tmp_path / "supersessions.jsonl")
    monkeypatch.setattr(EM, "STATE_SNAPSHOT", tmp_path / "state.json")
    rows = [_book_row(variant="a", dsr=0.99), _book_row(variant="b", dsr=0.98)]
    (tmp_path / "evidence_memory.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return tmp_path


def _strip_block(text: str) -> str:
    """The registry as it was BEFORE any export -- the tree's copy already
    carries a generated block, and a test that starts from it would only ever
    exercise the replace path."""
    if EM._BEGIN not in text:
        return text
    head, rest = text.split(EM._BEGIN, 1)
    tail = rest.split(EM._END, 1)[1]
    return head.rstrip("\r\n") + ("\r\n" if "\r\n" in text else "\n")


@pytest.fixture()
def registry_copy(tmp_path):
    """A copy of the REAL registry with no generated block, so the round-trip is
    tested against the file that actually has 56 lines of comment and CRLF
    endings rather than against a synthetic stub."""
    p = tmp_path / "signal_registry.yaml"
    text = REGISTRY.read_bytes().decode("utf-8")
    p.write_bytes(_strip_block(text).encode("utf-8"))
    return p


# ------------------------------------------------------- 1. inert for the PM

def test_no_reader_of_the_registry_consumes_conditional_evidence():
    """The proof that the block is read-only, done by looking rather than
    asserting. Every `.py` in the repo is searched for the string; the only
    files permitted to mention it are the generator and its two tests."""
    allowed = {
        Path("learner/evidence_memory.py"),
        Path("backend/tests/test_evidence_registry_export.py"),
        Path("backend/tests/test_evidence_memory_superseded.py"),
    }
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__",
                 "site-packages", "frontend", "docs"}
    hits, scanned = [], 0
    for p in REPO.rglob("*.py"):
        rel = p.relative_to(REPO)
        if set(rel.parts) & skip_dirs or rel in allowed:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        if "conditional_evidence" in text:
            hits.append(str(rel))
    # A SEARCH THAT FOUND NOTHING BECAUSE IT LOOKED AT NOTHING IS NOT EVIDENCE.
    # Every reader named in the receipt lives under backend/services, and the
    # scan must demonstrably have covered them.
    assert scanned > 500, f"only {scanned} files scanned -- the search is broken"
    assert (REPO / "backend" / "services" / "signal_registry.py").exists()
    assert not hits, (
        f"{hits} mention `conditional_evidence`. The block is read-only for the "
        f"PM until B9; a consumer needs B9's decision, not a grep-passing edit.")


def test_the_loaded_registry_cannot_see_the_block(registry_copy):
    """Structural, not incidental: `Registry` has no field for it, and `load()`
    reads five top-level keys. A block it does not name cannot reach the PM."""
    from backend.services import signal_registry as SR

    EM.to_registry(registry_copy)
    raw = yaml.safe_load(registry_copy.read_text(encoding="utf-8"))
    assert "conditional_evidence" in raw, "the block must actually be in the file"

    assert "conditional_evidence" not in SR.Registry.__dataclass_fields__
    assert "conditional_evidence" not in SR.Signal.__dataclass_fields__

    reg = SR.load(str(registry_copy))          # must still validate cleanly
    assert reg.schema == "signal-registry-v1"
    assert not hasattr(reg, "conditional_evidence")
    assert reg.summary()["n_signals"] == SR.load(str(REGISTRY)).summary()["n_signals"]


def test_the_writer_refuses_if_another_block_would_move(registry_copy, monkeypatch):
    """The guard that makes 'appends only' a fact. If the rewritten file's other
    keys differ from the original's by so much as one value, nothing is written."""
    real_dump = yaml.safe_dump

    def sabotage(obj, **kw):
        # Emit a block that also redefines `schema` -- the shape of an editing
        # accident, and exactly what must never land silently.
        return real_dump(obj, **kw) + "schema: tampered\n"

    monkeypatch.setattr(EM.yaml if hasattr(EM, "yaml") else yaml, "safe_dump",
                        sabotage, raising=False)
    monkeypatch.setattr("yaml.safe_dump", sabotage)
    before = registry_copy.read_bytes()
    with pytest.raises(EM.EvidenceMemoryError, match="another block"):
        EM.to_registry(registry_copy)
    assert registry_copy.read_bytes() == before, "a refused write must write nothing"


# ------------------------------------------------------------- 2. idempotence

def test_running_it_twice_is_byte_identical(registry_copy):
    EM.to_registry(registry_copy)
    once = registry_copy.read_bytes()
    second = EM.to_registry(registry_copy)
    twice = registry_copy.read_bytes()
    assert hashlib.sha256(once).hexdigest() == hashlib.sha256(twice).hexdigest()
    assert second["changed"] is False, "the second run must report no change"


def test_the_block_carries_no_wall_clock(registry_copy):
    """A timestamp would make every run a diff. Provenance is a content hash and
    the newest observation on file, which are functions of the input."""
    EM.to_registry(registry_copy)
    block = yaml.safe_load(
        registry_copy.read_text(encoding="utf-8"))["conditional_evidence"]
    assert "rows_sha256" in block["provenance"]
    assert not any("written" in k or "generated_utc" in k
                   for k in block["provenance"]), block["provenance"]


# -------------------------------------------------------- 3. disturbs nothing

def test_everything_outside_the_markers_survives_byte_for_byte(registry_copy):
    original = registry_copy.read_bytes()
    EM.to_registry(registry_copy)
    after = registry_copy.read_bytes().decode("utf-8")

    head, rest = after.split(EM._BEGIN, 1)
    tail = rest.split(EM._END, 1)[1]
    sep = "\r\n" if b"\r\n" in original else "\n"
    assert head.encode("utf-8") == original + sep.encode("utf-8"), (
        "the text before the block must be the original file, verbatim")
    assert tail.strip() == "", "nothing may be written after the block"

    # And a re-write replaces the block rather than stacking a second copy.
    EM.to_registry(registry_copy)
    assert registry_copy.read_text(encoding="utf-8").count(EM._BEGIN) == 1


def test_a_begin_with_no_end_is_refused(registry_copy):
    """Refusing to guess where a generated block stops. A wrong guess deletes a
    hand-written registry entry, and the file is the interface to the PM."""
    registry_copy.write_bytes(
        registry_copy.read_bytes()
        + f"\n{EM._BEGIN}\nconditional_evidence: {{}}\n".encode("utf-8"))
    with pytest.raises(EM.EvidenceMemoryError, match="END marker"):
        EM.to_registry(registry_copy)


def test_the_tree_copy_is_replaced_not_stacked():
    """The registry in the tree already carries a block; exporting onto it must
    replace that block and leave exactly one."""
    text = REGISTRY.read_text(encoding="utf-8")
    assert text.count(EM._BEGIN) == 1 and text.count(EM._END) == 1
    assert text.index(EM._BEGIN) < text.index(EM._END)


# ------------------------------------------------------------- 4. the verdicts

def test_the_vocabulary_matches_the_lab():
    """The copy in `evidence_memory` cannot drift from the definition in
    `weekend_lab_jobs`. Parsed, not imported: the lab pulls pandas and the
    panel, and this is a test about seven words."""
    src = (REPO / "scripts" / "weekend_lab_jobs.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    words = set()
    for name in ("verdict_from", "screen_verdict"):
        for node in ast.walk(fns[name]):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                w = EM._leading_vocabulary_word(node.value)
                if w:
                    words.add(w)
            elif isinstance(node, ast.JoinedStr):
                head = node.values[0]
                if isinstance(head, ast.Constant):
                    w = EM._leading_vocabulary_word(head.value)
                    if w:
                        words.add(w)
    assert words <= set(EM.VERDICT_VOCABULARY), sorted(words - set(EM.VERDICT_VOCABULARY))
    assert {"NOVEL", "NOISE", "CANNOT DETERMINE", "DECAYED",
            "SCREEN_SURVIVOR", "SCREEN_ONLY"} <= words, sorted(words)
    assert "A screen cannot reach it" in src, (
        "the rule this export enforces must still be stated where it is defined")


@pytest.mark.parametrize("cleared", [True, False])
@pytest.mark.parametrize("holm", [None, 0.0001, 0.5])
@pytest.mark.parametrize("powered", [True, False, None])
def test_a_screen_can_never_reach_novel(cleared, holm, powered):
    """Exhaustive over the fields a screen row has. NOVEL is unreachable by
    construction, not by the numbers happening to fall short."""
    row = _book_row(screen_cleared=cleared, holm_p=holm, powered=powered,
                    dsr=0.999, spa_p=0.0001, pbo=0.0,
                    controlled_t=9.0, verdict="SURVIVES_HOLM")
    v, _ = EM.export_verdict(row)
    assert v != "NOVEL"
    assert v in EM.VERDICT_VOCABULARY
    assert v in ("SCREEN_SURVIVOR", "SCREEN_ONLY", "CANNOT DETERMINE", "NOISE")


def test_the_export_never_grades_above_the_job(store):
    """W3 IS THIS CASE ON THE REAL TAPE. dsr 0.9835, spa 0.016, pbo 0.086, three
    positive eras -- NOVEL by the arithmetic -- and the job's own verdict is
    "NOISE (clears the market bar, does NOT beat lgbm)", because the comparison
    that mattered was against lgbm and the arithmetic never saw it."""
    clean = _book_row(verdict=None)
    assert EM.export_verdict(clean)[0] == "NOVEL"

    capped, why = EM.export_verdict(
        _book_row(verdict="NOISE (clears the market bar, does NOT beat lgbm)"))
    assert capped == "NOISE"
    assert "capped by the job" in why

    for recorded in ("REFUTED -- three powered passes",
                     "CANNOT DETERMINE (underpowered)"):
        v, why = EM.export_verdict(_book_row(verdict=recorded))
        assert v == EM._leading_vocabulary_word(recorded)
        assert why


def test_an_era_slice_cannot_exceed_screen_only(store):
    """A third of one sample carries no deflation and no multiplicity
    correction. Letting a three-way split produce three findings is how one
    result becomes three."""
    rows, _meta = EM.registry_rows()
    era_rows = [r for r in rows if r["era"] != "ALL"]
    assert era_rows, "the fixture must produce era rows"
    for r in era_rows:
        assert r["verdict"] in ("SCREEN_ONLY", "NOISE", "CANNOT DETERMINE"), r
        # Full-sample corrections are NOT pasted onto a slice they were not
        # computed for -- the mistake `_record_cells` already documents.
        assert r["dsr"] is None and r["spa_p"] is None and r["pbo"] is None, r


def test_every_exported_row_has_the_required_shape(store):
    rows, meta = EM.registry_rows()
    assert rows
    for r in rows:
        assert set(("family", "era", "state")) <= set(r)
        for k in ("n", "sharpe", "dsr", "spa_p", "pbo", "verdict"):
            assert k in r, f"{k} missing from {r}"
        assert r["state"] in EM.EXPORTED_STATES
        assert EM._leading_vocabulary_word(r["verdict"]) is not None, r["verdict"]
    assert meta["idea_cells_not_exported"] >= 0


def test_idea_cells_are_not_exported(store):
    """One observation is not evidence, and 313 rows saying so would bury the
    twelve that mean something. An absent family is the honest encoding."""
    (store / "evidence_memory.jsonl").write_text(
        json.dumps(_book_row()) + "\n", encoding="utf-8")
    rows, meta = EM.registry_rows()
    assert rows == []
    assert meta["idea_cells_not_exported"] == 1


def test_the_real_registry_still_loads_after_the_export():
    """The file in the tree, as it stands. A block that broke the registry would
    break `permits()` for the whole PM, and the suite must say so here."""
    from backend.services import signal_registry as SR
    reg = SR.load(str(REGISTRY))
    assert reg.summary()["n_signals"] > 0
    raw = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert raw["conditional_evidence"]["schema"] == "conditional-evidence-1"
    assert raw["conditional_evidence"]["rows"], "the committed block must not be empty"
