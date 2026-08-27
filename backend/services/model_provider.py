"""One contract for every LLM provider, so adding a model is not adding a client.

    from backend.services import model_provider as mp
    mp.status()                      # what is configured, what actually answers
    mp.complete("nvidia", "...")     # same call shape for every provider

WHY A CONTRACT AND NOT THREE INTEGRATIONS
=========================================
DeepSeek, NVIDIA NIM and Hugging Face Inference Providers all speak the SAME
OpenAI-compatible `/chat/completions`. Three separate clients for one wire format
is how `llm_analyzer._get_provider` ended up reading as if Claude were primary
while returning `deepseek` for months -- nobody was lying, the shape just made
the truth hard to see.

So a provider here is DATA, not code: a base URL, an env var holding its key, and
a default model. Adding Fireworks or a local vLLM is a row in `PROVIDERS`.

WHAT THIS IS NOT
================
**It has no trading authority and never will.** `docs/CLAUDE.md` is explicit: no
LLM has authority over real capital anywhere in this system. This returns text.
Nothing downstream of it places an order.

It is also NOT a router. Choosing which provider handles which job is a decision
that needs evidence -- the Research Gym benchmark -- and a router built before
that evidence is a preference wearing a measurement's clothes. `status()` exists
so the evidence can be gathered; the routing comes after.

CONFIGURED IS NOT WORKING
=========================
`status()` distinguishes three states and never collapses them:

    absent      no env var at all
    configured  a key is present -- says NOTHING about whether it answers
    live        a real request came back

That distinction is the whole point. An `ANTHROPIC_API_KEY=` line with an empty
value read as configured for months and never was. And `agent-reach doctor`,
asked about a service whose config had just been written, refused to call it
available because it had not opened a connection -- which is the same rule.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

#: A provider is a row, not a class. `key_env` is the ONLY place its credential
#: is named, so a missing key reports the variable the reader must set.
PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "nvidia": {
        # NVIDIA NIM is OpenAI-compatible; the base URL already carries /v1.
        # NOTE: NIM RETIRES MODELS ON A DATE. The first default here,
        # meta/llama-3.3-70b-instruct, returned HTTP 410 "reached its end of
        # life on 2026-08-26" -- one day after it was written. `status(probe=True)`
        # caught it; `status()` alone would have reported "configured" forever.
        # Re-probe after any NIM outage rather than assuming a default still exists.
        # Of six candidates on this account only gpt-oss-20b answered: two were
        # 410 END-OF-LIFE, one 404 not-available-to-this-account (being LISTED by
        # /v1/models is not being callable), three timed out at 45s.
        #
        # gpt-oss-20b is a REASONING model: it spends tokens thinking before it
        # writes `content`. At max_tokens=16 content came back EMPTY and only
        # `reasoning_content` was populated; at 300 it answered "ready" in 120
        # tokens. So a small budget on a reasoning model reads as a dead model.
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "default_model": "openai/gpt-oss-20b",
    },
    "huggingface": {
        # HF Inference Providers routes one OpenAI-compatible endpoint to
        # whichever backend serves the model.
        "base_url": "https://router.huggingface.co/v1",
        "key_env": "HF_TOKEN",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
    },
}

#: Appended to every system prompt. `deepseek-chat` code-switches to Chinese when
#: no output language is named -- the parent bug was fixed centrally in
#: `llm_analyzer._call_llm` after `explain_move.py` fixed it at ONE call site and
#: every other caller inherited it for months. Same rule here: centrally, once.
_LANGUAGE_PIN = " Respond in English."


class ProviderRefusal(RuntimeError):
    """The provider was not configured, or its reply could not be trusted."""


@dataclass(frozen=True)
class Reply:
    provider: str
    model: str
    text: str
    latency_s: float
    prompt_tokens: int | None
    completion_tokens: int | None

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens


def _key(name: str) -> str:
    spec = PROVIDERS.get(name)
    if spec is None:
        raise ProviderRefusal(f"unknown provider {name!r}; have {sorted(PROVIDERS)}")
    # `.strip()` matters: an `X=` line with an empty value is ABSENT, not
    # configured. That exact shape made ANTHROPIC_API_KEY read as live.
    return os.getenv(spec["key_env"], "").strip()


def configured(name: str) -> bool:
    return bool(_key(name))


def complete(name: str, prompt: str, *, system: str = "You are a precise research assistant.",
             model: str | None = None, max_tokens: int = 512,  # reasoning models need headroom
             temperature: float = 0.2, timeout: int = 60) -> Reply:
    """One chat completion. Same shape for every provider in `PROVIDERS`."""
    spec = PROVIDERS[name] if name in PROVIDERS else None
    if spec is None:
        raise ProviderRefusal(f"unknown provider {name!r}; have {sorted(PROVIDERS)}")
    key = _key(name)
    if not key:
        raise ProviderRefusal(
            f"{name} is not configured: set {spec['key_env']}. This is a REFUSAL and not a "
            "fallback to another provider -- silently answering from a different model is how "
            "a benchmark ends up measuring the wrong one.")
    body = {
        "model": model or spec["default_model"],
        "messages": [{"role": "system", "content": system + _LANGUAGE_PIN},
                     {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        spec["base_url"].rstrip("/") + "/chat/completions", method="POST",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderRefusal(f"{name} HTTP {exc.code}: {exc.read().decode()[:300]}") from exc
    except Exception as exc:  # noqa: BLE001 -- transport failures are the provider's state
        raise ProviderRefusal(f"{name} unreachable: {type(exc).__name__}: {exc}") from exc
    dt = time.monotonic() - t0
    try:
        msg = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderRefusal(f"{name} returned no message: {str(payload)[:300]}") from exc
    # A REASONING model can return content=None and put the answer in
    # `reasoning_content`. The first version indexed straight to ["content"] and
    # handed callers a None that blew up one frame later with an AttributeError
    # naming neither the provider nor the model. Never return None as text.
    text = msg.get("content")
    if not text:
        text = msg.get("reasoning_content") or ""
    if not text.strip():
        raise ProviderRefusal(
            f"{name}/{body['model']} returned an EMPTY message (finish_reason="
            f"{payload['choices'][0].get('finish_reason')!r}). Empty is a refusal, not an "
            "answer -- a caller that treats it as text records a model saying nothing as a "
            f"model agreeing. Raw: {str(msg)[:200]}")
    usage = payload.get("usage") or {}
    return Reply(provider=name, model=body["model"], text=text, latency_s=round(dt, 3),
                 prompt_tokens=usage.get("prompt_tokens"),
                 completion_tokens=usage.get("completion_tokens"))


def status(*, probe: bool = False, timeout: int = 30) -> dict[str, dict]:
    """Per provider: absent / configured / live -- three states, never two.

    `probe=False` (default) reports only what the environment SAYS. It cannot
    report `live`, and it does not pretend to: a configured key is a claim about
    a file, not about a service.

    `probe=True` sends one tiny request per configured provider and reports what
    actually came back. That costs money, so it is opt-in and never the default.
    """
    out: dict[str, dict] = {}
    for name, spec in PROVIDERS.items():
        if not configured(name):
            out[name] = {"state": "absent", "key_env": spec["key_env"],
                         "why": f"{spec['key_env']} is unset or empty"}
            continue
        row = {"state": "configured", "key_env": spec["key_env"],
               "default_model": spec["default_model"],
               "why": "a key is present; this says NOTHING about whether it answers"}
        if probe:
            try:
                rep = complete(name, "Reply with the single word: ready.",
                               max_tokens=8, timeout=timeout)
                row.update(state="live", latency_s=rep.latency_s,
                           reply=rep.text.strip()[:40], model=rep.model,
                           why="a real request came back")
            except ProviderRefusal as exc:
                row.update(state="configured", error=str(exc)[:200],
                           why="a key is present and the request FAILED -- "
                               "configured is not working")
        out[name] = row
    return out


def main() -> int:
    # Imported for its side effect: backend.config loads .env at import time
    # (gated on AEGIS_IGNORE_DOTENV -- never move the file to mimic CI).
    import backend.config  # noqa: F401

    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--probe", action="store_true",
                   help="actually call each configured provider (costs money)")
    p.add_argument("--ask", metavar="PROMPT", help="send one prompt to --provider")
    p.add_argument("--provider", default="deepseek")
    args = p.parse_args()

    if args.ask:
        rep = complete(args.provider, args.ask)
        print(f"[{rep.provider}/{rep.model}] {rep.latency_s}s "
              f"tokens={rep.total_tokens}\n{rep.text}")
        return 0
    width = max(len(n) for n in PROVIDERS)
    for name, row in status(probe=args.probe).items():
        print(f"{name:{width}}  {row['state']:10}  {row.get('why','')}")
        if row.get("error"):
            print(f"{'':{width}}  {'':10}  {row['error']}")
    if not args.probe:
        print("\n(no --probe: this reports the ENVIRONMENT, not the services. "
              "A key that is present has not been shown to work.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
