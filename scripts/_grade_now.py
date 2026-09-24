"""One-shot: grade every prediction that is past its resolution date."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services import forecast_grader as FG
r = FG.grade_due()
print(json.dumps(r, indent=1, default=str)[:3000])
