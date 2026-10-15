import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from backend.services.portfolio_intelligence import branch_population as p
from backend.services.portfolio_intelligence import branch_population_registry as r

def test_actual_existing_helper_append_only_reconciliation_preserves_old_rows(tmp_path):
 from backend.services.portfolio_intelligence.trial_registry import ensure_trial_registered
 db=tmp_path/'FIXTURE_NOT_CANONICAL.db'
 ensure_trial_registered('fixture:local',{'original':'retained'},db_path=db)
 before=r.actual_rows(db)
 peerrow=dict(before[0],id=999,param='fixture:peer',created_at='2020-01-01',notes=json.dumps({'original':'remote'}))
 peer={'schema':'actual_registry_peer_export/1','site':'railway_actual','observed_at':'2026-10-15T12:00:00Z','rows':[peerrow],'rows_sha256':p.digest([peerrow]),'count':1}
 out=r.reconcile_peer(peer,db_path=db,ensure_trial_registered=ensure_trial_registered)
 after=r.actual_rows(db)
 assert after[0]==before[0] and len(after)==2 and out['added'][0]['param']=='fixture:peer'
 added=json.loads(after[1]['notes']);assert added['original_row']==peerrow and after[1]['created_at']!='2020-01-01'
 assert r.reconcile_peer(peer,db_path=db,ensure_trial_registered=ensure_trial_registered)['added']==[]
 peer['rows'][0]['notes']='changed'
 with pytest.raises(ValueError,match='PINNED_PEER_EXPORT'):r.reconcile_peer(peer,db_path=db,ensure_trial_registered=ensure_trial_registered)
