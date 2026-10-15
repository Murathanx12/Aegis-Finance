"""Explicit append-only operations using the existing registry helper.

No imports mutate a database. Export before either site registers; preserve
peer row provenance for missing natural params, never update existing rows.
"""
import datetime,json,sqlite3
from pathlib import Path
from backend.services.portfolio_intelligence.branch_population import digest
from backend.services.portfolio_intelligence.branch_population_runtime import register_before_data,verify_actual_registry,committed_identity

def actual_rows(db_path):
 path=Path(db_path).resolve()
 if not path.is_file():raise ValueError('EXISTING_ACTUAL_REGISTRY_REQUIRED')
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
  conn.row_factory=sqlite3.Row
  rows=[dict(row) for row in conn.execute('SELECT * FROM rule_experiments ORDER BY id')]
 if len(rows)>10000 or len({r['param'] for r in rows})!=len(rows):raise ValueError('BOUNDED_UNIQUE_NATURAL_REGISTRY_REQUIRED')
 return rows

def export_registry(db_path,site):
 if site not in ('local_canonical','railway_actual'):raise ValueError('EXACT_REGISTRY_SITE')
 rows=actual_rows(db_path)
 return {'schema':'actual_registry_peer_export/1','site':site,'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':rows,'rows_sha256':digest(rows),'count':len(rows),'max_cumulative':max((r['cumulative_trials'] for r in rows),default=0)}

def reconcile_peer(peer,*,db_path,ensure_trial_registered):
 if peer.get('schema')!='actual_registry_peer_export/1' or peer.get('rows_sha256')!=digest(peer['rows']) or peer.get('count')!=len(peer['rows']):raise ValueError('ACTUAL_PINNED_PEER_EXPORT_REQUIRED')
 current=actual_rows(db_path);existing={r['param']:r for r in current};added=[]
 for row in peer['rows']:
  if row['param'] in existing:continue
  notes={'kind':'append_only_peer_registry_reconciliation','peer_site':peer['site'],'peer_observed_at':peer['observed_at'],'peer_export_sha256':digest(peer),'original_row':row,'original_row_sha256':digest(row),'no_existing_row_updated':True,'no_historical_clock_inherited':True}
  identity=ensure_trial_registered(row['param'],notes,db_path=db_path,config_version=row['config_version'],lane_id=row['lane_id'])
  added.append({'id':identity,'param':row['param']})
 after=actual_rows(db_path);by_id={r['id']:r for r in after}
 if any(by_id.get(r['id'])!=r for r in current):raise ValueError('EXISTING_REGISTRY_ROW_CHANGED')
 if not {r['param'] for r in peer['rows']}<={r['param'] for r in after}:raise ValueError('PEER_UNION_INCOMPLETE')
 return {'before_count':len(current),'after_count':len(after),'added':added,'union_param_sha256':digest(sorted(r['param'] for r in after))}

def register_population(specs,peer,*,db_path,site,ensure_trial_registered):
 # The existing helper performs one commit per append; any interrupted batch
 # resumes by natural identity and must pass full readback before accrual.
 reconcile=reconcile_peer(peer,db_path=db_path,ensure_trial_registered=ensure_trial_registered)
 registration=register_before_data(specs,db_path=db_path,ensure_trial_registered=ensure_trial_registered)
 readback=registry_readback(specs,registration,db_path=db_path,site=site)
 return {'schema':'population_registration_operation/1','reconciliation':reconcile,'registration':registration,'readback':readback}

def registry_readback(specs,registration,*,db_path,site):
 with sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True) as conn:
  conn.row_factory=sqlite3.Row;registered=verify_actual_registry(specs,registration,conn)
 rows=actual_rows(db_path);expected={r['param'] for r in registration['rows']};actual={r['param'] for r in rows}
 if not expected<=actual:raise ValueError('ALL_VARIANTS_GLOBAL_REGISTRY_REQUIRED')
 selected=[r for r in rows if r['param'] in expected]
 return {'schema':'actual_population_registry_readback/1','site':site,'manifest_sha256':digest(specs),'commit':committed_identity(),'source_package_sha256':registration['source_package_sha256'],'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'registered_at':registered.isoformat(),'count':len(rows),'max_cumulative':max(r['cumulative_trials'] for r in rows),'population_row_count':len(selected),'population_params_sha256':digest(sorted(expected)),'population_rows_sha256':digest(selected),'all_params':sorted(actual),'all_params_sha256':digest(sorted(actual)),'activation':'NONE'}
