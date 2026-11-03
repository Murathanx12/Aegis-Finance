"""Offline provisional warning; no scheduler, network, broker or database imports.

Normalized input schema (or use build_saved_warning for native saved files):
source JSONL row: ticker, form='8-K', exhibit='EX-99.1', optional item='2.02',
event_type='earnings_results', accession, url (SEC Archives HTTPS document),
published_at, captured_at, body. Snapshot: lane='PC-PAPER', as_of,
equity_usd, positions=[{ticker, market_value_usd, instrument='equity', leverage=1}].
All clocks must be timezone-aware UTC. Hashes use the exact supplied UTF-8
JSON row and snapshot strings, including whitespace. No raw inputs are emitted.
Freshness limits are conservative engineering defaults, not calibrated signals.

Build first with build_warning; deliver only through an explicitly injected
telegram_bridge.send_owner_once callback. The caller owns the journal directory
and must preserve it across runs. This module has no default sender. No automatic
reconciliation or retries: even a crash after SENDING requires human review.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from urllib.parse import urlsplit

SOURCE_MAX_AGE = timedelta(hours=24)
SNAPSHOT_MAX_AGE = timedelta(hours=24)
POSITION_SUM_TOLERANCE_FRACTION = Decimal('0.0001')  # 0.01% of saved equity
EQUITY_TOLERANCE_USD = Decimal('0.01')
HELD_MARK_TOLERANCE_USD = Decimal('0.01')


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _digest(value):
    return _hash(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False))


def _object(text):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('duplicate key')
            out[key] = value
        return out
    value = json.loads(text, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(value, dict):
        raise ValueError('object required')
    return value


def _utc(value):
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('UTC timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() != timedelta(0):
        raise ValueError('UTC timestamp required')
    return result


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('number required')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('finite number required')
    return result


def build_warning(source_row: str, snapshot_json: str, *, now: datetime) -> dict:
    """Return a sanitized dated artifact, including explicit refusal evidence.

    HOLD_EXISTING is a provisional paper posture, never an execution instruction.
    Stress is conditional loss on saved notional, not probability or forecast.
    """
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        raise ValueError('now must be aware UTC')
    artifact = {'schema': 'owner-event-warning/1', 'at': now.isoformat(),
                'status': 'REFUSED', 'reason': 'MALFORMED_INPUT',
                'missing': ['consensus', 'current_quote', 'owner_loss_budget'],
                'next_update_trigger': 'Fresh verified public evidence and reconciled PC-PAPER snapshot; owner loss budget review.'}
    if not isinstance(source_row, str) or not isinstance(snapshot_json, str):
        return artifact
    artifact.update(source_row_sha256=_hash(source_row), snapshot_sha256=_hash(snapshot_json))
    reason = 'MALFORMED_INPUT'
    try:
        row, snap = _object(source_row), _object(snapshot_json)
        ticker = row['ticker']
        if not isinstance(ticker, str) or not re.fullmatch(r'[A-Z]{1,5}(?:[.-][A-Z])?', ticker):
            raise ValueError()
        reason = 'SOURCE_AMBIGUOUS'
        if (row['form'] != '8-K' or row['exhibit'] not in ('EX-99.1', 'EX-99')
                or ('item' in row and row['item'] != '2.02') or row['event_type'] != 'earnings_results'
                or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', row['accession'])
                or not isinstance(row['body'], str)
                or not re.search(r'\b(?:financial|earnings) results\b', row['body'], re.I)):
            raise ValueError()
        url = urlsplit(row['url'])
        # Strict allowlist excludes credentials, query strings and arbitrary body text.
        if (url.scheme != 'https' or url.netloc != 'www.sec.gov' or url.query or url.fragment
                or not re.fullmatch(r'/Archives/edgar/data/\d+/\d{18}/[A-Za-z0-9_-]+\.html?', url.path)
                or url.path.split('/')[5] != row['accession'].replace('-', '')):
            raise ValueError()
        reason = 'SOURCE_CLOCK_INVALID'
        published, captured = _utc(row['published_at']), _utc(row['captured_at'])
        if not published <= captured <= now:
            raise ValueError()
        reason = 'SOURCE_STALE'
        if now - published > SOURCE_MAX_AGE:
            raise ValueError()
        reason = 'SNAPSHOT_CLOCK_INVALID'
        as_of = _utc(snap['as_of'])
        if as_of > now:
            raise ValueError()
        reason = 'SNAPSHOT_STALE'
        if now - as_of > SNAPSHOT_MAX_AGE:
            raise ValueError()
        reason = 'BAD_EQUITY_OR_EXPOSURE'
        equity = _number(snap['equity_usd'])
        if snap['lane'] != 'PC-PAPER' or equity <= 0 or not isinstance(snap['positions'], list):
            raise ValueError()
        seen, total, held = set(), Decimal(0), None
        for pos in snap['positions']:
            symbol = pos['ticker']
            value = _number(pos['market_value_usd'])
            if (symbol in seen or not isinstance(symbol, str) or value < 0
                    or pos['instrument'] != 'equity' or _number(pos['leverage']) != 1):
                raise ValueError()
            seen.add(symbol)
            total += value
            if symbol == ticker:
                held = value
        if total > equity:
            raise ValueError()
        reason = 'NOT_HELD'
        if held is None or held <= 0:
            raise ValueError()
        artifact.update(status='PROVISIONAL', reason='SAVED_EVIDENCE_ONLY', ticker=ticker,
                        forecast_status='NO_CALIBRATED_EVENT_FORECAST',
                        source_url=row['url'], published_at=published.isoformat(),
                        captured_at=captured.isoformat(), snapshot_as_of=as_of.isoformat(),
                        exposure_weight=str(held / equity), saved_exposure_usd=str(held),
                        conditional_loss_usd={'5_percent_decline': str(held * Decimal('.05')),
                                              '10_percent_decline': str(held * Decimal('.10'))},
                        stress_basis='Conditional arithmetic on saved exposure; NOT probabilities or forecasts.',
                        paper_decision=['HOLD_EXISTING', 'NO_NEW_BET', 'REVIEW_NEW_EVIDENCE'],
                        interpretation='No beat/miss or price direction inferred. Owner loss budget UNKNOWN.')
        # Event identity deliberately excludes capture clock, snapshot and now.
        artifact['event_key'] = _digest({'ticker': ticker, 'accession': row['accession']})
    except (ValueError, TypeError, KeyError, InvalidOperation, AttributeError, OverflowError):
        artifact['reason'] = reason
    return artifact


def _message(artifact):
    lineage = ''
    if 'forecast_input_id' in artifact:
        lineage = (f"Forecast input: {artifact['forecast_input_id']}\n"
                   f"Provisional decision: {artifact['provisional_decision_id']}\n"
                   "New allocation USD: 0; no numerical event forecast.\n")
    return (f"PROVISIONAL PC-PAPER {artifact['ticker']} | {artifact['at']}\n"
            f"Evidence: {artifact['source_url']} | published {artifact['published_at']}\n"
            f"Snapshot: {artifact['snapshot_as_of']} | weight {artifact['exposure_weight']}\n"
            f"{artifact.get('source_proof', 'Normalized saved source')}\n"
            f"{artifact.get('snapshot_basis', 'Normalized saved PC-PAPER snapshot')}\n"
            f"{artifact.get('reconciliation_note', '')}\n"
            f"Conditional dollar loss: {json.dumps(artifact['conditional_loss_usd'], sort_keys=True)}\n"
            f"Forecast: {artifact['forecast_status']}; conditional stresses only.\n"
            f"{lineage}"
            f"{artifact['stress_basis']}\n"
            "HOLD_EXISTING / NO_NEW_BET / REVIEW_NEW_EVIDENCE (paper only).\n"
            "Missing consensus/current quote; owner loss budget UNKNOWN. No beat/miss or direction inferred.\n"
            f"Next: {artifact['next_update_trigger']}\n"
            f"Source SHA256 {artifact['source_row_sha256']}\nSnapshot SHA256 {artifact['snapshot_sha256']}")


def warn(source_row: str, snapshot_json: str, *, now: datetime, journal_dir: Path,
         sender=None) -> dict:
    """Build and optionally attempt delivery. Inject send_owner_once(text, tag=...).

    A create-exclusive, flushed and fsynced SENDING file precedes the callback.
    Filesystem power-loss durability of its directory entry is not proven.
    Transport exceptions are
    ambiguous and never retried automatically. A valid persisted ACK may be
    reported as ALREADY_SENT on replay; this is no general exactly-once claim.
    The journal path is checked before and after SENDING, but path components
    are not pinned by an open directory handle against same-user replacement.
    A private journal is trusted against same-user tampering; its ACK hash
    cannot independently prove the native Telegram message ID.
    """
    artifact = build_warning(source_row, snapshot_json, now=now)
    return _deliver(artifact, journal_dir=journal_dir, sender=sender)


def _windows_private_acl(path):
    """Read the exact Windows owner SID and every DACL ACE SID; fail closed."""
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.c_void_p
    advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, wintypes.DWORD,
        wintypes.DWORD, ctypes.POINTER(pointer), pointer, ctypes.POINTER(pointer),
        pointer, ctypes.POINTER(pointer)]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetSecurityDescriptorDacl.argtypes = [pointer, ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(pointer), ctypes.POINTER(wintypes.BOOL)]
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.GetAclInformation.argtypes = [pointer, pointer, wintypes.DWORD, wintypes.DWORD]
    advapi.GetAclInformation.restype = wintypes.BOOL
    advapi.GetAce.argtypes = [pointer, wintypes.DWORD, ctypes.POINTER(pointer)]
    advapi.GetAce.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(pointer)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.GetLengthSid.argtypes = [pointer]
    advapi.GetLengthSid.restype = wintypes.DWORD
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, pointer,
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [('sid', pointer), ('attributes', wintypes.DWORD)]

    class AclSize(ctypes.Structure):
        _fields_ = [('ace_count', wintypes.DWORD), ('bytes_used', wintypes.DWORD),
                    ('bytes_free', wintypes.DWORD)]

    class AceHeader(ctypes.Structure):
        _fields_ = [('ace_type', ctypes.c_ubyte), ('flags', ctypes.c_ubyte),
                    ('size', wintypes.WORD)]

    def sid_string(sid):
        if not sid or not advapi.GetLengthSid(sid):
            raise OSError('invalid ACL SID')
        value = pointer()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(value)):
            raise OSError('SID conversion failed')
        try:
            return ctypes.wstring_at(value)
        finally:
            kernel.LocalFree(value)

    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise OSError('token unavailable')
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if size.value < ctypes.sizeof(SidAndAttributes) or size.value > 65536:
            raise OSError('token SID size invalid')
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size,
                                           ctypes.byref(size)):
            raise OSError('token SID unavailable')
        current_sid = sid_string(ctypes.cast(buffer,
            ctypes.POINTER(SidAndAttributes)).contents.sid)
    finally:
        kernel.CloseHandle(token)

    owner, dacl, descriptor = pointer(), pointer(), pointer()
    code = advapi.GetNamedSecurityInfoW(str(path), 1, 0x00000001 | 0x00000004,
                                        ctypes.byref(owner), None, ctypes.byref(dacl),
                                        None, ctypes.byref(descriptor))
    if code:
        raise OSError('journal security descriptor unavailable')
    try:
        if sid_string(owner) != current_sid:
            raise OSError('journal owner differs from current user')
        present, defaulted, actual_dacl = wintypes.BOOL(), wintypes.BOOL(), pointer()
        if not advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                                ctypes.byref(actual_dacl),
                                                ctypes.byref(defaulted)) or not present.value or not actual_dacl:
            raise OSError('journal has no explicit DACL')
        info = AclSize()
        if not advapi.GetAclInformation(actual_dacl, ctypes.byref(info),
                                       ctypes.sizeof(info), 2) or not info.ace_count:
            raise OSError('journal DACL unreadable')
        allowed = {current_sid, 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-4'}
        for index in range(info.ace_count):
            ace = pointer()
            if not advapi.GetAce(actual_dacl, index, ctypes.byref(ace)):
                raise OSError('journal ACE unreadable')
            header = ctypes.cast(ace, ctypes.POINTER(AceHeader)).contents
            if header.ace_type not in (0, 1) or header.size < 16:
                raise OSError('journal ACE type or size unsupported')
            sid_ptr = pointer(ace.value + 8)  # ACCESS_ALLOWED/DENIED_ACE SidStart
            length = advapi.GetLengthSid(sid_ptr)
            if not length or 8 + length > header.size or sid_string(sid_ptr) not in allowed:
                raise OSError('journal ACE has foreign SID')
    finally:
        kernel.LocalFree(descriptor)


def _journal_identity(directory):
    """Inspect an existing private root; this is not a handle-bound path lock."""
    directory = Path(directory).absolute()
    for component in (directory, *directory.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400):
            raise OSError('redirected journal path')
    info = directory.stat()
    if not directory.is_dir():
        raise OSError('journal root is not a directory')
    if os.name == 'nt':
        _windows_private_acl(directory)
    elif info.st_mode & 0o077:
        raise OSError('journal directory is not private')
    return (info.st_dev, info.st_ino)


_ACK_HASH_KEYS = ('native_ack_sha256', 'tag_sha256', 'text_sha256')


def _valid_ack(ack, record):
    return (isinstance(ack, dict) and ack.get('state') == 'SENT'
            and type(ack.get('messages')) is int and ack['messages'] == 1
            and all(isinstance(ack.get(k), str) and re.fullmatch('[0-9a-f]{64}', ack[k])
                    for k in (*_ACK_HASH_KEYS, 'delivery_binding_sha256'))
            and ack['tag_sha256'] == record['tag_sha256']
            and ack['text_sha256'] == record['text_sha256']
            and ack['delivery_binding_sha256'] == _digest({k: ack[k] for k in _ACK_HASH_KEYS}))


def _confirmed_replay(path, result_path, pending_path, event_key):
    """Only a complete original SENDING/ACK pair can certify a prior attempt."""
    try:
        if os.path.lexists(pending_path) or not path.is_file() or not result_path.is_file():
            return False
        for candidate in (path, result_path):
            info = candidate.lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                return False
        record = _object(path.read_text(encoding='utf-8'))
        result = _object(result_path.read_text(encoding='utf-8'))
        saved = record['artifact']
        tag = 'owner-event-warning:' + event_key
        if (record['state'] != 'SENDING' or not isinstance(saved, dict)
                or saved['schema'] != 'owner-event-warning/1'
                or saved['status'] != 'PROVISIONAL' or saved['event_key'] != event_key
                or record['artifact_sha256'] != _digest(saved)
                or record['tag_sha256'] != _digest({'tag': tag})
                or record['text_sha256'] != _hash(_message(saved))
                or result['state'] != 'SENT' or result['at'] != saved['at']
                or not _valid_ack(result['ack'], record)):
            return False
        return True
    except (OSError, UnicodeError, ValueError, KeyError, TypeError,
            AttributeError, OverflowError):
        return False


def _deliver(artifact, *, journal_dir, sender):
    if artifact['status'] != 'PROVISIONAL':
        return {'artifact': artifact, 'delivery': 'NOT_SENT'}
    text = _message(artifact)
    tag = 'owner-event-warning:' + artifact['event_key']
    record = {'state': 'SENDING', 'artifact': artifact,
              'artifact_sha256': _digest(artifact),
              'tag_sha256': _digest({'tag': tag}), 'text_sha256': _hash(text)}
    directory = Path(journal_dir)
    try:
        identity = _journal_identity(directory)
    except (OSError, ValueError):
        return {'artifact': artifact, 'delivery': ('NOT_SENT' if sender is None
                                                 else 'REFUSED_JOURNAL_UNQUALIFIED')}
    path = directory / (artifact['event_key'] + '.json')
    result_path = path.with_suffix('.result.json')
    pending_path = path.with_suffix('.result.pending.json')
    if any(os.path.lexists(candidate) for candidate in (path, result_path, pending_path)):
        if _confirmed_replay(path, result_path, pending_path, artifact['event_key']):
            return {'artifact': artifact, 'delivery': 'ALREADY_SENT'}
        return {'artifact': artifact, 'delivery': 'DUPLICATE_RECONCILE_REQUIRED'}
    if sender is None:
        return {'artifact': artifact, 'delivery': 'NOT_SENT'}
    try:
        with path.open('x', encoding='utf-8') as file:
            json.dump(record, file, sort_keys=True, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        return {'artifact': artifact, 'delivery': 'DUPLICATE_RECONCILE_REQUIRED'}
    except OSError:
        return {'artifact': artifact, 'delivery': 'UNKNOWN_RECONCILE_REQUIRED'}
    try:
        if _journal_identity(directory) != identity:
            raise OSError('journal changed')
    except (OSError, ValueError):
        return {'artifact': artifact, 'delivery': 'UNKNOWN_RECONCILE_REQUIRED'}
    state = 'UNKNOWN_RECONCILE_REQUIRED'
    sanitized_ack = None
    try:
        ack = sender(text, tag=tag)
        if _valid_ack(ack, record):
            state = 'SENT'
            sanitized_ack = {k: ack[k] for k in (*_ACK_HASH_KEYS, 'delivery_binding_sha256')}
            sanitized_ack.update(state='SENT', messages=1)
    except Exception:
        pass  # explicit UNKNOWN below; transport may have succeeded
    try:
        with pending_path.open('x', encoding='utf-8') as file:
            json.dump({'state': state, 'at': artifact['at'], 'ack': sanitized_ack},
                      file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        # Expose a final result only after staging was synced. Hard-link creation
        # is exclusive: an existing result is never overwritten.
        os.link(pending_path, result_path)
        pending_path.unlink()
    except (OSError, TypeError, ValueError):
        state = 'UNKNOWN_RECONCILE_REQUIRED'
    return {'artifact': artifact, 'delivery': state}


def build_saved_warning(*, source_jsonl_path: Path, pc_paper_snapshot_path: Path,
                        ticker: str, now: datetime,
                        source_row_sha256: str | None = None) -> dict:
    """Read ONLY injected saved files; caller explicitly attests PC-PAPER path.

    Native corpus proof: exact source id, single-ticker binding, 8-K/EX-99 title,
    SEC Archives URL and accession:filename raw_id agreement, results body.
    No Item 2.02 is inferred. Multiple distinct rows for the requested ticker
    are refused rather than silently choosing an event. Snapshot's native
    positive qty/market_value shape is treated as cash equity under the caller's
    PC-PAPER path contract; this is disclosed, not independent instrument proof.
    Negative cash, shorts, leverage flags or gross above equity are refused.
    Hashes bind exact source line bytes (including newline) and snapshot bytes.
    Paths, arbitrary title/body, account fields and exceptions never leave here.
    """
    snapshot_bytes = b''
    try:
        snapshot_bytes = Path(pc_paper_snapshot_path).read_bytes()
        source_bytes = Path(source_jsonl_path).read_bytes()
    except (OSError, ValueError, TypeError):
        # Preserve sanitized legacy I/O refusal, including the snapshot digest.
        source_bytes = b''
    return build_saved_warning_bytes(source_bytes=source_bytes,
        snapshot_bytes=snapshot_bytes, ticker=ticker, now=now,
        source_row_sha256=source_row_sha256)


def build_saved_warning_bytes(*, source_bytes: bytes, snapshot_bytes: bytes,
                              ticker: str, now: datetime,
                              source_row_sha256: str | None = None) -> dict:
    """Assess frozen native UTF-8 bytes. No input path is opened here."""
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        raise ValueError('now must be aware UTC')
    artifact = {'schema': 'owner-event-warning/1', 'at': now.isoformat(),
                'status': 'REFUSED', 'reason': 'SAVED_INPUT_INVALID',
                'missing': ['consensus', 'current_quote', 'owner_loss_budget'],
                'next_update_trigger': 'Fresh verified SEC exhibit and reconciled PC-PAPER snapshot.'}
    reason = 'SAVED_INPUT_INVALID'
    try:
        if not isinstance(ticker, str) or not re.fullmatch(r'[A-Z]{1,5}(?:[.-][A-Z])?', ticker):
            raise ValueError()
        artifact['snapshot_sha256'] = hashlib.sha256(snapshot_bytes).hexdigest()
        snap = _object(snapshot_bytes.decode('utf-8'))
        if source_row_sha256 is not None and not re.fullmatch('[0-9a-f]{64}', source_row_sha256):
            raise ValueError()
        matches = {}
        for line in source_bytes.splitlines(keepends=True):
            if not line.strip():
                continue
            row = _object(line.decode('utf-8'))
            if (ticker in row.get('tickers', [])
                    and (source_row_sha256 is None
                         or hashlib.sha256(line).hexdigest() == source_row_sha256)):
                matches[line] = row
        reason = 'SOURCE_SELECTION_AMBIGUOUS'
        if len(matches) != 1:
            raise ValueError()
        line, row = next(iter(matches.items()))
        artifact['source_row_sha256'] = hashlib.sha256(line).hexdigest()
        reason = 'SOURCE_AMBIGUOUS'
        if (row['source'] != 'sec_edgar_8k_ex99_body' or row['tickers'] != [ticker]
                or not re.fullmatch(r'8-K - .+ \(\d{10}\) \(Filer\).+EX-99(?:\.1)?', row['title'])):
            raise ValueError()
        url = urlsplit(row['url'])
        match = re.fullmatch(r'/Archives/edgar/data/(\d+)/(\d{18})/([A-Za-z0-9_-]+\.html?)', url.path)
        if not match:
            raise ValueError()
        accession, filename = row['raw_id'].split(':')
        title_cik = re.search(r'\((\d{10})\)', row['title']).group(1)
        if (not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession)
                or accession.replace('-', '') != match[2] or filename != match[3]
                or int(title_cik) != int(match[1]) or accession[:10] != title_cik):
            raise ValueError()
        normalized_row = dict(ticker=ticker, form='8-K', exhibit='EX-99.1' if row['title'].endswith('EX-99.1') else 'EX-99',
                              event_type='earnings_results', accession=accession,
                              url=row['url'], body=row['body'], published_at=row['published_utc'],
                              captured_at=row['first_seen_utc'])
        reason = 'BAD_EQUITY_OR_EXPOSURE'
        if not isinstance(snap['positions'], list):
            raise ValueError()
        equity = _number(snap['equity'])
        cash = _number(snap['cash'])
        reported_long = _number(snap['long_market_value'])
        reported_short = _number(snap['short_market_value'])
        if (equity <= 0 or cash < 0 or reported_long < 0 or reported_short != 0
                or type(snap['n_positions']) is not int
                or snap['n_positions'] != len(snap['positions'])
                or abs(cash + reported_long - reported_short - equity) > EQUITY_TOLERANCE_USD):
            raise ValueError()
        positions = []
        held_mark_residual = None
        for pos in snap['positions']:
            qty = _number(pos['qty'])
            market_value = _number(pos['market_value'])
            if (qty <= 0 or market_value <= 0
                    or pos.get('side', 'long') != 'long'
                    or pos.get('asset_class', 'us_equity') != 'us_equity'
                    or _number(pos.get('leverage', 1)) != 1):
                raise ValueError()
            if pos['symbol'] == ticker:
                held_mark_residual = market_value - qty * _number(pos['current_price'])
                if abs(held_mark_residual) > HELD_MARK_TOLERANCE_USD:
                    raise ValueError()
            positions.append(dict(ticker=pos['symbol'], market_value_usd=pos['market_value'],
                                  instrument='equity', leverage=1))
        position_sum = sum((_number(pos['market_value']) for pos in snap['positions']), Decimal(0))
        position_residual = reported_long - position_sum
        allowed_residual = max(Decimal('1.00'), equity * POSITION_SUM_TOLERANCE_FRACTION)
        if abs(position_residual) > allowed_residual:
            raise ValueError()
        normalized_snap = dict(lane='PC-PAPER', as_of=snap['t'], equity_usd=snap['equity'], positions=positions)
        built = build_warning(json.dumps(normalized_row), json.dumps(normalized_snap), now=now)
        built.update({k: artifact[k] for k in ('source_row_sha256', 'snapshot_sha256')})
        built['source_proof'] = 'Saved SEC 8-K EX-99 earnings-results exhibit; Item 2.02 UNKNOWN.'
        built['snapshot_basis'] = 'Caller-attested PC-PAPER path; long cash-equity snapshot shape, instrument classification not independently verified.'
        if built['status'] == 'PROVISIONAL':
            built['reconciliation'] = {
                'reported_long_minus_positions_usd': str(position_residual),
                'position_sum_tolerance_usd': str(allowed_residual),
                'equity_identity_tolerance_usd': str(EQUITY_TOLERANCE_USD),
                'held_qty_price_residual_usd': str(held_mark_residual),
                'held_mark_tolerance_usd': str(HELD_MARK_TOLERANCE_USD),
            }
            built['reconciliation_note'] = (
                'Saved snapshot uncertainty: reported long minus summed positions '
                f'${position_residual}; tolerance ${allowed_residual}. '
                f'Held quantity-price residual ${held_mark_residual}; tolerance ${HELD_MARK_TOLERANCE_USD}.')
        return built
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, InvalidOperation,
            AttributeError, OverflowError):
        artifact['reason'] = reason
        return artifact


def warn_saved(*, source_jsonl_path: Path, pc_paper_snapshot_path: Path, ticker: str,
               now: datetime, journal_dir: Path, sender=None,
               source_row_sha256: str | None = None) -> dict:
    """Native saved-file entry point; same journal/ACK contract as warn."""
    artifact = build_saved_warning(source_jsonl_path=source_jsonl_path,
                                  pc_paper_snapshot_path=pc_paper_snapshot_path,
                                  ticker=ticker, now=now,
                                  source_row_sha256=source_row_sha256)
    return _deliver(artifact, journal_dir=journal_dir, sender=sender)


def build_lineage_warning_bytes(*, source_bytes: bytes, snapshot_bytes: bytes,
                                ticker: str, now: datetime,
                                source_row_sha256: str | None = None) -> dict:
    """Bind the reviewed pure connector before any journal reservation.

    The legacy builder remains pure and unmodified for connector use, avoiding
    recursive enrichment. Cutoff and decision are the caller's frozen run clock.
    Refusals retain the original dated warning contract (including expiry).
    """
    artifact = build_saved_warning_bytes(source_bytes=source_bytes,
        snapshot_bytes=snapshot_bytes, ticker=ticker, now=now,
        source_row_sha256=source_row_sha256)
    if artifact['status'] != 'PROVISIONAL':
        return artifact
    # Lazy import: the reviewed connector itself consumes the legacy builder.
    from backend.services.saved_sec_event_path import build_saved_sec_event_path
    lineage = build_saved_sec_event_path(event_bytes=source_bytes,
        snapshot_bytes=snapshot_bytes, ticker=ticker,
        cutoff_utc=now.isoformat(), decision_utc=now.isoformat())
    if (lineage['status'] != 'PROVISIONAL'
            or lineage['decision_artifact'] != artifact):
        return {**artifact, 'status': 'REFUSED', 'reason': 'LINEAGE_BINDING_REFUSED'}
    return {**artifact, 'forecast_input_id': lineage['forecast_input_id'],
            'provisional_decision_id': lineage['decision_id'],
            'evidence_packet_sha256': lineage['evidence_packet_sha256'],
            'forecast_id': None, 'new_allocation_usd': '0',
            'lineage_schema': lineage['schema']}


def warn_saved_bytes(*, source_bytes: bytes, snapshot_bytes: bytes, ticker: str,
                     now: datetime, journal_dir: Path, sender=None,
                     source_row_sha256: str | None = None) -> dict:
    """Frozen-input entry point; preserves the existing private journal/ACK path."""
    artifact = build_lineage_warning_bytes(source_bytes=source_bytes,
        snapshot_bytes=snapshot_bytes, ticker=ticker, now=now,
        source_row_sha256=source_row_sha256)
    return _deliver(artifact, journal_dir=journal_dir, sender=sender)
