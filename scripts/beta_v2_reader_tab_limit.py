"""Pure reader launch ceiling; no browser, config, process or filesystem access.

The existing pool governor, OS-paging policy and reading budgets retain control.
Omitted preferences use the configured ceiling; dispatch remains governed.
"""


class TabLimitRefused(ValueError):
    """The requested launch limit is outside the explicit configured ceiling."""


def tab_limit(requested=None, *, configured=None, capacity_ceiling=None):
    if type(configured) is not int or not 1 <= configured <= 12:
        raise TabLimitRefused("READER_CONFIGURED_TAB_CEILING_MUST_BE_1_TO_12")
    if capacity_ceiling is not None:
        if type(capacity_ceiling) is not int or not 1 <= capacity_ceiling <= 12:
            raise TabLimitRefused("READER_EXPLICIT_CAPACITY_CEILING_MUST_BE_1_TO_12")
        configured = capacity_ceiling
    chosen = configured if requested is None else requested
    if type(chosen) is not int or not 1 <= chosen <= configured:
        raise TabLimitRefused("READER_TAB_LIMIT_MUST_BE_1_TO_CONFIGURED_CEILING")
    return chosen


def supervisor_limit(requested=None, *, configured=None, preferred=None, capacity_ceiling=None):
    """CLI wins; an explicit preference otherwise overrides the configured ceiling."""
    return tab_limit(preferred if requested is None else requested, configured=configured,
                     capacity_ceiling=capacity_ceiling)
