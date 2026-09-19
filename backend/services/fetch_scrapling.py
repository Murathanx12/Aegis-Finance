"""Scrapling's stealthy fetcher, behind ONE boxed adapter. Chunk 20, T1.

    from backend.services import fetch_scrapling
    res = fetch_scrapling.fetch(url, budget_s=45.0)
    res["status"], res["html"], res["text"], res["final_url"], res["refused"]

WHY AN ADAPTER AND NOT A DIRECT CALL
====================================
`docs/research_notes/2026-09-19/research_external_repos_round4.md` §6 rates
Scrapling **ATTACH_NOW** (BSD-3-Clause, 180 KB core, actively maintained) for
one named live failure: the insider collector 403s on 100% of production
fetches while twelve unit tests stay green. A stealthy fetcher is a direct
answer to that failure class — and it is also a second network door, which is
the thing lane N spent a week making singular. So it arrives as ONE function,
with the same three disciplines every other fetch in this repo has:

1. **A HARD WALL-CLOCK BOX.** `scripts.news_pull.call_with_timeout` is reused
   rather than re-derived: a third-party session's own `timeout=` bounds an
   operation and not the call, which this repo paid for twice — five minutes on
   one ESTABLISHED socket to Yahoo (2026-09-11) and a two-hour TLS handshake to
   Alpaca (2026-09-13). Scrapling drives a real browser, so it has strictly
   more ways to sit still than urllib does.
2. **AT MOST ONE RETRY.** Two attempts, sharing ONE deadline. A browser fetch
   costs seconds, and a retry loop behind a stealth layer is how a polite
   crawler becomes an impolite one without anybody choosing to.
3. **EVERY OUTCOME IS A NAMED REFUSAL, never an exception past this function.**
   `news_pull`'s rule 2: a source is refused BY NAME and the run continues.

WHAT IT IS NOT FOR
==================
It is not a discovery path. `backend/services/news_registry.py` still refuses
an id that is not in the registry, and a row reaches the stealthy fetcher only
because its own registry row says `fetcher: scrapling` — a deliberate
per-source edit, never a blanket swap (the recipe's own condition, §6). A
scraped page gets no exemption from invariant 20 either: its `pit_grade` is
whatever its registry row declares, and `index_state` still forbids labelling.

THE INSTALL, AND THE ONE CONFLICT IT CREATED
============================================
`pip install "scrapling[fetchers]"` — 0.4.15 as installed 2026-09-19, pinned in
`backend/requirements.txt`. The `fetchers` extra carries `curl_cffi>=0.16.1`,
and the LOCALLY installed `yfinance 1.2.0` declares `curl_cffi<0.14`; the
install moved curl_cffi 0.13.0 -> 0.16.3 and pip printed that conflict. It was
checked rather than assumed: `yfinance 1.7.0` — what CI's unpinned
`yfinance>=0.2.36` actually resolves to — requires `curl_cffi>=0.15`, so the
conflict is a STALE LOCAL PIN and not a CI conflict, and one live call on the
new pair returned 10 news rows and 5 daily bars. The browser binaries
(`scrapling install`) are a BY-HAND step and are deliberately not fetched here:
no test may need them, and a runtime download inside a fetch is a fetch that
does something else first.

LICENCE: PRODUCT_EXPERIMENT. This writes no row, labels nothing, ranks nothing.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any, Callable

#: The name that reaches a receipt and a corpus row. One string, one place.
FETCHER_NAME = "scrapling"

#: Default wall-clock box for ONE call, seconds. A browser fetch is seconds,
#: not milliseconds; 45 s is generous for a page and short enough that a
#: 26-source sweep cannot be held up by one wedged site.
DEFAULT_BUDGET_S = 45.0

#: Below this many seconds left on the deadline, the retry is NOT attempted:
#: starting a browser fetch with two seconds of budget buys a timeout, not a
#: page.
MIN_RETRY_BUDGET_S = 5.0

#: Attempts per call, TOTAL. One retry means two attempts. Not configurable on
#: purpose — see the module docstring.
MAX_ATTEMPTS = 2

#: Every refusal this adapter can return, by name. A caller matches on these
#: strings; nothing here ever raises past `fetch`.
REFUSALS = (
    "SCRAPLING_NOT_INSTALLED",
    "SCRAPLING_FETCHERS_NOT_INSTALLED",
    "SCRAPLING_NO_URL",
    "SCRAPLING_TIMEOUT",
    "SCRAPLING_FETCH_FAILED",
)


def _empty(url: str = "") -> dict:
    return {"fetcher": FETCHER_NAME, "url": url, "final_url": "", "status": None,
            "text": "", "html": "", "elapsed_s": 0.0, "attempts": 0,
            "refused": "", "detail": ""}


def resolve_fetcher() -> tuple[Callable[..., Any] | None, str, str]:
    """`(StealthyFetcher.fetch, "", "")`, or `(None, REFUSAL_NAME, detail)`.

    The two import failures are DIFFERENT facts and are named differently:
    `scrapling` absent is "the dependency was never installed"; `scrapling`
    present with `scrapling.fetchers` unimportable is "the core is installed
    and the `[fetchers]` extra is not" — which is a one-line fix and would be
    indistinguishable from the first under one refusal name.
    """
    try:
        import scrapling  # noqa: F401
    except Exception as exc:                                       # noqa: BLE001
        return None, "SCRAPLING_NOT_INSTALLED", f"{type(exc).__name__}: {exc}"
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as exc:                                       # noqa: BLE001
        return (None, "SCRAPLING_FETCHERS_NOT_INSTALLED",
                f"{type(exc).__name__}: {exc} — `pip install \"scrapling[fetchers]\"`")
    return StealthyFetcher.fetch, "", ""


def available() -> dict:
    """Is the stealthy path usable RIGHT NOW, and if not, which refusal.

    Printed on a receipt. Never a bare boolean: "not available" and "available
    but the browser binaries were never downloaded" are answered by different
    people.
    """
    fn, refusal, detail = resolve_fetcher()
    version = ""
    try:
        import scrapling
        version = str(getattr(scrapling, "__version__", "") or "")
    except Exception:                                              # noqa: BLE001
        pass
    return {"fetcher": FETCHER_NAME, "available": fn is not None,
            "refused": refusal, "detail": detail, "version": version,
            "browser_binaries": ("`scrapling install` is a BY-HAND step; this "
                                 "adapter never downloads one at fetch time")}


def _decode(body: Any, encoding: str = "") -> str:
    """Bytes to text, UTF-8 first and cp1252 second, never an exception.

    EDGAR's exhibit documents are frequently cp1252 (smart quotes, en dashes)
    served without a charset, and `errors="replace"` on UTF-8 turns every one
    of them into a replacement character — readable, and wrong in exactly the
    characters a quotation lands on.
    """
    if isinstance(body, str):
        return body
    if not isinstance(body, (bytes, bytearray)):
        return "" if body is None else str(body)
    for enc in ([encoding] if encoding else []) + ["utf-8", "cp1252"]:
        try:
            return bytes(body).decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return bytes(body).decode("utf-8", "replace")


def _unpack(page: Any, url: str) -> dict:
    """One Scrapling `Response` into the adapter's flat dict.

    Every attribute is read defensively: `Response` is a third-party class and
    an adapter that raises while reading a successful reply is a fetcher that
    reports failure for pages it actually got.
    """
    out = _empty(url)
    status = getattr(page, "status", None)
    out["status"] = int(status) if isinstance(status, (int, float)) else None
    out["final_url"] = str(getattr(page, "url", "") or url)
    encoding = str(getattr(page, "encoding", "") or "")
    html = getattr(page, "html_content", None)
    if html is None:
        html = getattr(page, "body", None)
    out["html"] = _decode(html, encoding)
    text = ""
    getter = getattr(page, "get_all_text", None)
    if callable(getter):
        try:
            text = str(getter() or "")
        except Exception:                                          # noqa: BLE001
            text = ""
    if not text:
        text = str(getattr(page, "text", "") or "")
    out["text"] = " ".join(text.split())
    return out


def fetch(url: str, *, budget_s: float = DEFAULT_BUDGET_S,
          fetcher: Callable[..., Any] | None = None,
          headless: bool = True, extra: dict | None = None) -> dict:
    """One page through Scrapling's stealthy fetcher. Never raises.

    Returns `{fetcher, url, final_url, status, text, html, elapsed_s, attempts,
    refused, detail}`. `refused` is `""` on success and one of `REFUSALS`
    otherwise; `status` is None whenever `refused` is set, because a refusal
    that also carried a plausible status code would be read as a page.

    `fetcher` is injectable so every test drives this without a browser, a
    socket or the `[fetchers]` extra — the same seam `hiring_pull._fetch` has.
    """
    out = _empty(str(url or ""))
    if not str(url or "").strip():
        out["refused"] = "SCRAPLING_NO_URL"
        out["detail"] = "fetch() was handed an empty url; there is nothing to ask for"
        return out

    if fetcher is None:
        fetcher, refusal, detail = resolve_fetcher()
        if fetcher is None:
            out["refused"] = refusal
            out["detail"] = detail
            return out

    # The box is imported here, not at module import: `scripts.news_pull`
    # imports THIS module at its top level, and a module-level import back
    # would be a cycle.
    from scripts.news_pull import CallTimeout, call_with_timeout

    host = urllib.parse.urlsplit(str(url)).netloc or "?"
    t0 = time.monotonic()
    deadline = t0 + max(1.0, float(budget_s))
    kwargs: dict = {"headless": bool(headless)}
    kwargs.update(dict(extra or {}))
    last = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            out["attempts"] = attempt - 1
            out["refused"] = "SCRAPLING_TIMEOUT"
            out["detail"] = (f"the {budget_s:.0f}s wall-clock box was spent before "
                             f"attempt {attempt} to {host}")
            out["elapsed_s"] = round(time.monotonic() - t0, 2)
            return out
        out["attempts"] = attempt
        call = dict(kwargs)
        # Scrapling's own `timeout` is milliseconds (Playwright's unit). It is
        # a HINT: the box below is what actually ends the call.
        call.setdefault("timeout", int(max(1.0, remaining) * 1000))
        try:
            page = call_with_timeout(lambda: fetcher(str(url), **call),   # noqa: B023
                                     remaining, f"{FETCHER_NAME} {host}")
        except CallTimeout as exc:
            last = str(exc)
            out["refused"] = "SCRAPLING_TIMEOUT"
            out["detail"] = last
            break
        except Exception as exc:                                   # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            out["refused"] = "SCRAPLING_FETCH_FAILED"
            out["detail"] = last
            if (deadline - time.monotonic()) < MIN_RETRY_BUDGET_S:
                break
            continue
        got = _unpack(page, str(url))
        got["attempts"] = attempt
        got["elapsed_s"] = round(time.monotonic() - t0, 2)
        return got
    out["elapsed_s"] = round(time.monotonic() - t0, 2)
    out["detail"] = (f"{out['detail']} (attempts: {out['attempts']} of "
                     f"{MAX_ATTEMPTS}; one retry is the maximum)")
    return out


def declaration() -> dict:
    """What a receipt prints about this adapter. Names, never a URL's content."""
    return {
        "fetcher": FETCHER_NAME,
        "library": "Scrapling (D4Vinci/Scrapling), BSD-3-Clause",
        "entry_point": "scrapling.fetchers.StealthyFetcher.fetch",
        "wall_clock_box_s": DEFAULT_BUDGET_S,
        "max_attempts": MAX_ATTEMPTS,
        "refusals": list(REFUSALS),
        "box": ("scripts.news_pull.call_with_timeout — the same daemon-thread "
                "box every other third-party call in lane N runs inside"),
        "not_a_discovery_path": (
            "a source reaches this adapter only because its own registry row "
            "says `fetcher: scrapling`. news_registry still refuses an id that "
            "is not in the file, and pit_grade is unchanged by how a page was "
            "fetched"),
        "availability": available(),
    }


__all__ = ["DEFAULT_BUDGET_S", "FETCHER_NAME", "MAX_ATTEMPTS", "REFUSALS",
           "available", "declaration", "fetch", "resolve_fetcher"]
