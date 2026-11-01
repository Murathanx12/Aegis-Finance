"""Private, bounded C05 acquisition from an exact plan; no native-store writes."""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from filelock import FileLock


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.now(timezone.utc)


def stream_rows(conn, query, params, *, deadline, max_rows=250000,
                max_logical_bytes=64 * 1024**2, batch_rows=2000, clock=utc):
    """Fetch a complete SELECT through a non-holdable server-side cursor.

    Bounds apply to rows per FETCH and accepted logical data, not process RSS,
    wire bytes or server work. A single large field/batch can exceed the logical
    acceptance cap before refusal. Never publish a partial declared partition.
    Each SELECT has its own read-only transaction, rolled back even on success.
    """
    def check_deadline():
        if clock() >= deadline:
            raise TimeoutError("CHECKPOINT_DEADLINE")

    check_deadline()
    if max_rows < 1 or max_logical_bytes < 1 or batch_rows < 1:
        raise ValueError("INVALID_STREAM_LIMITS")
    original_autocommit = conn.autocommit
    cursor = None
    failure = None
    try:
        # Named cursors require a transaction. set_session configures the next
        # BEGIN; the explicit SET also asserts this transaction's write policy.
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as control:
            control.execute("SET TRANSACTION READ ONLY")
            control.execute("SELECT current_setting('transaction_read_only')")
            if control.fetchone()[0] != "on":
                raise RuntimeError("READ_ONLY_NOT_CONFIRMED")
        check_deadline()
        cursor = conn.cursor(name="c05_" + uuid4().hex,
                             scrollable=False, withhold=False)
        cursor.itersize = batch_rows
        cursor.arraysize = batch_rows
        cursor.execute(query, params)
        check_deadline()
        rows, size, names, source_types = [], 0, None, None
        while True:
            check_deadline()
            # Fetch at most the remaining allowance plus one refusal witness.
            batch = cursor.fetchmany(min(batch_rows, max_rows - len(rows) + 1))
            check_deadline()
            # Psycopg named cursors expose description after the first FETCH,
            # including the empty-result case, rather than after DECLARE.
            if names is None:
                names = [d.name for d in cursor.description]
                source_types = {d.name: d.type_code for d in cursor.description}
            if not batch:
                return names, source_types, rows
            size += sum(sum(len(v.encode("utf-8")) if isinstance(v, str) else 16
                            for v in row) for row in batch)
            if len(rows) + len(batch) > max_rows or size > max_logical_bytes:
                raise RuntimeError("PARTITION_REQUIRES_SMALLER_KEY_RANGE")
            rows.extend(batch)
    except Exception as exc:
        failure = exc
        raise
    finally:
        try:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as close_error:
                    if failure is None:
                        raise
                    # Failed DECLARE/FETCH can abort the transaction so CLOSE
                    # also fails. Preserve the original SQLSTATE (e.g. 42501).
                    failure.add_note("CURSOR_CLOSE_FAILED_" + type(close_error).__name__)
        finally:
            try:
                conn.rollback()
            except Exception:
                # A failed rollback must never leave a reusable live writer or
                # broken transaction for a later partition on this connection.
                conn.close()
                raise
            else:
                conn.autocommit = original_autocommit


def connect():
    """Existing libpq storage only. Never return/print credentials or raw errors."""
    import psycopg2
    paths = ([Path(os.environ["PGPASSFILE"])] if os.environ.get("PGPASSFILE") else [])
    if os.environ.get("APPDATA"):
        paths.append(Path(os.environ["APPDATA"]) / "postgresql/pgpass.conf")
    paths.append(Path.home() / ".pgpass")
    for path in dict.fromkeys(paths):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            values = re.split(r"(?<!\\):", line)
            if len(values) != 5:
                continue
            values = [re.sub(r"\\(.)", r"\1", x) for x in values]
            host, port, database, user, password = values
            if "wrds" not in host.lower() or database.lower() != "wrds" or not user or not password:
                continue
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                conn = psycopg2.connect(host=host, port=port, dbname=database, user=user,
                    passfile=str(path), sslmode="require", connect_timeout=8,
                    options="-c statement_timeout=15000 -c default_transaction_read_only=on",
                    application_name="aegis_c05_incremental", keepalives=1,
                    keepalives_idle=5, keepalives_interval=2, keepalives_count=1,
                    tcp_user_timeout=8000)
            conn.autocommit = True
            return conn
    raise RuntimeError("LOCAL_CREDENTIAL_STORAGE_UNAVAILABLE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--stop-new-work-utc", required=True)
    args = parser.parse_args()
    raw = args.plan.read_bytes()
    if sha(raw) != args.plan_sha256:
        raise SystemExit("PLAN_PIN_MISMATCH")
    plan = json.loads(raw)
    deadline = datetime.fromisoformat(args.stop_new_work_utc.replace("Z", "+00:00"))
    # Both initial and resumed runs must explicitly name a deadline, never run
    # across the protected local 16:35-17:10 interval.
    if deadline.tzinfo is None or utc() >= deadline:
        raise SystemExit("DEADLINE_ALREADY_PASSED")
    local = utc().astimezone(timezone.utc)
    quiet_from = datetime(2026, 10, 25, 8, 35, tzinfo=timezone.utc)
    quiet_until = datetime(2026, 10, 25, 9, 10, tzinfo=timezone.utc)
    if quiet_from <= local < quiet_until or (local < quiet_from and deadline > quiet_from):
        raise SystemExit("QUIET_WINDOW_REFUSAL")
    root = Path(plan["output_root"]).resolve()
    expected = args.plan.resolve().parent / "artifacts"
    if root != expected or plan.get("schema") != "C05_INCREMENTAL_PLAN/1":
        raise SystemExit("PRIVATE_OUTPUT_SCOPE_MISMATCH")
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root.parent / "ACQUISITION_MANIFEST.json"
    with FileLock(str(manifest_path) + ".lock", timeout=1):
        manifest = (json.loads(manifest_path.read_text()) if manifest_path.exists() else
                    {"schema": "C05_WRDS_incremental_receipts/1", "plan_sha256": args.plan_sha256,
                     "jobs": {}, "database_writes": 0, "native_store_writes": 0})
        if manifest["plan_sha256"] != args.plan_sha256:
            raise SystemExit("EXISTING_MANIFEST_PLAN_MISMATCH")
        conn = None

        def checkpoint():
            manifest["updated_at"] = utc().isoformat()
            temp = manifest_path.with_suffix(".json.tmp")
            with temp.open("w", encoding="utf-8") as stream:
                json.dump(manifest, stream, sort_keys=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, manifest_path)

        def fetch(key, query, params=(), *, max_rows=250000):
            previous = manifest["jobs"].get(key)
            if previous and previous["status"] == "COMPLETE":
                path = Path(previous["path"])
                if sha(path.read_bytes()) != previous["sha256"]:
                    raise RuntimeError("RESUME_ARTIFACT_HASH_MISMATCH")
                return pq.read_table(path)
            if previous and previous.get("sqlstate") in ("42501", "42P01"):
                return None  # retain explicit entitlement/object gate, no blind retry
            reused = plan.get("reuse_jobs", {}).get(key)
            if reused:
                path = Path(reused["path"])
                if sha(path.read_bytes()) != reused["sha256"]:
                    raise RuntimeError("REUSED_ARTIFACT_HASH_MISMATCH")
                table = pq.read_table(path)
                if table.num_rows != reused["rows"]:
                    raise RuntimeError("REUSED_ARTIFACT_ROWS_MISMATCH")
                manifest["jobs"][key] = {**reused, "reused_existing_verified_artifact": True}
                checkpoint()
                return table
            if utc() >= deadline:
                raise TimeoutError("CHECKPOINT_DEADLINE")
            info = {"started_at": utc().isoformat(), "status": "STARTED", "query_template_sha256": sha(query.encode())}
            manifest["jobs"][key] = info
            checkpoint()
            try:
                names, source_types, rows = stream_rows(
                    conn, query, params, deadline=deadline, max_rows=max_rows)
                info["source_types"] = source_types
                info["acquisition_cursor"] = "named_server_side_nonholdable_readonly_transaction"
                info["fetch_rows_max"] = 2000
                info["logical_acceptance_bytes_max"] = 64 * 1024**2
                info["logical_cap_is_not_RSS_or_wire_bound"] = True
                # No LIMIT or truncation: only a completely fetched partition
                # can be marked COMPLETE. Preserve native scalar/text values.
                table = pa.Table.from_pylist([dict(zip(names, row)) for row in rows]) if rows else pa.table({n: [] for n in names})
                buffer = io.BytesIO()
                pq.write_table(table, buffer)
                payload = buffer.getvalue()
                directory = root / key
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / (sha(payload) + ".parquet")
                if path.exists():
                    if sha(path.read_bytes()) != sha(payload):
                        raise RuntimeError("CONTENT_ADDRESS_COLLISION")
                else:
                    with path.open("xb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                back = pq.read_table(path)
                if not back.equals(table):
                    raise RuntimeError("ARTIFACT_READBACK_MISMATCH")
                info.update(status="COMPLETE", rows=table.num_rows, columns=names,
                    bytes=len(payload), sha256=sha(payload), path=str(path),
                    readback_equal=True, completed_at=utc().isoformat())
                checkpoint()
                print(json.dumps({"event": "PRIVATE_PARTITION_OBTAINED", "job": key,
                    "rows": table.num_rows, "bytes": len(payload), "sha256": sha(payload)}), flush=True)
                return table
            except Exception as exc:
                info.update(status="CHECKPOINTED" if isinstance(exc, TimeoutError) else "REFUSED_OR_FAILED",
                    exception_type=type(exc).__name__, sqlstate=getattr(exc, "pgcode", None), completed_at=utc().isoformat())
                if type(exc) is RuntimeError and re.fullmatch(r"[A-Z0-9_]+", str(exc)):
                    info["controlled_gate"] = str(exc)
                checkpoint()
                print(json.dumps({"event": "PARTITION_NOT_COMPLETED", "job": key,
                    "exception_type": type(exc).__name__, "sqlstate": getattr(exc, "pgcode", None)}), flush=True)
                if isinstance(exc, TimeoutError):
                    raise
                return None

        try:
            conn = connect()
            with conn.cursor() as cursor:
                cursor.execute("select current_setting('transaction_read_only')")
                if cursor.fetchone()[0] != "on":
                    raise RuntimeError("READ_ONLY_NOT_CONFIRMED")
            bounds = plan["initial_partition"]
            prefix = "transcripts_" + bounds["from_utc"][:10]
            headers = fetch(prefix + "/headers",
                "select * from ciq_transcripts.ciqtranscript where transcriptcreationdateutc >= %s and transcriptcreationdateutc < %s order by transcriptcreationdateutc,transcriptid",
                (bounds["from_utc"], bounds["until_utc"]))
            if headers is None or not headers.num_rows:
                manifest["next_gate"] = "NO_HEADER_ROWS_IN_EXPLICIT_DAY; inspect source high-water before any new date partition"
                return
            ids = sorted(set(headers["transcriptid"].to_pylist()))
            if len(ids) != headers.num_rows:
                raise RuntimeError("DUPLICATE_HEADER_TRANSCRIPT_ID")
            components = fetch(prefix + "/components",
                "select * from ciq_transcripts.ciqtranscriptcomponent where transcriptid = any(%s) order by transcriptid,componentorder,transcriptcomponentid", (ids,))
            if components is not None:
                people = sorted({i for i in components["transcriptpersonid"].to_pylist() if i is not None})
                if people:
                    fetch(prefix + "/people", "select * from ciq_transcripts.ciqtranscriptperson where transcriptpersonid = any(%s) order by transcriptpersonid", (people,))
            for name in ["ciqtranscriptcomponenttype", "ciqtranscriptspeakertype", "ciqtranscriptcollectiontype", "ciqtranscriptpresentationtype"]:
                fetch("dimensions/" + name, "select * from ciq_transcripts." + name + " order by 1", max_rows=10000)
            detail = fetch(prefix + "/detail", "select * from ciq_transcripts.wrds_transcript_detail where transcriptid = any(%s) order by transcriptid", (ids,))
            if detail is not None and detail.num_rows and "companyid" in detail.column_names:
                companies = sorted({i for i in detail["companyid"].to_pylist() if i is not None})
                fetch(prefix + "/companies", "select companyid,companyname,countryid,companytypeid,companystatustypeid from ciq_common.ciqcompany where companyid = any(%s) order by companyid", (companies,))
                fetch(prefix + "/dated_cusip", "select * from ciq_common.wrds_cusip where companyid = any(%s) order by companyid,startdate,cusip", (companies,))
                fetch(prefix + "/dated_gvkey", "select * from ciq_common.wrds_gvkey where companyid = any(%s) order by companyid,startdate,gvkey", (companies,))
            manifest["next_gate"] = "RUN_OFFLINE_ROLE_TEXT_AND_IDENTIFIER_JOIN_READBACK; remaining dates/families remain queued"
        except Exception as exc:
            manifest["run_gate"] = {"exception_type": type(exc).__name__, "sqlstate": getattr(exc, "pgcode", None), "at": utc().isoformat()}
            print(json.dumps({"event": "BOUNDED_RUN_STOPPED", **manifest["run_gate"]}), flush=True)
        finally:
            if conn is not None:
                conn.close()
            manifest["connection_closed"] = True
            checkpoint()
            print(json.dumps({"event": "CONNECTION_CLOSED_CHECKPOINT_SAVED", "manifest_sha256": sha(manifest_path.read_bytes())}), flush=True)


if __name__ == "__main__":
    main()
