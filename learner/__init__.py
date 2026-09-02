"""The AEGIS LEARNER. Research-side ML that learns the ENGINE'S RESIDUALS.

    prior.py      BAND_PRIOR v2 as a function -- the incumbent, and the offset
    dataset.py    the versioned PIT training table (IBES + CRSP, 2013-2024)
    baselines.py  the rulers: constant, prior, rank_upside, rank_consensus
    models.py     ridge / LightGBM / MLP, each in a raw and a residual arm
    evaluate.py   rank IC, calibration, decile spread, terminal wealth
    shadow.py     scores today's tracker and writes a file. Places NOTHING.

    entrypoints:  scripts/learner_run.py, scripts/learner_shadow_seal.py

This package lives in `aegis-finance` on purpose: ML dependencies (torch,
LightGBM, sklearn) stay OUT of the execution repo. Nothing here imports a
broker, and `backend/tests/test_learner_pit.py` asserts that mechanically over
the AST rather than trusting the sentence.
"""
