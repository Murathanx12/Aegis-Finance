"""E6 preview only. This candidate ships no production sender or activation path."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from backend.services import provisional_owner_notice as N
from scripts.current_exposure_link import Pin


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--send',action='store_true',help='refused: only injected offline API tests exist')
    args=parser.parse_args(argv)
    try:
        if args.send:raise N.NoticeRefused('PRODUCTION_SENDER_NOT_IMPLEMENTED')
        result=N.run_notice(Pin(args.manifest,args.manifest_sha256))
        print(json.dumps(result,sort_keys=True))
        return 2 if result['state']=='PREVIEW_BLOCKED' else 0
    except N.NoticeRefused as exc:
        print(json.dumps(dict(state='REFUSED',reason=str(exc),transport_calls=0),sort_keys=True))
        return 2

if __name__=='__main__':raise SystemExit(main())
