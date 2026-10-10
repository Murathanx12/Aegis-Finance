from datetime import date

import pandas as pd
import pytest

from scripts.budgeted_paired_results import scoring, max_drawdown, main, regrade_original
from scripts.original_evidence_audit import EvidenceRefused


def test_original_probabilities_losses_pending_and_void_stay_visible():
    rs = [{'probability': .6, 'outcome': 0, 'made_at': '2026-09-26', 'inputs_used': {'post_url': 'a'}},
          {'probability': .4, 'outcome': 1, 'made_at': '2026-09-26', 'inputs_used': {'post_url': 'a'}},
          {'probability': .6, 'outcome': None}, {'outcome': None, 'void_reason': 'missing bars'}]
    s = scoring(rs)
    assert s['n_total'] == 4 and s['n_scored'] == 2
    assert s['n_void'] == 1 and s['n_unresolved'] == 1
    assert s['brier'] == pytest.approx(.36)
    assert s['paired_brier_delta_vs_p50'] == pytest.approx(.11)
    assert s['source_url_clusters'] == 1 and s['decision_date_clusters'] == 1


def test_drawdown_includes_initial_capital_and_losses():
    assert max_drawdown([-.02, .10, -.01]) == pytest.approx(-.1)
    assert max_drawdown([-.02]) == pytest.approx(-.02)
    with pytest.raises(EvidenceRefused):
        max_drawdown([float('nan')])


def test_refuses_runtime_output_before_writing(tmp_path):
    root = tmp_path / 'runtime'
    root.mkdir()
    with pytest.raises(SystemExit):
        main(['--data-root', str(root), '--out-dir', str(root / 'report'), '--asof', '2026-10-09'])
    assert list(root.iterdir()) == []


def test_regrade_recomputes_a_wrong_recorded_outcome_without_mutation():
    row = {'prediction_id': 'frozen', 'ticker': 'AAA', 'observable': 'beats_benchmark',
           'benchmark': 'SPY', 'horizon_days': 1, 'probability': .6,
           'made_at': '2026-09-26T12:00:00+00:00', 'resolves_after': '2026-09-30',
           'outcome': 0, 'brier': .36, 'resolution_detail': {'realised_return': -.5}}
    px = pd.DataFrame({'AAA': [100, 110], 'SPY': [100, 101]},
                      index=pd.to_datetime(['2026-09-28', '2026-09-29']))
    result = regrade_original(row, px, date(2026, 10, 9))
    assert result['outcome'] == 1
    assert result['brier'] == pytest.approx(.16)
    assert result['resolution_detail']['realised_return'] == pytest.approx(.1)
    assert row['outcome'] == 0 and row['resolution_detail']['realised_return'] == -.5
    assert regrade_original(row, px, date(2026, 9, 29)) is None
