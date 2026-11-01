"""Local observation only. No network, credential, policy or queue mutation."""
from __future__ import annotations
import ctypes,hashlib,json,os,threading
from datetime import datetime,timezone
from pathlib import Path

SCHEMA='native_pool_carry_lineage/2'
def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def item_id(item,queue_key=None)->str:
    value={'kind':item.get('kind'),'url':item.get('url'),'queue_key':queue_key if queue_key is not None else item.get('key')}
    return sha(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
def native_generation(source:Path,persistent:bool)->dict:
    if not persistent:return {'schema':'reader_pool_generation/1','status':'NONPERSISTENT_FIXTURE_NO_NATIVE_CLAIM'}
    try:
        if os.name!='nt':raise OSError('WINDOWS_NATIVE_UNAVAILABLE')
        from ctypes import wintypes as W
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.GetCurrentProcess.restype=W.HANDLE
        k.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)]
        k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
        times=[W.FILETIME() for _ in range(4)];handle=k.GetCurrentProcess()
        if not k.GetProcessTimes(handle,*[ctypes.byref(v) for v in times]):raise OSError('BIRTH_QUERY')
        image=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(image))
        if not k.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(size)):raise OSError('IMAGE_QUERY')
        result={'schema':'reader_pool_generation/1','status':'NATIVE_SELF','pid':os.getpid(),'parent_pid':os.getppid(),
                'raw_birth':(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime,
                'image_path':str(Path(image.value).resolve()),'image_sha256':sha(Path(image.value).read_bytes()),
                'reader_source_path':str(Path(source).resolve()),'reader_source_sha256':sha(Path(source).read_bytes()),
                'helper_source_sha256':sha(Path(__file__).read_bytes())}
        result['generation_id']=sha(json.dumps(result,sort_keys=True,separators=(',',':')).encode())
        return result
    except (OSError,ValueError):
        return {'schema':'reader_pool_generation/1','status':'NATIVE_QUERY_UNAVAILABLE','pid':os.getpid(),'raw_birth':None}

class CarryReceipts:
    def __init__(self,generation,clock):
        self.generation=generation;self.clock=clock;self.lock=threading.RLock()
        self.source={'present':None,'status':'NOT_LOADED','sha256':None,'item_count':None}
        self.entries=[];self.accepted=set();self.activity={};self.active=set();self.returned=set();self.policy_removed={}
        self.load_complete=False;self.source_deleted=None;self.saved=None;self.body_total=0;self.bodies=[]
        self.errors=[];self.finalized_utc=None
    def capture(self,path,parsed):
        try:
            with Path(path).open('rb') as f:raw=f.read(8*1024**2+1)
        except FileNotFoundError:
            self.source={'present':False,'status':'GENUINELY_ABSENT' if parsed=={} else 'CHANGED_DURING_CAPTURE','sha256':None,'item_count':None};return
        except OSError:
            self.source={'present':None,'status':'READ_FAILED_UNQUALIFIED','sha256':None,'item_count':None};return
        self.source={'present':True,'status':'CAPTURED','sha256':sha(raw),'item_count':None}
        if len(raw)>8*1024**2:self.source['status']='OVERSIZE_UNQUALIFIED';return
        try:
            actual=json.loads(raw.decode('utf-8'))
            if actual!=parsed or not isinstance(actual,dict) or not isinstance(actual.get('items'),list):raise ValueError('SHAPE_OR_RACE')
            self.source.update(item_count=len(actual['items']),t=actual.get('t'),producer_generation=actual.get('generation'))
        except (ValueError,UnicodeError):self.source['status']='PARSE_OR_RACE_UNQUALIFIED'
    def decision(self,index,item,identity,decision,reason):
        with self.lock:
            entry={'index':index,'item_id':identity,'decision':decision,'reason':reason}
            entry['entry_id']=sha(json.dumps({'source_sha256':self.source['sha256'],'index':index,'item_id':identity},sort_keys=True,separators=(',',':')).encode())
            self.entries.append(entry)
            if decision=='ACCEPTED':self.accepted.add(identity);self.activity[identity]='QUEUED'
    def note(self,identity,state):
        with self.lock:
            if identity not in self.accepted:return
            self.activity[identity]=state
            if state=='DEQUEUED_FOR_PROCESS':self.active.add(identity)
            elif state=='PROCESS_RETURNED':self.active.discard(identity);self.returned.add(identity)
            elif state=='REQUEUED':self.active.discard(identity)
    def removed(self,identities,reason):
        with self.lock:
            for identity in identities:
                if identity in self.accepted:self.policy_removed[identity]=reason;self.activity[identity]='REMOVED_BY_EXISTING_POLICY'
    def saved_carry(self,path,items,generation,identities,ok):
        with self.lock:
            self.saved={'status':'WRITTEN' if ok else 'WRITE_FAILED_UNQUALIFIED','path':str(path),'item_count':len(items),'item_ids':identities,'generation':generation,'file_sha256':None}
            if ok:
                try:self.saved['file_sha256']=sha(Path(path).read_bytes())
                except OSError:self.saved['status']='READBACK_FAILED_UNQUALIFIED'
    def stored_body(self,identity,stored,root):
        witness={'item_id':identity,'status':'STORED_POINTER_UNAVAILABLE'}
        try:
            if not isinstance(stored,dict) or not isinstance(stored.get('path'),str):raise ValueError('NO_POINTER')
            path=Path(stored['path']).resolve()
            if Path(root).resolve() not in path.parents or path.suffix!='.json':raise ValueError('OUTSIDE_CORPUS')
            with path.open('rb') as f:raw=f.read(16*1024**2+1)
            if len(raw)>16*1024**2:raise ValueError('BODY_BOUND')
            record=json.loads(raw)
            if not isinstance(record,dict):raise ValueError('BODY_DOCUMENT_SCHEMA')
            body=record.get('text')
            if not isinstance(body,str) or not body.strip() or record.get('sha')!=stored.get('sha'):raise ValueError('NO_BODY_OR_IDENTITY')
            witness.update(status='ACTUAL_BODY_FILE_READ_BACK',path=str(path),source_id=record['sha'],file_sha256=sha(raw),body_sha256=sha(body.encode()),body_chars=len(body),duplicate=stored.get('duplicate') is True)
        except (OSError,ValueError,TypeError):witness['status']='BODY_PERSISTENCE_UNPROVED'
        with self.lock:self.body_total+=1;self.bodies.append(witness);self.bodies=self.bodies[-256:]
    def snapshot(self,pending_ids):
        with self.lock:
            queued=self.accepted&set(pending_ids)
            accounted=queued|self.active|self.returned|set(self.policy_removed)
            source_count=self.source['item_count']
            complete=self.load_complete and not self.errors and self.generation.get('status')=='NATIVE_SELF' and (
                source_count==len(self.entries) and self.source['status']=='CAPTURED' and self.source_deleted is True
                if source_count is not None else self.source['status']=='GENUINELY_ABSENT')
            return {'schema':SCHEMA,'observed_utc':self.clock().isoformat(),'generation':self.generation,
                    'status':'ACCOUNTED' if complete and not self.accepted-accounted else 'UNQUALIFIED',
                    'source':dict(self.source),'entries':[dict(e) for e in self.entries],
                    'accepted_item_ids':sorted(self.accepted),'queued_item_ids':sorted(queued),
                    'accepted_entry_count':sum(e['decision']=='ACCEPTED' for e in self.entries),
                    'rejected_entry_count':sum(e['decision']=='REJECTED' for e in self.entries),
                    'active_item_ids':sorted(self.active),'process_returned_item_ids':sorted(self.returned),
                    'policy_removed_item_ids':dict(self.policy_removed),'unaccounted_item_ids':sorted(self.accepted-accounted),
                    'handoff_consumed_entry_ids':[e['entry_id'] for e in self.entries] if self.load_complete else [],
                    'handoff_consumed_meaning':'INPUT_DECISION_COMPLETED_NOT_ARTICLE_READ_OR_BODY_STORED',
                    'source_deleted':self.source_deleted,'load_complete':self.load_complete,'saved_carry':self.saved,
                    'finalized_utc':self.finalized_utc,'body_evidence_total':self.body_total,
                    'body_evidence':[dict(v) for v in self.bodies],'body_history_truncated':self.body_total>len(self.bodies),
                    'errors':list(self.errors)}
