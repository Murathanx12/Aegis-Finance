"""Fail-closed campaign accounting gate. No application imports before exec.

Only the exact llm_research legacy file is linked. Never seed/reset the durable
file on startup. This is not a reservation system or a financial-state writer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid
from datetime import datetime
from decimal import Decimal

SHA = "16f5715663bd6a88cb3f8d8d3e716c65f45386cc"
LEGACY = Path("/app/docs/BUILD1/llm_ledger.jsonl")
PREFIX = Path("/data/optimus/campaign_ledger")
TARGET = PREFIX / "llm_ledger.jsonl"
MAX_BYTES = 64 * 1024 * 1024


class Refused(RuntimeError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Refused("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_float=Decimal, parse_constant=lambda _: (_ for _ in ()).throw(Refused("NONFINITE_JSON")))


def history(raw, *, allow_empty=False):
    if len(raw) > MAX_BYTES or (not raw and not allow_empty) or (raw and not raw.endswith(b"\n")):
        raise Refused("ABSENT_OVERSIZED_OR_TORN_HISTORY")
    total, rows = Decimal(0), 0
    for line in raw.splitlines():
        if not line.strip():
            raise Refused("BLANK_LEDGER_ROW")
        try:
            row = decode(line)
            cost = row["cost_usd"]
            if type(cost) not in (int, Decimal) or cost < 0 or not Decimal(cost).is_finite():
                raise ValueError
            timestamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
            if timestamp.utcoffset() is None or not isinstance(row["purpose"], str) or not isinstance(row["model"], str):
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise Refused("MALFORMED_OR_UNPRICED_HISTORY") from None
        total += cost
        rows += 1
    return {"rows": rows, "cost_usd": str(total), "bytes": len(raw), "sha256": digest(raw)}


def stable_read(path):
    if path.is_symlink() or not path.is_file():
        raise Refused("EXPECTED_REGULAR_FILE")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_BYTES:
            raise Refused("HISTORY_TOO_LARGE")
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    now = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if identity(before) != identity(after) or identity(after) != identity(now) or len(raw) != before.st_size:
        raise Refused("SOURCE_CHANGED_DURING_READ")
    return raw


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_new(path, raw):
    """Exclusive create; existing bytes are never replaced."""
    try:
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        fsync_dir(path.parent)
    except FileExistsError:
        if stable_read(path) != raw:
            raise Refused("EXISTING_DURABLE_FILE_DIFFERS")


def no_symlink_ancestors(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise Refused("SYMLINKED_PERSISTENT_PATH")


def mount_identity(mountpoint=Path("/data")):
    # This proves a separate mount, not Railway identity by itself. The reviewed
    # anchor must pin this actual mount source/fs/root as well as the platform
    # service/volume IDs; no directory-existence fallback is accepted.
    found = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        fields, fs = left.split(), right.split()
        if fields[4] == str(mountpoint):
            found.append({"mountpoint": fields[4], "root": fields[3], "fstype": fs[0], "source": fs[1]})
    if len(found) != 1:
        raise Refused("PERSISTENT_MOUNT_NOT_PROVEN")
    return found[0]


def verify_anchor(anchor, *, legacy=LEGACY, target=TARGET, prefix=PREFIX, source_root=Path("/app"), mount_check=mount_identity):
    if (anchor.get("schema") != "campaign-ledger-anchor/1" or anchor.get("review_status") != "REVIEWED_FOR_PRESTART"
            or anchor.get("source_sha") != SHA or anchor.get("campaign_cap_usd") != 30
            or anchor.get("legacy") != str(legacy) or anchor.get("target") != str(target)
            or anchor.get("persistent_prefix") != str(prefix) or target.parent != prefix):
        raise Refused("REVIEWED_ANCHOR_SCOPE_REQUIRED")
    no_symlink_ancestors(prefix)
    if mount_check() != anchor.get("mount_identity"):
        raise Refused("REVIEWED_VOLUME_MOUNT_MISMATCH")
    if not prefix.is_dir():
        raise Refused("REVIEWED_PERSISTENT_PREFIX_ABSENT")
    marker = prefix / "volume-anchor.json"
    if digest(stable_read(marker)) != anchor.get("volume_marker_sha256"):
        raise Refused("PERSISTENT_PREFIX_ANCHOR_MISMATCH")
    sources = anchor.get("source_files", {})
    if set(sources) != {"backend/config.py", "backend/services/llm_research.py"}:
        raise Refused("EXACT_DEPLOYED_SOURCES_REQUIRED")
    for name, expected in sources.items():
        if digest(stable_read(source_root / name)) != expected:
            raise Refused("DEPLOYED_SOURCE_MISMATCH")
    raw = stable_read(target)
    summary = history(raw)
    cut = anchor["prefix_bytes"]
    if type(cut) is not int or cut <= 0 or len(raw) < cut or digest(raw[:cut]) != anchor["prefix_sha256"]:
        raise Refused("DURABLE_REVIEWED_PREFIX_MISSING_OR_SHORTENED")
    if history(raw[:cut])["rows"] != anchor["prefix_rows"]:
        raise Refused("REVIEWED_PREFIX_ROW_COUNT_MISMATCH")
    witnesses = stable_read(prefix / "continuity.jsonl")
    wcut = anchor["witness_prefix_bytes"]
    if (type(wcut) is not int or wcut <= 0 or len(witnesses) < wcut
            or digest(witnesses[:wcut]) != anchor["witness_prefix_sha256"] or not witnesses.endswith(b"\n")):
        raise Refused("REVIEWED_CONTINUITY_WITNESS_MISSING")
    previous = 0
    for line in witnesses.splitlines():
        witness = decode(line)
        size = witness["through_bytes"]
        if (witness.get("schema") != "campaign-continuity/1" or type(size) is not int
                or size < previous or size > len(raw) or digest(raw[:size]) != witness["prefix_sha256"]
                or history(raw[:size])["rows"] != witness["rows"]):
            raise Refused("PERSISTENT_HISTORY_REWOUND_OR_DIVERGED_FROM_WITNESS")
        previous = size
    return raw, summary


def witness_line(raw):
    summary = history(raw)
    return (json.dumps({"schema": "campaign-continuity/1", "through_bytes": len(raw),
                        "prefix_sha256": summary["sha256"], "rows": summary["rows"]}, sort_keys=True) + "\n").encode()


def append_witness(prefix, raw):
    path = prefix / "continuity.jsonl"
    prior = stable_read(path)
    line = witness_line(raw)
    if prior.splitlines()[-1] == line.rstrip(b"\n"):
        return
    with path.open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_dir(prefix)


class Links:
    def is_link(self, path): return path.is_symlink()
    def read_link(self, path): return os.readlink(path)
    def install(self, path, target):
        temp = path.with_name(path.name + ".link-" + uuid.uuid4().hex)
        os.symlink(str(target), temp)
        try:
            os.replace(temp, path)
            fsync_dir(path.parent)
        finally:
            if temp.is_symlink(): temp.unlink()


def prepare(anchor, *, legacy=LEGACY, target=TARGET, prefix=PREFIX, source_root=Path("/app"), mount_check=mount_identity, links=None):
    links = links or Links()
    no_symlink_ancestors(legacy.parent)
    raw, summary = verify_anchor(anchor, legacy=legacy, target=target, prefix=prefix,
                                  source_root=source_root, mount_check=mount_check)
    if links.is_link(legacy):
        if links.read_link(legacy) != str(target):
            raise Refused("FOREIGN_LEGACY_SYMLINK")
        append_witness(prefix, raw)
        return {**summary, "status": "EXACT_DURABLE_LINK_ALREADY_PRESENT"}
    if legacy.exists():
        old = stable_read(legacy)
        history(old, allow_empty=True)
        if not raw.startswith(old):
            raise Refused("LEGACY_AHEAD_OR_DIVERGENT_REQUIRES_FROZEN_HANDOFF")
        archive = prefix / ("legacy-preimage-" + digest(old) + ".jsonl")
        durable_new(archive, old)
        if stable_read(legacy) != old:
            raise Refused("LEGACY_CHANGED_BEFORE_LINK")
    else:
        legacy.parent.mkdir(parents=True, exist_ok=True)
    # Never modify durable target here. A later append does not invalidate the
    # prefix. Link only after preserving a compatible immutable old file.
    no_symlink_ancestors(legacy.parent)
    links.install(legacy, target)
    if not links.is_link(legacy) or links.read_link(legacy) != str(target):
        raise Refused("EXACT_LINK_READBACK_FAILED")
    append_witness(prefix, raw)
    return {**summary, "status": "DURABLE_SINGLE_FILE_LINK_READY"}


def enforce_production(*, environ=None, anchor_path=PREFIX / "anchor.json",
                       anchor_sha256="92b9a952e8f7f801cde92887436260eff89a9648cd4bbbf7b266134688eda5eb",
                       prepare_fn=prepare):
    """Application import gate; defaults intentionally refuse until handoff is bound.

    No application/config/router import is reachable here. Local development
    remains local; a Railway deployment must use the exact reviewed service and
    preserved campaign prefix. This does not create a new campaign budget.
    """
    env = os.environ if environ is None else environ
    railway_markers = ("RAILWAY_SERVICE_ID", "RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID",
                       "RAILWAY_DEPLOYMENT_ID", "RAILWAY_GIT_COMMIT_SHA")
    if not any(env.get(name) for name in railway_markers):
        return {"status": "LOCAL_NOT_APPLIED"}
    expected = {"RAILWAY_PROJECT_ID": "8105f1ef-f39d-4a82-971e-e5d02db5ac8c",
                "RAILWAY_SERVICE_ID": "05e102b9-b7ee-479d-9257-a506f74730d5",
                "RAILWAY_ENVIRONMENT_ID": "c36ec00c-9250-494d-ae1c-3d07c2bcf60a"}
    if any(env.get(name) != value for name, value in expected.items()):
        raise Refused("EXACT_RAILWAY_SERVICE_SCOPE_REQUIRED")
    if env.get("AEGIS_REPO_ROOT") not in (None, "", "/app"):
        raise Refused("UNREVIEWED_APPLICATION_ROOT")
    if env.get("AEGIS_DATA_DIR") != "/data":
        raise Refused("EXACT_PERSISTENT_DATA_ROOT_REQUIRED")
    raw = stable_read(anchor_path)
    if digest(raw) != anchor_sha256:
        raise Refused("STARTUP_ANCHOR_HASH_MISMATCH")
    receipt = prepare_fn(decode(raw))
    print(json.dumps({"campaign_ledger_prestart": receipt}), flush=True)
    return receipt


def start(anchor, argv, *, prepare_fn=prepare, exec_fn=os.execvp):
    port = os.environ.get("PORT", "8000")
    if not port.isdecimal() or not 0 < int(port) < 65536:
        raise Refused("VALID_PORT_REQUIRED")
    expected = ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", port]
    if argv != expected:
        raise Refused("EXACT_REVIEWED_UVICORN_COMMAND_REQUIRED")
    receipt = prepare_fn(anchor)
    print(json.dumps({"campaign_ledger_prestart": receipt}), flush=True)
    exec_fn(argv[0], argv)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--anchor-sha256", required=True)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        raw = stable_read(Path(args.anchor))
        if digest(raw) != args.anchor_sha256:
            raise Refused("STARTUP_ANCHOR_HASH_MISMATCH")
        start(decode(raw), args.argv[1:] if args.argv[:1] == ["--"] else args.argv)
    except Exception as exc:
        print(json.dumps({"status": "CAMPAIGN_LEDGER_PRESTART_REFUSED", "reason": str(exc) if isinstance(exc, Refused) else type(exc).__name__}), file=sys.stderr)
        sys.exit(78)
