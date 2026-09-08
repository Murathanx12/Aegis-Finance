"""Free inference: a named backend, a declared capability table, one price table.

    from backend.services import free_inference as fi

    fi.capability_declaration()          # what exists, what it costs, what was probed
    fi.complete("nvidia_nim", "...")     # a free call, accounted at $0.00
    fi.usage()                           # a spend line per backend -- $0.00 is a LINE

WHY THIS EXISTS
===============
Murat, 2026-09-07: *"I have 9 dollars on deepseek left so I wish to do a webscrape
pull and store all the data and run a local model (free or nvidia free models) to
review them."* That is three instructions, and this module is the first: **stop
paying per token.** DeepSeek stays configured and stays the only PAID provider;
it is not the default for anything written after this file.

WHAT THIS IS NOT
================
It is not a router (choosing a backend per job needs benchmark evidence that does
not exist), and it has **no trading authority**. Nothing downstream of it sizes,
stops or orders. It returns text, and `local_review` turns text into a ROW.

FOUR THINGS CARRY OVER FROM THE DEEPSEEK PATH AND ARE NOT OPTIONAL
==================================================================
1. **The language pin is central.** `explain_move.py` once fixed the Chinese
   code-switch at ONE call site and the other six inherited the bug for months.
   Here the pin AND the >10% non-Latin refusal live in `llm_language`, are applied
   in `complete()`, and are counted per backend. A refused reply is REFUSED --
   not repaired, not retried, and the tokens it burned are still recorded.
2. **One price table.** `config.LLM_PRICE_PER_MTOK`. A free model is a row of
   zeros in that table, not a special case in code: it is priced at 0.0, it still
   emits a token count, and it goes through `llm_telemetry` like every paid call.
   A backend with no spend must produce a LINE reading $0.00, because an absent
   line and a zero line read identically in a summary and mean opposite things.
3. **Configured is not working.** A declared model is a claim about this file. A
   `probed_on` date beside it is a claim about the service. They are separate
   fields here on purpose: NIM lists 81 models to this account and served 12.
4. **An undeclared model is a REFUSAL.** Not a warning, not a call. A model that
   is not in the table is also not in the price table, so calling it would record
   `cost_usd=None` and make every total a lower bound.

THE MODEL LIST IS THE CATALOGUE, NOT THE GRANT
==============================================
Measured 2026-09-07 against this account: `GET /v1/models` returns **81** models
in 578 ms; **12** of them answered a chat completion. Thirty-one returned HTTP
404 *"Not found for account"* -- visible and not provisioned, the same shape as
WRDS showing every subscriber all 1,316 schemas. Two timed out at 200 s
(CANNOT DETERMINE -- not a dead key and not a working model), one returned 500,
and one returned 503 *"Worker local total request limit reached"* on the first
attempt and answered in 0.9 s on the second, so a single 503 is not evidence.

The receipt is `backend/data/optimus/free_inference_2026-09-07/L1_nim_probe.json`
and `docs/BUILD_2026-09-07b_L_FREE_INFERENCE.md`. **Re-probe rather than trust
this table**: NIM retires models on a date, and a previous default here
(`meta/llama-3.3-70b-instruct`) returned HTTP 410 "end of life" the day after it
was written.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field

from backend.config import LLM_PRICE_PER_MTOK
from backend.services import llm_language as _lang
from backend.services import llm_telemetry as _tel
from backend.services.model_provider import (PROVIDERS, LanguageRefused,
                                             ProviderRefusal, complete as _wire)

logger = logging.getLogger(__name__)

#: The default for anything written from 2026-09-07 on. Deliberately NOT
#: `deepseek`: the balance is ~$9 and every new caller that reaches for the paid
#: provider by default is how it gets to $0 without a decision being taken.
DEFAULT_BACKEND = "nvidia_nim"

#: The one PAID backend. Named here so a test can assert it is never the default
#: and never the free tier, rather than that fact living in a comment.
PAID_BACKEND = "deepseek"

FREE = "free"
PAID = "paid"


@dataclass(frozen=True)
class Backend:
    """A backend is DATA. Adding one is a row, not a client.

    `transport` names the row in `model_provider.PROVIDERS` that carries the wire
    details (base URL, key env). This table carries the POLICY: what it costs,
    which models are declared, and when a human last saw it answer.
    """
    name: str
    transport: str
    cost_class: str
    default_model: str
    models: tuple[str, ...]
    probed_on: str | None
    note: str
    #: Models that are LISTED by the endpoint and did not serve this account.
    #: Kept beside the live ones because "we tried it and it 404s" is a fact a
    #: future session otherwise re-buys at 30 HTTP calls.
    not_served: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_free(self) -> bool:
        return self.cost_class == FREE


#: ---------------------------------------------------------------------------
#: THE CAPABILITY TABLE. Every model here must also be a row in
#: `config.LLM_PRICE_PER_MTOK` -- pinned by `test_free_inference.py`.
BACKENDS: dict[str, Backend] = {
    "nvidia_nim": Backend(
        name="nvidia_nim",
        transport="nvidia",
        cost_class=FREE,
        # gpt-oss-20b is a REASONING model: it spends tokens thinking before it
        # writes `content`. At max_tokens=16 content came back EMPTY and only
        # `reasoning_content` was populated. A small budget on a reasoning model
        # reads as a dead model, so `complete()` defaults to 512.
        default_model="openai/gpt-oss-20b",
        models=(
            # -- measured 2026-09-07, latency to first full reply in seconds --
            "openai/gpt-oss-20b",                             # 2.6 s
            "nvidia/nemotron-3.5-lightning-30b-a3b",          # 3.8 s
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",  # 1.0 s
            "nvidia/nemotron-3-super-120b-a12b",              # 1.8 s
            "nvidia/nemotron-3-ultra-550b-a55b",              # 41.7 s (cold)
            "nvidia/ising-calibration-1.5-31b",               # 0.6 s
            "nvidia/nemotron-3.5-content-safety",             # 0.8 s (classifier)
            "meta/muse-glimmer-30b",                          # 0.9 s
            "minimaxai/minimax-m3",                           # 0.7 s
            "moonshotai/kimi-k3",                             # 33.8 s (cold)
            "google/gemma-4-31b-it",                          # 51.7 s (cold)
            "poolside/laguna-xs-2.1",                         # 0.9 s (503 first try)
        ),
        not_served=(
            # HTTP 404 "Not found for account" -- LISTED, not granted.
            "writer/palmyra-fin-70b-32k", "nvidia/nemotron-nano-3-30b-a3b",
            "mistralai/mistral-7b-instruct-v0.3", "google/gemma-3-4b-it",
            "google/gemma-3-12b-it", "nvidia/llama-3.1-nemotron-70b-instruct",
            "moonshotai/kimi-k2.6", "nvidia/nemotron-4-340b-instruct",
            # HTTP 500 / read timeout at 200 s -- CANNOT DETERMINE, not dead.
            "mistralai/mistral-nemotron", "deepseek-ai/deepseek-v4-flash-0731",
            "deepseek-ai/deepseek-v4-pro-0813",
        ),
        probed_on="2026-09-07",
        note=("NVIDIA NIM free tier, OpenAI-compatible. The SAFE BET: plain HTTP, "
              "and the same key already serves nemotron-3-embed-1b. "
              "81 listed, 12 served."),
    ),
    "local_gguf": Backend(
        name="local_gguf",
        transport="local",
        cost_class=FREE,
        default_model="local",
        models=("local",),
        # A date here means "a human saw it answer ON that date". It does NOT
        # mean it is answering now: nothing is listening on 127.0.0.1:8080
        # unless somebody started llama-server, and only `model_provider.status(
        # probe=True)` can say. That is why `key_present` stays None for this
        # row rather than False -- a keyless endpoint has no credential to be
        # missing, so a config read carries no information about it, and
        # reporting False would be the ANTHROPIC_API_KEY mistake with the sign
        # flipped.
        probed_on="2026-09-07",
        note=("llama.cpp's own OpenAI-compatible server, serving whatever GGUF it "
              "was given -- so the model id is always `local`. MEASURED 2026-09-07 "
              "on this box: Qwen2.5-7B-Instruct-Q4_K_M (4.68 GB) at -ngl 99 -c 8192, "
              "5,642 MiB of the RTX 5060's 8,151 MiB, first token in ~10 s from a "
              "cold start and 43.5 output tok/s thereafter. START IT FIRST: "
              "C:/Users/mrthn/llama/llama-start.cmd (stop it before gaming). Use the "
              "CUDA 13.x build: the 12.4 build does not see this GPU (Blackwell, "
              "sm_120) and falls back to CPU silently -- fast enough to look "
              "like it worked."),
    ),
    "deepseek": Backend(
        name="deepseek",
        transport="deepseek",
        cost_class=PAID,
        default_model="deepseek-chat",
        models=("deepseek-chat", "deepseek-reasoner",
                "deepseek-v4-flash", "deepseek-v4-pro"),
        probed_on="2026-09-06",
        note=("THE ONLY PAID PROVIDER, and DORMANT for this lane. Balance ~$9 on "
              "2026-09-07, deliberately preserved for the era replay (roadmap R, "
              "cap $10). Never the default; a caller must name it."),
    ),
}


#: Re-exported so a caller of THIS module never has to import the transport to
#: catch its own refusal. It is the same class -- one exception for one failure,
#: not a parallel hierarchy that a caller can catch half of.
LanguageRefusal = LanguageRefused


#: Per-backend running totals for THIS process. Exists so `usage()` can emit a
#: line for a backend that spent nothing: an absent line and a $0.00 line read
#: the same in a summary and mean opposite things.
_USAGE: dict[str, dict] = {}


def _touch(backend: str) -> dict:
    return _USAGE.setdefault(backend, {
        "calls": 0, "tokens_in": 0, "tokens_out": 0,
        "cost_usd": 0.0, "language_refusals": 0, "errors": 0})


@dataclass(frozen=True)
class FreeReply:
    backend: str
    model: str
    text: str
    latency_s: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cost_class: str

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out


def resolve(backend: str | None) -> Backend:
    """The backend row, or a refusal naming what is on offer."""
    name = backend or DEFAULT_BACKEND
    row = BACKENDS.get(name)
    if row is None:
        raise ProviderRefusal(
            f"unknown backend {name!r}; declared: {sorted(BACKENDS)}. This is a "
            "REFUSAL and not a fallback -- silently answering from a different "
            "model is how a benchmark ends up measuring the wrong one.")
    return row


def price_of(model: str) -> float | None:
    """Per-Mtok input price from the ONE table, or None if unpriced."""
    row = LLM_PRICE_PER_MTOK.get(model)
    return None if row is None else float(row["in"])


def is_free_model(model: str) -> bool:
    """A free model is a row of ZEROS in the price table -- derived, not declared.

    Deriving it means the two facts cannot disagree. A separate list of "free
    models" beside a price table is two tables for one question, and X7 is in the
    roadmap because that is exactly how a rate table drifts.
    """
    row = LLM_PRICE_PER_MTOK.get(model)
    return row is not None and all(float(v) == 0.0 for v in row.values())


def complete(backend: str | None = None, prompt: str = "", *,
             system: str = "You are a precise research assistant.",
             model: str | None = None, purpose: str = "free_inference",
             max_tokens: int = 512, temperature: float = 0.0,
             timeout: int = 120, record: bool = True) -> FreeReply:
    """One completion through a named backend, guarded and accounted.

    Raises `ProviderRefusal` (or `LanguageRefusal`) rather than returning
    something unusable. Every raise is a finding: a check that did not run is
    not a check that passed.
    """
    row = resolve(backend)
    chosen = model or row.default_model
    if chosen not in row.models:
        raise ProviderRefusal(
            f"{row.name} has not declared model {chosen!r}. Declared: "
            f"{list(row.models)}. Add it to free_inference.BACKENDS AND to "
            "config.LLM_PRICE_PER_MTOK (zeros for a free model) -- an undeclared "
            "model records cost_usd=None and makes every total a lower bound.")
    if LLM_PRICE_PER_MTOK.get(chosen) is None:
        raise ProviderRefusal(
            f"{chosen!r} is declared by {row.name} but has no row in "
            "config.LLM_PRICE_PER_MTOK. One price table, no exceptions.")

    stats = _touch(row.name)
    t0 = time.monotonic()
    refused = False
    try:
        # The wire. `model_provider` owns the transport AND the whole language
        # contract -- the pin on the way out and the >10% non-Latin refusal on
        # the way back, centrally, once, for every backend. Nothing about the
        # language is re-implemented here; that is the entire lesson of
        # `explain_move.py` fixing it at one call site.
        rep = _wire(row.transport, prompt, system=system, model=chosen,
                    max_tokens=max_tokens, temperature=temperature,
                    timeout=timeout, purpose=purpose, provider_label=row.name)
    except LanguageRefused as exc:
        # A refused reply still BURNED TOKENS. They are accounted below and then
        # the refusal is re-raised: discarded is not free, and a spend line that
        # omits refusals under-reports exactly the calls worth worrying about.
        rep, refused = exc.reply, True
    except ProviderRefusal:
        stats["errors"] += 1
        raise
    dt = round(time.monotonic() - t0, 3)
    tin = int(rep.prompt_tokens or 0)
    tout = int(rep.completion_tokens or 0)
    cost = _tel.price_call(chosen, tin, tout)
    if cost is None and row.is_free:
        cost = 0.0

    if record:
        # Recorded EITHER WAY. A provider's refusal RATE is what decides whether
        # it is fit for gradeable records -- and a rate needs a denominator.
        _tel.record_call(
            provider=row.name, model=chosen, purpose=purpose,
            prompt=prompt, tokens_in=tin, tokens_out=tout,
            latency_ms=dt * 1000.0, schema_valid=not refused,
            error=("LANGUAGE_REFUSED" if refused else None),
            meta={"cost_class": row.cost_class, "transport": row.transport,
                  "free": row.is_free})
    stats["calls"] += 1
    stats["tokens_in"] += tin
    stats["tokens_out"] += tout
    if cost is not None:
        stats["cost_usd"] = round(stats["cost_usd"] + cost, 8)

    if refused:
        stats["language_refusals"] += 1
        raise LanguageRefused(
            f"{row.name}/{chosen} replied >{int(_lang.NON_LATIN_BAR * 100)}% "
            f"non-Latin script for purpose={purpose!r}. DISCARDED -- not "
            f"repaired and not retried. {tin + tout} tokens ARE recorded against "
            f"this backend. Refusals so far: {_lang.refusals()}",
            reply=rep, share=_lang.non_latin_share(rep.text))

    return FreeReply(backend=row.name, model=chosen, text=rep.text, latency_s=dt,
                     tokens_in=tin, tokens_out=tout,
                     cost_usd=float(cost or 0.0), cost_class=row.cost_class)


def usage() -> dict:
    """A spend line per DECLARED backend, including the ones that spent nothing."""
    out = {}
    refusals = _lang.refusals()
    for name, row in BACKENDS.items():
        stats = dict(_touch(name))
        stats["language_refusals"] = refusals.get(name,
                                                  stats["language_refusals"])
        stats["cost_class"] = row.cost_class
        stats["cost_usd_str"] = f"${stats['cost_usd']:.2f}"
        out[name] = stats
    return out


def counterfactual_deepseek(tokens_in: int, tokens_out: int,
                            model: str = "deepseek-chat") -> float:
    """What the SAME token counts would have cost on the paid provider.

    The point of the lane in one number. Priced from `config.LLM_PRICE_PER_MTOK`,
    the same table that prices everything else -- a counterfactual computed at a
    made-up rate is a wish.
    """
    return float(_tel.price_call(model, int(tokens_in), int(tokens_out)) or 0.0)


def capability_declaration() -> dict:
    """What each backend IS (config) and what it was last SEEN to do (probe).

    Two separate claims, never collapsed. `test_free_inference.py` pins this
    against `model_provider.PROVIDERS` and `config.LLM_PRICE_PER_MTOK`, exactly
    as `test_llm_provider_declaration.py` pins the DeepSeek declaration: if the
    resolved backend ever stops matching what this says, the suite is red.
    """
    rows = {}
    for name, row in BACKENDS.items():
        spec = PROVIDERS[row.transport]
        key_env = spec["key_env"]
        rows[name] = {
            **asdict(row),
            "base_url": spec["base_url"],
            "key_env": key_env,
            "needs_key": key_env is not None,
            # Presence only. The VALUE is never read into a return, a log or a
            # receipt -- `.strip()` because an `X=` line with an empty value is
            # ABSENT, which is the shape that made ANTHROPIC_API_KEY read as live.
            "key_present": (None if key_env is None
                            else bool(os.getenv(key_env, "").strip())),
            "prices_zero": all(is_free_model(m) for m in row.models),
        }
    return {
        "default_backend": DEFAULT_BACKEND,
        "paid_backend": PAID_BACKEND,
        "free_backends": sorted(n for n, r in BACKENDS.items() if r.is_free),
        "price_table": "backend.config.LLM_PRICE_PER_MTOK",
        "language_pin": _lang.LANGUAGE_PIN,
        "non_latin_bar": _lang.NON_LATIN_BAR,
        "backends": rows,
    }


def main() -> int:
    import argparse
    import json

    import backend.config  # noqa: F401  side effect: gated dotenv load

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--declare", action="store_true",
                   help="print the capability table")
    p.add_argument("--ask", metavar="PROMPT")
    p.add_argument("--backend", default=DEFAULT_BACKEND)
    p.add_argument("--model", default=None)
    a = p.parse_args()
    if a.ask:
        rep = complete(a.backend, a.ask, model=a.model)
        print(f"[{rep.backend}/{rep.model}] {rep.latency_s}s {rep.tokens_total} "
              f"tok ${rep.cost_usd:.4f} ({rep.cost_class})\n{rep.text}")
        print("\nusage:", json.dumps(usage(), indent=1))
        return 0
    print(json.dumps(capability_declaration(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
