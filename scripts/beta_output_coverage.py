"""Bounded read-only generated-output census; private receipts, never grading.

All discovered files receive a disposition. Row counts are only observations
actually decoded; protected and bounded files have unknown row counts, not zero.
Sources are pinned to complete prefixes; runtime appends are excluded. No mtime
is interpreted as an output date. No scores or outcome values are emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

from scripts.original_evidence_audit import EvidenceRefused

PROTECTED = re.compile(r'sealed|holdout|(?:^|/)gold(?:/|\.)|iif1|trial|arena|amnesia|congress|insider.*ic|ark.*ic|nn_lab|straddle_forward|teacher_library|shadow_bayes', re.I)
RESOLUTION = {'resolved_at', 'outcome', 'brier', 'resolution_detail', 'void_reason',
              'calibration_bucket', 'vs_benchmark', 'vs_control', 'voided_at', 'voided_by'}
STAMP_FIELDS = ('made_at', 'generated_utc', 'generated_at', 'timestamp', 'ts',
                'recorded_at', 'as_of', 'asof', 'date', 'frozen_utc', 'first_seen_utc')
IDENTITY_FIELDS = ('prediction_id', 'event_id', 'call_id', 'decision_id', 'id')
CONSUMERS = {
    'forecast': 'candidate_route_unverified: backend.services.forecast_grader / evidence_population / reputation; schema, target and actual consumption not proven by this census',
    'llm_calls': 'backend.services.llm_telemetry; ledger_archive',
    'evidence_memory': 'evidence-memory retrieval; ledger_archive',
    'paper_accounts': 'paper account ROI/book_dna/results_voice (marks are descriptive)',
    'typed_events': 'night_l2_typed_events; model/replay pipeline',
    'x_lane': 'X-lane replay/model pipeline',
    'strategy_library': 'strategy library frozen-book evaluation',
    'shadow_bayes': 'scripts.shadow_grade (protected trial read gates still apply)',
    'news_corpus': 'PIT event extraction/replay',
    'decision_story': 'backend.services.regret_ledger; HOLD and alternatives at 5/21/63 sessions',
    'expected_return': 'backend.services.expected_return; held-out dated component cells, not forecast-event counts',
    'decisions': 'decision/autopsy history; context events, not one row per decision ID',
    'promises': 'commitment tracking; excluded from E[r] by design',
}
GENERATOR_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def family_for(rel):
    parts = Path(rel).parts
    name = parts[0] if len(parts) > 1 else Path(rel).stem
    if 'prediction' in name or name in ('forecasts', 'resolutions'):
        return 'forecast'
    return re.sub(r'[_-]\d{4}[-_]\d{2}(?:[-_]\d{2})?.*$', '', name)


def stamp(row):
    for key in STAMP_FIELDS:
        v = row.get(key)
        if isinstance(v, str):
            try:
                return date.fromisoformat(v[:10]).isoformat()
            except ValueError:
                pass
    return None


def dimension(value, fallback):
    """Technical class labels only; never repr a payload or free-form evidence."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_:.+/\-]{1,160}', value):
        return value
    return fallback


def census(roots, *, as_of, max_file_bytes=256 << 20, max_total_bytes=2 << 30,
           max_json_bytes=4 << 20, max_unique_records=100_000, metadata_roots=(), identity_db=None):
    """No mutation beneath roots. Stable results for identical bytes and as_of.

    Identity dedup is scoped to root + ledger family + task + horizon. Versions
    with differing immutable bytes are conflicts, never silently collapsed.
    Mutable outcome status from an active copy outranks its unresolved archive.
    """
    if identity_db and any(Path(identity_db).resolve().is_relative_to(Path(p).resolve()) for p in roots.values()):
        raise EvidenceRefused('scratch identity database must be outside every source root')
    today = date.fromisoformat(as_of)
    result = {'schema': 'beta_output_coverage/1', 'generator_sha256': GENERATOR_SHA256,
              'as_of': as_of, 'roots': {},
              'sources': [], 'file_families': {}, 'row_families': {}, 'errors': [],
              'complete': True, 'limits': {'max_file_bytes': max_file_bytes,
                  'max_total_bytes': max_total_bytes, 'max_json_bytes': max_json_bytes,
                  'max_unique_records': max_unique_records},
              'count_semantics': {'raw': 'decoded records entering their declared view, including archived copies; split folded forecasts are logical rows; physical stream rows are separately in sources.rows',
                  'unique': 'immutable identity union within family/task/horizon',
                  'graded': 'outcome-present rows; no skill metrics',
                  'due_ungraded': 'due by recorded calendar date only; not market-close eligibility or grading authorization',
                  'daily_delta': 'unique rows whose own dated stamp equals as_of',
                  'cells': 'distinct family/task/horizon groups; not forecast rows'},
              'limitations': ['Cloud stores are not live-enumerated; existing local backup receipts only.',
                  'Static consumer names are routing hints, not proof of live consumption.',
                  'Protected research outputs are metadata only; no early scores or outcomes.',
                  'Parquet data panels use footer metadata only; usable rows and grading unknown.']}
    result['limitations'].append('Quarantine counts identify persisted flags only; the official live/campaign quarantine guard was not invoked, so an absent flag is not proof of eligibility.')
    # Private scratch identity index contains hashes/status only, never raw rows.
    # Disk backing makes archive unions independent of available process RAM.
    db = sqlite3.connect(str(identity_db) if identity_db else ':memory:')
    # Scratch only: a crash discards the census, never modifies any input.
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('PRAGMA synchronous=OFF')
    db.execute('PRAGMA cache_size=-32768')
    db.execute('DROP TABLE IF EXISTS coverage_identity')
    db.execute('CREATE TABLE coverage_identity (family TEXT, identity TEXT, hash TEXT, status TEXT, terminal TEXT, PRIMARY KEY(family, identity)) WITHOUT ROWID')
    db.execute('DROP TABLE IF EXISTS coverage_split_forecast')
    db.execute('DROP TABLE IF EXISTS coverage_split_terminal')
    db.execute('CREATE TABLE coverage_split_forecast (root TEXT, identity TEXT, PRIMARY KEY(root, identity)) WITHOUT ROWID')
    db.execute('CREATE TABLE coverage_split_terminal (root TEXT, identity TEXT, hash TEXT, source TEXT, PRIMARY KEY(root, identity)) WITHOUT ROWID')
    unique_count = 0
    forecast_hashes = {}
    consumed = 0
    memory_limited = False

    def error(path, reason, **extra):
        result['errors'].append({'path': str(path), 'reason': reason, **extra})
        result['complete'] = False

    def observe(row, source, label, fam):
        nonlocal memory_limited, unique_count
        if not isinstance(row, dict):
            error(source, 'non_object_row')
            return
        forecast = 'prediction_id' in row and 'event' not in row
        task = dimension(row.get('observable') or row.get('task') or row.get('event') or row.get('row_type') or row.get('event_type'), 'unspecified')
        horizon = dimension(row.get('horizon_days') or row.get('horizon'), 'unspecified')
        mechanism = dimension(row.get('mechanism_id') or row.get('specialist'), 'UNATTRIBUTED')
        group = f'{label}:forecast:{mechanism}|{task}|{horizon}' if forecast else f'{label}:{fam}|{task}|{horizon}'
        g = result['row_families'].setdefault(group, {'unit': 'forecast' if forecast else 'event_or_record',
            'consumer': CONSUMERS.get('forecast' if forecast else fam, 'awaiting_evidence: consumer/grader unverified'),
            'raw': 0, 'unique': 0, 'duplicates': 0, 'conflicts': 0, 'states': Counter(),
            'first_date': None, 'last_date': None, 'daily_delta': 0,
            'undated': 0, 'identity_hash': hashlib.sha256(), 'sources': set(),
            'evidence_classes': Counter()})
        g['raw'] += 1
        g['sources'].add(str(source))
        immutable = {k: v for k, v in row.items() if k not in RESOLUTION} if forecast else row
        h = digest(immutable)
        # A decision id denotes a whole story with repeated alternatives/events.
        # Only forecasts/calls/explicit event IDs promise record-level identity.
        id_fields = IDENTITY_FIELDS if forecast else ('event_id', 'call_id')
        identity = next((str(row[k]) for k in id_fields if row.get(k) is not None), h)
        key = (group, digest(identity))
        status = 'context_record'
        if forecast:
            if row.get('void_reason') or row.get('voided_at'):
                status = 'void'
            elif row.get('quarantined') or row.get('quarantine_reason'):
                status = 'quarantined'
            elif row.get('outcome') is not None:
                status = 'graded'
            else:
                try:
                    status = 'due_ungraded' if date.fromisoformat(str(row['resolves_after'])[:10]) <= today else 'pending'
                except (KeyError, ValueError):
                    status = 'unknown_due'
        terminal = digest({k: row.get(k) for k in RESOLUTION if k not in ('resolved_at', 'voided_at', 'voided_by')}) if status in ('graded', 'void') else None
        previous = db.execute('SELECT hash, status, terminal FROM coverage_identity WHERE family=? AND identity=?', key).fetchone()
        if previous:
            old_hash, old_status, old_terminal = previous
            if old_hash != h:
                g['conflicts'] += 1
                error(source, 'conflicting_original_identity', identity_sha256=digest(identity))
                return
            if terminal and old_terminal and terminal != old_terminal:
                g['conflicts'] += 1
                error(source, 'conflicting_terminal_outcome', identity_sha256=digest(identity))
                return
            g['duplicates'] += 1
            if status in ('graded', 'void', 'quarantined') and old_status in ('due_ungraded', 'pending', 'unknown_due'):
                g['states'][old_status] -= 1
                g['states'][status] += 1
                db.execute('UPDATE coverage_identity SET status=?, terminal=? WHERE family=? AND identity=?', (status, terminal, *key))
            elif status in ('graded', 'void') and old_status in ('graded', 'void') and status != old_status:
                error(source, 'conflicting_terminal_status', identity_sha256=digest(identity))
            return
        if unique_count >= max_unique_records:
            if not memory_limited:
                error(source, 'unique_record_memory_limit', cap=max_unique_records)
                memory_limited = True
            return
        db.execute('INSERT INTO coverage_identity VALUES (?, ?, ?, ?, ?)', (*key, h, status, terminal))
        unique_count += 1
        if unique_count % 65536 == 0:
            db.commit()
        g['unique'] += 1
        if forecast:
            forecast_hashes.setdefault(label, set()).add(h)
        evidence_class = row.get('evidence_population') or row.get('evidence') or 'unspecified'
        if not isinstance(evidence_class, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:.-]{0,79}', evidence_class):
            evidence_class = 'UNCLASSIFIED_STRUCTURED_OR_INVALID'
        g['evidence_classes'][evidence_class] += 1
        g['states'][status] += 1
        g['identity_hash'].update(h.encode('ascii') + b'\n')
        day = stamp(row)
        if day:
            g['first_date'] = min(g['first_date'] or day, day)
            g['last_date'] = max(g['last_date'] or day, day)
            g['daily_delta'] += day == as_of
        else:
            g['undated'] += 1

    for label, root_arg in sorted(roots.items(), key=lambda item: (item[0] != 'runtime', item[0])):
        root = Path(root_arg).resolve()
        if not root.is_dir():
            result['roots'][label] = {'path': str(root), 'status': 'inaccessible', 'files': None}
            error(root, 'root_inaccessible')
            continue
        result['roots'][label] = {'path': str(root), 'status': 'enumerated', 'files': 0}
        walk_errors = []
        paths = []
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_errors.append):
            dirs[:] = sorted(d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.venv'))
            paths.extend(Path(directory) / f for f in sorted(files))
        for e in walk_errors:
            error(root, 'walk_inaccessible', detail=str(e))
        # Logical split ledger is folded by the existing immutable-event implementation.
        logical = root / 'predictions.jsonl'
        migration = root / 'ledger_manifests/forecast_ledger/MIGRATION.json'
        split = migration.exists()
        def marker_state():
            try:
                st = migration.stat()
                return (True, st.st_size, st.st_mtime_ns)
            except FileNotFoundError:
                return (False,)
        initial_marker = marker_state()
        root_protected = label in metadata_roots or bool(PROTECTED.search(root.as_posix()))
        split_sources = []
        for path in sorted(paths, key=lambda p: (not ('prediction' in p.name or p.parent.name in ('forecasts', 'resolutions')), str(p))):
            rel = path.relative_to(root).as_posix()
            fam = family_for(rel)
            fk = label + ':' + fam
            ff = result['file_families'].setdefault(fk, {'files': 0, 'bytes': 0,
                'dispositions': Counter(), 'consumer': CONSUMERS.get(fam,
                    'awaiting_evidence: consumer/grader unverified'), 'row_count': None})
            src = {'root': label, 'path': rel, 'family': fk, 'coverage': 'metadata_only',
                   'sha256': None, 'rows': None, 'first_date': None, 'last_date': None}
            result['sources'].append(src)
            result['roots'][label]['files'] += 1
            try:
                stat = path.stat()
                src['bytes'] = stat.st_size
                ff['files'] += 1
                ff['bytes'] += stat.st_size
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    src['coverage'] = 'excluded_symlink'
                elif root_protected or PROTECTED.search(rel):
                    src['coverage'] = 'protected_metadata_only'
                elif (stat.st_size > max_file_bytes or consumed + stat.st_size > max_total_bytes) and (path.suffix.lower() != '.parquet' or 'ledger_archive' in path.parts):
                    src['coverage'] = 'awaiting_evidence_byte_limit'
                    result['complete'] = False
                elif path.suffix.lower() == '.jsonl':
                    # split raw rows are counted later using the canonical fold.
                    skip = split and (path == logical or rel.startswith(('forecasts/', 'resolutions/')))
                    if split and rel.startswith(('forecasts/', 'resolutions/')):
                        split_sources.append((path, src, len(result['errors'])))
                    src['coverage'] = 'logical_physical_source' if skip else 'streamed'
                    consumed += stat.st_size
                    h = hashlib.sha256()
                    rows = 0
                    with path.open('rb') as stream:
                        left = stat.st_size
                        while left:
                            line = stream.readline(left)
                            if not line:
                                raise EvidenceRefused('source truncated during census')
                            left -= len(line)
                            h.update(line)
                            if not line.endswith(b'\n'):
                                error(path, 'incomplete_final_line', line=rows + 1)
                                continue
                            if not line.strip():
                                error(path, 'blank_line', line=rows + 1)
                                continue
                            try:
                                row = json.loads(line)
                                if not skip:
                                    observe(row, path, label, fam)
                                elif rel.startswith('forecasts/'):
                                    if not isinstance(row, dict) or not isinstance(row.get('prediction_id'), str):
                                        error(path, 'logical_forecast_invalid_identity')
                                    else:
                                        db.execute('INSERT OR IGNORE INTO coverage_split_forecast VALUES (?, ?)', (label, digest(row['prediction_id'])))
                                elif rel.startswith('resolutions/'):
                                    from backend.services import forecast_ledger as FL
                                    problem = FL.event_problem(row)
                                    if problem:
                                        error(path, 'logical_terminal_event_refused', detail=problem)
                                    else:
                                        event_id = digest(row['prediction_id'])
                                        event_hash = digest({'event': row['event'], 'set': row['set']})
                                        prior = db.execute('SELECT hash FROM coverage_split_terminal WHERE root=? AND identity=?', (label, event_id)).fetchone()
                                        if prior and prior[0] != event_hash:
                                            error(path, 'conflicting_terminal_event', identity_sha256=event_id)
                                        elif prior:
                                            src['duplicate_terminal_events'] = src.get('duplicate_terminal_events', 0) + 1
                                        else:
                                            db.execute('INSERT INTO coverage_split_terminal VALUES (?, ?, ?, ?)', (label, event_id, event_hash, str(path)))
                                rows += 1
                                day = stamp(row) if isinstance(row, dict) else None
                                if day:
                                    src['first_date'] = min(src['first_date'] or day, day)
                                    src['last_date'] = max(src['last_date'] or day, day)
                            except (ValueError, UnicodeDecodeError) as exc:
                                error(path, 'malformed_row', line=rows + 1, exception=type(exc).__name__)
                    from backend.services.forecast_ledger import _prefix_sha256
                    if _prefix_sha256(path, stat.st_size) != h.hexdigest():
                        raise EvidenceRefused('source prefix changed during census')
                    src.update(sha256=h.hexdigest(), complete_prefix_bytes=stat.st_size, rows=rows)
                elif path.suffix.lower() == '.json' and stat.st_size <= max_json_bytes:
                    consumed += stat.st_size
                    raw = path.read_bytes()
                    value = json.loads(raw)
                    src['sha256'] = hashlib.sha256(raw).hexdigest()
                    if hashlib.sha256(path.read_bytes()).hexdigest() != src['sha256']:
                        raise EvidenceRefused('JSON changed during census')
                    src['coverage'] = 'context_receipt_or_manifest'
                    if isinstance(value, list):
                        src['rows'] = len(value)
                        src['unit'] = 'JSON array elements; record objects are censused separately'
                        src['excluded_nonrecord_context_elements'] = 0
                        for row in value:
                            if isinstance(row, dict):
                                observe(row, path, label, fam)
                            else:
                                src['excluded_nonrecord_context_elements'] += 1
                        value = {}
                    elif not isinstance(value, dict):
                        src['coverage'] = 'excluded_scalar_context'
                        value = {}
                    src['first_date'] = src['last_date'] = stamp(value)
                    # Preserve delta/cumulative vocabulary; do not infer row counts from arbitrary n.
                    src['count_metadata'] = {k: value[k] for k in ('newly', 'new_rows_since_last_run',
                        'n_rows', 'rows_count', 'n_forecasts', 'n_cells', 'schema_version')
                        if isinstance(value.get(k), (int, str))}
                    for key in ('forecasts', 'predictions'):
                        if isinstance(value.get(key), list):
                            for row in value[key]:
                                observe(row, path, label, fam)
                            src['rows'] = len(value[key])
                elif path.suffix.lower() == '.parquet':
                    import pyarrow.parquet as pq
                    parquet = pq.ParquetFile(path)
                    src['coverage'] = 'parquet_footer_only'
                    src['rows'] = parquet.metadata.num_rows
                    src['columns'] = parquet.schema.names
                    for col in ('date', 'stamp', 'timestamp', 'as_of'):
                        if col not in parquet.schema.names:
                            continue
                        index = parquet.schema.names.index(col)
                        days = []
                        for rg in range(parquet.metadata.num_row_groups):
                            stats = parquet.metadata.row_group(rg).column(index).statistics
                            if stats and stats.has_min_max:
                                for val in (stats.min, stats.max):
                                    if isinstance(val, bytes):
                                        val = val.decode('utf-8', errors='replace')
                                    try:
                                        days.append(date.fromisoformat(str(val)[:10]).isoformat())
                                    except ValueError:
                                        pass
                        if days:
                            src['first_date'], src['last_date'] = min(days), max(days)
                            src['dated_by'] = f'parquet footer {col} min/max'
                            break
                    # Lossless monthly archives have verbatim lines; dedup with active month.
                    if 'ledger_archive' in path.parts and 'line' in parquet.schema.names:
                        src['coverage'] = 'lossless_archive_streamed'
                        consumed += stat.st_size
                        from backend.services.forecast_ledger import sha256_file
                        src['sha256'] = sha256_file(path)
                        ledger_fam = re.sub(r'_\d{4}-\d{2}$', '', path.stem)
                        for batch in parquet.iter_batches(batch_size=4096, columns=['line']):
                            for line in batch.column(0).to_pylist():
                                try:
                                    observe(json.loads(line), path, label, ledger_fam)
                                except ValueError:
                                    error(path, 'malformed_archive_line')
                        if sha256_file(path) != src['sha256']:
                            raise EvidenceRefused('archive changed during census')
                else:
                    src['coverage'] = 'context_or_binary_metadata_only'
            except Exception as exc:
                src['coverage'] = 'inaccessible_or_invalid'
                error(path, 'source_refused', exception=type(exc).__name__, detail=str(exc)[:200])
            ff['dispositions'][src['coverage']] += 1
        if marker_state() != initial_marker:
            error(logical, 'forecast_ledger_migration_marker_changed_during_census')
        if split and not root_protected:
            try:
                from backend.services import forecast_ledger as FL
                orphan_events = db.execute('SELECT t.identity,t.source FROM coverage_split_terminal t LEFT JOIN coverage_split_forecast f ON t.root=f.root AND t.identity=f.identity WHERE t.root=? AND f.identity IS NULL', (label,)).fetchall()
                for event_id, source in orphan_events:
                    error(source, 'orphan_terminal_event', identity_sha256=event_id)
                if marker_state() != initial_marker:
                    raise EvidenceRefused('migration marker changed during scan')
                active_paths = [p for p in paths if p.relative_to(root).as_posix().startswith(('forecasts/', 'resolutions/')) and p.suffix == '.jsonl']
                if not active_paths or set(active_paths) != {p for p, _, _ in split_sources}:
                    raise EvidenceRefused('logical streams not fully captured within bounds')
                for p, src, _ in split_sources:
                    if src['coverage'] != 'logical_physical_source' or any(e['path'] == str(p) for e in result['errors']):
                        raise EvidenceRefused('logical stream is malformed, protected, or incomplete')
                    if p.stat().st_size != src['complete_prefix_bytes'] or FL.sha256_file(p) != src['sha256']:
                        raise EvidenceRefused('logical stream changed since pinned capture')
                before = FL.fingerprint(logical)
                backend = FL.backend_for(logical)
                pinned_paths = {p for p, _, _ in split_sources}
                def actual_stream_paths():
                    return {p for stream in FL.STREAMS for _, p in FL.stream_files(backend, stream)}
                if backend.kind != 'streams' or actual_stream_paths() != pinned_paths:
                    raise EvidenceRefused('actual logical stream inventory differs from pinned capture')
                for line in FL.logical_lines(logical):
                    observe(json.loads(line), logical, label, 'forecast')
                if FL.fingerprint(logical) != before or marker_state() != initial_marker or actual_stream_paths() != pinned_paths:
                    raise EvidenceRefused('logical ledger changed during census')
                for p, src, _ in split_sources:
                    if p.stat().st_size != src['complete_prefix_bytes'] or FL.sha256_file(p) != src['sha256']:
                        raise EvidenceRefused('logical stream changed during fold')
            except Exception as exc:
                error(logical, 'logical_ledger_refused', detail=str(exc)[:200])
    for g in result['row_families'].values():
        g['states'] = dict(sorted((k, v) for k, v in g['states'].items() if v))
        g['sources'] = sorted(g['sources'])
        g['evidence_classes'] = dict(sorted(g['evidence_classes'].items()))
        g['identity_sha256'] = g.pop('identity_hash').hexdigest()
    for ff in result['file_families'].values():
        ff['dispositions'] = dict(sorted(ff['dispositions'].items()))
    result['totals'] = {'files': len(result['sources']), 'file_families': len(result['file_families']),
        'task_horizon_cells': len(result['row_families']), 'decoded_raw_rows': sum(g['raw'] for g in result['row_families'].values()),
        'unique_records': sum(g['unique'] for g in result['row_families'].values()),
        'duplicate_records': sum(g['duplicates'] for g in result['row_families'].values()),
        'errors': len(result['errors']), 'bytes_inspected_budget': consumed}
    labels = sorted(forecast_hashes)
    result['forecast_population_overlaps'] = [
        {'root_a': a, 'root_b': b, 'identical_immutable_originals': len(forecast_hashes[a] & forecast_hashes[b]),
         'interpretation': 'byte-canonical overlap only; populations are not pooled'}
        for i, a in enumerate(labels) for b in labels[i + 1:]]
    db.commit()
    db.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', required=True, help='LABEL=PATH; repeatable')
    parser.add_argument('--metadata-root', action='append', default=[])
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--out', required=True, help='Private receipt outside input roots and Git')
    parser.add_argument('--max-total-mib', type=int, default=2048)
    parser.add_argument('--identity-db', help='Private coverage scratch SQLite index outside input roots')
    parser.add_argument('--max-unique-records', type=int, default=100_000)
    args = parser.parse_args(argv)
    roots = dict(v.split('=', 1) for v in args.root)
    output = Path(args.out).resolve()
    if any(output.is_relative_to(Path(p).resolve()) for p in roots.values()):
        parser.error('output must be outside all input roots')
    if args.identity_db and any(Path(args.identity_db).resolve().is_relative_to(Path(p).resolve()) for p in roots.values()):
        parser.error('identity database must be outside all input roots')
    result = census(roots, as_of=args.as_of, metadata_roots=args.metadata_root,
                    max_total_bytes=args.max_total_mib << 20, identity_db=args.identity_db,
                    max_unique_records=args.max_unique_records)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'receipt': str(output), 'complete': result['complete'], **result['totals']}))
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
