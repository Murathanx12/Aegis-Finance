"""Pure bounded forecast receipt metadata. No prompts/errors/financial values."""
def count(value):return value if type(value) is int and value>=0 else None

def _finish(unit,attempted,failed,written,reason,*,complete=True,scope='ALL_RETURNED_ROWS',classes=None):
    if written is None:state='UNAVAILABLE'
    elif failed is not None and failed>0:state='DEGRADED'
    elif written>0:state='WRITTEN'
    else:state='ZERO_WRITES'
    return {'schema':'forecast-accrual-receipt/1','unit':unit,'attempted':attempted,'failed':failed,'written':written,
        'count_scope':scope,'counts_complete':complete,'status':state,
        'zero_write_reason':reason if written==0 else None,'unavailable_reason':reason if written is None else None,
        'failure_class':'CALL_OR_PARSE_FAILURE_UNCLASSIFIED' if failed is not None and failed>0 else None,
        'review_status_classes':classes or {}}

def _status(value):
    # Prefixes are source-defined enums; arbitrary/raw error strings never pass.
    prefix=value.split(':',1)[0] if isinstance(value,str) else None
    return {'ok':'OK','disabled':'DISABLED','nothing_to_review':'NOTHING_TO_REVIEW',
        'daily_cap_reached':'DAILY_CAP_REACHED','llm_unavailable':'LLM_UNAVAILABLE',
        'import_failed':'IMPORT_FAILED','error':'REVIEW_EXCEPTION','already_marked':'ALREADY_MARKED'}.get(prefix,'UNKNOWN')

def arena_metadata(summary):
    rows=summary.get('receipts') if isinstance(summary,dict) else None
    if not isinstance(rows,list) or not rows:
        reason='NO_SEEDED_BOOKS' if isinstance(summary,dict) and summary.get('status')=='no_seeded_books' else 'COUNTERS_UNAVAILABLE'
        return _finish('ARENA_REVIEW_NAMES',None,None,None,reason,complete=False)
    triples=[];classes={};partial=[]
    for row in rows:
        review=row.get('belief_review') if isinstance(row,dict) else None
        status=_status(review.get('status')) if isinstance(review,dict) else _status(row.get('status')) if isinstance(row,dict) else 'UNKNOWN'
        classes[status]=classes.get(status,0)+1
        if not isinstance(review,dict):continue
        values=tuple(count(review.get(k)) for k in ('attempted','failed','written'))
        if any(v is None for v in values):
            partial.append({'attempted':values[0],'failed':values[1],'written':values[2],'status_class':status});continue
        if values[1]>values[0] or values[2]>values[0] or values[1]+values[2]>values[0]:continue
        triples.append(values)
    if not triples:
        known_skip={'DISABLED','NOTHING_TO_REVIEW','DAILY_CAP_REACHED','LLM_UNAVAILABLE','IMPORT_FAILED','REVIEW_EXCEPTION','ALREADY_MARKED'}
        reason=next(iter(classes)) if len(classes)==1 and next(iter(classes)) in known_skip else 'COUNTERS_UNAVAILABLE'
        result=_finish('ARENA_REVIEW_NAMES',None,None,None,reason,complete=False,classes=classes)
        result['partial_review_counters']=partial;return result
    attempted,failed,written=(sum(t[i] for t in triples) for i in range(3))
    complete=len(triples)==len(rows)
    if written==0 and attempted>0 and failed==attempted:reason='ALL_ATTEMPTS_FAILED' if complete else 'ALL_REPORTED_ATTEMPTS_FAILED'
    elif written==0 and failed>0:reason='REPORTED_ATTEMPTS_FAILED_NO_WRITES'
    elif written==0 and 'NOTHING_TO_REVIEW' in classes:reason='NOTHING_TO_REVIEW'
    elif written==0 and 'DAILY_CAP_REACHED' in classes:reason='DAILY_CAP_REACHED'
    else:reason='NO_REPORTED_FORECAST_WRITES'
    result=_finish('ARENA_REVIEW_NAMES',attempted,failed,written,reason,complete=complete,
        scope='ALL_RETURNED_REVIEWS' if complete else 'REPORTED_VALID_REVIEWS_ONLY',classes=classes)
    result['partial_review_counters']=partial;return result

def why_metadata(result):
    if not isinstance(result,dict):return _finish('WHY_MOVED_LENSES',None,None,None,'COUNTERS_UNAVAILABLE',complete=False)
    lenses=result.get('lenses');rows=list(lenses.values()) if isinstance(lenses,dict) else lenses if isinstance(lenses,list) else None
    valid=rows is not None and all(isinstance(r,dict) and r.get('status') in ('ok','degraded') for r in rows)
    attempted=len(rows) if valid else None
    failed=sum(r['status']=='degraded' for r in rows) if valid else None
    written=count(result.get('n_predictions_minted'))
    state=result.get('status')
    if state=='already_written':reason='ALREADY_WRITTEN'
    elif state=='attribution_only':reason='HYPOTHESES_DISABLED'
    elif valid and attempted and failed==attempted:reason='ALL_LENSES_DEGRADED'
    elif written==0:reason='NO_VALID_FORWARD_CLAIMS'
    else:reason='COUNTERS_UNAVAILABLE'
    return _finish('WHY_MOVED_LENSES',attempted,failed,written,reason,complete=valid and written is not None,
        scope='RETURNED_LENSES_AND_MINTED_RECORDS')

def forecast_metadata(kind,result):
    return arena_metadata(result) if kind=='arena' else why_metadata(result)
