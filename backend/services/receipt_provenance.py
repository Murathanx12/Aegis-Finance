"""Every receipt names the file it ACTUALLY opened, or the test says so.

THE FAILURE THIS CLOSES
=======================
`learner/features_graph.build()` stamped `"source": str(edge_source())` -- the
module-level default, or its env override -- and ignored the `edges_path` it had
been handed. Three W4b arms ran over three different edge sets on 2026-09-05 and
all three receipts named the SAME file. Only `source_rows` disagreed
(2020 / 10923 / 12943), and nothing in the repository compared those numbers to
the path beside them. A reader checking provenance would have been told that the
never-seen 1999-2013 tape came out of the 2014-2024 file it was being tested
against -- i.e. would have been told the experiment did not exist. The finding
survived; the provenance line did not.
(`backend/data/optimus/continuation_2026-09-06/S3_graph_receipt_provenance_run01.json`,
review claim 8.)

The local fix was to record the argument. That closes one call site. This module
closes the CLASS, in the shape Fable named:

    every receipt writer records `sys.argv`, the resolved config, and the
    SHA-256 of every input file it opened; a provenance test compares the
    stamped input paths with the paths actually opened.

The strace-free version of "actually opened" is a list the loader appends to, so
the recording is done BY the code that opens the file rather than by the code
that describes it afterwards. Description is what was wrong.

WHY THIS MODULE RAISES NOTHING
==============================
It defines no refusal exception, on purpose, and so is not a missing-input
guard (`backend/tests/guard_contract.py`). Two of its three surfaces are
recorders, and a recorder that raises loses the receipt it was writing:

* `InputTracker.opened()` on a file that is not there records
  `{"error": "MISSING"}` and returns. A receipt that says "I tried to open X and
  it was not there" is more useful than a traceback, and far more useful than
  the house failure mode, which is a silent skip.
* `check_receipt()` RETURNS its findings instead of raising them, because the
  session sweep has to report every bad receipt in one pass rather than the
  first one. Handed `{}` it returns `["MISSING_PROVENANCE: ..."]` -- a finding,
  not silence, which is the property `guard_contract` actually cares about.

HARD AND SOFT FINDINGS
======================
`check_receipt` returns strings prefixed by a name. Two names are SOFT
(`hard_failures()` drops them) because they are facts about the world rather
than defects in the receipt:

    STALE_OR_CHANGED       the file on disk today hashes differently. Inputs
                           legitimately change; the receipt is still an honest
                           record of what was read at the time.
    NO_INPUTS_TRACKED      the receipt stamps an input path but its loader was
                           never instrumented, so there is nothing to compare
                           against. A gap in adoption, not a false provenance
                           line -- and a red suite here would only punish
                           whoever adopted the block first.

Everything else is hard, and `UNOPENED_PATH_STAMPED` is the W4b bug itself.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Read size for hashing. Some panel inputs are 50 MB+ and a receipt writer must
#: never be the reason a job runs out of memory, so the hash is streamed. Named
#: rather than inlined because the test asserts on the constant: "it is chunked"
#: is checkable, "it did not hold the file in memory" is not.
CHUNK_BYTES = 1 << 20  # 1 MiB

#: Soft finding prefixes -- reported, but not a failure. See the docstring.
SOFT_PREFIXES = ("STALE_OR_CHANGED", "NO_INPUTS_TRACKED")

#: A stamped value is only compared against the opened set when it LOOKS like a
#: file. `"source": "IBES"` is a provenance line about a vendor, not a path, and
#: flagging it would teach readers to ignore this checker.
_PATHY_SUFFIXES = (".parquet", ".csv", ".json", ".jsonl", ".txt", ".db",
                   ".sqlite", ".npy", ".npz", ".pkl", ".feather",
                   ".yaml", ".yml", ".gz", ".zip", ".h5", ".arrow", ".tsv",
                   ".md", ".sas7bdat")

#: Keys whose value is an INPUT the writer claims to have read.
_INPUT_KEY_RE = re.compile(
    r"(^|_)(source|src|input|inputs|edges|edge|panel|corpus|dataset|data|"
    r"features|universe|prices|tape|table|cache|manifest|fixture|from)"
    r"(_(file|files|path|paths|table))?$"
    r"|(_(file|files|path|paths))$",
    re.IGNORECASE)

#: ...unless the key is plainly about where the writer WROTE. An output path was
#: never opened for reading and must not be compared against the opened set.
_OUTPUT_HINTS = ("out", "output", "dest", "dst", "target", "written", "write",
                 "receipt", "report", "log", "leaderboard", "checkpoint",
                 "artifact", "save")


# ───────────────────────────────────────────────── hashing and the recorder

def sha256_of(path: str | os.PathLike[str], *, chunk: int = CHUNK_BYTES) -> str:
    """SHA-256 of a file, streamed. Never reads the whole file into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def normalise(path: str | os.PathLike[str]) -> str:
    """One spelling for one file: absolute, resolved case, forward slashes.

    `os.path.normcase` matters on Windows (this repo's dev machine) and is a
    no-op elsewhere, so the comparison is the same rule on both.
    """
    return os.path.normcase(os.path.abspath(str(path))).replace("\\", "/")


class InputTracker:
    """The list the LOADER appends to. One entry per distinct file.

    `opened()` is called by the code that opens the file, which is the whole
    point: the W4b receipt was written by code that described the open rather
    than by code that performed it, and the description was wrong.

    Hashes are cached per normalised path for the life of the tracker, so a
    50 MB panel opened five times in a job is hashed once.
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []

    def opened(self, path: str | os.PathLike[str], *,
               note: str | None = None) -> dict[str, Any]:
        """Record one input. Returns the entry; never raises on a bad path."""
        try:
            key = normalise(path)
        except Exception:                                        # noqa: BLE001
            key = str(path)
        if key in self._entries:
            return self._entries[key]
        entry: dict[str, Any] = {"path": key}
        try:
            p = Path(path)
            if not p.is_file():
                entry["error"] = "MISSING"
            else:
                entry["sha256"] = sha256_of(p)
                entry["bytes"] = int(p.stat().st_size)
        except OSError as exc:
            entry["error"] = f"UNREADABLE: {type(exc).__name__}"
        entry["opened_utc"] = _now()
        if note:
            entry["note"] = note
        self._entries[key] = entry
        self._order.append(key)
        return entry

    # A tracker used as a context manager reads well at a call site that opens
    # several files in a row; it holds no resources, so exit does nothing.
    def __enter__(self) -> "InputTracker":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def entries(self) -> list[dict[str, Any]]:
        """The `_inputs_opened` list, in the order the files were opened."""
        return [dict(self._entries[k]) for k in self._order]

    def paths(self) -> list[str]:
        return list(self._order)

    def __len__(self) -> int:
        return len(self._order)

    def read_bytes(self, path: str | os.PathLike[str]) -> bytes:
        """Convenience: record the open, then perform it."""
        self.opened(path)
        return Path(path).read_bytes()

    def read_text(self, path: str | os.PathLike[str],
                  encoding: str = "utf-8") -> str:
        self.opened(path)
        return Path(path).read_text(encoding=encoding)


# ───────────────────────────────────────────────────────── resolved config

def argv_mentions(key: str, argv: Sequence[str]) -> bool:
    """Did `key` appear on the command line, under either spelling?

    argparse dests use underscores and flags use dashes, so both are checked,
    with and without an `=value` tail. Used by BOTH `resolve_config` (to stamp
    the source) and `check_receipt` (to catch a `default` stamp on a key that
    was in fact passed) -- one rule, so the two can never disagree.
    """
    names = {key, key.replace("_", "-")}
    for tok in argv or ():
        t = str(tok)
        head = t.split("=", 1)[0]
        if head.startswith("-") and head.lstrip("-") in names:
            return True
    return False


def resolve_config(namespace: Any,
                   module_defaults: Mapping[str, Any],
                   *,
                   argv: Sequence[str] | None = None,
                   env_overrides: Mapping[str, str] | None = None,
                   env: Mapping[str, str] | None = None) -> dict[str, dict]:
    """The values ACTUALLY USED, each tagged with where it came from.

    `module_defaults` is the EXPLICIT dict of module constants -- passing the
    constants rather than importing them keeps this module from knowing
    anything about its callers, and forces the caller to name the defaults it
    is claiming to have overridden.

    `source` is one of:
        arg      the flag was on the command line, or the namespace value
                 differs from the module default
        env      an env var named in `env_overrides` is set for that key
        default  neither -- the module constant is what ran
    """
    env = os.environ if env is None else env
    if namespace is None:
        ns: dict[str, Any] = {}
    elif isinstance(namespace, Mapping):
        ns = dict(namespace)
    else:
        ns = dict(vars(namespace))
    out: dict[str, dict] = {}
    for key in sorted(set(ns) | set(module_defaults)):
        value = ns[key] if key in ns else module_defaults[key]
        if argv is not None and argv_mentions(key, argv):
            source = "arg"
        elif (env_overrides and key in env_overrides
              and env.get(env_overrides[key]) not in (None, "")):
            source = "env"
        elif key in module_defaults and key in ns and \
                _differs(value, module_defaults[key]):
            source = "arg"
        elif key not in module_defaults and _value_in_argv(value, argv):
            # A POSITIONAL argument carries no flag, so `argv_mentions` cannot
            # see it. Without this branch `job` in `weekend_lab_jobs W4 --out x`
            # would be stamped `default`, which is exactly the false provenance
            # line this module exists to catch -- committed by the module
            # itself.
            source = "arg"
        elif key not in module_defaults:
            # No declared default to fall back on. With no command line to
            # check against, the namespace is the only source there is.
            source = "default" if argv is not None else "arg"
        else:
            source = "default"
        out[key] = {"value": _jsonable(value), "source": source}
    return out


def _value_in_argv(value: Any, argv: Sequence[str] | None) -> bool:
    """Does this value appear on the command line as a bare (non-flag) token?"""
    if argv is None or value is None or isinstance(value, bool):
        return False
    want = str(value)
    if not want:
        return False
    return any(str(t) == want and not str(t).startswith("-") for t in argv)


def _differs(a: Any, b: Any) -> bool:
    try:
        return str(a) != str(b)
    except Exception:                                            # noqa: BLE001
        return True


def _jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, Mapping):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    return str(v)


# ─────────────────────────────────────────────────────────── the block itself

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_commit_short(root: str | os.PathLike[str] | None = None) -> str | None:
    """The short HEAD sha, read off `.git` directly.

    No subprocess: a receipt writer that shells out inherits the shell's
    failure modes, and this must work inside a test with no git on PATH.
    Returns None when it cannot be determined -- never a guess, never "".
    """
    start = Path(root) if root is not None else Path(__file__).resolve()
    for base in [start, *start.parents]:
        gitdir = base / ".git"
        if gitdir.is_file():                       # a worktree: ".git" is a file
            try:
                line = gitdir.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not line.startswith("gitdir:"):
                return None
            gitdir = Path(line.split(":", 1)[1].strip())
        if not gitdir.is_dir():
            continue
        try:
            head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not head.startswith("ref:"):
            return head[:12] or None
        ref = head.split(":", 1)[1].strip()
        p = gitdir / ref
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8").strip()[:12]
            except OSError:
                return None
        packed = gitdir / "packed-refs"
        if packed.is_file():
            try:
                for row in packed.read_text(encoding="utf-8").splitlines():
                    if row.endswith(" " + ref):
                        return row.split(" ", 1)[0][:12]
            except OSError:
                return None
        return None
    return None


def provenance_block(argv: Sequence[str],
                     resolved_config: Mapping[str, Any],
                     tracker: InputTracker | Iterable[Mapping[str, Any]] | None,
                     *,
                     git_commit: str | None = None) -> dict[str, Any]:
    """The `_provenance` value.

    The key names are FIXED -- four sibling agents write this schema in the
    same session, so renaming a key here silently invalidates their receipts.
    """
    if isinstance(tracker, InputTracker):
        inputs = tracker.entries()
    elif tracker is None:
        inputs = []
    else:
        inputs = [dict(e) for e in tracker]
    return {
        "sys_argv": [str(a) for a in (argv or [])],
        "resolved_config": _jsonable(dict(resolved_config or {})),
        "_inputs_opened": inputs,
        "git_commit": git_commit if git_commit is not None else git_commit_short(),
        "generated_utc": _now(),
    }


def attach(receipt: dict, argv: Sequence[str],
           resolved_config: Mapping[str, Any],
           tracker: InputTracker | None,
           *, git_commit: str | None = None) -> dict:
    """Stamp a receipt in place, at the ONE place it is written.

    The W4b bug happened because provenance was written by hand at each call
    site; a helper that takes the finished payload is the shape that keeps
    there being one site.
    """
    receipt["_provenance"] = provenance_block(
        argv, resolved_config, tracker, git_commit=git_commit)
    return receipt


# ─────────────────────────────────────────────────────────────── the checker

def _looks_like_a_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if not value.lower().endswith(_PATHY_SUFFIXES):
        return False
    return ("/" in value) or ("\\" in value)


def _is_input_key(key: str) -> bool:
    low = key.lower()
    if any(h in low for h in _OUTPUT_HINTS):
        return False
    return bool(_INPUT_KEY_RE.search(low))


def stamped_input_paths(receipt: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Every `(dotted.key, value)` in the receipt that claims to be an input file.

    `_provenance` itself is skipped -- it is the record being checked, not a
    claim to be checked against.
    """
    found: list[tuple[str, str]] = []

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, Mapping):
            for k, v in node.items():
                if k == "_provenance" and not trail:
                    continue
                sub = f"{trail}.{k}" if trail else str(k)
                if isinstance(v, str):
                    if _is_input_key(str(k)) and _looks_like_a_path(v):
                        found.append((sub, v))
                else:
                    walk(v, sub)
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{trail}[{i}]")

    walk(receipt, "")
    return found


def _matches_opened(stamped: str, opened: Sequence[str]) -> bool:
    if normalise(stamped) in opened:
        return True
    # A receipt written from the repo root may stamp a relative path while the
    # tracker recorded the absolute one. Suffix match on the normalised
    # spelling covers that without weakening the check: the W4b failure had a
    # different basename AND a different directory.
    rel = os.path.normcase(str(stamped).replace("\\", "/")).replace("\\", "/")
    rel = rel.lstrip(".").lstrip("/")
    if not rel:
        return False
    return any(o.endswith("/" + rel) or o == rel for o in opened)


def check_receipt(receipt: Mapping[str, Any], *,
                  require_inputs: bool = True,
                  verify_hashes: bool = False) -> list[str]:
    """Named findings, one string each. An empty list means the receipt is clean.

    `verify_hashes` is OFF by default because it re-reads every input from disk
    and some are 50 MB+; the session sweep leaves it off, the provenance test
    turns it on deliberately.
    """
    if not isinstance(receipt, Mapping):
        return [f"MISSING_PROVENANCE: receipt is a {type(receipt).__name__}, "
                f"not an object"]
    out: list[str] = []
    prov = receipt.get("_provenance")
    if not isinstance(prov, Mapping):
        return ["MISSING_PROVENANCE: no `_provenance` block. Stamp it with "
                "backend.services.receipt_provenance.provenance_block()."]

    for key in ("sys_argv", "resolved_config", "_inputs_opened"):
        if key not in prov:
            out.append(f"MALFORMED_PROVENANCE: `_provenance` has no `{key}`")

    argv = prov.get("sys_argv") or []
    raw_inputs = prov.get("_inputs_opened")
    inputs = raw_inputs if isinstance(raw_inputs, list) else []
    opened = [normalise(e.get("path", "")) for e in inputs
              if isinstance(e, Mapping) and e.get("path")]

    if require_inputs and not opened:
        out.append("EMPTY_INPUTS: `_inputs_opened` is empty while inputs were "
                   "required. A number produced from no file it can name is a "
                   "number with no provenance.")

    # ── the W4b failure ──────────────────────────────────────────────────
    stamped = stamped_input_paths(receipt)
    if stamped and not opened:
        out.append(
            "NO_INPUTS_TRACKED: the receipt names input file(s) "
            + ", ".join(f"`{k}`" for k, _ in stamped[:4])
            + " but `_inputs_opened` is empty, so the stamp cannot be checked "
              "against what the loader actually opened.")
    else:
        for key, value in stamped:
            if _matches_opened(value, opened):
                continue
            out.append(
                f"UNOPENED_PATH_STAMPED: `{key}` names {value!r}, which is not "
                f"among the {len(opened)} path(s) the loader opened "
                f"({', '.join(opened[:3])}"
                f"{', ...' if len(opened) > 3 else ''}). This is the W4b "
                f"defect: a module default stamped in place of the argument "
                f"the job was handed.")

    # ── a `default` stamp on a key that was passed ───────────────────────
    cfg = prov.get("resolved_config")
    if isinstance(cfg, Mapping):
        for key, spec in cfg.items():
            if not isinstance(spec, Mapping):
                continue
            if spec.get("source") == "default" and argv_mentions(str(key), argv):
                out.append(
                    f"DEFAULT_SOURCE_BUT_PASSED: resolved_config[{key!r}] is "
                    f"marked `default` while `--{str(key).replace('_', '-')}` "
                    f"appears in sys_argv. The receipt is describing the "
                    f"module constant, not the run.")

    # ── the file on disk today ───────────────────────────────────────────
    if verify_hashes:
        for e in inputs:
            if not isinstance(e, Mapping) or not e.get("sha256"):
                continue
            p = Path(str(e.get("path", "")))
            if not p.is_file():
                out.append(f"STALE_OR_CHANGED: {p} is no longer on disk")
                continue
            try:
                now = sha256_of(p)
            except OSError as exc:
                out.append(f"STALE_OR_CHANGED: {p} unreadable "
                           f"({type(exc).__name__})")
                continue
            if now != e["sha256"]:
                out.append(
                    f"STALE_OR_CHANGED: {p} hashes {now[:12]} today, stamped "
                    f"{str(e['sha256'])[:12]}. Not a defect in the receipt -- "
                    f"inputs change -- but the run is no longer reproducible "
                    f"from this file as it stands.")
    return out


def hard_failures(findings: Iterable[str]) -> list[str]:
    """Findings that are defects in the RECEIPT, not facts about the world."""
    return [f for f in findings if not f.startswith(SOFT_PREFIXES)]
