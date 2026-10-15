"""Read actual Dockerfile/context rules; no image build/provider operation."""
import fnmatch,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def included(path):
    # Current repository patterns use plain components and *, no exotic
    # escaping/**. Match parents too: ignoring a directory ignores children.
    parts=path.split('/');prefixes=['/'.join(parts[:n]) for n in range(1,len(parts)+1)]
    ignored=False
    for raw in (ROOT/'.dockerignore').read_text().splitlines():
        rule=raw.strip()
        if not rule or rule.startswith('#'):continue
        negate=rule.startswith('!');pattern=rule.lstrip('!').strip('/')
        matched=any(fnmatch.fnmatchcase(prefix,pattern) for prefix in prefixes)
        if '/' not in pattern:matched=matched or any(fnmatch.fnmatchcase(part,pattern) for part in parts)
        if matched:ignored=not negate
    return not ignored

def test_actual_exact_registration_sources_enter_image_other_docs_still_excluded():
    docker=(ROOT/'backend/Dockerfile').read_text()
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
