"""Synthetic quote/identity/window mechanics, never prices or performance evidence."""
from copy import deepcopy
from datetime import timedelta
import math

import pytest
from backend.services import beta_v1_news_outcomes as O, beta_v1_news_runtime as R
from backend.services import beta_v1_policy as P
from backend.tests.test_beta_v1_news_runtime import original_fixture


def quote_fixture(original, *, winning=True):
    row=original['record'];binding=original['capture']['binding'];quotes=[]
    for sid,ticker in ((binding['identity']['security_id'],row['ticker']),
                       (binding['target']['benchmark_security_id'],'SPY')):
        for endpoint in ('label_start_at','label_end_at'):
            close=row[endpoint]
            price=100 if endpoint=='label_start_at' else (120 if ticker!='SPY' and winning else 90 if ticker!='SPY' else 105)
            quotes.append({'security_id':sid,'ticker':ticker,'session_close_at':close,'close':price,
                'available_at':(R.utc(close)+timedelta(minutes=10)).isoformat(),
                'source_hash':P.digest({'synthetic':sid,'endpoint':endpoint}),
                'price_basis':row['price_basis'],'price_basis_id':binding['target']['price_basis_id'],'cost_basis':'GROSS'})
    cutoff=(R.utc(row['label_end_at'])+timedelta(hours=1)).isoformat()
    return quotes,qualify_quotes(quotes),cutoff


def qualify_quotes(quotes):
    qualified={}
    for quote in quotes:
        try:key=P.digest(quote)
        except ValueError:continue
        qualified[key]={'quote_sha256':key,'decision':'EXACT_ENDPOINT_ACCEPTED','independent':True,
            'reviewer':'synthetic-independent-quote','source_hash':quote['source_hash'],
            'source_ref':'fixture://quotes','qualification_reason':'synthetic exact endpoint only',
            'reviewed_at':(R.utc(quote['available_at'])+timedelta(minutes=10)).isoformat()}
    return qualified


@pytest.mark.parametrize('winning',[True,False])
def test_exact_expired_original_scores_success_and_loss_without_current_reuse(winning):
    original=original_fixture();snapshot=deepcopy(original)
    quotes,q,cutoff=quote_fixture(original,winning=winning)
    result=O.score(original,quotes,q,cutoff=cutoff)
    assert result['status']=='OUTCOME_EXTERNAL_REVIEW_REQUIRED' and not result['learning_authority']
    assert result['original_probability']==.7 and original==snapshot
    assert R.utc(cutoff)>R.utc(original['record']['valid_until_at'])
    expected=.15 if winning else -.15
    assert result['gross_relative_price_return']==pytest.approx(expected)
    assert result['graded_record']['y']==int(winning)
    assert result['brier']==pytest.approx((.7-int(winning))**2)
    assert result['log_loss']==pytest.approx(-math.log(.7 if winning else .3))
    assert result['net_50bps_relative_diagnostic']==pytest.approx(expected-.005)
    assert result['diagnostic_cost_only'] and result['original_forecast_at']==original['record']['forecast_at']
    assert result['grade_available_at']==max(R.utc(v['reviewed_at']) for v in q.values()).isoformat()
    assert result['scored_at']==cutoff


@pytest.mark.parametrize('mutation',[
    lambda q:q[0].update(security_id='different-security'),
    lambda q:q[2].update(security_id='different-SPY'),
    lambda q:q[0].update(session_close_at=(R.utc(q[0]['session_close_at'])+timedelta(days=1)).isoformat()),
    lambda q:q[0].update(price_basis='TOTAL_RETURN'),
    lambda q:q[0].update(price_basis_id='other-provider-basis'),
    lambda q:q[0].update(cost_basis='NET'),
    lambda q:q[0].update(close=True),lambda q:q[0].update(close=0),lambda q:q[0].update(close=-1),
    lambda q:q[0].update(close=float('inf')),
    lambda q:q.__setitem__(1,deepcopy(q[0])),
])
def test_wrong_security_endpoint_basis_price_duplicates_never_yield_zero(mutation):
    original=original_fixture();quotes,_,cutoff=quote_fixture(original)
    mutation(quotes)
    result=O.score(original,quotes,qualify_quotes(quotes),cutoff=cutoff)
    assert result['status']=='UNAVAILABLE' and result['records']==[]
    assert 'graded_record' not in result and 'brier' not in result


def test_future_quote_or_review_and_missing_access_are_named_unavailable():
    original=original_fixture();quotes,q,cutoff=quote_fixture(original)
    quotes[-1]['available_at']=(R.utc(cutoff)+timedelta(seconds=1)).isoformat()
    result=O.score(original,quotes,qualify_quotes(quotes),cutoff=cutoff)
    assert result['status']=='UNAVAILABLE'
    unavailable=O.score(original,None,{},cutoff=original['record']['forecast_at'])
    assert unavailable['status']=='UNAVAILABLE' and unavailable['reason']=='QUOTE_ACCESS_UNAVAILABLE'
    not_due=O.score(original,[],{},cutoff=original['record']['forecast_at'])
    assert not_due['status']=='NOT_YET_DUE'


def test_original_capture_identity_probability_and_review_are_bound():
    original=original_fixture();quotes,q,cutoff=quote_fixture(original)
    for field,value in (('x',.9),('ticker','BBB'),('source_hash','0'*64)):
        changed=deepcopy(original);changed['record'][field]=value
        assert O.score(changed,quotes,q,cutoff=cutoff)['status']=='UNAVAILABLE'
    changed=deepcopy(original);changed['numeric_review']['independent']=False
    assert O.score(changed,quotes,q,cutoff=cutoff)['status']=='UNAVAILABLE'
    changed=deepcopy(original);changed['capture']['raw_reply']='{"p":null,"abstain":true}'
    assert O.score(changed,quotes,q,cutoff=cutoff)['status']=='UNAVAILABLE'


def test_catchup_duplicates_id_root_conflicts_and_revisions_preserve_prior_grade():
    original=original_fixture();quotes,q,cutoff=quote_fixture(original);ident=original['record']['forecast_id']
    first=O.catchup([original,deepcopy(original)],{ident:quotes},q,cutoff=cutoff)
    assert len(first['grades'])==1
    frozen=deepcopy(first['grades'])
    revised=deepcopy(quotes);revised[1]['close']=500
    repeated=O.catchup([original],{ident:revised},qualify_quotes(revised),
                       cutoff=(R.utc(cutoff)+timedelta(days=1)).isoformat(),existing=first['grades'])
    assert repeated['grades']==frozen and first['grades']==frozen
    conflicting=deepcopy(original);conflicting['record']['x']=.1
    result=O.catchup([original,conflicting],{ident:quotes},q,cutoff=cutoff,existing=frozen)
    assert result['grades']==frozen and result['refusals'][0]['reason']=='CONFLICTING_ORIGINAL_ID_OR_ROOT_QUARANTINED'
    root_clone=deepcopy(original);root_clone['record']['forecast_id']='another-original'
    quarantined=O.catchup([original,root_clone],{ident:quotes},q,cutoff=cutoff)
    assert not quarantined['grades'] and len(quarantined['refusals'])==2



def test_sequential_same_cell_root_conflict_preserves_saved_bytes():
    original=original_fixture();quotes,q,cutoff=quote_fixture(original);ident=original['record']['forecast_id']
    first=O.catchup([original],{ident:quotes},q,cutoff=cutoff);before=R.encode(first['grades'])
    new=deepcopy(original);new['record']['forecast_id']='later-conflicting-original'
    result=O.catchup([new],{},q,cutoff=cutoff,existing=first['grades'])
    assert R.encode(result['grades'])==before and R.encode(first['grades'])==before
    assert result['refusals'][0]['reason']=='CONFLICTING_ORIGINAL_ID_OR_ROOT_QUARANTINED'


def test_same_event_separate_h5_h21_exact_cells_both_grade():
    h21=original_fixture();h5=original_fixture(horizon=5)
    q21,reviews21,cutoff21=quote_fixture(h21);q5,reviews5,cutoff5=quote_fixture(h5)
    assert h21['record']['root_event']==h5['record']['root_event']
    ids=[h21['record']['forecast_id'],h5['record']['forecast_id']];assert len(set(ids))==2
    cutoff=max(cutoff21,cutoff5)
    first=O.catchup([h21],{ids[0]:q21},reviews21,cutoff=cutoff)
    both=O.catchup([h5],{ids[1]:q5},reviews5,cutoff=cutoff,existing=first['grades'])
    assert len(both['grades'])==2 and not both['refusals']
    assert both['grades'][ids[0]]==first['grades'][ids[0]]


def test_existing_plus_incoming_count_and_size_bound_before_deepcopy(monkeypatch):
    monkeypatch.setattr(O,'deepcopy',lambda *a:pytest.fail('must refuse before copy'))
    with pytest.raises(ValueError,match='ROW_CAP'):O.catchup([],{}, {},cutoff='2026-10-12T12:00:00Z',existing={str(i):{} for i in range(O.MAX_ORIGINALS+1)})
    with pytest.raises(ValueError,match='INPUT_CAP'):O.catchup([],{}, {},cutoff='2026-10-12T12:00:00Z',existing={'huge':{'text':'x'*R.MAX_OUTPUT}})
