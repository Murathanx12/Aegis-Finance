"""Pure reader launch ceiling; no browser, config, process or filesystem access.

The existing pool governor, OS-paging policy and reading budgets retain control.
Two slots are the supervised qualification default, not a throughput guarantee.
"""


class TabLimitRefused(ValueError):
    """The requested launch limit is outside the explicit configured ceiling."""


def tab_limit(requested=None, *, configured=None):
    if type(configured) is not int or not 1 <= configured <= 6:
        raise TabLimitRefused("READER_CONFIGURED_TAB_CEILING_MUST_BE_1_TO_6")
    chosen = configured if requested is None else requested
    if type(chosen) is not int or not 1 <= chosen <= configured:
        raise TabLimitRefused("READER_TAB_LIMIT_MUST_BE_1_TO_CONFIGURED_CEILING")
    return chosen


def supervisor_limit(requested=None, *, configured=None, preferred=2):
    """CLI wins; optional config preference otherwise starts qualification at 2."""
    return tab_limit(preferred if requested is None else requested, configured=configured)
