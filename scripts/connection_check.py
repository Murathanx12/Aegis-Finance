"""CONNECTION CHECK — one READ-ONLY probe per provider, and a failure CLASS for each.

    python -m scripts.connection_check                  # table to stdout
    python -m scripts.connection_check --json           # receipt JSON to stdout
    python -m scripts.connection_check --json OUT.json  # receipt JSON to a file
    python -m scripts.connection_check --no-llm         # skip every paid call
    python -m scripts.connection_check --only fred,edgar

WHY THIS EXISTS (Labor Day Lab, lane D, 2026-09-07)
===================================================
Five separate sessions have concluded "the key is dead" from a 403, and at
least two of those were wrong. The lesson is written into the classifier here
rather than into a comment:

- **403 on a paid endpoint while another endpoint of the SAME provider returns
  200 is ENTITLEMENT, not a dead key.** Finnhub's free tier answers `/quote`
  and refuses `/stock/price-target`; a probe that only touched the second one
  would report a dead key and a session would spend an hour re-minting it.
- **A timeout is `network`, never "no data".** A rate limit reads as absence
  (`feedback-a-rate-limit-reads-as-absence`); silence is not evidence.
- **A probe that cannot determine an answer says CANNOT_DETERMINE with the
  reason.** A guard DERIVES its inputs or REFUSES. There is no guessed `ok`
  anywhere in this file.

NEVER PRINTS A KEY
==================
`key_fp()` returns `sha256:<8 hex>/len<N>` and nothing else. Not the first four
characters, not the last four — a fingerprint that is a one-way hash cannot
become a leak if a receipt is committed, and every receipt this writes IS
committed. The length is kept because a truncated paste is the single most
common credential defect in this project (`AAT_OPENAI_API_KEY` was 109 chars
when the real key was 164), and length alone catches it.

READ-ONLY
=========
Places nothing, cancels nothing, deploys nothing, sets no variable. The only
writes are the receipt file this is asked for and one row per paid LLM call in
the spend ledger of whichever repo owns it. `railway status` is read-only and
is the one shell-out here.

BUDGET
======
Paid LLM probes are 5 output tokens each and are individually skippable
(`--no-llm`). DeepSeek is probed at `GET /user/balance`, which costs nothing
and is the economic truth — our telemetry has been wrong before, the
provider's balance has not.

CALLABLE ENTRY POINT
====================
`run_checks()` returns the receipt dict, so this can become a nightly job in
the finance scheduler and in the terminal's `fleet_health` without a shell.
It is NOT scheduled by this file. Nothing here registers a job.
"""

from __future__ import annotations

import argparse
import concurrent.futures as _cf
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
RECEIPT_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"

#: Failure classes. Every non-ok row carries exactly one of these.
AUTH = "auth"                 # credential rejected (401 / explicit invalid-key body)
QUOTA = "quota"               # rate limited or over plan volume (429 / quota text)
NETWORK = "network"           # DNS, TCP, TLS, timeout, 5xx — the wire, not us
ENTITLEMENT = "entitlement"   # credential valid, this resource not included in the plan
DEAD_KEY = "dead_key"         # every endpoint refuses the credential
ABSENT = "absent"             # no credential configured at all
CANNOT = "cannot_determine"   # the probe could not answer; the reason is recorded

OK = "ok"

_DEFAULT_TIMEOUT = 25.0
_UA = os.environ.get(
    "SEC_USER_AGENT", "Aegis Finance Research mrthnabdullaev@gmail.com")


# ── credentials, never values ────────────────────────────────────────────────

def key_fp(value: str | None) -> str | None:
    """A one-way fingerprint of a credential. Never the credential.

    Returns None when there is nothing configured, so an absent key and an
    empty key are the same visible thing (they are the same real thing:
    `ANTHROPIC_API_KEY=` with an empty value has read as "configured" in this
    repo's own provider resolver for months).
    """
    v = (value or "").strip()
    if not v:
        return None
    return f"sha256:{hashlib.sha256(v.encode('utf-8')).hexdigest()[:8]}/len{len(v)}"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def load_env() -> str:
    """Populate the process env through the repo's own loader.

    NEVER move, copy or rename `.env` — on 2026-08-24 a subshell that moved it
    aside to mimic CI died before its EXIT trap ran and the machine lost every
    key on it. `backend.config` gates `load_dotenv` on `AEGIS_IGNORE_DOTENV`
    precisely so nothing has to.
    """
    try:
        import backend.config  # noqa: F401  (import side effect: load_dotenv)
        return "backend.config"
    except Exception:                                                # noqa: BLE001
        try:
            from dotenv import load_dotenv
            load_dotenv(REPO / ".env")
            return "dotenv fallback"
        except Exception as e:                                       # noqa: BLE001
            return f"NOT LOADED ({type(e).__name__})"


# ── HTTP, with the classification attached to the response ───────────────────

class Probe:
    """One provider's result. Immutable once `finish` is called."""

    def __init__(self, name: str, *, group: str, why: str) -> None:
        self.name, self.group, self.why = name, group, why
        # "CANNOT_DETERMINE", not the lowercase class name: `run_checks` counts
        # `status == "CANNOT_DETERMINE"`, so a probe that never ran was counted
        # as neither ok, nor fail, nor unknown — it fell out of the totals.
        self.status: str = "CANNOT_DETERMINE"
        self.failure_class: str | None = CANNOT
        self.latency_ms: float | None = None
        self.entitlement: str = "unknown"
        self.quota_hint: str | None = None
        self.detail: str = "probe did not run"
        self.key_fp: str | None = None
        self.endpoints: list[dict[str, Any]] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.name, "group": self.group, "why": self.why,
            "status": self.status, "failure_class": self.failure_class,
            "latency_ms": (round(self.latency_ms, 1)
                           if self.latency_ms is not None else None),
            "entitlement": self.entitlement, "quota_hint": self.quota_hint,
            "detail": self.detail[:400], "key_fingerprint": self.key_fp,
            "endpoints": self.endpoints,
        }

    def ok(self, detail: str, *, entitlement: str = "granted",
           quota_hint: str | None = None) -> "Probe":
        self.status, self.failure_class = OK, None
        self.detail, self.entitlement, self.quota_hint = detail, entitlement, quota_hint
        return self

    def fail(self, klass: str, detail: str, *, entitlement: str = "unknown") -> "Probe":
        self.status, self.failure_class = "FAIL", klass
        self.detail, self.entitlement = detail, entitlement
        return self

    def cannot(self, detail: str) -> "Probe":
        self.status, self.failure_class = "CANNOT_DETERMINE", CANNOT
        self.detail = detail
        return self


def _classify_http(code: int, body: str) -> tuple[str, str]:
    """(failure_class, why) for a non-2xx HTTP code. Body is used only for the
    words providers actually put in refusal bodies, never echoed wholesale."""
    low = (body or "")[:400].lower()
    if code in (401,):
        return AUTH, "401"
    if code == 403:
        # 403 is the ambiguous one and is resolved by the CALLER, which knows
        # whether another endpoint of the same provider answered 200.
        if "invalid api key" in low or "api key" in low and "invalid" in low:
            return AUTH, "403 with an invalid-key body"
        return ENTITLEMENT, "403"
    if code == 429:
        return QUOTA, "429"
    if code in (402,):
        return QUOTA, "402 payment required"
    if 500 <= code < 600:
        return NETWORK, f"{code} upstream"
    if code == 404:
        return CANNOT, "404 — the endpoint moved or the probe path is wrong"
    return CANNOT, str(code)


def http(url: str, *, headers: dict[str, str] | None = None,
         data: bytes | None = None, timeout: float = _DEFAULT_TIMEOUT,
         method: str | None = None) -> dict[str, Any]:
    """One request. NEVER raises; returns a dict that always has `class`.

    The URL is redacted before it enters the result: query strings carry
    `api_key=` and an error message that embeds the request URL is how keys
    reach log files.
    """
    h = {"User-Agent": _UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(256 * 1024)
            ms = (time.perf_counter() - t0) * 1000
            return {"ok": True, "code": r.status, "ms": ms,
                    "body": raw.decode("utf-8", "replace"),
                    "headers": dict(r.headers), "class": None,
                    "url": _redact_url(url)}
    except urllib.error.HTTPError as e:                              # noqa: PERF203
        ms = (time.perf_counter() - t0) * 1000
        try:
            body = e.read(32 * 1024).decode("utf-8", "replace")
        except Exception:                                            # noqa: BLE001
            body = ""
        klass, why = _classify_http(e.code, body)
        return {"ok": False, "code": e.code, "ms": ms, "body": body,
                "headers": dict(getattr(e, "headers", {}) or {}),
                "class": klass, "why": why, "url": _redact_url(url)}
    except Exception as e:                                           # noqa: BLE001
        ms = (time.perf_counter() - t0) * 1000
        # A timeout, a DNS failure and a TLS failure are all the WIRE. None of
        # them is "no data" and none of them is a bad key.
        return {"ok": False, "code": None, "ms": ms, "body": "",
                "headers": {}, "class": NETWORK,
                "why": f"{type(e).__name__}: {str(e)[:160]}",
                "url": _redact_url(url)}


def _redact_url(url: str) -> str:
    """Strip every query value that could be a credential."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.query:
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    secretish = ("key", "token", "apikey", "api_key", "apiKey", "secret",
                 "api_token", "access_token", "password")
    kept = [(k, ("<redacted>" if any(s in k.lower() for s in secretish) else v))
            for k, v in q]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path,
         urllib.parse.urlencode(kept), ""))


def _record(p: Probe, label: str, r: dict[str, Any]) -> dict[str, Any]:
    p.endpoints.append({"endpoint": label, "url": r.get("url"),
                        "code": r.get("code"), "ms": round(r.get("ms") or 0, 1),
                        "class": r.get("class"), "why": r.get("why")})
    return r


def _multi(p: Probe, calls: list[tuple[str, str, dict[str, str] | None]],
           *, free: set[str]) -> Probe:
    """Probe several endpoints of ONE provider and resolve 403 correctly.

    `free` names the endpoints expected to work on the cheapest plan. The rule
    that this function exists to encode:

        any 200 anywhere  =>  the credential is LIVE.
        403 elsewhere     =>  ENTITLEMENT (the plan), not a dead key.
        no 200 anywhere and 401/403 everywhere  =>  DEAD_KEY.
    """
    best_ms: float | None = None
    got_200: list[str] = []
    denied: list[str] = []
    for label, url, headers in calls:
        r = _record(p, label, http(url, headers=headers))
        if r["ok"]:
            got_200.append(label)
            best_ms = r["ms"] if best_ms is None else min(best_ms, r["ms"])
        else:
            denied.append(f"{label}:{r.get('code')}")
    p.latency_ms = best_ms
    codes = {e["code"] for e in p.endpoints}
    if got_200:
        # 401 and 403 are NOT the same finding even when both mean "you cannot
        # have this". 403 is the plan; 401 on one endpoint of a credential that
        # answers another is a LAPSED or SCOPED subscription, and saying
        # "not entitled" for both hides which one a renewal would fix.
        gated = [e["endpoint"] for e in p.endpoints if e["code"] in (402, 403)]
        unauth = [e["endpoint"] for e in p.endpoints if e["code"] == 401]
        limited = [e["endpoint"] for e in p.endpoints if e["code"] == 429]
        ent = ("granted: " + ",".join(sorted(got_200))
               + (" | NOT entitled(403): " + ",".join(sorted(gated)) if gated else "")
               + (" | 401 on: " + ",".join(sorted(unauth)) if unauth else ""))
        return p.ok(f"{len(got_200)}/{len(calls)} endpoints answered 200",
                    entitlement=ent,
                    quota_hint=("429 on " + ",".join(limited)) if limited else None)
    if codes and codes <= {401, 403}:
        return p.fail(DEAD_KEY,
                      "every endpoint refused the credential: " + ", ".join(denied),
                      entitlement="none")
    if 429 in codes:
        return p.fail(QUOTA, "rate limited on every endpoint: " + ", ".join(denied))
    if None in codes:
        return p.fail(NETWORK, "no endpoint reachable: " + ", ".join(
            e.get("why") or "" for e in p.endpoints if e["code"] is None)[:300])
    return p.cannot("no 200 and no recognised refusal: " + ", ".join(denied))


# ── the probes ───────────────────────────────────────────────────────────────

def _needs(p: Probe, var: str) -> str | None:
    """Return the key, or mark the probe ABSENT and return None."""
    v = _env(var)
    p.key_fp = key_fp(v)
    if not v:
        p.fail(ABSENT, f"{var} is not set (or is empty) in this process")
        p.entitlement = "none"
        return None
    return v


def probe_fred() -> Probe:
    p = Probe("FRED", group="data", why="VIX, rates, macro series")
    k = _needs(p, "FRED_API_KEY")
    if not k:
        return p
    return _multi(p, [
        ("series/VIXCLS",
         f"https://api.stlouisfed.org/fred/series?series_id=VIXCLS&api_key={k}&file_type=json",
         None),
        ("series/observations/DGS10",
         f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10"
         f"&api_key={k}&file_type=json&limit=1&sort_order=desc", None),
    ], free={"series/VIXCLS"})


def probe_finnhub() -> Probe:
    """The free-tier 403 map, explicitly.

    Finnhub's free plan answers quotes, profiles, company news and
    recommendations, and 403s price targets, candles and several premium
    endpoints. A session that probed only `/stock/candle` would report a dead
    key. This probes both sides so the row can say ENTITLEMENT and name which
    endpoints are and are not in the plan.
    """
    p = Probe("Finnhub", group="data",
              why="quotes, profiles, analyst recommendations; the free-tier map")
    k = _needs(p, "FINNHUB_API_KEY")
    if not k:
        return p
    b = "https://finnhub.io/api/v1"
    return _multi(p, [
        ("quote (free)", f"{b}/quote?symbol=AAPL&token={k}", None),
        ("stock/profile2 (free)", f"{b}/stock/profile2?symbol=AAPL&token={k}", None),
        ("stock/recommendation (free)", f"{b}/stock/recommendation?symbol=AAPL&token={k}", None),
        ("company-news (free)",
         f"{b}/company-news?symbol=AAPL&from={(date.today()-timedelta(days=5)).isoformat()}"
         f"&to={date.today().isoformat()}&token={k}", None),
        ("stock/price-target (PREMIUM)", f"{b}/stock/price-target?symbol=AAPL&token={k}", None),
        ("stock/candle (PREMIUM)",
         f"{b}/stock/candle?symbol=AAPL&resolution=D&count=2&token={k}", None),
        ("stock/insider-transactions", f"{b}/stock/insider-transactions?symbol=AAPL&token={k}", None),
    ], free={"quote (free)"})


def probe_fmp() -> Probe:
    p = Probe("FMP", group="data", why="fundamentals, ratios, congress trades")
    k = _needs(p, "FMP_API_KEY")
    if not k:
        return p
    # BOTH bases, on purpose. FMP retired the `/api/v3` legacy surface on
    # 2025-08-31 and answers it with 403 + "Legacy Endpoint" for anyone who did
    # not hold a subscription before that date. A probe that touched only v3
    # would report a DEAD KEY for a key that answers `/stable` in 300 ms.
    pr = _multi(p, [
        ("stable/quote", f"https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey={k}", None),
        ("stable/profile", f"https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey={k}", None),
        ("v3/quote (LEGACY)", f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={k}", None),
        ("v3/ratios-ttm (LEGACY)",
         f"https://financialmodelingprep.com/api/v3/ratios-ttm/AAPL?apikey={k}", None),
    ], free={"stable/quote"})
    legacy_dead = [e for e in pr.endpoints
                   if "LEGACY" in e["endpoint"] and e["code"] == 403]
    if pr.status == OK and legacy_dead:
        pr.detail += ("; the /api/v3 LEGACY surface is retired for this key. "
                      "backend/services/providers/fmp_provider.py and "
                      "backend/services/esg.py still point at /api/v3 — every "
                      "call they make is a 403.")
    # The budget is PROCESS-LOCAL state; a fresh process reports a fresh budget
    # and therefore cannot speak for the running website. Say so rather than
    # print a reassuring 0/240.
    try:
        from backend.services import fmp_budget
        st = fmp_budget.status()
        pr.quota_hint = (
            f"configured daily_budget={st.get('daily_budget')} "
            f"reserve={st.get('priority_reserve')}; this process spent "
            f"{st.get('spent')} — PROCESS-LOCAL counter, NOT the live website's")
    except Exception as e:                                           # noqa: BLE001
        pr.quota_hint = f"budget state unreadable: {type(e).__name__}"
    return pr


def probe_polygon() -> Probe:
    p = Probe("Polygon", group="data", why="aggregates, reference data")
    k = _needs(p, "POLYGON_API_KEY")
    if not k:
        return p
    return _multi(p, [
        ("v2/aggs prev close", f"https://api.polygon.io/v2/aggs/ticker/AAPL/prev?apiKey={k}", None),
        ("v3/reference/tickers",
         f"https://api.polygon.io/v3/reference/tickers?limit=1&apiKey={k}", None),
        ("v2/last/trade (PAID tier)", f"https://api.polygon.io/v2/last/trade/AAPL?apiKey={k}", None),
    ], free={"v2/aggs prev close"})


def probe_alpha_vantage() -> Probe:
    p = Probe("AlphaVantage", group="data", why="fallback quotes and FX")
    k = _needs(p, "ALPHA_VANTAGE_API_KEY")
    if not k:
        return p
    r = _record(p, "GLOBAL_QUOTE", http(
        f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey={k}"))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    # Alpha Vantage answers 200 for EVERY failure and puts the refusal in the
    # body. A probe that trusted the status code would call a rate limit `ok`.
    try:
        d = json.loads(r["body"])
    except json.JSONDecodeError:
        return p.cannot("200 with a non-JSON body")
    if "Note" in d or "Information" in d:
        msg = str(d.get("Note") or d.get("Information"))[:200]
        low = msg.lower()
        if "premium" in low or "higher api call" in low or "rate limit" in low:
            return p.fail(QUOTA, f"200 body carries a limit notice: {msg}",
                          entitlement="free tier")
        return p.fail(CANNOT, f"200 body carries a notice: {msg}")
    if "Error Message" in d:
        return p.fail(AUTH, str(d["Error Message"])[:200])
    if not d.get("Global Quote"):
        return p.cannot(f"200 with neither a quote nor a notice: keys={list(d)[:5]}")
    return p.ok("GLOBAL_QUOTE returned a quote", entitlement="free tier",
                quota_hint="free tier is 25 requests/day — one spent by this probe")


def probe_eodhd() -> Probe:
    p = Probe("EODHD", group="data", why="EOD prices, splits, fundamentals")
    k = _needs(p, "EODHD_API_TOKEN")
    if not k:
        return p
    pr = _multi(p, [
        ("eod/AAPL.US",
         f"https://eodhd.com/api/eod/AAPL.US?api_token={k}&fmt=json&period=d"
         f"&from={(date.today()-timedelta(days=7)).isoformat()}", None),
        ("user (plan + quota)", f"https://eodhd.com/api/user?api_token={k}&fmt=json", None),
    ], free={"eod/AAPL.US"})
    # EODHD states its own plan and daily allowance. Quoting the vendor's
    # number beats inferring one: `quote the cost rate or don't quote the count`.
    for e in p.endpoints:
        if e["endpoint"].startswith("user") and e["code"] == 200:
            r = http(f"https://eodhd.com/api/user?api_token={k}&fmt=json")
            try:
                d = json.loads(r["body"])
                pr.quota_hint = (f"plan={d.get('subscriptionType')} "
                                 f"dailyRateLimit={d.get('dailyRateLimit')} "
                                 f"apiRequests={d.get('apiRequests')} "
                                 f"on {d.get('apiRequestsDate')}")
            except Exception:                                        # noqa: BLE001
                pr.quota_hint = "user endpoint answered but did not parse"
    if pr.status == OK and any(e["code"] == 401 for e in p.endpoints):
        pr.detail += ("; the DATA endpoints 401 while /user answers 200 — the "
                      "token is real and the data subscription is not active. "
                      "That is a BILLING finding, not a dead key.")
    return pr


def probe_deepseek() -> Probe:
    """The BALANCE, which costs nothing and is the economic truth.

    `reference-deepseek-balance-is-the-truth`: our own telemetry has been wrong
    about spend before; the provider's balance has not. No completion is issued
    — a balance that answers proves the key, and a 5-token chat would prove
    nothing further while costing money.
    """
    p = Probe("DeepSeek", group="llm", why="THE sole provisioned LLM provider")
    k = _needs(p, "DEEPSEEK_API_KEY")
    if not k:
        return p
    r = _record(p, "GET /user/balance", http(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        d = json.loads(r["body"])
        infos = d.get("balance_infos") or []
        bal = ", ".join(f"{i.get('total_balance')} {i.get('currency')}" for i in infos)
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable balance body")
    return p.ok(f"balance endpoint answered; is_available={d.get('is_available')}",
                entitlement="pay-as-you-go", quota_hint=f"balance {bal}")


def _chat_5_tokens(p: Probe, url: str, key: str, model: str,
                   extra: dict[str, Any] | None = None,
                   timeout: float = 90.0) -> Probe:
    """ONE 5-token completion. The whole paid surface of this file.

    The system prompt names the output language on purpose: `deepseek-chat`
    (and every model on the HF router that wraps a Chinese base) code-switches
    when nothing pins it, and a probe that read a Chinese reply as a failure
    would report a working provider dead.
    """
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": "Answer in English. One word."},
                     {"role": "user", "content": "Reply with the word: up"}],
        "max_tokens": 5}
    for k_, v_ in (extra or {}).items():
        # An explicit None means REMOVE the parameter, not send null: OpenAI's
        # gpt-5 family 400s on `max_tokens: null` exactly as it 400s on
        # `temperature`, and a 400 from a malformed probe body is indexed as a
        # provider failure by anyone reading the receipt later.
        if v_ is None:
            body.pop(k_, None)
        else:
            body[k_] = v_
    r = _record(p, f"chat/completions {model}", http(
        url, headers={"Authorization": f"Bearer {key}",
                      "Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8"), method="POST", timeout=timeout))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        # A 404 on a chat endpoint usually means the MODEL id is wrong, which is
        # a configuration finding and not a credential one.
        if r.get("code") == 404:
            return p.cannot(f"404 — model id {model!r} not served on this route")
        if r.get("class") == NETWORK and "timed out" in str(r.get("why", "")).lower():
            # A LISTED model that never answers is a model finding, not a
            # credential finding, and the two must not share a row: a reasoning
            # model can spend a 5-token budget entirely on thinking.
            return p.cannot(
                f"model {model!r} is listed but did not return within "
                f"{timeout:.0f}s — the credential authenticated (the model list "
                f"answered); this is a MODEL LATENCY finding")
        return p.fail(r["class"] or CANNOT, f"{r.get('code')} {str(r.get('why'))[:160]}")
    try:
        d = json.loads(r["body"])
        txt = (d["choices"][0]["message"].get("content") or "").strip()
        usage = d.get("usage") or {}
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable completion body")
    return p.ok(f"5-token completion returned {txt[:24]!r}",
                entitlement=f"model {model} served",
                quota_hint=f"usage={usage.get('prompt_tokens')}p/"
                           f"{usage.get('completion_tokens')}c")


def probe_nvidia(*, llm: bool) -> Probe:
    p = Probe("NVIDIA NIM", group="llm", why="second LLM family (kimi/minimax/gemma)")
    k = _needs(p, "NVIDIA_API_KEY")
    if not k:
        return p
    base = _env("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
    r = _record(p, "GET /models", http(base.rstrip("/") + "/models",
                                       headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        n = len(json.loads(r["body"]).get("data") or [])
    except Exception:                                                # noqa: BLE001
        n = -1
    if not llm:
        return p.ok(f"model list returned {n} models (completion skipped: --no-llm)",
                    entitlement=f"{n} models visible")
    # THE MODEL LIST IS THE CATALOGUE, NOT THE GRANT. Measured 2026-09-05: the
    # list returns 81 models in 306 ms and `google/gemma-3-4b-it`,
    # `mistralai/mistral-7b-instruct-v0.3`, `moonshotai/kimi-k2.6`,
    # `nvidia/llama-3.1-nemotron-70b-instruct` and `google/gemma-2b` all answer
    # a completion with **404 "Not found for account"** — visible, not
    # provisioned. That is the same shape as WRDS showing every subscriber all
    # 1,316 schemas. So the completion is attempted against the models the
    # council actually declares, and a 404 is recorded as ENTITLEMENT rather
    # than as a dead key or a bad model id.
    attempts = ("moonshotai/kimi-k3", "minimaxai/minimax-m3", "google/gemma-4-31b-it")
    url = base.rstrip("/") + "/chat/completions"
    for model in attempts:
        q = _chat_5_tokens(p, url, k, model, timeout=30.0)
        if q.status == OK:
            q.entitlement = f"{n} models visible; {model} served"
            return q
    codes = [e.get("code") for e in p.endpoints if "chat/completions" in e["endpoint"]]
    if any(c == 404 for c in codes):
        return p.fail(ENTITLEMENT,
                      f"model list answers ({n} models) but every declared model "
                      f"404s 'Not found for account': {', '.join(attempts)}. The "
                      f"credential is LIVE and no completion is provisioned.",
                      entitlement=f"{n} listed, 0 of {len(attempts)} declared served")
    return p.cannot(
        f"credential authenticated ({n} models listed) and none of "
        f"{', '.join(attempts)} returned within 30 s each. NOT a key failure "
        f"and NOT proof the family works — CANNOT DETERMINE.")


def probe_hf_router(*, llm: bool) -> Probe:
    p = Probe("HF router", group="llm", why="third LLM family via huggingface router")
    k = _needs(p, "HF_TOKEN")
    if not k:
        return p
    r = _record(p, "GET /v1/models", http(
        "https://router.huggingface.co/v1/models",
        headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        n = len(json.loads(r["body"]).get("data") or [])
    except Exception:                                                # noqa: BLE001
        n = -1
    if not llm:
        return p.ok(f"router listed {n} models (completion skipped: --no-llm)",
                    entitlement=f"{n} models visible")
    q = _chat_5_tokens(p, "https://router.huggingface.co/v1/chat/completions", k,
                       "zai-org/GLM-5.3-Flash")
    if q.status == OK:
        q.entitlement = f"{n} models visible; GLM-5.3-Flash served"
    return q


def probe_openai(*, llm: bool) -> Probe:
    """`GTP_TOKEN` is the name Murat pasted it under. That is not a typo to fix
    silently: `alpha/council/providers.KEY_ALIASES` already accepts it, and an
    hour was spent in August concluding "the OpenAI family is blocked" while a
    working 164-char key sat one file over under this name."""
    p = Probe("OpenAI", group="llm", why="gpt-5-nano bulk extraction; gpt-5-mini judge")
    k = _env("GTP_TOKEN") or _env("OPENAI_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "neither GTP_TOKEN nor OPENAI_API_KEY is set")
    r = _record(p, "GET /v1/models", http("https://api.openai.com/v1/models",
                                          headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        n = len(json.loads(r["body"]).get("data") or [])
    except Exception:                                                # noqa: BLE001
        n = -1
    if not llm:
        return p.ok(f"model list returned {n} models (completion skipped: --no-llm)",
                    entitlement=f"{n} models visible")
    # `temperature` is a 400 on gpt-5-nano and `reasoning_effort` must be
    # "minimal" or the model spends the whole token budget thinking and returns
    # an empty string (session 24, measured).
    q = _chat_5_tokens(p, "https://api.openai.com/v1/chat/completions", k,
                       "gpt-5-nano",
                       # `temperature` is a 400 on this family, and so is a
                       # completion budget the model cannot finish inside:
                       # gpt-5-nano at max_completion_tokens=16 returns
                       # `invalid_request_error: max_tokens or model output
                       # limit was reached` even at reasoning_effort=minimal
                       # (measured 2026-09-05). 64 output tokens is ~$0.000026.
                       {"reasoning_effort": "minimal",
                        "max_completion_tokens": 64, "max_tokens": None})
    if q.status == OK:
        q.entitlement = f"{n} models visible; gpt-5-nano served"
    return q


def probe_featherless(*, llm: bool) -> Probe:
    p = Probe("Featherless", group="llm", why="fifth LLM family (qwen/alibaba)")
    k = _env("AAT_FEATHERLESS_API_KEY") or _env("FEATHERLESS_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(
            ABSENT,
            "no AAT_FEATHERLESS_API_KEY/FEATHERLESS_API_KEY in THIS process — "
            "the key lives in the terminal repo's .env, so probe it from there")
    base = _env("AAT_FEATHERLESS_BASE_URL") or "https://api.featherless.ai/v1"
    r = _record(p, "GET /models", http(base.rstrip("/") + "/models",
                                       headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    if not llm:
        return p.ok("model list answered (completion skipped: --no-llm)")
    return _chat_5_tokens(p, base.rstrip("/") + "/chat/completions", k,
                          _env("AAT_FEATHERLESS_MODEL") or "Qwen/Qwen2.5-72B-Instruct")


def probe_wrds() -> Probe:
    """Connect, then attempt a BOUNDED read of the two tables the entitlement
    question is actually about. Catalogue visibility is not access — WRDS shows
    every subscriber all 1,316 schemas regardless of grant, which is how three
    checks disagreed about RavenPack on 2026-08-31. Verify a link at its FAR
    end (`scripts/wrds_entitlement_probe.py` is the long form)."""
    p = Probe("WRDS", group="research",
              why="CRSP / IBES / OptionMetrics panels; the RavenPack question")
    host, port, db, user = ("wrds-pgdata.wharton.upenn.edu", 9737, "wrds", "murathan12")
    pgpass = os.path.expandvars(r"%APPDATA%\postgresql\pgpass.conf")
    if os.name != "nt":
        pgpass = os.environ.get("PGPASSFILE", str(Path.home() / ".pgpass"))
    os.environ.setdefault("PGPASSFILE", pgpass)
    if not Path(pgpass).exists():
        return p.cannot(f"no pgpass file at the configured PGPASSFILE path "
                        f"({Path(pgpass).name}); cannot authenticate")
    try:
        import psycopg2
    except ImportError:
        return p.cannot("psycopg2 is not installed in this interpreter")
    t0 = time.perf_counter()
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=db, user=user,
                                sslmode="require", connect_timeout=20)
    except Exception as e:                                           # noqa: BLE001
        msg = str(e).strip().splitlines()[0][:180]
        klass = AUTH if "authentication" in msg.lower() or "password" in msg.lower() else NETWORK
        p.fail(klass, msg)
        # The wire is down; the ENTITLEMENT question still has a last recorded
        # answer, and quoting it is honest as long as it is labelled a RECORD
        # rather than a measurement. `absence of a local object is not evidence
        # of absence` cuts both ways: an unreachable host is not a lost grant.
        prev = REPO / "backend" / "data" / "optimus" / "wrds" / "entitlement_probe.json"
        if prev.exists():
            try:
                d = json.loads(prev.read_text(encoding="utf-8"))
                res = d.get("results") or d.get("rows") or []
                rd = d.get("readable_families") or [r["family"] for r in res
                                                    if r.get("readable")]
                nd = d.get("denied_families") or [r["family"] for r in res
                                                  if not r.get("readable")]
                p.entitlement = (f"NOT MEASURED TODAY. Last recorded {d.get('at', '?')[:10]}: "
                                 f"READ={','.join(rd)} | DENIED={','.join(nd)}")
                p.endpoints.append({"endpoint": "last recorded entitlement map",
                                    "source": str(prev.relative_to(REPO)),
                                    "at": d.get("at")})
            except Exception:                                        # noqa: BLE001
                pass
        return p
    p.latency_ms = (time.perf_counter() - t0) * 1000
    grants: dict[str, str] = {}
    targets = (("tr_ibes.ptgdetu", "the 4.66M analyst price targets we DO own"),
               ("ravenpack_full.rpa_full_equities_2024", "the news archive we do NOT own"),
               ("crsp.dsf", "daily prices"),
               ("optionm.opprcd2023", "option chains"))
    try:
        for qualified, _why in targets:
            schema, table = qualified.split(".", 1)
            cur = conn.cursor()
            try:
                cur.execute("SET LOCAL statement_timeout = 20000")
                cur.execute(f'SELECT 1 FROM "{schema}"."{table}" LIMIT 1')
                cur.fetchall()
                grants[qualified] = "READ"
            except Exception as e:                                   # noqa: BLE001
                m = str(e).strip().splitlines()[0].lower()
                grants[qualified] = ("NOT_ENTITLED" if "permission denied" in m
                                     else "NO_SUCH_TABLE" if "does not exist" in m
                                     else "TIMEOUT" if "timeout" in m or "canceling" in m
                                     else "ERROR")
            finally:
                conn.rollback()
                cur.close()
    finally:
        conn.close()
    p.endpoints.append({"endpoint": "bounded SELECT per table", "grants": grants})
    readable = [k for k, v in grants.items() if v == "READ"]
    ent = "; ".join(f"{k}={v}" for k, v in grants.items())
    if readable:
        return p.ok(f"connected as {user}; {len(readable)}/{len(targets)} tables readable",
                    entitlement=ent)
    return p.fail(ENTITLEMENT, "connected but no probed table is readable",
                  entitlement=ent)


def probe_gdelt() -> Probe:
    p = Probe("GDELT", group="news", why="global news volume; the stability canary")
    r = _record(p, "v2/doc artlist", http(
        "https://api.gdeltproject.org/api/v2/doc/doc"
        "?query=%22Federal%20Reserve%22&mode=artlist&maxrecords=1&format=json",
        timeout=45))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        n = len(json.loads(r["body"]).get("articles") or [])
    except json.JSONDecodeError:
        # GDELT answers 200 with an HTML/plain error page when it throttles.
        low = r["body"][:200].lower()
        if "rate" in low or "too many" in low:
            return p.fail(QUOTA, f"200 with a throttle page: {r['body'][:120]}")
        return p.cannot(f"200 with a non-JSON body: {r['body'][:120]}")
    return p.ok(f"artlist returned {n} article(s)", entitlement="public, no key",
                quota_hint="unauthenticated; throttles under load")


def probe_edgar() -> Probe:
    p = Probe("EDGAR", group="filings", why="8-K item codes, Form 4, submissions")
    # NO `Accept-Encoding: gzip` here: urllib does not decompress, and the
    # 200-with-an-unparseable-body that produces reads as a broken endpoint.
    # The production collectors send it AND decompress; a probe does not need
    # the bandwidth and does need an unambiguous answer.
    r = _record(p, "submissions CIK0000320193", http(
        "https://data.sec.gov/submissions/CIK0000320193.json",
        headers={"User-Agent": _UA, "Accept-Encoding": "identity"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        if r.get("code") == 403:
            return p.fail(AUTH, "403 — SEC rejected the User-Agent; set SEC_USER_AGENT "
                                "to 'Name email' (this is a UA policy refusal, not a key)")
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        d = json.loads(r["body"])
        name = d.get("name")
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable submissions body")
    return p.ok(f"submissions answered for {name!r}",
                entitlement=f"public; declared UA present ({len(_UA)} chars)",
                quota_hint="SEC fair access: 10 req/s")


def probe_kalshi() -> Probe:
    p = Probe("Kalshi", group="prediction", why="event probabilities")
    try:
        from backend.config import KALSHI_API_BASE as base
    except Exception:                                                # noqa: BLE001
        base = "https://api.elections.kalshi.com/trade-api/v2"
    r = _record(p, "GET /events", http(f"{base}/events?limit=1&status=open"))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        n = len(json.loads(r["body"]).get("events") or [])
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable events body")
    return p.ok(f"/events returned {n} event(s)", entitlement="public read, no key")


def probe_polymarket() -> Probe:
    p = Probe("Polymarket", group="prediction", why="event probabilities")
    try:
        from backend.config import POLYMARKET_API_BASE as base
    except Exception:                                                # noqa: BLE001
        base = "https://gamma-api.polymarket.com"
    r = _record(p, "GET /markets", http(f"{base}/markets?limit=1&closed=false"))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        d = json.loads(r["body"])
        n = len(d if isinstance(d, list) else d.get("data") or [])
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable markets body")
    return p.ok(f"/markets returned {n} market(s)", entitlement="public read, no key")


def probe_cboe() -> Probe:
    """CBOE is NOT wired into this repo — VIX arrives through FRED's `VIXCLS`.
    The probe exists so the row says "reachable, unwired" rather than leaving
    a named provider unanswered."""
    p = Probe("CBOE", group="data", why="delayed quotes / VIX; NOT wired in code")
    r = _record(p, "delayed_quotes/_VIX", http(
        "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        json.loads(r["body"])
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable quote body")
    return p.ok("delayed VIX quote answered",
                entitlement="public CDN, no key; NO CALLER IN THIS REPO")


def probe_website() -> Probe:
    """`/api/health/full` has no `section=` parameter, so the slicing is done
    HERE: a summary is extracted and the ~100 KB payload is dropped. Dumping
    the whole thing into a receipt is how a receipt stops being read."""
    p = Probe("website /api/health/full", group="ours",
              why="the deployed backend; scheduler, lanes, source health")
    url = "https://aegis-finance-production.up.railway.app/api/health/full"
    r = _record(p, "GET (sliced locally)", http(url, timeout=90))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        d = json.loads(r["body"])
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable health body")
    tr = (d.get("track_record") or {}).get("lanes") or {}
    summary = {
        "status": d.get("status"),
        "commit": str(d.get("commit") or d.get("build") or "")[:12],
        "uptime_s": d.get("uptime_seconds"),
        "top_level_keys": sorted(d)[:20],
        "lane_count": len(tr),
        "warning_count": len(d.get("recent_warnings") or []),
        "payload_bytes": len(r["body"]),
    }
    p.endpoints[-1]["summary"] = summary
    st = str(summary["status"] or "").lower()
    if st and st not in ("ok", "healthy", "pass"):
        return p.fail(CANNOT, f"reachable but status={summary['status']!r}",
                      entitlement="ours")
    return p.ok(f"status={summary['status']!r}, {summary['lane_count']} lanes, "
                f"{summary['warning_count']} recent warnings "
                f"({summary['payload_bytes']} B sliced away)",
                entitlement="ours")


def probe_seal_authority() -> Probe:
    """GET only. The public authority is meant to be read-only; POST is lane
    C4's question, not this one — this probe never issues one."""
    p = Probe("seal-authority (public GET)", group="ours",
              why="the artery: books the fleet reads instead of re-deriving")
    base = (_env("AAT_PREDICTION_BOOK_BASE_URL")
            or "https://seal-authority-production.up.railway.app").rstrip("/")
    day = date.today().isoformat()
    r_root = _record(p, "GET /", http(base + "/", timeout=45))
    r_day = _record(p, f"GET /{day}.json", http(f"{base}/{day}.json", timeout=45))
    p.latency_ms = min([x["ms"] for x in (r_root, r_day)])
    if r_day["ok"]:
        try:
            d = json.loads(r_day["body"])
            return p.ok(f"today's book served: day={d.get('day')!r}, "
                        f"portfolios={len(d.get('portfolios') or {})}",
                        entitlement="ours, public read")
        except Exception:                                            # noqa: BLE001
            return p.cannot(f"/{day}.json answered 200 with an unparseable body")
    if r_root["ok"] or r_root.get("code") in (403, 404):
        # The service answering at all is the liveness fact; a missing day is a
        # SEAL fact, not a connection fact, and must not be reported as a
        # connection failure.
        return p.ok(f"authority reachable (root {r_root.get('code')}); "
                    f"no book for {day} yet — that is a seal state, not a "
                    f"connection failure",
                    entitlement="ours, public read")
    return p.fail(r_root["class"] or CANNOT, f"root {r_root.get('code')}: "
                                             f"{str(r_root.get('why'))[:140]}")


def probe_alpaca_revoked() -> Probe:
    """The finance repo's OWN Alpaca keys — `ALPACA_API_KEY_ID` and
    `ALPACA_ARENA_API_KEY_ID`. Session 36 recorded these as REVOKED. This probe
    exists to CONFIRM that with a status code instead of a memory, and to state
    that `aegis-alpha-terminal/alpha/config.py::_FORBIDDEN_INHERITED` refuses to
    read either of them, so a revoked key here cannot reach a live book."""
    p = Probe("Alpaca (finance mirror/arena)", group="venue",
              why="the two key pairs session 36 recorded as revoked")
    pairs = (("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "mirror"),
             ("ALPACA_ARENA_API_KEY_ID", "ALPACA_ARENA_API_SECRET_KEY", "arena"))
    base = _env("ALPACA_PAPER_BASE") or "https://paper-api.alpaca.markets"
    results: dict[str, Any] = {}
    for kid, ksec, label in pairs:
        k, s = _env(kid), _env(ksec)
        if not (k and s):
            results[label] = {"class": ABSENT, "code": None,
                              "key_fingerprint": key_fp(k)}
            continue
        r = _record(p, f"{label} /v2/account", http(
            base + "/v2/account",
            headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}))
        results[label] = {"code": r.get("code"),
                          "class": (None if r["ok"] else (r.get("class") or CANNOT)),
                          "key_fingerprint": key_fp(k)}
    p.endpoints.append({"endpoint": "per-pair result", "pairs": results})
    live = [lab for lab, v in results.items() if v.get("code") == 200]
    rejected = [lab for lab, v in results.items()
                if v.get("code") in (401, 403)]
    if live:
        return p.fail(
            CANNOT,
            f"UNEXPECTED: {','.join(live)} still authenticate — session 36 "
            f"recorded them revoked. Re-check before believing either record.",
            entitlement="paper venue")
    if rejected and len(rejected) == len([v for v in results.values()
                                          if v.get("code") is not None]):
        return p.fail(AUTH,
                      f"{','.join(rejected)} rejected (401/403) — CONFIRMS the "
                      f"revocation. Neither is read by the terminal repo: "
                      f"alpha/config._FORBIDDEN_INHERITED refuses both names.",
                      entitlement="revoked")
    return p.cannot("neither pair produced a 200 or an auth refusal: "
                    + json.dumps({k: v.get("code") for k, v in results.items()}))


def probe_railway() -> Probe:
    """`railway status` for every service. Read-only; no deploy, no variable."""
    p = Probe("Railway (loving-elegance)", group="ours",
              why="is every fleet service Online / Failed / Sleeping")
    rail = shutil.which("railway") or shutil.which("railway.cmd") or shutil.which("railway.exe")
    if not rail:
        return p.cannot("railway CLI not on PATH")
    term = Path(os.environ.get("AAT_REPO", r"C:\Users\mrthn\aegis-alpha-terminal"))
    if not term.exists():
        return p.cannot(f"terminal repo not at {term} — `railway status` needs a "
                        f"linked project directory")
    t0 = time.perf_counter()
    try:
        # BYTES, not text=True. Railway prints status glyphs and a cp1252
        # console decoder raises UnicodeDecodeError inside subprocess's reader
        # THREAD, which surfaces as an empty stdout and a service list of zero
        # -- i.e. as "everything is fine, there is nothing here".
        r = subprocess.run([rail, "status"], cwd=str(term), capture_output=True,
                           timeout=180)
        stdout = r.stdout.decode("utf-8", "replace")
        stderr = r.stderr.decode("utf-8", "replace")
    except Exception as e:                                           # noqa: BLE001
        return p.cannot(f"railway status did not run: {type(e).__name__}: {e}")
    p.latency_ms = (time.perf_counter() - t0) * 1000
    if r.returncode != 0:
        return p.fail(NETWORK, (stderr or stdout).strip()[:200])
    services: dict[str, str] = {}
    for line in stdout.splitlines():
        s = line.strip()
        if not s.startswith("- "):
            continue
        name = s[2:].split(":", 1)[0].strip()
        low = s.lower()
        state = ("Online" if "online" in low else
                 "Failed" if "failed" in low else
                 "Sleeping" if "sleep" in low else
                 "Crashed" if "crash" in low else "UNKNOWN")
        services[name] = state
    p.endpoints.append({"endpoint": "railway status", "services": services})
    if not services:
        return p.cannot("railway status returned 0 but listed no services")
    bad = {k: v for k, v in services.items() if v != "Online"}
    note = ("; ".join(f"{k}={v}" for k, v in sorted(bad.items()))) or "all Online"
    # aat-loop-staging is EXPECTED to be Failed. Expected is not the same as ok
    # and it is not the same as a surprise: it is named so a reader does not
    # re-diagnose it every night.
    expected_failed = services.get("aat-loop-staging") == "Failed"
    unexpected = {k: v for k, v in bad.items() if k != "aat-loop-staging"}
    if unexpected:
        return p.fail(NETWORK, f"{len(unexpected)} service(s) not Online: {note}",
                      entitlement="ours")
    return p.ok(f"{len(services)} services; "
                + (f"aat-loop-staging=Failed (EXPECTED, and it is the only one)"
                   if expected_failed else "all Online"),
                entitlement="ours")


# ── registry ─────────────────────────────────────────────────────────────────

PROBES: dict[str, Callable[..., Probe]] = {
    "fred": probe_fred,
    "finnhub": probe_finnhub,
    "fmp": probe_fmp,
    "polygon": probe_polygon,
    "alpha_vantage": probe_alpha_vantage,
    "eodhd": probe_eodhd,
    "deepseek": probe_deepseek,
    "nvidia": probe_nvidia,
    "hf_router": probe_hf_router,
    "openai": probe_openai,
    "featherless": probe_featherless,
    "wrds": probe_wrds,
    "gdelt": probe_gdelt,
    "edgar": probe_edgar,
    "kalshi": probe_kalshi,
    "polymarket": probe_polymarket,
    "cboe": probe_cboe,
    "website": probe_website,
    "seal_authority": probe_seal_authority,
    "alpaca_revoked": probe_alpaca_revoked,
    "railway": probe_railway,
}

#: Probes that issue a PAID completion when `llm=True`.
LLM_PROBES = ("nvidia", "hf_router", "openai", "featherless")

#: The justification every paid probe here carries, in the shape the terminal's
#: `alpha/spend.justify()` demands (a decision verb, not a subject label). The
#: terminal-side twin of this script passes it through that gate; this repo has
#: no equivalent choke point, so it is stamped on the receipt instead of being
#: implied by the fact that somebody ran the script.
LLM_PROBE_WHY = (
    "Decides whether to KEEP or DELETE each LLM credential and whether the "
    "council may RANK a family in its provider order: a 5-token completion is "
    "the only evidence that separates a live key from a listed-but-unserved "
    "model, and a dead family must be dropped from the probe order rather than "
    "retried nightly.")


def run_checks(*, only: list[str] | None = None, llm: bool = True,
               workers: int = 6) -> dict[str, Any]:
    """Run every probe and return the receipt dict. The callable entry point.

    Nothing here schedules itself. A caller that wants this nightly registers
    it; this function only measures.
    """
    env_source = load_env()
    names = [n for n in PROBES if not only or n in only]
    started = datetime.now(timezone.utc)
    results: dict[str, Probe] = {}

    def _run(n: str) -> tuple[str, Probe]:
        fn = PROBES[n]
        try:
            return n, (fn(llm=llm) if n in LLM_PROBES else fn())
        except Exception as e:                                       # noqa: BLE001
            p = Probe(n, group="?", why="?")
            return n, p.cannot(f"probe raised {type(e).__name__}: {str(e)[:200]}")

    with _cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for n, p in ex.map(_run, names):
            results[n] = p

    rows = [results[n].as_dict() for n in names]
    by_class: dict[str, list[str]] = {}
    for r in rows:
        if r["failure_class"]:
            by_class.setdefault(r["failure_class"], []).append(r["provider"])
    return {
        "receipt": "LABOR-D1-CONNECTION-CHECK",
        "repo": "aegis-finance",
        "argv": sys.argv[1:],
        "env_source": env_source,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "llm_probes_enabled": llm,
        "llm_probes_issued": [n for n in names if n in LLM_PROBES] if llm else [],
        "llm_probe_max_output_tokens_each": 5,
        "why_this_call_can_change_a_decision": LLM_PROBE_WHY if llm else None,
        "counts": {
            "total": len(rows),
            "ok": sum(1 for r in rows if r["status"] == OK),
            "fail": sum(1 for r in rows if r["status"] == "FAIL"),
            "cannot_determine": sum(1 for r in rows
                                    if r["status"] == "CANNOT_DETERMINE"),
        },
        "failure_classes": by_class,
        "rows": rows,
    }


# ── D2: key inventory reconciliation ─────────────────────────────────────────
#
#     python -m scripts.connection_check --inventory OUT.json
#
# For every variable NAME in both repos' `.env` files: is it read in code, does
# the reading site look like a production caller, and what did its probe return?
# A key nobody reads is DEAD WEIGHT — it can leak and it buys nothing.
#
# NAMES AND LENGTHS ONLY. Each value is hashed the moment it is parsed and only
# the hash prefix is retained; no value is ever assigned to something printed.
# No `.env` file is moved, copied, renamed or edited (2026-08-24: a subshell
# that moved one aside lost every key on the machine).

#: Directories never walked: vendored code, build output, data trees.
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".next",
              ".pytest_cache", ".mypy_cache", "dist", "build", ".ruff_cache",
              "site-packages", ".claude", "data", "state"}
#: Extensions worth searching. A key name inside a parquet is not a caller.
_CODE_EXT = {".py", ".md", ".yml", ".yaml", ".toml", ".cfg", ".sh", ".ps1",
             ".txt", ".ini", ".example"}

#: env var -> the probe whose result answers "does this credential still work".
VAR_TO_PROBE: dict[str, str | None] = {
    "FRED_API_KEY": "fred", "AAT_FRED_API_KEY": "fred",
    "FINNHUB_API_KEY": "finnhub", "AAT_FINNHUB_API_KEY": "finnhub",
    "FMP_API_KEY": "fmp", "POLYGON_API_KEY": "polygon",
    "ALPHA_VANTAGE_API_KEY": "alpha_vantage", "EODHD_API_TOKEN": "eodhd",
    "DEEPSEEK_API_KEY": "deepseek", "AAT_DEEPSEEK_API_KEY": "deepseek",
    "NVIDIA_API_KEY": "nvidia", "AAT_NVIDIA_API_KEY": "nvidia",
    "HF_TOKEN": "hf_router", "AAT_HF_TOKEN": "hf_router",
    "GTP_TOKEN": "openai", "AAT_OPENAI_API_KEY": "openai",
    "AAT_FEATHERLESS_API_KEY": "featherless",
    "ALPACA_API_KEY_ID": "alpaca_revoked", "ALPACA_API_SECRET_KEY": "alpaca_revoked",
    "ALPACA_ARENA_API_KEY_ID": "alpaca_revoked",
    "ALPACA_ARENA_API_SECRET_KEY": "alpaca_revoked",
}

#: probe key -> the provider display names a row may carry, across both repos'
#: receipts, so a variable can be joined to a measured result.
_PROBE_DISPLAY: dict[str, tuple[str, ...]] = {
    "fred": ("FRED", "FRED (AAT key)"),
    "finnhub": ("Finnhub", "Finnhub (AAT key)"),
    "fmp": ("FMP",), "polygon": ("Polygon",), "alpha_vantage": ("AlphaVantage",),
    "eodhd": ("EODHD",), "deepseek": ("DeepSeek",), "nvidia": ("NVIDIA NIM",),
    "hf_router": ("HF router",), "openai": ("OpenAI",),
    "featherless": ("Featherless",),
    "alpaca_revoked": ("Alpaca (finance mirror/arena)",),
}


def _env_names(path: Path) -> dict[str, dict[str, Any]]:
    """NAMES, LENGTHS and FINGERPRINTS from one `.env`. Never a value.

    The fingerprint exists so "is the terminal's DeepSeek key the same object
    as the finance one" is answerable by COMPARISON rather than by looking.
    """
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("'\"")
        if name:
            out[name] = {"length": len(value), "empty": not value,
                         "fingerprint": key_fp(value)}
    return out


def _references(repos: dict[str, Path], names: list[str]) -> dict[str, list[str]]:
    """`repo:file:line` for every literal occurrence of each name."""
    hits: dict[str, list[str]] = {n: [] for n in names}
    for tag, root in repos.items():
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if fn.startswith(".env") and fn != ".env.example":
                    continue          # a real .env is never opened for content
                if Path(fn).suffix not in _CODE_EXT:
                    continue
                fp = Path(dirpath) / fn
                # A PROBE IS NOT A CALLER. This file names variables in its own
                # comments and in `VAR_TO_PROBE`; counting those made
                # `AAT_HACK4_KEY_ID` read as READ_IN_CODE because a comment
                # ABOUT it being invisible to grep was itself grep-visible.
                if fp.name == "connection_check.py":
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                present = [n for n in names if n in text]
                if not present:
                    continue
                rel = fp.relative_to(root).as_posix()
                for i, line in enumerate(text.splitlines(), 1):
                    for n in present:
                        if n in line and len(hits[n]) < 40:
                            hits[n].append(f"{tag}:{rel}:{i}")
    return hits


#: Names that NO literal grep can find, because code builds them at runtime.
#:
#: `alpha/config.py::credentials` does `os.getenv(f"{prefix}_KEY_ID")` with
#: `prefix = f"AAT_{role.upper()}"`, so `AAT_HACK4_KEY_ID` appears nowhere in
#: the source and is read on every single order pass. A grep-only inventory
#: reports all twelve fleet credentials as DEAD WEIGHT — and the action that
#: verdict invites is "delete them", which would disarm the entire fleet.
#:
#: Each entry is (regex, the suffix literal that must exist in code for the
#: claim to hold, a human reason). The rule is only applied when that literal
#: is actually found, so this is a DERIVED classification, not an exemption
#: list that keeps asserting itself after the code changes.
_CONSTRUCTED_NAME_RULES: tuple[tuple[str, str, str], ...] = (
    (r"^AAT_[A-Z0-9]+_KEY_ID$", '"_KEY_ID"',
     "alpha/config.py::credentials builds AAT_<ROLE>_KEY_ID from the role"),
    (r"^AAT_[A-Z0-9]+_SECRET_KEY$", '"_SECRET_KEY"',
     "alpha/config.py::credentials builds AAT_<ROLE>_SECRET_KEY from the role"),
)


def _constructed_name_evidence(name: str, repos: dict[str, Path]) -> str | None:
    """Is `name` built at runtime rather than written literally? Evidence, or None."""
    import re as _re
    for pattern, literal, reason in _CONSTRUCTED_NAME_RULES:
        if not _re.match(pattern, name):
            continue
        for tag, root in repos.items():
            for rel in ("alpha/config.py", "alpha/arms.py", "backend/config.py"):
                fp = root / rel
                if not fp.exists():
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if literal.strip('"') in line and "getenv" in line:
                        return f"{reason} ({tag}:{rel}:{i})"
    return None


def _classify_refs(refs: list[str]) -> str:
    """WHERE a name is referenced decides whether it has a production caller."""
    if not refs:
        return "UNREFERENCED"

    def kind(r: str) -> str:
        _tag, rel, _line = r.split(":", 2)
        low = rel.lower()
        if low.startswith(("tests", "backend/tests")) or "/tests/" in low \
                or Path(low).name.startswith(("test_", "tests_")):
            return "test"
        if low.endswith(".md") or low.startswith("docs/"):
            return "doc"
        if ".example" in low:
            return "template"
        return "code"

    kinds = {kind(r) for r in refs}
    for k, label in (("code", "READ_IN_CODE"), ("test", "TESTS_ONLY"),
                     ("template", "TEMPLATE_ONLY")):
        if k in kinds:
            return label
    return "DOCS_ONLY"


def inventory(*, probe_receipts: list[Path] | None = None) -> dict[str, Any]:
    """The D2 reconciliation: every env NAME -> read? -> caller? -> probe result."""
    repos = {"finance": REPO,
             "terminal": Path(os.environ.get(
                 "AAT_REPO", r"C:\Users\mrthn\aegis-alpha-terminal"))}
    env_files = {"finance": REPO / ".env", "terminal": repos["terminal"] / ".env"}
    per_file = {tag: _env_names(p) for tag, p in env_files.items()}
    names = sorted({n for d in per_file.values() for n in d})

    probes: dict[str, dict[str, Any]] = {}
    for rp in (probe_receipts or []):
        if not rp.exists():
            continue
        try:
            for row in json.loads(rp.read_text(encoding="utf-8")).get("rows", []):
                prev = probes.get(row["provider"])
                # An `ok` from EITHER repo wins over a FAIL from the other: the
                # finance twin reports Featherless `absent` because the key
                # lives in the terminal's .env, and the terminal twin reports it
                # serving a completion. Both are true; only one is the answer to
                # "does this credential work".
                if prev is None or (prev["status"] != OK and row["status"] == OK):
                    probes[row["provider"]] = row
        except Exception:                                            # noqa: BLE001
            continue

    refs = _references(repos, names)
    rows: list[dict[str, Any]] = []
    for n in names:
        where = {t: per_file[t].get(n) for t in per_file}
        fps = {t: v["fingerprint"] for t, v in where.items() if v}
        distinct = {v for v in fps.values() if v}
        probe_row = None
        for disp in _PROBE_DISPLAY.get(VAR_TO_PROBE.get(n) or "", ()):
            if disp in probes:
                probe_row = probes[disp]
                break
        ref_class = _classify_refs(refs[n])
        constructed = None
        if ref_class in ("UNREFERENCED", "TESTS_ONLY", "DOCS_ONLY"):
            constructed = _constructed_name_evidence(n, repos)
            if constructed:
                ref_class = "READ_VIA_CONSTRUCTED_NAME"
        empty = any(v["empty"] for v in where.values() if v)
        # A key is DEAD WEIGHT when it exists and nothing reads it. It is a dead
        # KEY only when a probe refused it everywhere. The two get different
        # actions from Murat (delete vs re-mint) so they get different words.
        if empty:
            verdict = "EMPTY_VALUE"
        elif ref_class == "UNREFERENCED":
            verdict = "DEAD_WEIGHT: present in .env, referenced nowhere"
        elif ref_class in ("DOCS_ONLY", "TEMPLATE_ONLY"):
            verdict = f"DEAD_WEIGHT: referenced only in {ref_class.lower()}"
        elif ref_class == "TESTS_ONLY":
            verdict = "TESTS_ONLY: no production caller"
        elif ref_class == "READ_VIA_CONSTRUCTED_NAME":
            verdict = "LIVE_AND_USED (name built at runtime; DO NOT DELETE)"
        elif probe_row is None:
            verdict = "READ_IN_CODE, NOT PROBED (no provider probe covers it)"
        elif probe_row["status"] == OK:
            verdict = "LIVE_AND_USED"
        elif probe_row["failure_class"] in (AUTH, DEAD_KEY):
            verdict = f"REFUSED BY PROVIDER ({probe_row['failure_class']})"
        else:
            verdict = (f"READ_IN_CODE, probe {probe_row['status']} "
                       f"({probe_row['failure_class']})")
        rows.append({
            "name": n,
            "in_env": [t for t, v in where.items() if v],
            "lengths": {t: v["length"] for t, v in where.items() if v},
            "fingerprints": fps,
            "same_object_across_repos": (len(distinct) == 1 if len(fps) > 1 else None),
            "reference_class": ref_class,
            "constructed_name_evidence": constructed,
            "reference_count": len(refs[n]),
            "references_sample": refs[n][:6],
            "probe": (probe_row or {}).get("provider"),
            "probe_status": (probe_row or {}).get("status"),
            "probe_failure_class": (probe_row or {}).get("failure_class"),
            "verdict": verdict,
        })
    # THE SAME CREDENTIAL UNDER TWO NAMES. The two repos deliberately do not
    # share variable names (`alpha/config._FORBIDDEN_INHERITED` refuses the
    # parent project's Alpaca names outright), so the useful question is not
    # "does this NAME appear twice" but "is the object behind
    # `DEEPSEEK_API_KEY` here the object behind `AAT_DEEPSEEK_API_KEY` there".
    # Fingerprints answer it without either value being seen.
    pairs = [("FRED_API_KEY", "AAT_FRED_API_KEY"),
             ("FINNHUB_API_KEY", "AAT_FINNHUB_API_KEY"),
             ("DEEPSEEK_API_KEY", "AAT_DEEPSEEK_API_KEY"),
             ("NVIDIA_API_KEY", "AAT_NVIDIA_API_KEY"),
             ("HF_TOKEN", "AAT_HF_TOKEN"),
             ("GTP_TOKEN", "AAT_OPENAI_API_KEY")]
    cross = []
    for fin, term in pairs:
        a = (per_file["finance"].get(fin) or {}).get("fingerprint")
        b = (per_file["terminal"].get(term) or {}).get("fingerprint")
        cross.append({"finance": fin, "terminal": term,
                      "finance_fingerprint": a, "terminal_fingerprint": b,
                      "same_object": (a == b) if (a and b) else None})

    return {
        "receipt": "LABOR-D2-KEY-INVENTORY",
        "at": datetime.now(timezone.utc).isoformat(),
        "method": ("NAMES AND LENGTHS ONLY. Values are hashed at parse time and "
                   "only an 8-hex prefix is retained. No .env file was moved, "
                   "copied, renamed or edited."),
        "env_files": {t: {"path": str(p), "exists": p.exists(),
                          "names": len(per_file[t])} for t, p in env_files.items()},
        "probe_receipts": [str(p) for p in (probe_receipts or []) if p.exists()],
        "counts": {"names": len(rows)},
        "dead_weight": [r["name"] for r in rows
                        if r["verdict"].startswith("DEAD_WEIGHT")],
        "empty": [r["name"] for r in rows if r["verdict"] == "EMPTY_VALUE"],
        "refused": [r["name"] for r in rows if r["verdict"].startswith("REFUSED")],
        "cross_repo_key_pairs": cross,
        "shared_across_repos": [r["name"] for r in rows
                                if r["same_object_across_repos"] is True],
        "same_name_different_object": [r["name"] for r in rows
                                       if r["same_object_across_repos"] is False],
        "rows": rows,
    }


def to_markdown(receipt: dict[str, Any]) -> str:
    """The table the handoff prints. No key, no fingerprint, no URL query."""
    out = ["| provider | status | latency | entitlement | failure class |",
           "|---|---|---|---|---|"]
    for r in receipt["rows"]:
        ms = "-" if r["latency_ms"] is None else f"{r['latency_ms']:.0f} ms"
        ent = (r["entitlement"] or "unknown").replace("|", "/")[:110]
        fc = r["failure_class"] or "-"
        out.append(f"| {r['provider']} | {r['status']} | {ms} | {ent} | {fc} |")
    c = receipt["counts"]
    out.append("")
    out.append(f"{c['ok']} ok · {c['fail']} FAIL · "
               f"{c['cannot_determine']} CANNOT DETERMINE of {c['total']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", nargs="?", const="-", default=None,
                    metavar="PATH", help="emit the receipt JSON (default stdout)")
    ap.add_argument("--markdown", nargs="?", const="-", default=None,
                    metavar="PATH", help="emit the Markdown table")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip every PAID completion (model lists still probed)")
    ap.add_argument("--only", default="",
                    help="comma-separated probe names: " + ",".join(PROBES))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--inventory", nargs="?", const="-", default=None,
                    metavar="PATH",
                    help="D2 key inventory reconciliation instead of probing")
    ap.add_argument("--from-receipts", default="",
                    help="comma-separated D1 receipt JSONs to join probe "
                         "results onto the inventory")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                            # noqa: BLE001
            pass
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None
    if only:
        unknown = [x for x in only if x not in PROBES]
        if unknown:
            ap.error(f"unknown probe(s): {unknown}; known: {sorted(PROBES)}")

    if a.inventory:
        load_env()
        recs = [Path(x.strip()) for x in a.from_receipts.split(",") if x.strip()]
        inv = inventory(probe_receipts=recs)
        blob = json.dumps(inv, indent=1, sort_keys=True, default=str)
        if a.inventory == "-":
            print(blob)
        else:
            Path(a.inventory).parent.mkdir(parents=True, exist_ok=True)
            Path(a.inventory).write_text(blob + "\n", encoding="utf-8")
            print(f"inventory -> {a.inventory}")
        print(f"  {inv['counts']['names']} names · "
              f"{len(inv['dead_weight'])} dead weight · "
              f"{len(inv['empty'])} empty · {len(inv['refused'])} refused")
        return 0

    rec = run_checks(only=only, llm=not a.no_llm, workers=a.workers)

    if a.json is None and a.markdown is None:
        print(to_markdown(rec))
        print()
        for r in rec["rows"]:
            if r["status"] != OK:
                print(f"  {r['status']:<17} {r['provider']:<30} "
                      f"[{r['failure_class']}] {r['detail'][:140]}")
    if a.json:
        blob = json.dumps(rec, indent=1, sort_keys=True, default=str)
        if a.json == "-":
            print(blob)
        else:
            Path(a.json).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json).write_text(blob + "\n", encoding="utf-8")
            print(f"receipt -> {a.json}")
    if a.markdown:
        md = to_markdown(rec)
        if a.markdown == "-":
            print(md)
        else:
            Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(a.markdown).write_text(md + "\n", encoding="utf-8")
            print(f"table -> {a.markdown}")
    # Exit non-zero only on a hard FAIL. CANNOT_DETERMINE is a finding to read,
    # not a broken build — a gate that goes red for "did not look" teaches the
    # reader to skim red lines.
    return 1 if rec["counts"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
