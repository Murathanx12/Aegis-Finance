"""Explicit registry operations; operating stage runs only in existing owner."""
import argparse,json
from pathlib import Path
from backend.services.portfolio_intelligence.branch_population import digest
from backend.services.portfolio_intelligence.branch_population_registry import export_registry,register_population
from backend.services.portfolio_intelligence.branch_population_inputs import sha

def main():
 p=argparse.ArgumentParser();p.add_argument('operation',choices=('inspect','export','register'));p.add_argument('--site',choices=('local_canonical','railway_actual'));p.add_argument('--server-default',action='store_true');p.add_argument('--peer-export');p.add_argument('--peer-sha256');p.add_argument('--output',required=True)
 args=p.parse_args()
 from backend.services.portfolio_intelligence.branch_population_runtime import D,committed_identity,source_package_hash
 from backend.services.portfolio_intelligence.branch_population_runtime import REPO
 manifest_path=REPO/'docs/TRIALS/POPULATION-1000-SPECIFICATIONS.json';specs=json.loads(manifest_path.read_bytes())
 if args.operation=='inspect':value={'manifest_sha256':digest(specs),'source_package_sha256':source_package_hash(),'commit':committed_identity(),'counts':specs['counts'],'activation':'NONE'}
 else:
  if args.server_default:
   if args.site!='railway_actual':raise ValueError('EXACT_SERVER_REGISTRY_SITE')
   from backend.db import DB_PATH
   db=DB_PATH
  else:
   if args.site!='local_canonical':raise ValueError('EXACT_LOCAL_REGISTRY_SITE')
   db=Path('C:/Users/mrthn/aegis-finance/backend/data/aegis_pi.db')
  if args.operation=='export':value=export_registry(db,args.site)
  else:
   if not args.peer_export or sha(args.peer_export)!=args.peer_sha256:raise ValueError('PINNED_ACTUAL_PEER_EXPORT_REQUIRED')
   peer=json.loads(Path(args.peer_export).read_bytes())
   if peer['site']==args.site:raise ValueError('DISTINCT_ACTUAL_REGISTRY_PEER_REQUIRED')
   from backend.services.portfolio_intelligence.trial_registry import ensure_trial_registered
   value=register_population(specs,peer,db_path=db,site=args.site,ensure_trial_registered=ensure_trial_registered)
 output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
 with output.open('x',encoding='utf8') as f:json.dump(value,f,sort_keys=True,allow_nan=False)
 print(json.dumps({'operation':args.operation,'output':str(output),'sha256':sha(output),'activation':'NONE'}))

if __name__=='__main__':main()
