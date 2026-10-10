"""Native daily-pass audit cache producer. No CLI, task or session control."""
import hashlib,json,os,stat,math,subprocess,sys,tempfile,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from backend.services import process_census as PC

def process_rows(timeout=3):return PC.read_processes(timeout=timeout)

class Refused(RuntimeError):pass

def file_identity(info):return (info.st_dev,info.st_ino)

def destination_guard(root,day,inputs=()):
    """Exact local day, not an in-root historical junction or file alias."""
    folder=root/'pc_book'/day
    for p in (root/'pc_book',folder):
        if p.resolve()!=p:raise Refused('noncanonical output-day parent alias')
        if os.path.lexists(p):
            s=p.lstat()
            if not stat.S_ISDIR(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400:
                raise Refused('output-day parent symlink/junction')
    for p in (folder/'learn_survivorship_audit.json',folder/'survivorship_audit_examinations.jsonl'):
        if p.resolve()!=p:raise Refused('output destination alias')
        if os.path.lexists(p):
            s=p.lstat()
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or getattr(s,'st_file_attributes',0)&0x400:
                raise Refused('output/examination destination is not a single owned regular file')
            if any(os.path.samefile(p,source) for source in inputs):raise Refused('output/input alias')

def valid_payload(payload,fingerprint):
    if not isinstance(payload,dict) or payload.get('bars_fingerprint')!=fingerprint:raise Refused('invalid native cache fingerprint/schema')
    fields={'n_symbols','panel_last_session','stopped_30d_before_end','stopped_90d_before_end','stopped_180d_before_end','fraction_dead_90d','verdict','ran_utc','bars_fingerprint','bounded_audit_identity'}
    if set(payload)!=fields:raise Refused('unexpected or incomplete native cache schema')
    n=payload.get('n_symbols');counts=[payload.get(f'stopped_{d}d_before_end') for d in (30,90,180)]
    if type(n) is not int or n<=0 or any(type(c) is not int or not 0<=c<=n for c in counts):raise Refused('invalid native cache counts')
    if counts!=sorted(counts,reverse=True):raise Refused('invalid native cache maturity counts')
    frac=payload.get('fraction_dead_90d')
    if type(frac) not in (int,float) or not math.isfinite(frac) or frac!=round(counts[1]/n,4):raise Refused('invalid native cache fraction')
    try:
        panel=datetime.strptime(payload['panel_last_session'],'%Y-%m-%d')
        if panel.date().isoformat()!=payload['panel_last_session']:raise ValueError('noncanonical date')
        ran=datetime.fromisoformat(payload['ran_utc'].replace('Z','+00:00'))
        if ran.utcoffset() is None or ran>datetime.now(timezone.utc):raise ValueError('invalid time')
    except (KeyError,ValueError,TypeError,AttributeError):raise Refused('invalid native cache dates')
    if not isinstance(payload.get('verdict'),str) or not payload['verdict']:raise Refused('missing native cache verdict')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()

def inventory():
    from backend.services import xs_ranker as XR,stitched_tickers as ST
    paths=[Path(p).resolve() for p in XR.survivorship_free_paths()]
    aux=[Path(ST.SEC_FACTS_PATH).resolve(),Path(ST.COMPANY_TICKERS_PATH).resolve()]
    return {'ordered_native_paths':[str(p) for p in paths],
            'auxiliary_present':[str(p) for p in aux if p.exists()],
            'auxiliary_missing':[str(p) for p in aux if not p.exists()]}

def verify_inventory(expected):
    current=inventory()
    if any(current[k]!=expected[k] for k in ('ordered_native_paths','auxiliary_present','auxiliary_missing')):
        raise Refused('native selection/auxiliary inventory drift')

def committed_output_proof(ledger,data,expected,day):
    """Bind current bytes to a prior canonical COMMITTED examination."""
    if not ledger.is_file() or ledger.stat().st_size>4*1024*1024:raise Refused('committed output provenance unavailable/bound exceeded')
    original=sha(ledger);last=None
    with ledger.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip():continue
            try:row=json.loads(line)
            except ValueError:raise Refused('malformed output examination provenance')
            if not isinstance(row,dict):raise Refused('malformed output examination provenance')
            if row.get('status')=='COMMITTED':last=row
    if sha(ledger)!=original:raise Refused('output examination provenance drift')
    if not last or last.get('producer')!='native_bounded_audit' or last.get('local_output_day')!=day or last.get('identity')!=expected or last.get('after_sha256')!=hashlib.sha256(data).hexdigest():
        raise Refused('cache differs from authentic committed audit output')
    return original

def identity():
    from backend import config as C
    from backend.services import xs_ranker as XR,stitched_tickers as ST,bar_defects as BD,sim_session as SS
    from scripts import survivorship_audit_bounded as B
    selected=inventory();paths=[Path(p) for p in selected['ordered_native_paths']]
    if not paths or any(not p.is_file() for p in paths):raise Refused('missing native bars')
    files=paths+[Path(m.__file__).resolve() for m in (C,XR,ST,BD,SS,PC,B)]+[Path(__file__).resolve(),Path(__file__).with_name('daily_pass.py').resolve()]+[Path(p) for p in selected['auxiliary_present']]
    frozen={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files}
    if inventory()!=selected:raise Refused('native inventory changed during identity hashing')
    return {'ordered_native_paths':selected['ordered_native_paths'],
            'pins':frozen,
            'auxiliary_present':selected['auxiliary_present'],
            'auxiliary_missing':selected['auxiliary_missing'],
            'bars_fingerprint':'|'.join(f'{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}' for p in paths)}

def native_child(timeout,stop):
    with tempfile.TemporaryDirectory(prefix='aegis-native-audit-') as folder:
        result=Path(folder)/'result.json'
        cmd=[sys.executable,'-m','scripts.survivorship_audit_bounded','--private-result',str(result),'--stop-file',str(stop)]
        r=subprocess.run(cmd,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=timeout)
        if r.returncode or not result.exists():raise Refused('bounded native subprocess failed; no cache replacement')
        return json.loads(result.read_text(encoding='utf-8'))

def produce(*,root=None,budget_seconds=180,audit_runner=native_child):
    """Own START_LOCK briefly; no active/uncertain writer and no history rewrite."""
    from backend import config as C
    from backend.services import sim_session as SS,disk_guard as DG
    started=time.monotonic();day=datetime.now().date().isoformat()
    root=Path(root if root is not None else C.OPTIMUS_LEDGER_DIR).resolve()
    lock=Path(SS.START_LOCK);token=None;owned_lock=None;complete_lock=False;tmp=None;owned_tmp=None;committed=False;before=None
    def guard():
        if not 25<=budget_seconds<=180 or time.monotonic()-started>=budget_seconds-5:raise Refused('audit deadline/reserve exhausted')
        if datetime.now().date().isoformat()!=day:raise Refused('local output day changed')
        if lock.parent.resolve()!=root/'sim' or Path(SS.SESSION_PATH).parent.resolve()!=root/'sim':raise Refused('cache and native owner roots differ')
        destination_guard(root,day,before['pins'] if before else ())
        if before is not None:verify_inventory(before)
        if Path(SS.STOP_FLAG).exists():raise Refused('owner STOP')
        if owned_lock is not None and (not lock.is_file() or file_identity(lock.lstat())!=owned_lock or lock.read_bytes()!=token):raise Refused('START_LOCK ownership lost')
        state_path=Path(SS.SESSION_PATH)
        if state_path.exists():
            try:state=json.loads(state_path.read_text(encoding='utf-8'))
            except (OSError,ValueError):raise Refused('unknown session state')
            if not isinstance(state,dict) or state.get('state') not in ('IDLE','STOPPED','COMPLETED'):raise Refused('active/starting/unknown session writer')
        rows=process_rows(timeout=min(3,budget_seconds-(time.monotonic()-started)-5))
        if rows is None:raise Refused('process ownership inaccessible')
        for p in rows:
            command=str(p.get('cmd') or p.get('CommandLine') or p.get('cmdline') or '')
            name=str(p.get('Name') or p.get('name') or '').lower()
            if 'sim_run' in command.lower() or (name.startswith('python') and not command):raise Refused('active or unknown sim process writer')
        if time.monotonic()-started>=budget_seconds-5:raise Refused('audit deadline after ownership probe')
    try:
        guard();lock.parent.mkdir(parents=True,exist_ok=True)
        token=json.dumps({'pid':os.getpid(),'at':datetime.now(timezone.utc).isoformat(),'producer_nonce':uuid.uuid4().hex}).encode()
        try:fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:token=None;raise Refused('another START_LOCK owner; never remove it')
        owned_lock=file_identity(os.fstat(fd))
        with os.fdopen(fd,'wb') as f:f.write(token);f.flush();os.fsync(f.fileno())
        complete_lock=True
        guard();before=identity();guard()
        cache=root/'pc_book'/day/'learn_survivorship_audit.json'
        if not cache.resolve().is_relative_to(root) or cache.is_symlink() or (cache.exists() and cache.stat().st_nlink!=1):raise Refused('cache path alias')
        old=cache.read_bytes() if cache.exists() else None
        if old:
            try:prior=json.loads(old)
            except ValueError:raise Refused('malformed existing cache')
            if not isinstance(prior,dict):raise Refused('malformed existing cache schema')
            if prior.get('bounded_audit_identity')==before:
                valid_payload(prior,before['bars_fingerprint'])
                ledger=cache.parent/'survivorship_audit_examinations.jsonl'
                ledger_pin=committed_output_proof(ledger,old,before,day)
                guard()
                if identity()!=before:raise Refused('source/input drift before reuse')
                guard()
                if not cache.exists() or cache.read_bytes()!=old or sha(cache)!=hashlib.sha256(old).hexdigest():raise Refused('cache byte drift before reuse')
                if sha(ledger)!=ledger_pin:raise Refused('committed audit receipt changed before reuse')
                verify_inventory(before)
                return {'status':'nothing_to_do','cache_path':str(cache),'reason':'full native source/input identity unchanged','bars_fingerprint':before['bars_fingerprint']}
        result=audit_runner(min(160,budget_seconds-(time.monotonic()-started)-15),SS.STOP_FLAG)
        guard()
        if identity()!=before:raise Refused('source/input selection/hash drift')
        guard()
        if result.get('canonical_input_paths')!=before['ordered_native_paths'] or not result.get('native_input_selection_bound'):raise Refused('native selection not bound')
        for p,pin in result['source_and_input_pins'].items():
            if before['pins'].get(p)!=pin:raise Refused('native result source/input differs')
        audit=result.get('audit')
        if not isinstance(audit,dict) or not audit.get('panel_last_session') or not isinstance(audit.get('n_symbols'),int) or audit['n_symbols']<=0:raise Refused('missing native result')
        payload={**audit,'ran_utc':result['ran_utc'],'bars_fingerprint':before['bars_fingerprint'],'bounded_audit_identity':before}
        valid_payload(payload,before['bars_fingerprint'])
        data=(json.dumps(payload,indent=1)+'\n').encode();guard();cache.parent.mkdir(parents=True,exist_ok=True)
        nonce=uuid.uuid4().hex
        backup=cache.parent/f'learn_survivorship_audit.backup_{nonce}.bin'
        if old is not None:
            with backup.open('xb') as f:f.write(old);f.flush();os.fsync(f.fileno())
        tmp=cache.parent/f'.survivorship_audit_{nonce}.tmp'
        with tmp.open('xb') as f:
            owned_tmp=file_identity(os.fstat(f.fileno()));f.write(data);f.flush();os.fsync(f.fileno())
        guard()
        if identity()!=before or (cache.read_bytes() if cache.exists() else None)!=old:raise Refused('cache/source/input drift at mutation')
        examination={'utc':datetime.now(timezone.utc).isoformat(),'producer':'native_bounded_audit','local_output_day':day,'before_sha256':hashlib.sha256(old).hexdigest() if old is not None else None,'after_sha256':hashlib.sha256(data).hexdigest(),'backup_path':str(backup) if old is not None else None,'identity':before,'status':'PREPARED'}
        ledger=cache.parent/'survivorship_audit_examinations.jsonl'
        DG.locked_append_line(ledger,json.dumps(examination))
        guard()
        if identity()!=before or (cache.read_bytes() if cache.exists() else None)!=old:raise Refused('drift after examination before mutation')
        guard()
        verify_inventory(before)
        os.replace(tmp,cache);tmp=None;committed=True
        examination['status']='COMMITTED';DG.locked_append_line(ledger,json.dumps(examination))
        return {'status':'ok','cache_path':str(cache),'examination_path':str(ledger),'backup_path':str(backup) if old is not None else None,'panel_last_session':audit['panel_last_session'],'elapsed_seconds':round(time.monotonic()-started,3)}
    except (Refused,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        return {'status':'refused','reason':str(exc),'cache_replaced':committed,'elapsed_seconds':round(time.monotonic()-started,3)}
    finally:
        try:
            if tmp is not None and owned_tmp is not None and tmp.exists() and file_identity(tmp.lstat())==owned_tmp:tmp.unlink()
        finally:
            # Partial writes are still OUR acquired inode. Completed tokens
            # additionally refuse in-place foreign content; replacements never
            # match the acquired file identity. Temporary cleanup cannot skip it.
            if owned_lock is not None and lock.exists() and file_identity(lock.lstat())==owned_lock and (not complete_lock or lock.read_bytes()==token):lock.unlink()
