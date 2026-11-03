"""Bounded, opt-in funnel transfer. No network on the default dry run.

Only stdlib; remote runs the same validator via stdin, never payload in argv.
"""
import argparse
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MAX_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 1500
MAX_AGE = timedelta(days=10)  # same operational horizon as the IC loader
# REC._zscores squares cross-sectional differences (up to 1500 terms), while
# PF.build uses 1 / vol_annual. These generous limits keep both finite.
MAX_ABS_NUMBER = 1e100
MIN_VOL_ANNUAL = 1e-100
CONSUMER_OPTIONAL_NUMBERS = (
    'score', 'quality', 'market_cap', 'mom_12_1', 'analyst_upside',
    'insider_score', 'fusion_score', 'short_interest',
    'earnings_surprise', 'rating_drift_3m',
)
TARGET = Path('/data/funnel_night10.json')
SGT = timezone(timedelta(hours=8))


class Refused(ValueError):
    """Safe, fixed reason codes only; never echo deserialized content."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Refused('duplicate_key')
        obj[key] = value
    return obj


def _bounded_number(value):
    if type(value) not in (int, float):
        return False
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(number) and abs(number) <= MAX_ABS_NUMBER


def _optional_string_list(obj, key):
    value = obj.get(key)
    if value is not None and (not isinstance(value, list) or
                              any(not isinstance(item, str) for item in value)):
        raise Refused('consumer_string_list')


def _consumer_shapes(obj):
    """Match IC.shortlist's mapping/join/list/numeric contracts.

    Missing/null optional fields retain the reader's existing defaults. Extra
    producer fields stay untouched; this is transport validation, not ranking.
    """
    for key in ('evidence_basis', 'universe'):
        value = obj.get(key)
        if value is not None and not isinstance(value, dict):
            raise Refused('consumer_mapping')
    basis = obj.get('evidence_basis') or {}
    for key in ('ranked_by', 'filtered_by', 'recorded_but_not_ranked_on'):
        _optional_string_list(basis, key)
    for row in obj['candidates']:
        for key in ('why', 'blocked_by'):
            _optional_string_list(row, key)
        # These enter shortlist float conversion or recommendation adapters.
        # Reject malformed types and magnitudes before cross-sectional variance.
        for key in CONSUMER_OPTIONAL_NUMBERS:
            value = row.get(key)
            if value is not None and not _bounded_number(value):
                raise Refused('consumer_numeric')


def validate(raw, *, fresh=True, now=None):
    if not 0 < len(raw) <= MAX_BYTES:
        raise Refused('size_bound')
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(Refused('nonfinite')))
        if not isinstance(obj, dict):
            raise Refused('object_required')
        stamp = obj['generated_at']
        if not isinstance(stamp, str) or len(stamp) > 40:
            raise Refused('stamp_required')
        ts = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise Refused('timezone_required')
        ts = ts.astimezone(timezone.utc)
        now = now or datetime.now(timezone.utc)
        if ts > now + timedelta(minutes=5):
            raise Refused('future_stamp')
        if fresh and now - ts > MAX_AGE:
            raise Refused('stale_source')
        rows = obj['candidates']
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CANDIDATES:
            raise Refused('candidate_bound')
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise Refused('candidate_object')
            ticker = row.get('ticker')
            if not isinstance(ticker, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.^-]{0,19}', ticker):
                raise Refused('ticker_invalid')
            if ticker in seen:
                raise Refused('ticker_duplicate')
            seen.add(ticker)
            for key in ('price', 'median_dollar_vol', 'vol_annual'):
                value = row.get(key)
                if not _bounded_number(value) or value <= 0:
                    raise Refused('candidate_numeric')
            if row['vol_annual'] < MIN_VOL_ANNUAL:
                raise Refused('vol_inverse_bound')
        _consumer_shapes(obj)
        # Walk the entire object: reject overflow (1e999), excessive nesting and huge collections.
        def walk(value, depth=0):
            if depth > 20:
                raise Refused('depth_bound')
            if type(value) in (int, float) and not _bounded_number(value):
                raise Refused('numeric_bound')
            if isinstance(value, (dict, list)):
                if len(value) > 10000:
                    raise Refused('collection_bound')
                for child in (value.values() if isinstance(value, dict) else value):
                    walk(child, depth + 1)
        walk(obj)
        return {'sha256': digest(raw), 'generated_at': ts.isoformat(), 'candidates': len(rows), 'bytes': len(raw)}
    except Refused:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise Refused('invalid_schema') from None


def read_bounded(path):
    with path.open('rb') as stream:
        return stream.read(MAX_BYTES + 1)


def guard_commit_deadline(deadline, *, seconds=0, now=None):
    """Opt-in IIF guard; deadline is an absolute UTC instant, not a duration."""
    if deadline is None:
        return
    try:
        cutoff = datetime.fromisoformat(deadline)
        if cutoff.utcoffset() != timedelta(0):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise Refused('invalid_commit_deadline') from None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise Refused('invalid_clock')
    local = current.astimezone(SGT)
    protected_start = local.replace(hour=16, minute=30, second=0, microsecond=0)
    protected_end = local.replace(hour=17, minute=5, second=0, microsecond=0)
    if protected_start <= local <= protected_end or current + timedelta(seconds=seconds) >= cutoff:
        raise Refused('iif_protection_clock')


def receive(raw, expected, *, target=TARGET, apply=False, commit_deadline=None, clock=None):
    """Remote transaction. Test target injection is not exposed through the CLI."""
    import fcntl  # Linux remote only; Windows local does not import it.
    incoming = validate(raw)
    parent = target.parent
    if parent.is_symlink() or not parent.is_dir():
        raise Refused('volume_missing')
    # Lock the directory inode: no persistent lock/backup/receipt writes.
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temp = None
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if target.is_symlink():
            raise Refused('target_symlink')
        current = None
        if target.exists():
            if not stat.S_ISREG(target.stat().st_mode):
                raise Refused('target_not_regular')
            current = validate(read_bounded(target), fresh=False)
        actual = current['sha256'] if current else 'ABSENT'
        if expected != actual:
            raise Refused('remote_changed')
        if current:
            old_ts = datetime.fromisoformat(current['generated_at'])
            new_ts = datetime.fromisoformat(incoming['generated_at'])
            if new_ts < old_ts:
                raise Refused('rollback')
            if new_ts == old_ts and incoming['sha256'] != actual:
                raise Refused('equal_stamp_conflict')
            if incoming['sha256'] == actual:
                return dict(incoming, status='already_present', wrote=False)
        if not apply:
            return dict(incoming, status='remote_dry_run', wrote=False)
        fd, temp = tempfile.mkstemp(prefix='.funnel-transfer-', dir=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if digest(read_bounded(Path(temp))) != incoming['sha256']:
            raise Refused('staging_hash')
        # Last-good stays untouched until this one atomic commit point.
        if commit_deadline is not None:
            guard_commit_deadline(commit_deadline, now=clock() if clock else None)
        os.replace(temp, target)
        temp = None
        os.fsync(directory)
        return dict(incoming, status='transferred', wrote=True)
    finally:
        if temp is not None:
            os.unlink(temp)
        os.close(directory)


def remote_entry(encoded, expected, apply, commit_deadline=None):
    try:
        if not os.path.ismount('/data'):
            raise Refused('volume_not_mounted')
        result = receive(base64.b64decode(encoded, validate=True), expected,
                         apply=apply, commit_deadline=commit_deadline)
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        # No exception text from the OS, Railway or payload is ever printed.
        print(json.dumps({'status': 'refused_or_unconfirmed', 'reason': str(exc) if isinstance(exc, Refused) else 'remote_io_failure'}))
        sys.exit(2)


def resolve_railway():
    """Resolve an explicit executable, including npm's Windows cmd shim.

    PowerShell aliases/ps1 scripts are not CreateProcess executables. Arguments
    remain a list with shell=False; target fields are restricted above spawning.
    """
    names = ('railway.exe', 'railway.cmd') if sys.platform == 'win32' else ('railway',)
    for name in names:
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
    raise Refused('railway_executable_missing')


def transfer(raw, *, project, environment, service, expected, apply=False,
             run=subprocess.run, commit_deadline=None, clock=None):
    meta = validate(raw)
    if not apply:
        return dict(meta, status='local_dry_run', wrote=False)
    for value in (project, environment, service):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
            raise Refused('explicit_target_uuid_required')
    if not isinstance(expected, str) or not re.fullmatch(r'ABSENT|[0-9a-f]{64}', expected):
        raise Refused('expected_remote_required')
    source = Path(__file__).read_text(encoding='utf-8').split("\nif __name__ == '__main__':")[0]
    wire = source + '\nremote_entry(' + repr(base64.b64encode(raw).decode('ascii')) + ', ' + repr(expected) + ', True'
    if commit_deadline is not None:
        guard_commit_deadline(commit_deadline, seconds=75, now=clock() if clock else None)
        wire += ', ' + repr(commit_deadline)
    wire += ')\n'
    command = [resolve_railway(), 'ssh', '--project', project, '--environment', environment,
               '--service', service, '--', 'python3', '-']
    try:
        if commit_deadline is not None:
            guard_commit_deadline(commit_deadline, seconds=75, now=clock() if clock else None)
        result = run(command, input=wire.encode('utf-8'), stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, timeout=60, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Refused('transport_unconfirmed') from None
    # Never forward Railway output: it can contain shell banners/private details.
    if result.returncode != 0 or len(result.stdout) > 4096:
        raise Refused('remote_refused_or_unconfirmed')
    try:
        receipt = json.loads(result.stdout)
        if receipt.get('status') not in ('transferred', 'already_present') or any(receipt.get(k) != v for k, v in meta.items()):
            raise Refused('receipt_mismatch')
        wrote = receipt.get('wrote')
        if type(wrote) is not bool or wrote != (receipt['status'] == 'transferred'):
            raise Refused('receipt_mismatch')
        return dict(meta, status=receipt['status'], wrote=wrote)
    except (ValueError, AttributeError):
        raise Refused('receipt_unconfirmed') from None


def target_uuid(value):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
        raise argparse.ArgumentTypeError('explicit lowercase target UUID required; names are not accepted')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--project', type=target_uuid, help='explicit Railway UUID (not a name)')
    parser.add_argument('--environment', type=target_uuid, help='explicit Railway UUID (not a name)')
    parser.add_argument('--service', type=target_uuid, help='explicit Railway UUID (not a name)')
    parser.add_argument('--expected-remote-sha256', dest='expected')
    args = parser.parse_args(argv)
    try:
        receipt = transfer(read_bounded(args.source), project=args.project, environment=args.environment,
                           service=args.service, expected=args.expected, apply=args.apply)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'refused_or_unconfirmed', 'reason': str(exc) if isinstance(exc, Refused) else 'local_io_failure'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
