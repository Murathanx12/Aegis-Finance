"""Canonical routing/provenance guards; no actual inputs or registrations."""
import hashlib,json,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
class CanonicalIntegration(unittest.TestCase):
 def test_original_core_contract_and_reviewed_stage_successor_are_exact(self):
  expected={
   'backend/services/prospective_exit_pair/pair_core.py':'585a6367963785306e9d77b70ea31608d466115af25b8869b46e1d7bf80cc174',
   'backend/services/prospective_exit_pair/owned_stage.py':'5eafdf5c0dc588b39a254132b32f95070838a4e0f8fdd716da3a155345ded5ee',
   'docs/TRIALS/DYNAMIC-EXIT5-PAIR-CONTRACT.json':'0beb3e5337a199f867e27ddc8565728ec392133adb0a52603e58b083d582147d'}
  for rel,want in expected.items():
   with self.subTest(rel=rel):self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),want)
 def test_exact_contract_identity_and_no_trial_weakening(self):
  contract=json.loads((ROOT/'docs/TRIALS/DYNAMIC-EXIT5-PAIR-CONTRACT.json').read_bytes())
  self.assertEqual(hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),'055a819a6b099cd95016ef97186ef8a087dd8d9c5241a7381c91a389060455a2')
  doc=(ROOT/'docs/TRIALS/TRIAL-DYNAMIC-EXIT5-PAIR-20261015.md').read_text()
  for text in ('NOT REGISTERED, NOT ACCRUING','slice_purpose: EXPLORE.','2026-09-28 through2026-10-14','cross_sectional_n: 1.','No grandfathered bars or prior returns.'):
   self.assertIn(text,doc)
 def test_source_manifest_binds_real_local_routes(self):
  manifest=json.loads((ROOT/'docs/TRIALS/DYNAMIC-EXIT5-PAIR-SOURCES.json').read_bytes())
  for rel,want in manifest['canonical_files'].items():
   self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),want)
  for ref in manifest['source_refs']:
   # The reviewed raw execution binding targets one Windows worktree. CI
   # verifies its relative route and canonical bytes without opening that
   # machine's absolute path or pretending CI is operational custody proof.
   rel=ref['path'].removeprefix(manifest['local_execution_root']+'/')
   self.assertIn(rel,manifest['canonical_files'])
   self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),manifest['canonical_files'][rel])
   if ROOT.as_posix()==manifest['local_execution_root']:
    self.assertEqual(hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest(),ref['sha256'])

if __name__=='__main__':unittest.main()
