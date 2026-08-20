"""ARENA — the Generation-1 live-learning product arena (ORDER 25).

PRODUCT_EXPERIMENT / SIMULATION. Forward paper books in their own namespace
under ``<OPTIMUS_LEDGER_DIR>/arena/``. Nothing in this package reads or writes
``paper_nav``, the lane YAMLs, the experiment registry, or the order path, and
nothing it produces may be cited as evidence of skill.

What it exists to do (docs/ORDER_25_LIVE_ARENA_GEN1.md):
  * give every surviving research finding a forward paper book the next day,
    beside a control twin that differs by exactly one rule;
  * write one EXPERIENCE record per decision — chosen AND rejected — so the
    decision corpus the NN will eventually train on actually accrues;
  * make the product LLM's perceptions gradeable (arena-local prediction
    ledger, belief-change contract) instead of cache-only;
  * be the caller for the 16 daily collectors that previously fed nothing.
"""
