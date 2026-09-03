# learner/states assignments

`company_states.parquet` -- one row per (permno, month) assigned OUT OF SAMPLE by a
representation fitted only on data strictly before that month. `state_k*` are
STABLE ids (Hungarian-matched across refits), `anomaly` is higher = more unusual,
`nn*_permno` / `nn*_month` / `nn*_dist` are the three nearest historical analogues,
and `nn_excess_1m_mean` is the mean 1m excess THOSE analogues realised (a PIT
retrieval predictor -- their targets had matured before this month began).

`market_states.parquet` -- one row per month, `market_state` assigned by a KMeans
fitted only on months strictly before it.

Written by `scripts/learner_states_run.py`. Receipt:
`backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json`.
