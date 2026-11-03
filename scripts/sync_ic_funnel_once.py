"""One guarded funnel sync; default validates locally without network or state writes."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from scripts import transfer_ic_funnel as tx

SGT = timezone(timedelta(hours=8))
TIMEOUT = 60
START_MARGIN = 15
COMMIT_CUTOFF = (16, 29)  # one full minute before the 16:30 margin


def commit_deadline(now):
    """One absolute UTC cutoff for this attempt; never extend it mid-pass."""
    local = now.astimezone(SGT)
    cutoff = local.replace(hour=COMMIT_CUTOFF[0], minute=COMMIT_CUTOFF[1],
                           second=0, microsecond=0)
    protected_end = local.replace(hour=17, minute=5, second=0, microsecond=0)
    if local > protected_end:
        cutoff += timedelta(days=1)
    return cutoff.astimezone(timezone.utc).isoformat()


def clock_guard(now, deadline, seconds=TIMEOUT):
    tx.guard_commit_deadline(deadline, seconds=seconds + START_MARGIN, now=now)


def inspect_remote(ids, *, hash_only=False, commit_deadline=None, clock=None,
                   run=subprocess.run):
    # Ship reviewed definitions, not a second validator. No data enters argv.
    source = Path(tx.__file__).read_text(encoding='utf-8').split("\nif __name__ == '__main__':")[0]
    body = '''
if not os.path.ismount('/data') or TARGET.parent.is_symlink():
    raise Refused('volume_not_mounted')
if TARGET.is_symlink():
    raise Refused('target_symlink')
if not TARGET.exists():
    result = {'sha256': 'ABSENT'}
else:
    if not stat.S_ISREG(TARGET.stat().st_mode):
        raise Refused('target_not_regular')
    raw = read_bounded(TARGET)
    if not 0 < len(raw) <= MAX_BYTES:
        raise Refused('size_bound')
    result = {'sha256': digest(raw)} if HASH_ONLY else validate(raw, fresh=False)
print(json.dumps(result, sort_keys=True))
'''.replace('HASH_ONLY', repr(hash_only))
    command = [tx.resolve_railway(), 'ssh', '--project', ids[0],
               '--environment', ids[1], '--service', ids[2], '--', 'python3', '-']
    try:
        if commit_deadline is not None:
            clock_guard(clock() if clock else datetime.now(timezone.utc),
                        commit_deadline)
        result = run(command, input=(source + '\n' + body).encode(),
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     timeout=TIMEOUT, shell=False)
        if result.returncode != 0 or len(result.stdout) > 4096:
            raise ValueError
        meta = json.loads(result.stdout)
        if not re.fullmatch(r'ABSENT|[0-9a-f]{64}', meta['sha256']):
            raise ValueError
        if not hash_only and meta['sha256'] != 'ABSENT':
            stamp = datetime.fromisoformat(meta['generated_at'])
            if stamp.utcoffset() != timedelta(0):
                raise ValueError
        return meta
    except tx.Refused:
        raise
    except Exception:
        # Do not expose subprocess output, OS errors or remote text.
        raise tx.Refused('inspection_unconfirmed') from None


def private_directory(path):
    """Dedicated state directory: current Windows identity only, or POSIX 0700."""
    if path.is_symlink():
        raise tx.Refused('state_symlink')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'nt':
        # Capture SID privately; avoid localized account names and inherited ACLs.
        result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                                capture_output=True, timeout=10, check=True)
        sid = re.search(rb'S-1-5-[0-9-]+', result.stdout)
        if not sid:
            raise tx.Refused('private_state_unconfirmed')
        script = '''$ErrorActionPreference = 'Stop'
$v = [Console]::In.ReadToEnd() | ConvertFrom-Json
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$sid = New-Object System.Security.Principal.SecurityIdentifier($v.sid)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$acl.AddAccessRule($rule)
$directory = New-Object System.IO.DirectoryInfo($v.path)
$directory.SetAccessControl($acl)
'''
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                       input=json.dumps({'path': str(path.resolve()), 'sid': sid[0].decode()}).encode(),
                       capture_output=True, timeout=10, check=True)
    else:
        os.chmod(path, 0o700)


def hold_write(path, record):
    fd, temp = tempfile.mkstemp(prefix='.hold-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def exclusive(path):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise tx.Refused('state_busy_or_interrupted') from None
    try:
        os.close(fd)
        yield
    finally:
        path.unlink()


def sync(source, ids, state_dir, *, apply=False, clock=None,
         inspect=inspect_remote, transfer=tx.transfer):
    clock = clock or (lambda: datetime.now(timezone.utc))
    for value in ids:
        try:
            tx.target_uuid(value)
        except (argparse.ArgumentTypeError, TypeError):
            raise tx.Refused('explicit_target_uuid_required') from None
    # One state namespace per target, independent of source filename.
    key = tx.digest('|'.join(ids).encode())
    hold = state_dir / (key + '.HOLD')
    raw = tx.read_bounded(source)
    meta = tx.validate(raw, fresh=not hold.exists(), now=clock())
    if not apply:
        return dict(meta, status='hold_no_network' if hold.exists() else 'local_dry_run', wrote=False)
    deadline = commit_deadline(clock())
    clock_guard(clock(), deadline, 2 * TIMEOUT)
    private_directory(state_dir)
    with exclusive(state_dir / (key + '.lock')):
        record = {'sha256': meta['sha256'], 'target': list(ids)}
        if hold.is_symlink():
            raise tx.Refused('hold_symlink')
        if hold.exists():
            with hold.open('rb') as stream:
                saved = json.loads(stream.read(4097))
            if saved != record:
                raise tx.Refused('hold_local_or_target_changed')
            clock_guard(clock(), deadline)
            remote = inspect(ids, hash_only=True, commit_deadline=deadline,
                             clock=clock)
            if remote['sha256'] != meta['sha256']:
                raise tx.Refused('hold_remote_mismatch')
            hold.unlink()
            return dict(meta, status='hold_reconciled', wrote=False)
        # Inspection failures also latch HOLD. Pre-arm to survive process death.
        clock_guard(clock(), deadline, 2 * TIMEOUT)
        hold_write(hold, record)
        clock_guard(clock(), deadline, 2 * TIMEOUT)
        remote = inspect(ids, commit_deadline=deadline, clock=clock)
        if remote['sha256'] == meta['sha256']:
            hold.unlink()
            return dict(meta, status='already_present', wrote=False)
        if remote['sha256'] != 'ABSENT':
            old = datetime.fromisoformat(remote['generated_at'])
            new = datetime.fromisoformat(meta['generated_at'])
            if new <= old:
                hold.unlink()  # Confirmed read-only refusal, no ambiguity.
                raise tx.Refused('remote_newer' if new < old else 'equal_stamp_conflict')
        # Recheck clock/freshness after inspection; do not reread changing source.
        try:
            clock_guard(clock(), deadline)
            tx.validate(raw, now=clock())
            clock_guard(clock(), deadline)
        except tx.Refused:
            hold.unlink()
            raise
        receipt = transfer(raw, project=ids[0], environment=ids[1], service=ids[2],
                           expected=remote['sha256'], apply=True,
                           commit_deadline=deadline, clock=clock)
        # tx verifies the exact remote postcommit receipt; any exception retains HOLD.
        hold.unlink()
        return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    for name in ('project', 'environment', 'service'):
        parser.add_argument('--' + name, required=True, type=tx.target_uuid)
    parser.add_argument('--state-dir', required=True, type=Path,
                        help='dedicated private persistent directory outside Git')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = sync(args.source, (args.project, args.environment, args.service),
                      args.state_dir, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'refused_or_unconfirmed',
                          'reason': str(exc) if isinstance(exc, tx.Refused) else 'local_io_failure'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
