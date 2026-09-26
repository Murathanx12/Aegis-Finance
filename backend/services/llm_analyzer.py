"""
Aegis Finance — LLM Analysis Service (Claude + DeepSeek)
==========================================================

Uses Claude API (preferred) or DeepSeek API (fallback) for:
  - Market news summarization
  - Stock outlook analysis (bull/bear thesis)
  - Expectations generation
  - Portfolio commentary (v9)

Provider priority:
  1. ANTHROPIC_API_KEY → Claude (Haiku for speed, Sonnet for quality)
  2. DEEPSEEK_API_KEY → DeepSeek (OpenAI-compatible)
  3. No key → graceful fallback (returns None)

Graceful fallback: returns None if no API key or rate limited.
1-hour TTL caching on LLM responses.

Usage:
    from backend.services.llm_analyzer import (
        summarize_market_news, analyze_stock_outlook, generate_expectations,
        generate_portfolio_commentary, is_available,
    )
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from backend.cache import cached
from backend import config as _config_mod
from backend.config import config as _cfg

logger = logging.getLogger(__name__)

_llm_cfg = _cfg.get("llm", {})

# ── Provider Detection ──────────────────────────────────────────────────────

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()

#: THE ONLY PROVISIONED PROVIDER IS DEEPSEEK. Stated here because the code
#: below reads as though Claude were the primary and DeepSeek the fallback, and
#: a reader — human or model — who believes that will spend time on a path that
#: has no key behind it. That happened on 2026-08-24.
#:
#: `.env` carries an `ANTHROPIC_API_KEY=` line with an EMPTY VALUE. That reads
#: as configured and is not: `_get_provider` tests truthiness, so it has always
#: returned "deepseek". **Nothing was broken and no call was lost** — DeepSeek
#: has been the live provider throughout. The only cost was to whoever read the
#: file and believed the first branch was live.
#:
#: The Claude branch stays. It costs nothing, it is tested, and it is the
#: migration path if a key ever exists. But it is DORMANT, not primary, and
#: `provider_status()` says so on the health surface rather than leaving the
#: next session to work it out from an empty string.
SOLE_PROVISIONED_PROVIDER = "deepseek"


def provider_status() -> dict:
    """Which providers are actually configured, and which only look it.

    `declared_but_empty` is the row that matters: an env var present with an
    empty value is the failure mode that reads as configured. Distinguishing it
    from "absent" is the whole point — "absent" is a decision, "empty" is a
    loose end.
    """
    keys = {"anthropic": ("ANTHROPIC_API_KEY", _ANTHROPIC_API_KEY),
            "deepseek": ("DEEPSEEK_API_KEY", _DEEPSEEK_API_KEY)}
    out: dict = {"active": _get_provider(),
                 "sole_provisioned": SOLE_PROVISIONED_PROVIDER,
                 "configured": [], "declared_but_empty": [], "absent": []}
    for name, (env, val) in keys.items():
        if val:
            out["configured"].append(name)
        elif os.getenv(env) is not None:
            out["declared_but_empty"].append(name)
        else:
            out["absent"].append(name)
    out["matches_declaration"] = bool(
        out["active"] == SOLE_PROVISIONED_PROVIDER)
    # NAMED providers (chunk G, 2026-09-26). Reachable only by name through
    # `call_named`; never a fallback, never the primary. Listed with the same
    # configured / declared_but_empty / absent vocabulary as the keys above.
    routes = getattr(_config_mod, "MODEL_ROUTING_PROVIDERS", {}) or {}
    nv_env = os.getenv("NVIDIA_API_KEY")
    out["named"] = {
        "nvidia": {"role": "adjudicator",
                   "model": _nvidia_model(),
                   "cost_status": (routes.get("nvidia") or {}).get("cost_status"),
                   "state": ("configured" if (nv_env or "").strip() else
                             "declared_but_empty" if nv_env is not None else "absent")},
        "local": {"role": "on_demand", "model": "local",
                  "cost_status": (routes.get("local") or {}).get("cost_status"),
                  "state": "unprobed (started on demand by llama_server.ensure)"},
    }
    out["roles"] = {"deepseek": "primary", "nvidia": "adjudicator", "local": "on_demand"}
    return out

# Claude models (fast → quality)
_CLAUDE_MODEL_FAST = _llm_cfg.get("claude_model_fast", "claude-haiku-4-5-20251001")
_CLAUDE_MODEL_QUALITY = _llm_cfg.get("claude_model_quality", "claude-sonnet-4-6")

# DeepSeek settings
_DEEPSEEK_BASE_URL = _llm_cfg.get("base_url", "https://api.deepseek.com")
_DEEPSEEK_MODEL = _llm_cfg.get("model", "deepseek-chat")

_MAX_TOKENS = _llm_cfg.get("max_tokens", 500)

#: The output-language contract lives in `llm_language`, ONCE, because
#: `llm_analyzer` is not the only path to the vendor — seven modules call
#: `chat.completions.create` directly. Fixing it here alone protected one of
#: seven, which is the same per-call-site mistake this module's own comment was
#: criticising. These names are re-exported so existing callers and tests keep
#: working, and `_LANGUAGE_REFUSALS` is THE SAME DICT every call site increments,
#: so the counter is program-wide rather than per-module.
from backend.services.llm_language import (  # noqa: E402,F401
    LANGUAGE_PIN as _LANGUAGE_PIN,          # noqa: F401  re-export
    NON_LATIN_BAR as _NON_LATIN_BAR,        # noqa: F401  re-export
    REFUSALS as _LANGUAGE_REFUSALS,         # noqa: F401  re-export
    non_latin_share as _non_latin_share,    # noqa: F401  re-export
    refusals as language_refusals,          # noqa: F401  re-export
)


_anthropic_client = None
_openai_client = None

# ── Spend Guards ────────────────────────────────────────────────────────────
# The DeepSeek balance is small and prepaid; two guards keep it alive:
#  1. Daily call cap — beyond it every helper falls back to its template path.
#  2. Billing breaker — a 401/402 (dead/empty key) trips a cooldown so we
#     don't burn a request per cache expiry against a key that cannot pay.

_DAILY_CAP = int(_llm_cfg.get("daily_call_cap", 150))
_BREAKER_COOLDOWN_S = float(_llm_cfg.get("billing_breaker_cooldown_s", 6 * 3600))

_spend_lock = threading.Lock()
_spend_state: dict = {"date": None, "count": 0, "breaker_until": 0.0,
                      "breaker_reason": None, "cap_logged": False}


def _is_billing_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (401, 402):
        return True
    msg = str(exc).lower()
    return "insufficient balance" in msg or "invalid api key" in msg


def _trip_breaker(exc: Exception) -> None:
    with _spend_lock:
        _spend_state["breaker_until"] = time.time() + _BREAKER_COOLDOWN_S
        _spend_state["breaker_reason"] = str(exc)[:200]
    logger.error(
        "LLM billing error — provider disabled for %.0f min: %s",
        _BREAKER_COOLDOWN_S / 60, exc,
    )


def _acquire_call_budget() -> bool:
    """True if one LLM call may proceed (counts it); False → use fallbacks."""
    with _spend_lock:
        if time.time() < _spend_state["breaker_until"]:
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        if _spend_state["date"] != today:
            _spend_state["date"] = today
            _spend_state["count"] = 0
            _spend_state["cap_logged"] = False
        if _spend_state["count"] >= _DAILY_CAP:
            if not _spend_state["cap_logged"]:
                _spend_state["cap_logged"] = True
                logger.warning(
                    "LLM daily call cap reached (%d) — template fallbacks "
                    "until UTC midnight", _DAILY_CAP,
                )
            return False
        _spend_state["count"] += 1
        return True


def llm_usage() -> dict:
    """Current spend-guard state (for health/diagnostics)."""
    with _spend_lock:
        return {
            "provider": _get_provider(),
            "calls_today": _spend_state["count"],
            "daily_cap": _DAILY_CAP,
            "breaker_active": time.time() < _spend_state["breaker_until"],
            "breaker_reason": _spend_state["breaker_reason"],
            # Non-English replies refused, by provider. On the surface because
            # the failure is SILENT otherwise: the caller falls back to its
            # template and the page still renders.
            "language_refusals": dict(_LANGUAGE_REFUSALS),
            "empty_content_refusals": dict(EMPTY_CONTENT_REFUSALS),
            "providers": provider_status(),
        }


def _get_provider() -> str:
    """Detect which LLM provider is available."""
    if _ANTHROPIC_API_KEY:
        return "claude"
    elif _DEEPSEEK_API_KEY:
        return "deepseek"
    return "none"


def _get_anthropic_client():
    """Lazy-init Anthropic client."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    if not _ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
        return _anthropic_client
    except ImportError:
        logger.warning("anthropic SDK not installed — Claude unavailable")
        return None
    except Exception as e:
        logger.warning("Failed to init Anthropic client: %s", e)
        return None


def _get_openai_client():
    """Lazy-init OpenAI client for DeepSeek."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not _DEEPSEEK_API_KEY:
        return None
    try:
        from openai import OpenAI
        _openai_client = OpenAI(
            api_key=_DEEPSEEK_API_KEY,
            base_url=_DEEPSEEK_BASE_URL,
        )
        return _openai_client
    except ImportError:
        logger.warning("openai SDK not installed — DeepSeek unavailable")
        return None
    except Exception as e:
        logger.warning("Failed to init DeepSeek client: %s", e)
        return None


def _record(provider: str, model: str, purpose: str, *, system: str, user: str,
            resp=None, text: Optional[str] = None, t0: float,
            validate=None, error: Optional[Exception] = None) -> None:
    """Write one telemetry row. Never raises — see llm_telemetry.record_call.

    `schema_valid` is answered by the CALLER's contract, not by "the HTTP call
    returned 200": a helper that needs `BULL:/BEAR:/WATCH:` and gets loose prose
    spent money and learned nothing, and that is the bucket the ledger exists to
    count. Absent a validator the bar is a non-empty reply — the weakest honest
    claim available, never an assumed True.
    """
    from backend.services import llm_telemetry as _tel

    usage = _tel.extract_usage(resp, provider) if resp is not None else {}
    if error is not None:
        ok = False
    elif validate is not None and text is not None:
        try:
            ok = bool(validate(text))
        except Exception:                                  # noqa: BLE001
            ok = False
    else:
        ok = bool((text or "").strip())
    _tel.record_call(
        provider=provider, model=model, purpose=purpose,
        prompt=system + "\n" + user, context=user,
        latency_ms=(time.perf_counter() - t0) * 1000.0,
        schema_valid=ok, error=(f"{type(error).__name__}: {error}"
                                if error else None),
        **usage,
    )


def _refuse_non_english(provider: str, purpose: str, text: str) -> bool:
    """Refuse a reply that is mostly not English. Returns True if refused.

    Delegates to the shared contract so every call site increments one counter.
    See `llm_language` for why it refuses rather than repairs or retries.
    """
    from backend.services import llm_language as _lang
    return _lang.refuse(provider, purpose, text)


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    quality: bool = False,
    *,
    purpose: str = "unspecified",
    validate=None,
) -> Optional[str]:
    """Make a single LLM call. Tries Claude first, then DeepSeek.

    Args:
        system_prompt: System instructions
        user_prompt: User message
        quality: If True, use higher-quality model (Sonnet vs Haiku)
        purpose: what this call is FOR — the slice every spend report is cut
            by. Defaulted rather than required so no caller can break, but a
            call left "unspecified" is unattributable spend and shows up as
            such in `llm_telemetry.summary()`.
        validate: optional predicate on the reply text deciding `schema_valid`.

    Returns:
        LLM response text or None on failure.

    Telemetry is deliberately NOT written on the two no-wire paths below (no
    provider, budget/breaker refusal): those cost nothing and produce nothing,
    and counting them would dilute the zero-yield share the ledger reports.
    """
    provider = _get_provider()
    if provider == "none" or not _acquire_call_budget():
        return None

    # Try Claude first
    if provider == "claude":
        client = _get_anthropic_client()
        if client:
            model = _CLAUDE_MODEL_QUALITY if quality else _CLAUDE_MODEL_FAST
            t0 = time.perf_counter()
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=_MAX_TOKENS,
                    system=system_prompt + _LANGUAGE_PIN,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                text = response.content[0].text.strip()
                _record("anthropic", model, purpose, system=system_prompt,
                        user=user_prompt, resp=response, text=text, t0=t0,
                        validate=validate)
                if _refuse_non_english("anthropic", purpose, text):
                    return None
                return text
            except Exception as e:
                logger.warning("Claude API call failed: %s", e)
                _record("anthropic", model, purpose, system=system_prompt,
                        user=user_prompt, t0=t0, error=e)
                if _is_billing_error(e):
                    _trip_breaker(e)
                    return None
                # Fall through to DeepSeek

    # Try DeepSeek
    if _DEEPSEEK_API_KEY:
        client = _get_openai_client()
        if client:
            t0 = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=_DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system",
                         "content": system_prompt + _LANGUAGE_PIN},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=_MAX_TOKENS,
                    temperature=_llm_cfg.get("temperature", 0.3),
                )
                text = response.choices[0].message.content.strip()
                _record("deepseek", _DEEPSEEK_MODEL, purpose,
                        system=system_prompt, user=user_prompt, resp=response,
                        text=text, t0=t0, validate=validate)
                if _refuse_non_english("deepseek", purpose, text):
                    return None
                return text
            except Exception as e:
                logger.warning("DeepSeek API call failed: %s", e)
                _record("deepseek", _DEEPSEEK_MODEL, purpose,
                        system=system_prompt, user=user_prompt, t0=t0, error=e)
                if _is_billing_error(e):
                    _trip_breaker(e)

    return None


# ── Named providers (chunk G, 2026-09-26) ───────────────────────────────────
#
# `_call_llm` answers "the house model" and that stays DeepSeek. `call_named`
# answers "THIS provider, by name" -- the /deep, /ask and /compare routes, where
# which model answered IS the measurement. Three rules:
#
#  * no fallback: a named provider that is not configured is a REFUSAL, never a
#    silent answer from another model (a comparison that quietly measured the
#    wrong model is worse than no comparison);
#  * the language pin and the non-English refusal apply to every provider, on
#    the same central path;
#  * every wire attempt writes ONE telemetry row with the provider's name, and
#    the reply carries the same `cost_usd` the row was priced at, plus the
#    `cost_status` (LISTED | UNPRICED) so a None is never read as free.

_NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
_nvidia_client = None
_local_client = None


def _nvidia_model() -> str:
    return str(getattr(_config_mod, "NVIDIA_ADJUDICATOR_MODEL", None)
               or getattr(_config_mod, "MODEL_ROUTING_NVIDIA_MODEL",
                          "meta/llama-3.2-11b-vision-instruct"))


#: Replies whose `content` was empty, by provider (G-fix, adjudication row 7).
#: A reasoning model can return content=None with its chain of thought in
#: `reasoning_content`; chunk G parsed that thought as the answer, so a
#: truncated "if momentum holds, P: 0.6 ... but" could be frozen as a forecast.
#: An empty content is now a REFUSAL, counted here and on `llm_usage()`.
EMPTY_CONTENT_REFUSALS: dict[str, int] = {}


def _is_rate_limited(e: Exception) -> bool:
    code = getattr(e, "status_code", None)
    if code is None:
        code = getattr(getattr(e, "response", None), "status_code", None)
    return code == 429 or type(e).__name__ == "RateLimitError"


def _create_with_429_retry(client, provider: str, *, tries: int | None = None,
                           sleep=None, rng=None, **kw):
    """`client.chat.completions.create(**kw)`, retrying HTTP 429 only.

    NVIDIA's free tier answered 429 in 2 of 5 runs on 2026-09-07. Other errors
    raise at once: retrying a 401 or a 400 spends nothing and learns nothing.
    Backoff doubles from MODEL_ROUTING_NVIDIA_BACKOFF_S plus uniform jitter.
    Returns (response, n_429). A final 429 re-raises carrying `n_429`.
    """
    import random as _random
    tries = int(tries or getattr(_config_mod, "MODEL_ROUTING_NVIDIA_TRIES", 3))
    base = float(getattr(_config_mod, "MODEL_ROUTING_NVIDIA_BACKOFF_S", 4.0))
    jit = float(getattr(_config_mod, "MODEL_ROUTING_NVIDIA_JITTER_S", 2.0))
    rng = rng or _random.Random()
    sleep = sleep or time.sleep
    n429 = 0
    for i in range(tries):
        try:
            return client.chat.completions.create(**kw), n429
        except Exception as e:                                 # noqa: BLE001
            if not _is_rate_limited(e):
                raise
            n429 += 1
            if i == tries - 1:
                try:
                    e.n_429 = n429                             # type: ignore[attr-defined]
                except AttributeError:
                    pass
                raise
            sleep(base * (2 ** i) + rng.uniform(0.0, jit))
    raise RuntimeError("unreachable")                          # pragma: no cover


def _nvidia_base_url() -> str:
    """`NVIDIA_BASE_URL` from the environment, normalised to end in /v1."""
    url = (os.getenv("NVIDIA_BASE_URL") or "").strip() or str(getattr(
        _config_mod, "MODEL_ROUTING_NVIDIA_DEFAULT_BASE_URL",
        "https://integrate.api.nvidia.com/v1"))
    url = url.rstrip("/")
    return url if url.endswith("/v1") else url + "/v1"


def _get_nvidia_client():
    global _nvidia_client
    if _nvidia_client is not None:
        return _nvidia_client
    if not _NVIDIA_API_KEY:
        return None
    from openai import OpenAI
    _nvidia_client = OpenAI(api_key=_NVIDIA_API_KEY, base_url=_nvidia_base_url(),
                            timeout=float(getattr(_config_mod, "MODEL_ROUTING_TIMEOUT_S", 180.0)))
    return _nvidia_client


def _get_local_client():
    global _local_client
    if _local_client is not None:
        return _local_client
    from openai import OpenAI
    from backend.services import llama_server as _ls
    _local_client = OpenAI(api_key="local-no-key",
                           base_url=f"http://{_ls.LLAMA_HOST}:{_ls.LLAMA_PORT}/v1",
                           timeout=float(getattr(_config_mod, "MODEL_ROUTING_TIMEOUT_S", 180.0)))
    return _local_client


def cost_status(model: str) -> str:
    """LISTED when the house price table knows the model, else UNPRICED."""
    return "LISTED" if str(model) in getattr(_config_mod, "LLM_PRICE_PER_MTOK", {}) else "UNPRICED"


def _reply_text(response) -> str:
    """`content` ONLY. A thought is not an answer: `reasoning_content` is never
    read as the reply (G-fix, adjudication row 7 -- chunk G fell back to it, a
    test pinned that, and a truncated chain of thought could be frozen as a
    forecast row). Empty content -> "" -> the caller's REFUSED_EMPTY_CONTENT."""
    msg = response.choices[0].message
    return str(getattr(msg, "content", None) or "").strip()


def _has_reasoning_only(response) -> bool:
    try:
        return bool(getattr(response.choices[0].message, "reasoning_content", None))
    except (AttributeError, IndexError):
        return False


def call_named(provider: str, system_prompt: str, user_prompt: str, *,
               purpose: str, max_tokens: int | None = None,
               validate=None, ensure_reason: str | None = None,
               temperature: float | None = None,
               production_budget: bool = True) -> dict:
    """One chat turn from the NAMED provider. Never raises for a provider error.

    Returns `{provider, model, served_model, text, ok, status, latency_s,
    cost_usd, cost_status, tokens_in, tokens_out, cached_tokens, n_429, error}`.
    `text` is None whenever `ok` is False. `provider` is one of `deepseek`,
    `nvidia`, `local`. `served_model` is what the PROVIDER says answered.

    G-fix (adjudication row 7): `text` is `content` only -- an empty content is
    `REFUSED_EMPTY_CONTENT`, counted in `EMPTY_CONTENT_REFUSALS`, never the
    reasoning parsed as an answer; NVIDIA retries HTTP 429 (3 tries, backoff
    with jitter) and a last 429 is `RATE_LIMITED`.
    """
    from backend.services import llm_telemetry as _tel

    routes = getattr(_config_mod, "MODEL_ROUTING_PROVIDERS", {}) or {}
    mt = int(max_tokens or getattr(_config_mod, "MODEL_ROUTING_MAX_TOKENS", 700))
    out = {"provider": provider, "model": None, "text": None, "ok": False,
           "status": None, "latency_s": None, "cost_usd": None,
           "cost_status": None, "tokens_in": 0, "tokens_out": 0,
           "cached_tokens": 0, "error": None}
    if provider == "deepseek":
        model, client = _DEEPSEEK_MODEL, (_get_openai_client() if _DEEPSEEK_API_KEY else None)
        if client is None:
            return {**out, "model": model, "status": "NOT_CONFIGURED",
                    "error": "DEEPSEEK_API_KEY is not set"}
        # `production_budget=False` is for an attended BATCH that enforces its
        # own dollar cap (the E-G1 bake-off, $0.15): the 150-call production
        # counter is sized for a user-facing endpoint, not a 240-item batch. The
        # billing breaker binds either way.
        if production_budget:
            if not _acquire_call_budget():
                return {**out, "model": model, "status": "BUDGET_REFUSED",
                        "error": "daily call cap or billing breaker"}
        elif time.time() < _spend_state["breaker_until"]:
            return {**out, "model": model, "status": "BUDGET_REFUSED",
                    "error": "billing breaker"}
    elif provider == "nvidia":
        model, client = _nvidia_model(), _get_nvidia_client()
        if client is None:
            return {**out, "model": model, "status": "NOT_CONFIGURED",
                    "error": "NVIDIA_API_KEY is not set"}
    elif provider == "local":
        from backend.services import llama_server as _ls
        model = str((routes.get("local") or {}).get("model") or "local")
        st = _ls.ensure(ensure_reason or purpose)
        if not st.get("ok"):
            return {**out, "model": model, "status": "LOCAL_UNAVAILABLE",
                    "error": f"llama_server.ensure: {st.get('action')} "
                             f"{st.get('reason') or st.get('detail') or ''}".strip()}
        client = _get_local_client()
    else:
        return {**out, "status": "UNKNOWN_PROVIDER",
                "error": f"unknown provider {provider!r}; have deepseek, nvidia, local"}

    out["model"] = model
    out["cost_status"] = cost_status(model)
    tel_provider = provider
    out["served_model"] = None
    out["n_429"] = 0
    t0 = time.perf_counter()
    kw = dict(model=model,
              messages=[{"role": "system", "content": system_prompt + _LANGUAGE_PIN},
                        {"role": "user", "content": user_prompt}],
              max_tokens=mt,
              temperature=(_llm_cfg.get("temperature", 0.3) if temperature is None
                           else float(temperature)))
    try:
        if provider == "nvidia":
            response, out["n_429"] = _create_with_429_retry(client, provider, **kw)
        else:
            response = client.chat.completions.create(**kw)
        text = _reply_text(response)
    except Exception as e:                                     # noqa: BLE001
        _record(tel_provider, model, purpose, system=system_prompt, user=user_prompt,
                t0=t0, error=e)
        if provider == "deepseek" and _is_billing_error(e):
            _trip_breaker(e)
        return {**out, "status": "RATE_LIMITED" if _is_rate_limited(e) else "ERROR",
                "n_429": int(getattr(e, "n_429", 0) or 0),
                "latency_s": round(time.perf_counter() - t0, 3),
                "error": f"{type(e).__name__}: {str(e)[:300]}"}
    latency = round(time.perf_counter() - t0, 3)
    _record(tel_provider, model, purpose, system=system_prompt, user=user_prompt,
            resp=response, text=text, t0=t0, validate=validate)
    usage = _tel.extract_usage(response, tel_provider)
    out.update(usage)
    out["latency_s"] = latency
    # the model the PROVIDER says answered (DeepSeek has said `deepseek-flash`
    # for `deepseek-chat` since 09-14); priced by it when the table knows it.
    served = getattr(response, "model", None)
    out["served_model"] = str(served) if isinstance(served, str) and served else None
    price_model = (out["served_model"] if out["served_model"]
                   and cost_status(out["served_model"]) == "LISTED" else model)
    out["cost_status"] = cost_status(price_model)
    out["cost_usd"] = _tel.price_call(price_model, usage["tokens_in"], usage["tokens_out"],
                                      usage["cached_tokens"])
    if provider == "local":
        from backend.services import llama_server as _ls
        _ls.touch(ensure_reason or purpose)
    if not text:
        EMPTY_CONTENT_REFUSALS[provider] = EMPTY_CONTENT_REFUSALS.get(provider, 0) + 1
        why = ("content empty, reasoning_content present: a thought is not an answer"
               if _has_reasoning_only(response) else "the model returned an empty message")
        return {**out, "status": "REFUSED_EMPTY_CONTENT", "error": why}
    if _refuse_non_english(tel_provider, purpose, text):
        return {**out, "status": "LANGUAGE_REFUSED",
                "error": "reply was mostly non-Latin script; discarded, not repaired"}
    return {**out, "text": text, "ok": True, "status": "OK"}


# ── Public API ──────────────────────────────────────────────────────────────


@cached(ttl=3600, key_prefix="llm_market_summary")
def summarize_market_news(news_items: list[dict]) -> Optional[dict]:
    """Generate a 2-3 sentence market news summary.

    Args:
        news_items: List of {title, publisher, published}

    Returns:
        {summary: str, sentiment: str, provider: str} or None
    """
    if not news_items:
        return None

    headlines = "\n".join(
        f"- {item.get('title', '')} ({item.get('publisher', '')})"
        for item in news_items[:15]
    )

    system = (
        "You are a concise financial analyst. Summarize market news in 2-3 sentences. "
        "Include the overall market sentiment (bullish/bearish/neutral/mixed). "
        "Be factual, not speculative. No disclaimers."
    )
    user = f"Summarize these recent market headlines:\n\n{headlines}"

    result = _call_llm(system, user, purpose="news_summary")
    if result is None:
        return None

    # Detect sentiment from the summary
    lower = result.lower()
    if any(w in lower for w in ["bullish", "rally", "surge", "optimis"]):
        sentiment = "bullish"
    elif any(w in lower for w in ["bearish", "decline", "crash", "pessimis", "fear"]):
        sentiment = "bearish"
    elif any(w in lower for w in ["mixed", "uncertain", "volatile"]):
        sentiment = "mixed"
    else:
        sentiment = "neutral"

    return {"summary": result, "sentiment": sentiment, "provider": _get_provider()}


_ADVICE_PATTERN = None  # compiled lazily


def _contains_advice_language(text: str) -> bool:
    """True when LLM prose crosses from analysis into recommendation.

    The two-sided card's hard constraint: no buy/sell language. Nouns like
    "analyst buy ratings" are fine; imperatives and recommendations are not.
    """
    global _ADVICE_PATTERN
    if _ADVICE_PATTERN is None:
        import re
        _ADVICE_PATTERN = re.compile(
            r"\b(we|i|you|investors?|one)\s+(should|must|ought to)\b"
            r"|\brecommend(s|ed|ing)?\b"
            r"|\b(buy|sell|short|accumulate)\s+(this|the)\s+(stock|shares|name)\b",
            re.IGNORECASE,
        )
    return bool(_ADVICE_PATTERN.search(text))


@cached(ttl=6 * 3600, key_prefix="llm_two_sided")
def argue_signal_two_sided(ticker: str, signal_json: str) -> Optional[dict]:
    """Argue BOTH sides of the computed per-stock signal (V4 chunk 5).

    The numeric signal is the input, never the output: the LLM writes prose
    around a score the engine already computed, and nothing it says feeds
    back into any number. Responses containing recommendation language are
    rejected outright (fail-closed) — disclosed-unavailable beats advice.

    signal_json: JSON string of {action, composite_score, confidence,
    components, price, crash_prob_3m} — a string so the cache key is stable.
    """
    import json as _json

    try:
        sig = _json.loads(signal_json)
    except (TypeError, ValueError):
        return None

    components = sig.get("components") or {}
    ranked = sorted(components.items(), key=lambda kv: abs(kv[1]), reverse=True)
    comp_lines = "\n".join(f"- {k}: {v:+.2f}" for k, v in ranked[:6]) or "n/a"

    system = (
        "You write educational two-sided analysis of a quantitative model's "
        "stock signal. Given the model's computed reading and its component "
        "scores, write the strongest honest case that the positives dominate "
        "(BULL) and the strongest honest case that the negatives dominate "
        "(BEAR), 2-3 sentences each, grounded ONLY in the evidence given. "
        "Then one sentence on what evidence would most change the picture "
        "(WATCH). Hard rules: no investment advice, no recommendation "
        "language (should/recommend), never tell anyone to buy or sell, no "
        "new numbers beyond those provided. Format exactly:\n"
        "BULL: ...\nBEAR: ...\nWATCH: ..."
    )
    user = (
        f"Ticker: {ticker}\n"
        f"Model signal: {sig.get('action', 'n/a')} "
        f"(composite {sig.get('composite_score', 'n/a')}, "
        f"confidence {sig.get('confidence', 'n/a')}%)\n"
        f"Price: {sig.get('price', 'n/a')}\n"
        f"3m crash probability (stock-adjusted): {sig.get('crash_prob_3m', 'n/a')}\n"
        f"Signal components (weighted, +bullish/−bearish):\n{comp_lines}"
    )

    # The card renders nothing unless BOTH sides came back, so that — not a
    # 200 — is what "the call worked" means here.
    result = _call_llm(
        system, user, purpose="two_sided_signal_card",
        validate=lambda t: "BULL:" in t and "BEAR:" in t)
    if result is None:
        return None
    if _contains_advice_language(result):
        logger.warning("two-sided card: rejected LLM output with advice "
                       "language for %s (fail-closed)", ticker)
        return None

    bull, bear, watch = "", "", ""
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith("BULL:"):
            bull = line[5:].strip()
        elif line.startswith("BEAR:"):
            bear = line[5:].strip()
        elif line.startswith("WATCH:"):
            watch = line[6:].strip()

    if not bull or not bear:
        return None  # malformed — the card renders nothing rather than half

    return {
        "ticker": ticker,
        "bull_case": bull,
        "bear_case": bear,
        "watch_for": watch,
        "signal_action": sig.get("action"),
        "composite_score": sig.get("composite_score"),
        "provider": _get_provider(),
    }


def _daily_brief_parses(text: str) -> bool:
    """The brief's contract is JSON with a non-empty `what_happened`.

    Same predicate the parser below applies, hoisted so the ledger records the
    SAME notion of success the product uses — a schema_valid flag that means
    something looser than "the card rendered" is a flag that flatters the spend.
    """
    import json as _json

    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):t.rfind("}") + 1]
    try:
        return bool(str(_json.loads(t).get("what_happened", "")).strip())
    except Exception:                                      # noqa: BLE001
        return False


@cached(ttl=1800, key_prefix="llm_daily_brief")
def summarize_daily_brief(payload_json: str) -> Optional[dict]:
    """Personalized daily brief summary — FinGPT-Forecaster-style contract.

    Takes a compact JSON payload (market moves, geopolitical read, the user's
    tickers with moves + headlines) and returns three structured sections.
    Cached by payload content so identical watchlists share one call.
    """
    system = (
        "You are a market-brief writer for a retail investor. Given today's "
        "market data as JSON, write EXACTLY this JSON (no markdown fences): "
        '{"what_happened": "...", "impact_on_holdings": "...", '
        '"risks_to_watch": "...", "sentiment": "bullish|bearish|mixed|neutral"}. '
        "what_happened: 2-3 sentences on today's tape (indices, oil/gold/rates, "
        "geopolitical drivers if the data shows them). impact_on_holdings: 2-3 "
        "sentences connecting those moves to the user's specific tickers, using "
        "their actual 1-day/5-day moves and headlines. risks_to_watch: 1-2 "
        "sentences on what could change the picture. Be factual and specific — "
        "cite the numbers given. Describe, never advise: no buy/sell/should "
        "language. If geopolitical conflict is elevated, explain the typical "
        "sector pattern (energy/defense vs travel/rate-sensitives) as a "
        "historical tendency, not a forecast."
    )
    result = _call_llm(system, payload_json, purpose="daily_brief",
                       validate=_daily_brief_parses)
    if result is None:
        return None
    try:
        import json as _json
        text = result.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):text.rfind("}") + 1]
        parsed = _json.loads(text)
        out = {
            "what_happened": str(parsed.get("what_happened", "")).strip(),
            "impact_on_holdings": str(parsed.get("impact_on_holdings", "")).strip(),
            "risks_to_watch": str(parsed.get("risks_to_watch", "")).strip(),
            "sentiment": str(parsed.get("sentiment", "neutral")).strip().lower(),
            "source": "llm",
        }
        if not out["what_happened"]:
            return None
        return out
    except Exception as e:
        logger.warning("daily brief LLM output unparseable: %s", e)
        return None


@cached(ttl=3600, key_prefix="llm_stock_outlook")
def analyze_stock_outlook(
    ticker: str,
    news: list[dict],
    fundamentals: dict,
) -> Optional[dict]:
    """Generate bull/bear thesis for a stock.

    Args:
        ticker: Stock ticker
        news: Recent news items
        fundamentals: Dict with pe_ratio, market_cap, beta, analyst_target, etc.

    Returns:
        {bull_case, bear_case, sentiment_score, summary} or None
    """
    headlines = "\n".join(
        f"- {item.get('title', '')}" for item in news[:10]
    ) if news else "No recent news available."

    pe = fundamentals.get("pe_ratio", "N/A")
    mc = fundamentals.get("market_cap")
    mc_str = f"${mc/1e9:.1f}B" if mc and mc > 0 else "N/A"
    beta = fundamentals.get("beta", "N/A")
    target = fundamentals.get("analyst_target", "N/A")
    price = fundamentals.get("current_price", "N/A")

    system = (
        "You are a senior equity analyst. Provide a concise bull case (2 sentences) "
        "and bear case (2 sentences) for the given stock. Then give a sentiment score "
        "from -1.0 (very bearish) to +1.0 (very bullish). Format:\n"
        "BULL: ...\nBEAR: ...\nSCORE: X.X\nSUMMARY: One sentence outlook."
    )
    user = (
        f"Stock: {ticker}\n"
        f"Price: ${price}, P/E: {pe}, Market Cap: {mc_str}, Beta: {beta}\n"
        f"Analyst Target: ${target}\n"
        f"Recent News:\n{headlines}"
    )

    result = _call_llm(system, user, purpose="stock_outlook")
    if result is None:
        return None

    # Parse structured response
    bull_case = ""
    bear_case = ""
    score = 0.0
    summary = ""

    for line in result.split("\n"):
        line = line.strip()
        if line.startswith("BULL:"):
            bull_case = line[5:].strip()
        elif line.startswith("BEAR:"):
            bear_case = line[5:].strip()
        elif line.startswith("SCORE:"):
            try:
                score = float(line[6:].strip())
            except ValueError:
                score = 0.0
        elif line.startswith("SUMMARY:"):
            summary = line[8:].strip()

    if not bull_case and not bear_case:
        return {"summary": result, "bull_case": "", "bear_case": "", "sentiment_score": 0.0}

    return {
        "bull_case": bull_case,
        "bear_case": bear_case,
        "sentiment_score": max(-1.0, min(1.0, score)),
        "summary": summary or result.split("\n")[0],
        "provider": _get_provider(),
    }


@cached(ttl=3600, key_prefix="llm_expectations")
def generate_expectations(
    ticker: str,
    analyst_targets: Optional[dict] = None,
    earnings: Optional[dict] = None,
) -> Optional[dict]:
    """Generate 'What to watch' section for a stock.

    Returns:
        {expectations: str, key_catalysts: list[str]} or None
    """
    target_info = ""
    if analyst_targets:
        target_info = (
            f"Analyst Price Targets — Low: ${analyst_targets.get('low', 'N/A')}, "
            f"Mean: ${analyst_targets.get('mean', 'N/A')}, "
            f"High: ${analyst_targets.get('high', 'N/A')}"
        )

    earnings_info = ""
    if earnings:
        next_date = earnings.get("next_date", "N/A")
        estimate = earnings.get("estimate", "N/A")
        earnings_info = f"Next Earnings: {next_date}, EPS Estimate: ${estimate}"

    if not target_info and not earnings_info:
        return None

    system = (
        "You are a financial analyst. List 3-4 key catalysts/risks to watch for this stock. "
        "Be specific and actionable. Format as a short paragraph followed by bullet points."
    )
    user = f"Stock: {ticker}\n{target_info}\n{earnings_info}"

    result = _call_llm(system, user, purpose="expectations")
    if result is None:
        return None

    catalysts = []
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*", "•")) and len(line) > 5:
            catalysts.append(line.lstrip("-*• "))

    return {
        "expectations": result,
        "key_catalysts": catalysts[:5],
    }


@cached(ttl=3600, key_prefix="llm_portfolio_commentary")
def generate_portfolio_commentary(
    holdings: list[dict],
    metrics: dict,
    factor_exposures: Optional[dict] = None,
    risk_contributions: Optional[dict] = None,
) -> Optional[dict]:
    """Generate AI portfolio commentary — Bloomberg PORT Enterprise style.

    Takes portfolio holdings, performance metrics, factor exposures, and risk
    contributions and produces plain-English analysis a client could read.

    Args:
        holdings: List of {ticker, weight, return_1m, sector}
        metrics: {total_return, sharpe, volatility, max_drawdown, ...}
        factor_exposures: Optional Fama-French factor loadings
        risk_contributions: Optional per-holding MCTR data

    Returns:
        {commentary: str, key_points: list[str], risk_alerts: list[str]}
    """
    # Build context
    holdings_str = "\n".join(
        f"  {h.get('ticker', '?')}: {h.get('weight', 0)*100:.1f}% weight, "
        f"{h.get('return_1m', 0):.1f}% 1M return, sector={h.get('sector', '?')}"
        for h in (holdings or [])[:20]
    )

    metrics_str = ""
    if metrics:
        metrics_str = (
            f"Portfolio Return (1M): {metrics.get('return_1m', 'N/A')}%\n"
            f"Annualized Volatility: {metrics.get('volatility', 'N/A')}%\n"
            f"Sharpe Ratio: {metrics.get('sharpe', 'N/A')}\n"
            f"Max Drawdown: {metrics.get('max_drawdown', 'N/A')}%\n"
            f"VaR (95%): {metrics.get('var_95', 'N/A')}%\n"
        )

    factor_str = ""
    if factor_exposures:
        factor_str = "Factor Exposures:\n" + "\n".join(
            f"  {k}: {v:.3f}" for k, v in factor_exposures.items()
        )

    risk_str = ""
    if risk_contributions:
        top_risk = sorted(risk_contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        risk_str = "Top Risk Contributors:\n" + "\n".join(
            f"  {k}: {v*100:.1f}% of portfolio risk" for k, v in top_risk
        )

    system = (
        "You are a portfolio analyst writing a monthly client report. "
        "Write a 3-4 paragraph portfolio commentary covering: "
        "1) Performance summary and key drivers, "
        "2) Risk assessment and concentration concerns, "
        "3) Factor tilts and style observations, "
        "4) Recommendations or areas to monitor. "
        "Be professional, specific, and actionable. No disclaimers. "
        "End with 3 bullet-point key takeaways."
    )
    user = (
        f"Portfolio Holdings:\n{holdings_str}\n\n"
        f"Performance Metrics:\n{metrics_str}\n"
        f"{factor_str}\n{risk_str}"
    )

    result = _call_llm(system, user, quality=True,
                       purpose="portfolio_commentary")
    if result is None:
        return None

    # Extract key points (bullet points at the end)
    key_points = []
    risk_alerts = []
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*", "•")) and len(line) > 10:
            point = line.lstrip("-*• ")
            if any(w in point.lower() for w in ["risk", "concern", "warning", "alert", "concentration"]):
                risk_alerts.append(point)
            else:
                key_points.append(point)

    return {
        "commentary": result,
        "key_points": key_points[:5],
        "risk_alerts": risk_alerts[:3],
        "provider": _get_provider(),
    }


def is_available() -> bool:
    """Check if LLM analysis is available (any API key configured + SDK installed)."""
    provider = _get_provider()
    if provider == "claude":
        return _get_anthropic_client() is not None
    elif provider == "deepseek":
        return _get_openai_client() is not None
    return False
