"""COPY-LAB — forward paper experiments over Teacher Library events.

PRODUCT_EXPERIMENT. NOT VALIDATED ALPHA. These lanes may run before a
hypothesis is certified — that is what a paper lane is for — and nothing they
produce may be cited as evidence of skill.

Three separations this package exists to keep:

  * from the research book. COPY-LAB has its own config file, its own hash and
    its own ledger namespace. `paper_portfolios.yaml` and the ten lanes
    accruing since 2026-06-08 are never touched.
  * from the Teacher Library. The library holds events; this package decides
    what a paper account would have done with them. No hypothesis is evaluated
    here and no outcome is joined for research.
  * from history. A lane's clock starts when it is seeded. Events public before
    that are ineligible forever — historical events are research material for a
    pre-registered study, never forward paper performance.
"""

from .lanes import LaneSpec, config_hash, load_lanes                # noqa: F401
from .execution import ExecutionPolicy, first_executable_session    # noqa: F401
