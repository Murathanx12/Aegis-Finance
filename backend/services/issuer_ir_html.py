"""Strict, single-page ASML investor-relations press-release extraction.

The caller supplies a registry-pinned URL. An index, redirect replacement, or
another issuer's page is a refusal, never an empty successful news pull.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urlsplit


class IssuerPageRefused(ValueError):
    pass


class _Release(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.article_depth = 0
        self.body_seen = False
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta":
            key = a.get("property") or a.get("name") or ""
            if key in {"sc:publication_date", "sc:page_type", "sc:page_title"}:
                self.meta[key] = a.get("content") or ""
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href") or ""
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        if tag == "div" and "full-release-body" in (a.get("class") or "").split():
            if self.body_seen:
                raise IssuerPageRefused("duplicate_release_body")
            self.body_seen = True
            self.article_depth = 1
        elif self.article_depth and tag == "div":
            self.article_depth += 1
        if self.article_depth and tag in {"p", "li", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if self.article_depth:
            if tag in {"p", "li", "h1", "h2", "h3"}:
                self.parts.append("\n")
            if tag == "div":
                self.article_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.article_depth and not self.skip_depth:
            self.parts.append(data)


def parse_asml_release(raw: bytes, expected_url: str) -> dict:
    parsed = urlsplit(expected_url)
    if (parsed.scheme, parsed.hostname) != ("https", "investor.asml.com") or not parsed.path.startswith(
            "/news-releases/news-release-details/") or parsed.query or parsed.fragment:
        raise IssuerPageRefused("unregistered_issuer_url_shape")
    if len(raw) > 1024 * 1024:
        raise IssuerPageRefused("issuer_page_over_one_mib")
    try:
        page = _Release()
        page.feed(raw.decode("utf-8", errors="strict"))
    except UnicodeDecodeError as exc:
        raise IssuerPageRefused("issuer_page_not_utf8") from exc
    if page.canonical != expected_url or page.meta.get("sc:page_type") != "press_release_page":
        raise IssuerPageRefused("issuer_canonical_or_type_drift")
    title = " ".join(page.meta.get("sc:page_title", "").split())
    if not title.startswith("ASML reports "):
        raise IssuerPageRefused("issuer_title_drift")
    try:
        published = datetime.fromisoformat(page.meta["sc:publication_date"].replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise IssuerPageRefused("issuer_publication_missing_or_invalid") from exc
    if published.tzinfo is None:
        raise IssuerPageRefused("issuer_publication_naive")
    body = "\n".join(" ".join(line.split()) for line in "".join(page.parts).splitlines() if line.strip())
    if not page.body_seen or page.article_depth or len(body) < 400 or "ASML Holding" not in body:
        raise IssuerPageRefused("issuer_body_missing_or_drifted")
    return {"title": title, "url": expected_url, "body": body,
            "published": published, "raw_id": expected_url,
            "raw_sha256": sha256(raw).hexdigest(), "entity_tags": ["issuer:ASML"],
            "tickers": ["ASML"]}
