"""Read actual Dockerfile/context rules; no image build/provider operation."""
import fnmatch,json,hashlib,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def included(path):
    # Current repository patterns use plain components and *, no exotic
    # escaping/**. Match parents too: ignoring a directory ignores children.
    parts=path.split('/');prefixes=['/'.join(parts[:n]) for n in range(1,len(parts)+1)]
    ignored=False
    for raw in (ROOT/'.dockerignore').read_text(encoding='utf8').splitlines():
        rule=raw.strip()
        if not rule or rule.startswith('#'):continue
        negate=rule.startswith('!');pattern=rule.lstrip('!').strip('/')
        matched=any(fnmatch.fnmatchcase(prefix,pattern) for prefix in prefixes)
        if '/' not in pattern:matched=matched or any(fnmatch.fnmatchcase(part,pattern) for part in parts)
        if matched:ignored=not negate
    return not ignored

def test_actual_exact_registration_sources_enter_image_other_docs_still_excluded():
    docker=(ROOT/'backend/Dockerfile').read_text(encoding='utf8')
    names=('POPULATION-1000-SOURCES.json','POPULATION-1000-SPECIFICATIONS.json','TRIAL-POPULATION-1000-20261015.md')
    for name in names:
        path='docs/TRIALS/'+name
        assert (ROOT/path).is_file() and included(path) and path in docker
    for name in ('branch_population.py','local_branching.py','local_branching_task.py','local_branching_grade_child.py','beta_v1_news_capture.py'):
        path='scripts/'+name
        assert (ROOT/path).is_file() and included(path) and path in docker
    assert 'COPY .dockerignore .dockerignore' in docker and included('.dockerignore')
    assert not included('docs/CANON.md') and not included('docs/TRIALS/UNRELATED.md') and not included('README.md')
    binding=json.loads((ROOT/'docs/TRIALS/POPULATION-1000-SOURCES.json').read_bytes())
    assert '.dockerignore' in binding['files'] and 'backend/Dockerfile' in binding['files']

def test_frozen_runtime_reads_source_bindings_from_explicit_checkout(tmp_path,monkeypatch):
    checkout=tmp_path/'external-checkout';(checkout/'docs/TRIALS').mkdir(parents=True)
    (checkout/'pinned.py').write_bytes(b'actual source\n')
    binding={'files':{'pinned.py':hashlib.sha256(b'actual source\n').hexdigest()}}
    (checkout/'docs/TRIALS/POPULATION-1000-SOURCES.json').write_text(json.dumps(binding))
    frozen=tmp_path/'_internal/runtime.py';frozen.parent.mkdir()
    frozen.write_bytes((ROOT/'backend/services/portfolio_intelligence/branch_population_runtime.py').read_bytes())
    monkeypatch.setenv('AEGIS_REPO_ROOT',str(checkout))
    spec=importlib.util.spec_from_file_location('frozen_population_runtime_fixture',frozen)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.REPO==checkout.resolve()
    assert module.source_package_hash()==module.digest(binding)
    (checkout/'pinned.py').write_bytes(b'changed source\n')
    import pytest
    with pytest.raises(ValueError,match='EXACT_COMMITTED_POPULATION_SOURCE_REQUIRED'):module.source_package_hash()
