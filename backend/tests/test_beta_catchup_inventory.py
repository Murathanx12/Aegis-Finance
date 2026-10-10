from datetime import datetime, timezone
from scripts.beta_catchup_inventory import classify


def row(**kw):
    return dict(made_at='2026-10-01T12:00:00Z', resolves_after='2026-10-02', horizon_days=1,
                ticker='X', observable='return_sign', probability=.6, evidence_population='campaign_forward', **kw)


def test_calendar_due_is_not_closed_before_exit_close():
    assert classify(row(), datetime(2026, 10, 2, 18, tzinfo=timezone.utc)) == 'CALENDAR_DUE_WINDOW_NOT_CLOSED'


def test_closed_is_only_price_unverified_candidate():
    assert classify(row(), datetime(2026, 10, 3, tzinfo=timezone.utc)) == 'MATURE_TARGET_VALID_PRICE_UNVERIFIED'


def test_already_terminal_and_bad_horizon_never_ready():
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    assert classify(row(outcome=0), now) == 'ALREADY_TERMINAL'
    r = row(); r['horizon_days'] = 'bad'
    assert classify(r, now) == 'INVALID_TARGET_OR_HORIZON'


def test_optional_null_mechanism_is_not_structured_protected_identity():
    now=datetime(2026,10,10,tzinfo=timezone.utc)
    assert classify(row(specialist='review:v0',mechanism_id=None),now)=='MATURE_TARGET_VALID_PRICE_UNVERIFIED'
    assert classify(row(specialist='review:v0',mechanism_id={'trial':'x'}),now)=='GATED_METADATA_ONLY'


def test_persisted_void_states_and_zero_outcome_are_terminal():
    now=datetime(2026,10,10,tzinfo=timezone.utc)
    for marker in ({'voided':True},{'resolution_state':'VOIDED'},{'outcome':0}):
        assert classify(row(**marker),now)=='ALREADY_TERMINAL'
