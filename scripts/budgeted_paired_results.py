"""Read-only original-record scoring and frozen-rule replay. No inference or orders."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from scripts.original_evidence_audit import (
    EvidenceRefused, Sources, PARENT_ID, TWIN_ID, SOURCE_COLUMNS,
    forecast_census, paper_census, common_window, partial_fills,
)


def scoring(rows: list[dict]) -> dict:
    """Score original probabilities, retaining unresolved/void rows in coverage."""
    resolved = [r for r in rows if r.get('outcome') in (0, 1)
                and r.get('outcome') is not None and not r.get('void_reason')]
    for r in resolved:
        p = r.get('probability')
        if not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
            raise EvidenceRefused('invalid original probability')
    bins = []
    for p in sorted({r['probability'] for r in resolved}):
        rs = [r for r in resolved if r['probability'] == p]
        bins.append({'p': p, 'n': len(rs),
                     'observed_rate': sum(r['outcome'] for r in rs) / len(rs)})
    return {'n_total': len(rows), 'n_scored': len(resolved),
            'n_void': sum(bool(r.get('void_reason')) for r in rows),
            'n_unresolved': sum(r.get('outcome') is None and not r.get('void_reason') for r in rows),
            'wins': sum(r['outcome'] for r in resolved),
            'losses': sum(r['outcome'] == 0 for r in resolved),
            'brier': sum((r['probability'] - r['outcome']) ** 2 for r in resolved) / len(resolved) if resolved else None,
            'without_news_p50_brier': 0.25 if resolved else None,
            'paired_brier_delta_vs_p50': sum((r['probability'] - r['outcome']) ** 2 - 0.25 for r in resolved) / len(resolved) if resolved else None,
            'calibration': bins,
            'cluster_rule': 'same source URL and overlapping event window; horizons never independent',
            'source_url_clusters': len({r.get('inputs_used', {}).get('post_url') for r in resolved}),
            'decision_date_clusters': len({r['made_at'][:10] for r in resolved}),
            'inference': 'descriptive only; one decision-date cluster, no significance claim'}


def max_drawdown(returns: list[float]) -> float:
    peak = 1.0
    worst = 0.0
    for ret in returns:
        nav = 1.0 + ret
        if not math.isfinite(nav) or nav <= 0:
            raise EvidenceRefused('invalid replay NAV')
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    return worst


def regrade_original(row: dict, prices: pd.DataFrame, asof: date) -> dict | None:
    """Recompute in memory; the resolver otherwise passes resolved rows through."""
    from backend.services import belief_state as B

    candidate = deepcopy(row)
    candidate['outcome'] = None
    for field in ('resolved_at', 'brier', 'resolution_detail', 'vs_benchmark', 'vs_control'):
        candidate.pop(field, None)
    return B.resolve_one(candidate, prices, today=asof)


def replay_book(book: dict, bars: pd.DataFrame, end: date) -> dict:
    from backend.services import llm_portfolio as LP

    grade = LP.grade(book, bars, today=end)
    if grade.get('status') != 'OK' or grade.get('to_date', {}).get('status') != 'OK':
        return {'status': 'REFUSED', 'grade': grade}
    entry = grade['entry_session']
    sessions = sorted(str(d.date()) for d in pd.to_datetime(
        bars.loc[bars.symbol == 'SPY', 'date'].drop_duplicates())
        if entry <= str(d.date()) <= str(end))
    path = []
    for day in sessions:
        g = LP.grade(book, bars, today=date.fromisoformat(day))
        if g.get('status') != 'OK' or g.get('to_date', {}).get('status') != 'OK':
            raise EvidenceRefused(f'replay grade refused on {day}')
        path.append({'session': day, **g['to_date']})
    contrib = []
    for p in book['positions']:
        solo = {**book, 'positions': [{'ticker': p['ticker'], 'weight': 1.0}], 'n_positions': 1}
        sg = LP.grade(solo, bars, today=end)
        cell = sg.get('to_date', {})
        contrib.append({'ticker': p['ticker'], 'weight': p['weight'], 'status': sg.get('status'),
                        'net_contribution_pp': 100 * p['weight'] * cell['net'] if cell.get('net') is not None else None})
    contrib.sort(key=lambda x: x['net_contribution_pp'] if x['net_contribution_pp'] is not None else -math.inf, reverse=True)
    return {'status': 'OK', 'entry_session': entry, 'to_date': grade['to_date'],
            'drawdown_net': max_drawdown([p['net'] for p in path]),
            'entry_cost_bps': grade['entry_cost_bps'],
            'turnover_one_way_entry': sum(p['weight'] for p in book['positions'] if p['ticker'] != 'CASH'),
            'rebalance_turnover': 0.0, 'daily_path': path,
            'top_name_contribution': contrib,
            'unpriceable': grade.get('unpriceable', []),
            'deferred_entry': grade.get('deferred_entry', []),
            'suspect_splits': grade.get('suspect_splits', [])}


def build(root: Path, out: Path, asof: date, run_id: str) -> dict:
    from backend.services import world_digest as WD

    src = Sources(root)
    census, _ = forecast_census(src, '2026-09-26', asof)
    original = [r for r in src.jsonl('predictions.jsonl')
                if str(r.get('made_at', '')).startswith('2026-09-26')
                and r.get('specialist') in SOURCE_COLUMNS]
    paper = paper_census(src, run_id)
    fills = partial_fills(src)
    try:
        window = common_window(src, 'leaderboard_2026-09-28.json', 'leaderboard_2026-10-09.json')
    except EvidenceRefused as exc:
        window = {'status': 'REFUSED', 'reason': str(exc)}
    books = {r['book_id']: r for r in src.jsonl('llm_portfolio/books.jsonl') if r.get('book_id') in (PARENT_ID, TWIN_ID)}
    contract = src.json('news_digest/shadow/CONTRACT_SHADOW_NEWS_v0.json')
    shadows = list(src.jsonl('news_digest/shadow/decisions.jsonl'))
    # First recorded eligible decision after the existing contract freeze, no selection by outcome.
    eligible = [r for r in shadows if r.get('contract_hash') == contract['contract_hash']
                and r.get('t', '') >= contract['frozen_utc']]
    if not eligible:
        raise EvidenceRefused('no historical shadow decision after contract freeze')
    shadow = min(eligible, key=lambda r: r['t'])
    if shadow.get('px_bar') != shadow['t'][:10] and shadow.get('px_bar', '') > shadow['t'][:10]:
        raise EvidenceRefused('future price vintage in shadow decision')
    decision_day = shadow['t'][:10]
    # This capture is before the US open, and can use the previous close as its asof DATE.
    if not shadow['t'].startswith('2026-09-29T03:') or shadow.get('px_bar') != '2026-09-28':
        raise EvidenceRefused('unexpected replay decision clock; review before selecting another')
    base = {p['ticker']: p['weight'] for p in books[PARENT_ID]['positions']}
    for b in books.values():
        if b['frozen_utc'] > shadow['t']:
            raise EvidenceRefused('book frozen after replay decision')
    tilted = WD.shadow_decision(base, shadow['signal'], trust_dir=shadow['trust_dir'],
                               trust_size=shadow['trust_size'], universe=set(base))
    without_news = WD.shadow_decision(base, {}, trust_dir=shadow['trust_dir'],
                                     trust_size=shadow['trust_size'], universe=set(base))
    plans = {'baseline': base, 'news_analyst_challenger': tilted, 'without_news': without_news,
             'without_analyst_frozen_random_twin': {p['ticker']: p['weight'] for p in books[TWIN_ID]['positions']}}
    frozen = {'schema': 'budgeted_paired_recipe/1', 'licence': 'PRODUCT_EXPERIMENT',
              'label': 'RETROSPECTIVE_PIT_REPLAY', 'decision_utc': shadow['t'],
              'asof_previous_close': shadow['px_bar'], 'end': str(asof),
              'original_book_ids': [PARENT_ID, TWIN_ID], 'shadow_contract': contract,
              'shadow_record': shadow, 'plans': plans,
              'rule': 'existing shadow_decision, historical recorded trusts; no tuning or new inference',
              'costs': 'existing LP.grade v2: empirical liquidity-band half round-trip on entry; SPY gross',
              'entry': 'LP.grade: next US session open after previous-close asof DATE'}
    blob = (json.dumps(frozen, indent=2, sort_keys=True) + '\n').encode()
    (out / 'recipe.json').write_bytes(blob)  # Written before reading replay outcomes.
    bar_rel = 'prices_2025_26/bars.parquet'
    p = root / bar_rel
    bb = p.read_bytes()
    src._record(bar_rel, hashlib.sha256(bb).hexdigest(), len(bb))
    import io
    bars = pd.read_parquet(io.BytesIO(bb))
    names = set().union(*[set(w) for w in plans.values()]) | {r['ticker'] for r in original} | {'SPY'}
    bars = bars[bars.symbol.isin(names) & (pd.to_datetime(bars.date) <= pd.Timestamp(asof))].copy()
    bars['date'] = pd.to_datetime(bars['date'])
    close = bars.pivot(index='date', columns='symbol', values='close')
    regraded = []
    for r in original:
        rr = regrade_original(r, close, asof)
        regraded.append({'prediction_id': r['prediction_id'], 'ticker': r['ticker'],
                         'horizon_days': r['horizon_days'], 'probability': r['probability'],
                         'made_at': r['made_at'], 'resolves_after': r['resolves_after'],
                         'recorded_outcome': r.get('outcome'),
                         'in_memory_outcome': rr.get('outcome') if rr else None,
                         'matches_recorded': (rr.get('outcome') == r['outcome']) if rr and r.get('outcome') is not None else None,
                         'costs_charged': r.get('costs_charged'),
                         'recorded_resolution_detail': r.get('resolution_detail'),
                         'recomputed_resolution_detail': rr.get('resolution_detail') if rr else None})
    replay = {}
    for name, weights in plans.items():
        b = {**deepcopy(books[PARENT_ID]), 'book_id': f'isolated:{name}', 'name': name,
             'asof': shadow['px_bar'], 'frozen_utc': shadow['t'],
             'positions': [{'ticker': t, 'weight': w} for t, w in weights.items()],
             'n_positions': len(weights)}
        replay[name] = replay_book(b, bars, asof)
    original_grades = {b['name']: replay_book(b, bars, asof) for b in books.values()}
    deltas = {name: {'net_delta_pp': 100 * (v['to_date']['net'] - replay['baseline']['to_date']['net']),
                     'weight_turnover_from_baseline': sum(abs(plans[name].get(t, 0) - base.get(t, 0)) for t in set(base) | set(plans[name])) / 2}
              for name, v in replay.items() if v.get('status') == 'OK' and replay['baseline'].get('status') == 'OK'}
    return {'schema': 'budgeted_paired_results/1', 'captured_utc': datetime.now(timezone.utc).isoformat(),
            'asof': str(asof), 'recipe_sha256': hashlib.sha256(blob).hexdigest(),
            'original_forecast_census': census, 'original_forecast_scores': scoring(original),
            'scores_by_horizon': {str(h): scoring([r for r in original if r['horizon_days'] == h]) for h in sorted({r['horizon_days'] for r in original})},
            'isolated_in_memory_regrades': regraded, 'original_policy_reproduction': original_grades,
            'recorded_forward_paper_census': paper, 'partial_execution': fills,
            'latest_fleet_window': window, 'paired_replay': replay, 'paired_deltas': deltas,
            'sources': src.records,
            'limitations': ['Not new forward evidence or an alpha claim; one short replay window.',
                            'Current rule implementation replays frozen original records; no current LLM knowledge used.',
                            'Recorded source probabilities concern beats SPY, without costs; p50 is a retrospective ablation.',
                            'Historical earned news trusts remain unchanged. Zero effect is valid, not evidence news cannot help.',
                            'Random twin is a frozen alternative portfolio, not a recomputed analyst-free rank.',
                            'Price panel is survivor-selected and unadjusted; dividends, true fills and fees unavailable.',
                            'Shadow signal provenance is the recorded input snapshot, not a revalidation of every original article.',
                            'Broker grade chain refusal retained; account execution may differ from theoretical portfolio.']}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', required=True, type=Path)
    ap.add_argument('--out-dir', required=True, type=Path)
    ap.add_argument('--asof', required=True, type=date.fromisoformat)
    ap.add_argument('--run-id', default='2026-10-09T235325Z')
    a = ap.parse_args(argv)
    root, out = a.data_root.resolve(), a.out_dir.resolve()
    if out.is_relative_to(root) or root.is_relative_to(out) or out.exists():
        ap.error('use a fresh isolated output outside runtime inputs')
    out.mkdir(parents=True)
    report = build(root, out, a.asof, a.run_id)
    (out / 'paired_results.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(out), 'scores': report['original_forecast_scores'], 'deltas': report['paired_deltas']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
