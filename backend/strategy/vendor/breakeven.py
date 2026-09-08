# VENDORED VERBATIM from Vibe-Trading (HKUDS), MIT.
#   source : agent/src/strategy_discovery/models.py :: breakeven_fee_bps
#   clone  : C:\Users\mrthn\reference\Vibe-Trading  HEAD a4f06a29 (2026-09-07)
#   ported : 2026-09-08, roadmap ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md block S5
#
# ONE FUNCTION copied verbatim out of a 453-line module -- the rest of that
# module is evidence-store plumbing Aegis has no use for. The extracted body
# is byte-identical to upstream's; only `import math` is added below, because
# the original inherited it from the module head.
#
# The upstream file carries no per-file header; the project's LICENSE is
# reproduced below verbatim, which is the MIT condition. THE BODY OF THIS FILE
# IS NOT EDITED -- test_strategy_execution.py byte-compares everything after
# this header against the clone. Aegis-side additions live in
# `backend/strategy/execution.py` and import from here.
#
# MIT License
#
# Copyright (c) 2026 Vibe-Trading Contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import math


def breakeven_fee_bps(
    gross_return: float,
    trades: int,
    position_size: float | None = None,
) -> float | None:
    """Sizing-corrected breakeven transaction fee in basis points.

    Identity (per sergio12S, #969)::

        breakeven_bps = ln(1 + gross_return) / (2 * trades * position_size) * 10_000

    ``position_size`` defaults to ``1.0`` (full capital deployed) when
    ``None``. Returns ``None`` whenever the inputs are not usable (zero /
    negative trades, a return at or below -100%, a non-positive position
    size, or any non-finite value) rather than producing a meaningless or
    infinite number.
    """
    s = 1.0 if position_size is None else position_size
    try:
        gross = float(gross_return)
        n_trades = float(trades)
        size = float(s)
    except (TypeError, ValueError):
        return None

    if not (math.isfinite(gross) and math.isfinite(n_trades) and math.isfinite(size)):
        return None
    if n_trades <= 0 or gross <= -1.0 or size <= 0:
        return None

    return math.log(1.0 + gross) / (2.0 * n_trades * size) * 10_000.0
