"""World digest public budget-failure receipts; no jobs or private state."""
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.services import task_receipts as TR


@pytest.fixture
def ctx(tmp_path):
    return SimpleNamespace(optimus_dir=tmp_path, now=datetime.now(timezone.utc))


def digest(ctx, clock, **extra):
    path = ctx.optimus_dir / 'digest' / f"world_digest_{clock:%Y%m%dT%H%M%SZ}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(dict(stamp=clock.isoformat(), status='OK', n_items=12,
                                   counts={'news': 12}, themes=[], spend={}, **extra)))
    return path


def failure(ctx, clock, **extra):
    stamp = clock.strftime('%Y%m%dT%H%M%SZ')
    path = ctx.optimus_dir / 'news_digest' / 'receipts' / f"budget_refused_{stamp}_{'a'*32}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state='BUDGET_REFUSED', reason='SHARED_ENVELOPE_BLOCKED',
                   stamp=stamp, observed_at=clock.isoformat(),
                   stage='shared_budget_preflight', written=False)
    payload.update(extra)
    path.write_text(json.dumps(payload))
    return path


def test_later_failure_wins_despite_mtime(ctx):
    good = digest(ctx, ctx.now - timedelta(hours=2))
    clock = ctx.now - timedelta(hours=1)
    bad = failure(ctx, clock)
    os.utime(good, (2000000000, 2000000000))
    os.utime(bad, (1, 1))
    rd = TR.r_world_digest(ctx, None)
    assert (rd.status, rd.reason, rd.stamp) == ('DEGRADED', 'SHARED_ENVELOPE_BLOCKED', clock)
    assert bad.name in rd.proof


def test_later_healthy_wins(ctx):
    failure(ctx, ctx.now - timedelta(hours=2))
    clock = ctx.now - timedelta(hours=1)
    digest(ctx, clock)
    rd = TR.r_world_digest(ctx, None)
    assert rd.status == 'OK'
    assert rd.stamp == clock


@pytest.mark.parametrize('damage', ['json', 'object', 'missing', 'invalid', 'future',
                                    'naive', 'mismatch', 'secret'])
def test_invalid_failure_fails_closed(ctx, damage):
    digest(ctx, ctx.now - timedelta(minutes=1))
    clock = ctx.now - timedelta(hours=1)
    extras = {
        'missing': {'observed_at': None},
        'invalid': {'observed_at': 'not-a-clock'},
        'future': {'observed_at': (ctx.now + timedelta(days=1)).isoformat()},
        'naive': {'observed_at': clock.replace(tzinfo=None).isoformat()},
        'mismatch': {'stamp': '20261399T999999Z'},
        'secret': {'reason': 'PRIVATE_SECRET_SENTINEL'},
    }
    path = failure(ctx, clock, **extras.get(damage, {}))
    if damage in ('json', 'object'):
        path.write_text('PRIVATE_SECRET_SENTINEL' if damage == 'json' else '[]')
    rd = TR.r_world_digest(ctx, None)
    assert rd.status == 'DEAD'
    assert rd.stamp is None
    assert 'PRIVATE_SECRET_SENTINEL' not in repr(rd)


def test_exact_tie_failure_wins(ctx):
    clock = (ctx.now - timedelta(hours=1)).replace(microsecond=0)
    digest(ctx, clock)
    failure(ctx, clock)
    assert TR.r_world_digest(ctx, None).status == 'DEGRADED'


def test_no_receipt(ctx):
    rd = TR.r_world_digest(ctx, None)
    assert rd.stamp is None
    assert rd.detail == 'no receipt at digest/world_digest_*.json'


def test_existing_digest_unchanged(ctx):
    clock = ctx.now - timedelta(hours=1)
    digest(ctx, clock)
    rd = TR.r_world_digest(ctx, None)
    assert (rd.status, rd.reason, rd.stamp) == ('OK', '', clock)
    assert rd.substance is not None


@pytest.mark.parametrize('reason', ['SHARED_ENVELOPE_BLOCKED', 'SHARED_ENVELOPE_INVALID',
                                   'SHARED_ENVELOPE_EXHAUSTED', 'SHARED_ENVELOPE_UNAVAILABLE'])
def test_failure_only_exact_safe_reason(ctx, reason):
    clock = ctx.now - timedelta(minutes=1)
    failure(ctx, clock, reason=reason)
    rd = TR.r_world_digest(ctx, None)
    assert (rd.status, rd.reason, rd.stamp) == ('DEGRADED', reason, clock)


def test_newest_failure_uses_content_clock(ctx):
    failure(ctx, ctx.now - timedelta(hours=2), reason='SHARED_ENVELOPE_EXHAUSTED')
    failure(ctx, ctx.now - timedelta(hours=1), reason='SHARED_ENVELOPE_BLOCKED')
    assert TR.r_world_digest(ctx, None).reason == 'SHARED_ENVELOPE_BLOCKED'


def test_malformed_failure_stays_dead_in_health_judge(ctx):
    failure(ctx, ctx.now - timedelta(minutes=1), observed_at=None)
    result = TR.judge(ctx, 'AegisWorldDigest', {'Scheduled Task State': 'Ready'})
    assert result.state == 'DEAD'
    assert 'malformed or future budget failure receipt' in result.detail
