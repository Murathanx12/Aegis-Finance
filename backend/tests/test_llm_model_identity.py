"""The model you asked for is not necessarily the model that answered.

On 2026-08-12, `GET https://api.deepseek.com/models` returned exactly two ids —
`deepseek-v4-flash` and `deepseek-v4-pro` — while this entire codebase was
calling `deepseek-chat` and `deepseek-reasoner`. Both legacy names are served
by v4-flash. Reading `model` off the response body proved it:

    asked "deepseek-chat"     -> served "deepseek-v4-flash"
    asked "deepseek-reasoner" -> served "deepseek-v4-flash"
    asked "deepseek-v4-pro"   -> served "deepseek-v4-pro"

That silent aliasing did two kinds of damage, and these tests pin both.

1. An experiment whose ARMS were "chat vs reasoner" compared one model with
   ITSELF, and would have reported "no model effect" — a null manufactured by a
   config bug. §19 says a number below its MDE is not detectable; this is worse,
   because the arm did not exist at all. A check that did not run is not a check
   that passed.

2. The price table priced those two names at 0.27/1.10 and 0.55/2.19, which
   overstated real v4-flash rates by ~2.8x. Ten thousand ledger rows carried
   the wrong cost and the budget governor gated on their sum.
"""
from __future__ import annotations

import pytest

from backend.config import LLM_PRICE_PER_MTOK
from backend.services import llm_telemetry as lt


# Verified against the live account 2026-08-12. If DeepSeek retires an alias,
# this list is what tells us — loudly, in CI — instead of a 400 in a night run.
_DEEPSEEK_SERVED_BY = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
}


@pytest.mark.parametrize("name", sorted(_DEEPSEEK_SERVED_BY))
def test_every_deepseek_name_we_send_is_priced(name: str) -> None:
    """An unpriced model makes every total a lower bound. Price all four."""
    assert name in LLM_PRICE_PER_MTOK, (
        f"{name} is sent by at least one call site but has no price; "
        "telemetry will record cost_usd=None and the governor will under-count")


def test_aliases_are_priced_as_the_model_that_actually_serves_them() -> None:
    """Pricing an alias differently from its server is pricing a fiction.

    `deepseek-reasoner` cost twice `deepseek-chat` in the old table. Both are
    v4-flash. Any spend split by model name was therefore fiction too.
    """
    for alias, served in _DEEPSEEK_SERVED_BY.items():
        assert LLM_PRICE_PER_MTOK[alias] == LLM_PRICE_PER_MTOK[served], (
            f"{alias} is served by {served} but is priced differently")


def test_v4_pro_is_not_priced_as_v4_flash() -> None:
    """The one REAL model distinction must survive in the price table.

    If these ever collapse to equal, the flash-vs-pro arm silently stops being
    a cost comparison — the same failure as the alias, one level up.
    """
    assert (LLM_PRICE_PER_MTOK["deepseek-v4-pro"]
            != LLM_PRICE_PER_MTOK["deepseek-v4-flash"])


def test_flash_cache_hit_is_the_dominant_cost_lever() -> None:
    """Cached input is ~50x cheaper than a miss, so shared prefixes matter more
    than any other optimisation available to an experiment designer."""
    flash = LLM_PRICE_PER_MTOK["deepseek-v4-flash"]
    assert flash["cached_in"] * 40 < flash["in"]


def test_reprice_recomputes_from_tokens_not_from_stored_dollars() -> None:
    """The stored dollar figure is a reconstruction; the tokens are the fact."""
    stale = [{
        "model": "deepseek-chat", "tokens_in": 1_000_000, "tokens_out": 1_000_000,
        "cached_tokens": 0, "cost_usd": 1.37,  # the OLD table's answer
    }]
    fresh = lt.reprice(stale)[0]
    # Was hardcoded `0.14 + 0.28`. Those were the 2026-08-12 numbers, and the
    # 2026-09-05 re-derivation from the provider balance moved the output leg
    # to $1.284835/Mtok — receipt `backend/data/optimus/continuation_2026-09-06b/
    # C3_deepseek_price_derivation_run01.json`. The INVARIANT here is "repriced
    # from tokens at the CURRENT table", not any particular number, so it now
    # reads the table; the numeric pin lives in `test_llm_price_from_balance.py`,
    # which checks the table against `config.LLM_PRICE_DERIVATION`.
    p = LLM_PRICE_PER_MTOK["deepseek-chat"]
    assert fresh["cost_usd"] == pytest.approx(p["in"] + p["out"])
    assert fresh["cost_usd"] != pytest.approx(1.37), (
        "reprice must not echo the stored dollars back")
    assert fresh["cost_repriced"] is True
    # The original is preserved, because "we used to think it cost this" is
    # itself a fact worth keeping when reconciling against a vendor invoice.
    assert fresh["cost_usd_as_written"] == 1.37
    assert stale[0]["cost_usd"] == 1.37, "reprice must not mutate its input"


def test_reprice_leaves_rows_with_no_token_counts_alone() -> None:
    """No tokens means no better answer is available. Say so by not inventing."""
    row = {"model": "deepseek-chat", "cost_usd": 0.99}
    out = lt.reprice([row])[0]
    assert out["cost_usd"] == 0.99
    assert "cost_repriced" not in out


def test_reprice_keeps_an_unknown_model_unpriced() -> None:
    """An unknown model yields None — a lower bound that announces itself —
    and must never be silently repriced to zero."""
    out = lt.reprice([{"model": "some-model-we-never-heard-of",
                       "tokens_in": 500, "tokens_out": 500, "cost_usd": None}])[0]
    assert out["cost_usd"] is None


@pytest.mark.slow
def test_live_deepseek_model_ids_still_match_what_we_send() -> None:
    """The only test that can catch the NEXT silent rename. Network-gated."""
    import json
    import os
    import urllib.request

    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        pytest.skip("DEEPSEEK_API_KEY not set")
    req = urllib.request.Request("https://api.deepseek.com/models",
                                 headers={"Authorization": f"Bearer {key}"})
    ids = {m["id"] for m in json.load(urllib.request.urlopen(req, timeout=30))["data"]}
    served = set(_DEEPSEEK_SERVED_BY.values())
    assert served <= ids, (
        f"a model we price no longer exists: {served - ids}. Every call site "
        "sending it is now relying on an alias that may also be gone.")
