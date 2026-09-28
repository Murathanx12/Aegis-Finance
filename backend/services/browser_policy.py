"""The owner's standing rules for the research browser, as refusals by name.

Murat, 2026-09-28: "dont use any payments, dont send any messages or emails
without asking me, use muratclaw mainly". And on the social hosts he added the
same day ("reddit x and other socials are logged in too"): READ, never act.

This module is PURE (no I/O, no browser). `openclaw_client` calls it before
every action on BOTH transports (the CLI and `POST /tools/invoke`), so a rule
here cannot be skipped by choosing a route. Each function returns a refusal
string (`REFUSED_<NAME>: ...`) or None; the caller raises it.

THE THREE RULES
===============
1. NO PAYMENTS. A click whose accessible name reads like paying, buying,
   ordering, subscribing, upgrading, billing or adding a card refuses
   (`REFUSED_PAYMENT_ACTION`); a navigation or open whose URL is a checkout /
   billing / payment path, or a store / checkout / billing subdomain, refuses
   (`REFUSED_PAYMENT_URL`).
2. NO MESSAGES OR EMAILS. A click whose name reads like send, post, reply,
   comment, follow, like, share, repost, vote, join or message refuses
   (`REFUSED_MESSAGE_ACTION`); a mail / messenger host or a DM path refuses
   (`REFUSED_MESSAGE_URL`). Typing is not a verb this browser has at all.
3. READ-ONLY. The browser navigates, scrolls (scroll keys only -- Enter can
   submit a form: `REFUSED_PRESS_KEY`), snapshots, reads text, opens a link,
   closes its own tab. A click is allowed only on a LINK this process saw in
   its own latest snapshot of that tab (`REFUSED_CLICK_UNSEEN_REF`,
   `REFUSED_CLICK_ROLE`), and never on a social host (`REFUSED_SOCIAL_CLICK`):
   there, a search is a navigation to a search URL.

Brokerage, bank and payment HOSTS stay refused in `openclaw_client.
DENIED_DOMAINS` (Murat asked on 2026-09-28 that the agent "can login to alpaca
anything"; the orchestrator declined and he agreed: "u are right dont give
alpaca or brokers to openclaw"). The broker is reached only through
`pc_broker`'s API path.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

#: Accessible-name patterns. Word-bounded so "Share Buyback" in a headline is
#: caught by the MESSAGE rule's "share" (a click on it is refused; the reader
#: then NAVIGATES to the link's URL instead, which the URL rule judges).
PAYMENT_TEXT = re.compile(
    r"\b(pay(ment|ments|pal)?|checkout|check\s*out|purchase|buy|order(s)?|"
    r"subscribe|subscription|upgrade|billing|add\s+(a\s+)?card|credit\s+card|"
    r"debit\s+card|wallet|donate|renew|start\s+(your\s+)?(free\s+)?trial|"
    r"free\s+trial|pricing|plans?\s+&\s+pricing|cart)\b", re.I)
MESSAGE_TEXT = re.compile(
    r"\b(send|post|reply|replies|comment|comments|follow|unfollow|like|unlike|"
    r"share|repost|retweet|quote|vote|upvote|downvote|join|message|messages|dm|"
    r"chat|email|e-mail|invite|publish|submit|tweet|compose|write)\b", re.I)
#: Account actions that are neither money nor messages but still change state.
ACCOUNT_TEXT = re.compile(
    r"\b(sign\s*(out|in|up)|log\s*(out|in)|register|delete|remove|block|mute|"
    r"report|settings|save|bookmark)\b", re.I)

#: Whole path SEGMENTS (not substrings: `/stocks-to-buy-now-1a2b` is an article).
PAYMENT_PATH = re.compile(
    r"(^|/)(checkout|billing|payment|payments|pay|purchase|subscribe|subscription|"
    r"subscriptions|upgrade|order|orders|cart|buy|add-card|addcard|wallet|"
    r"premium|pricing|donate)(/|$)", re.I)
#: Host LABELS that mean a store, a checkout or an account's billing.
PAYMENT_HOST_LABELS = frozenset({"store", "shop", "buy", "checkout", "billing", "pay",
                                 "payments", "subscribe", "customercenter", "commerce",
                                 "cart", "premium"})

#: Messaging hosts, and DM paths on otherwise-allowed hosts.
MESSAGE_HOSTS: tuple[str, ...] = ("mail.google.com", "gmail.com", "outlook.live.com",
                                  "outlook.office.com", "web.whatsapp.com", "messenger.com",
                                  "web.telegram.org", "discord.com", "chat.reddit.com")
MESSAGE_PATH = re.compile(r"(^|/)(messages|message|compose|inbox|chat|dm|i/chat)(/|$)",
                          re.I)
#: Social write paths reachable by URL (x.com/intent/tweet, /submit, /compose).
SOCIAL_WRITE_PATH = re.compile(r"(^|/)(intent|submit|compose|share|settings)(/|$)", re.I)

#: Keys that scroll. Anything else (Enter, Space-on-a-button, Tab, letters)
#: can submit, toggle or type, and is refused.
SCROLL_KEYS: frozenset[str] = frozenset({"PageDown", "PageUp", "ArrowDown", "ArrowUp",
                                         "Home", "End"})

#: Roles a click may land on: a LINK. Everything else is a control.
CLICKABLE_ROLES: frozenset[str] = frozenset({"link"})


def _host(url: str) -> str:
    try:
        return (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""


def on_hosts(url: str, hosts: tuple[str, ...]) -> bool:
    h = _host(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in hosts)


def url_refusal(url: str) -> str | None:
    """REFUSED_PAYMENT_URL / REFUSED_MESSAGE_URL / REFUSED_SOCIAL_WRITE_URL, or
    None. Applied to every navigate / open / click destination."""
    if not url or url == "about:blank":
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return f"REFUSED_URL_UNPARSEABLE: {url!r}"
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    labels = set(host.split("."))
    if labels & PAYMENT_HOST_LABELS or PAYMENT_PATH.search(path):
        return (f"REFUSED_PAYMENT_URL: {url!r} is a store / checkout / billing / payment "
                f"address. Murat, 2026-09-28: \"dont use any payments\".")
    if any(host == m or host.endswith("." + m) for m in MESSAGE_HOSTS) \
            or MESSAGE_PATH.search(path):
        return (f"REFUSED_MESSAGE_URL: {url!r} is a mail / message address. Murat, "
                f"2026-09-28: \"dont send any messages or emails without asking me\".")
    return None


def social_url_refusal(url: str, social_hosts: tuple[str, ...]) -> str | None:
    """On a social host, a write path (intent/submit/compose/share/settings)
    refuses even by URL: posting there needs no typing if the URL pre-fills."""
    if on_hosts(url, social_hosts):
        try:
            path = urlsplit(url).path or "/"
        except ValueError:
            return f"REFUSED_URL_UNPARSEABLE: {url!r}"
        if SOCIAL_WRITE_PATH.search(path):
            return (f"REFUSED_SOCIAL_WRITE_URL: {url!r} is a write path on a social "
                    f"host; the social hosts are READ-ONLY (2026-09-28).")
    return None


def text_refusal(name: str) -> str | None:
    """A control / link NAME that reads like paying, messaging or an account
    action refuses."""
    n = name or ""
    if PAYMENT_TEXT.search(n):
        return (f"REFUSED_PAYMENT_ACTION: {n[:80]!r} reads like a payment / purchase / "
                f"subscription action. Murat, 2026-09-28: \"dont use any payments\".")
    if MESSAGE_TEXT.search(n):
        return (f"REFUSED_MESSAGE_ACTION: {n[:80]!r} reads like sending, posting or "
                f"reacting. Murat, 2026-09-28: \"dont send any messages or emails "
                f"without asking me\".")
    if ACCOUNT_TEXT.search(n):
        return f"REFUSED_ACCOUNT_ACTION: {n[:80]!r} reads like an account action."
    return None


def press_refusal(keys: list[str]) -> str | None:
    """Only scroll keys. `Enter` submits a focused form or follows a focused
    control; `Space` activates a focused button."""
    bad = [k for k in keys if k not in SCROLL_KEYS]
    if not keys or bad:
        return (f"REFUSED_PRESS_KEY: {bad or keys!r} -- the research browser presses "
                f"scroll keys only {sorted(SCROLL_KEYS)} (read-only, 2026-09-28).")
    return None


# ── snapshots: both shapes ───────────────────────────────────────────────────
# chrome-mcp (the old `user` profile) printed the tree and then a `Links:`
# appendix of `N. text -> url`. The attach profile (openclaw driver, Playwright,
# 2026-09-28) prints each link's URL INLINE: `- link "WSJ" [ref=e203]
# [url=https://...]` and has no appendix. A parser that only knew the appendix
# returned 0 links on every page of the new driver.

_NODE = re.compile(r'^\s*-\s+(\w+)\s+"((?:[^"\\]|\\.)*)"(.*)$')
_REF = re.compile(r"\[ref=([^\]]+)\]")
_URL = re.compile(r"\[url=([^\]\s]+)\]")
_APPENDIX_LINK = re.compile(r"^\s*\d+\.\s+(.*?)\s+->\s+(\S+)\s*$")


def parse_snapshot(text: str) -> dict:
    """`{nodes: [{role, name, ref, url}], links: [{text, url, ref}]}` from either
    snapshot shape. `links` holds appendix rows AND inline `[url=]` links."""
    nodes: list[dict] = []
    links: list[dict] = []
    in_links = False
    for line in (text or "").splitlines():
        if line.strip() == "Links:":
            in_links = True
            continue
        if in_links:
            m = _APPENDIX_LINK.match(line)
            if m:
                links.append({"text": m.group(1).strip(), "url": m.group(2).strip(),
                              "ref": None})
            continue
        m = _NODE.match(line)
        if not m:
            continue
        rest = m.group(3) or ""
        ref = _REF.search(rest)
        url = _URL.search(rest)
        node = {"role": m.group(1).lower(), "name": m.group(2).replace('\\"', '"').strip(),
                "ref": ref.group(1).strip() if ref else None,
                "url": url.group(1).strip() if url else None}
        nodes.append(node)
        if node["url"] and node["role"] == "link":
            links.append({"text": node["name"], "url": node["url"], "ref": node["ref"]})
    return {"nodes": nodes, "links": links}


def click_refusal(snapshot_text: str | None, ref: str, *, tab_url: str,
                  social_hosts: tuple[str, ...], allowed_hosts: tuple[str, ...]) -> str | None:
    """A click is allowed only on a LINK that THIS process saw in its latest
    snapshot of the same tab, whose name and destination pass every rule, and
    never while the tab is on a social host."""
    if on_hosts(tab_url, social_hosts):
        return (f"REFUSED_SOCIAL_CLICK: the tab is on {_host(tab_url)!r}; the social hosts "
                f"are read-only -- navigate to a URL instead of clicking (2026-09-28).")
    if not snapshot_text:
        return (f"REFUSED_CLICK_UNSEEN_REF: {ref!r} -- no snapshot of this tab was taken "
                f"by this process; a click lands only on a ref it has seen.")
    snap = parse_snapshot(snapshot_text)
    node = next((n for n in snap["nodes"] if n["ref"] == ref), None)
    if node is None:
        return f"REFUSED_CLICK_UNSEEN_REF: {ref!r} is not in this tab's latest snapshot."
    if node["role"] not in CLICKABLE_ROLES:
        return (f"REFUSED_CLICK_ROLE: {ref!r} is a {node['role']!r}; the research browser "
                f"clicks links only.")
    why = text_refusal(node["name"])
    if why:
        return why
    url = node.get("url") or next((lk["url"] for lk in snap["links"]
                                   if lk["text"] == node["name"]), None)
    if url:
        why = url_refusal(url) or social_url_refusal(url, social_hosts)
        if why:
            return why
        if not on_hosts(url, allowed_hosts):
            return (f"REFUSED_CLICK_OFF_HOSTS: {ref!r} leads to {_host(url)!r}, not one of "
                    f"{allowed_hosts}.")
    return None


def rules_summary() -> dict[str, Any]:
    """What a receipt prints about the rules in force."""
    return {"payment_text": PAYMENT_TEXT.pattern, "message_text": MESSAGE_TEXT.pattern,
            "payment_path": PAYMENT_PATH.pattern, "message_hosts": list(MESSAGE_HOSTS),
            "scroll_keys": sorted(SCROLL_KEYS), "clickable_roles": sorted(CLICKABLE_ROLES)}
