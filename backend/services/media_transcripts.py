"""The media an article carries, and the transcript the SITE ITSELF publishes.

Murat, 2026-09-28 21:45 HKT: "... and also the media too." Then, 22:00 HKT:
"use the transcript of the videos, its much better."

What this module does, and what it never does
=============================================
* It turns the reply of `openclaw_client.read_media` (one FIXED JavaScript
  function that only READS what the page already holds) into a media summary
  (video / audio or podcast / charts / images: counts, titles, captions) and a
  list of media ITEMS, each with `media_kind`, title, duration, publication time
  and, where the site exposes one, its transcript as TEXT.
* Transcript sources, in the order they are used:
    1. `structured_data` -- the page's own JSON-LD (VideoObject / AudioObject /
       PodcastEpisode) carries a `transcript` string;
    2. `page_section`    -- a transcript block the page shows as text;
    3. `captions_track`  -- a captions / subtitles file (WebVTT, SRT, TTML) the
       page's player lists. That ONE text file may be fetched from the host the
       page names (often a CDN); the host is recorded; nothing else is taken
       from it (`fetch_captions`).
* No video or audio file is ever downloaded, no third-party downloader is
  used, nothing is typed or clicked, and there is no speech-to-text here (a
  separate decision). An item with none of the three is stored with
  `transcript = "NONE_PUBLISHED"`.

Rows land in `news_corpus/media_transcripts/<host>/<YYYY-MM-DD>.jsonl`
(gitignored corpus), one per media item, deduplicated by (page url, item title).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from backend import config as _config
from backend.services import disk_guard as DG

NONE_PUBLISHED = "NONE_PUBLISHED"
CAPTION_EXT = re.compile(r"\.(vtt|srt|ttml|dfxp)(\?|$)", re.I)
CAPTION_CT = re.compile(r"text/vtt|text/plain|application/x-subrip|application/ttml|"
                        r"text/xml|application/xml", re.I)
_ISO_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$", re.I)
_CUE_TIME = re.compile(r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->")
_TAGS = re.compile(r"<[^>]+>")


def iso_duration_s(s: str | None) -> int | None:
    """PURE. `PT2M30S` -> 150; a plain number of seconds passes; else None."""
    if not s:
        return None
    t = str(s).strip()
    if t.replace(".", "", 1).isdigit():
        return int(float(t))
    m = _ISO_DUR.match(t)
    if not m or not any(m.groups()):
        return None
    d, h, mi, se = (float(x) if x else 0.0 for x in m.groups())
    return int(d * 86400 + h * 3600 + mi * 60 + se)


def parse_captions(text: str) -> str:
    """PURE. WebVTT / SRT / TTML -> plain text: cue numbers, timings, headers,
    NOTE blocks and markup removed; consecutive duplicate lines collapsed (live
    captions repeat a line as it grows)."""
    t = text or ""
    if "<tt" in t[:500] or "<p " in t or "</p>" in t:           # TTML / DFXP
        t = re.sub(r"</p>|<br\s*/?>", "\n", t)
        t = _TAGS.sub("", t)
    out: list[str] = []
    skip_block = False
    for ln in t.splitlines():
        s = ln.strip()
        if not s:
            skip_block = False
            continue
        if s.upper().startswith(("WEBVTT", "STYLE", "REGION")) or s.startswith("NOTE"):
            skip_block = True
            continue
        if skip_block or s.isdigit() or _CUE_TIME.match(s) or "-->" in s:
            continue
        s = _TAGS.sub("", s).replace("&nbsp;", " ").replace("&amp;", "&").strip()
        if s and (not out or out[-1] != s):
            out.append(s)
    return "\n".join(out)


def summarize(media: dict | None) -> dict:
    """PURE. The media summary stored on an article: counts and titles per
    kind, no transcript text (that goes to the transcript rows)."""
    m = media or {}

    def part(k: str, titles: str = "titles") -> dict:
        d = m.get(k) or {}
        return {"n": int(d.get("n") or 0), titles: [str(x)[:200] for x in (d.get(titles) or [])][:10]}
    return {"video": part("video"), "audio": part("audio"), "charts": part("charts"),
            "images": part("images", "captions"),
            "caption_urls": len(m.get("caption_urls") or []),
            "structured_items": len(m.get("structured") or []),
            "transcript_sections": len(m.get("transcript_sections") or [])}


def _kind_of(type_or_tag: str) -> str:
    t = (type_or_tag or "").lower()
    if "podcast" in t:
        return "podcast"
    if "audio" in t:
        return "audio"
    return "video"


def items_from_media(page_url: str, media: dict | None, *,
                     published_utc: str | None = None) -> list[dict]:
    """PURE. The media ITEMS of one page, each `{media_kind, title, duration_s,
    published, transcript_source?, transcript?, caption_url?}`. Structured data
    items first; else the page's <video>/<audio> elements; else one item per
    kind the page counts. A transcript is attached where the page exposes one:
    a JSON-LD `transcript`, else the page's transcript section (to the first
    item), else a caption URL to fetch (`caption_url`, first item)."""
    m = media or {}
    items: list[dict] = []
    for s in (m.get("structured") or [])[:10]:
        it = {"media_kind": _kind_of(s.get("type") or ""), "title": (s.get("name") or "")[:300],
              "duration_s": iso_duration_s(s.get("duration")),
              "published": s.get("published") or published_utc}
        if (s.get("transcript") or "").strip():
            it.update(transcript_source="structured_data", transcript=s["transcript"].strip())
        cap = s.get("caption") or ""
        if isinstance(cap, str) and CAPTION_EXT.search(cap):
            it["caption_url"] = cap
        items.append(it)
    if not items:
        for e in (m.get("elements") or [])[:10]:
            it = {"media_kind": _kind_of(e.get("kind") or ""), "title": (e.get("title") or "")[:300],
                  "duration_s": e.get("duration"), "published": published_utc}
            tr = [t.get("src") for t in (e.get("tracks") or []) if t.get("src")]
            if tr:
                it["caption_url"] = tr[0]
            items.append(it)
    if not items:
        for k, kind in (("video", "video"), ("audio", "audio")):
            d = m.get(k) or {}
            if int(d.get("n") or 0) > 0:
                items.append({"media_kind": kind, "title": ((d.get("titles") or [""])[0] or "")[:300],
                              "duration_s": None, "published": published_utc})
    # an ad slot is not a media item (MarketWatch labels its player "Advertisement")
    items = [i for i in items if not re.fullmatch(r"\s*advertisement\s*", i.get("title") or "",
                                                  re.I)]
    if not items:
        return []
    first = next((i for i in items if "transcript" not in i), None)
    secs = [t for t in (m.get("transcript_sections") or []) if (t or "").strip()]
    if first is not None and secs:
        first.update(transcript_source="page_section", transcript=secs[0].strip())
    caps = [u for u in (m.get("caption_urls") or []) if u]
    if first is not None and "transcript" not in first and "caption_url" not in first and caps:
        first["caption_url"] = caps[0]
    for it in items:
        it["page_url"] = page_url
    return items


def caption_url_refusal(url: str) -> str | None:
    """Why a caption URL may NOT be fetched (None = it may): https only, a
    caption-file extension, never a denied / message / payment / social host."""
    try:
        sp = urlsplit(url or "")
    except ValueError:
        return "REFUSED_CAPTION_URL_UNPARSEABLE"
    if sp.scheme != "https" or not sp.hostname:
        return f"REFUSED_CAPTION_URL_SCHEME: {url[:120]!r}"
    if not CAPTION_EXT.search(sp.path + ("?" if sp.query else "")):
        return f"REFUSED_CAPTION_URL_NOT_CAPTIONS: {url[:120]!r}"
    from backend.services import browser_policy as BP
    from backend.services import web_reader as WR
    h = sp.hostname.lower()
    if any(h == n or h.endswith("." + n) for n in WR.NEVER_HOSTS) or WR.is_social(url):
        return f"REFUSED_CAPTION_HOST: {h!r}"
    why = BP.url_refusal(url) if hasattr(BP, "url_refusal") else None
    if why:
        return why
    try:
        from backend.services import openclaw_client as OC
        OC.check_url(url)
    except Exception as exc:  # noqa: BLE001 -- a denied domain refuses
        return f"REFUSED_CAPTION_DENIED: {str(exc)[:120]}"
    return None


def fetch_captions(url: str, *, get: Callable[..., Any] | None = None,
                   max_bytes: int | None = None) -> dict:
    """Fetch ONE captions text file a page's player named. Returns `{ok, host,
    text?, bytes?, error?}`. `get(url, timeout=, stream=)` is `requests.get` in
    production and a fake in tests. No cookies, no retries, text only, size
    capped; anything else refuses."""
    host = (urlsplit(url or "").hostname or "").lower()
    why = caption_url_refusal(url)
    if why:
        return {"ok": False, "host": host, "error": why}
    cap = int(max_bytes or getattr(_config, "READER_CAPTIONS_MAX_BYTES", 2_000_000))
    if get is None:
        import requests
        get = requests.get
    try:
        r = get(url, timeout=20, stream=True)
        if int(getattr(r, "status_code", 0)) != 200:
            return {"ok": False, "host": host, "error": f"HTTP {getattr(r, 'status_code', '?')}"}
        ct = str((getattr(r, "headers", {}) or {}).get("Content-Type") or "")
        if ct and not CAPTION_CT.search(ct):
            return {"ok": False, "host": host, "error": f"REFUSED_CAPTION_CONTENT_TYPE: {ct[:60]}"}
        buf = b""
        for chunk in r.iter_content(65536):
            buf += chunk or b""
            if len(buf) > cap:
                return {"ok": False, "host": host, "error": f"REFUSED_CAPTION_TOO_BIG: > {cap} bytes"}
    except Exception as exc:  # noqa: BLE001 -- a failed fetch is a named result
        return {"ok": False, "host": host, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    text = parse_captions(buf.decode("utf-8", "replace"))
    return {"ok": bool(text.strip()), "host": host, "text": text, "bytes": len(buf),
            **({} if text.strip() else {"error": "EMPTY_CAPTIONS"})}


def resolve_transcripts(items: list[dict], *, fetch: Callable[[str], dict] | None = None
                        ) -> list[dict]:
    """Give every item a transcript: its own, else its caption file's text
    (fetched with `fetch`, `fetch_captions` by default), else NONE_PUBLISHED."""
    fetch = fetch or fetch_captions
    out = []
    for it in items:
        it = dict(it)
        if not (it.get("transcript") or "").strip() and it.get("caption_url"):
            got = fetch(it["caption_url"])
            it["captions_host"] = got.get("host")
            if got.get("ok"):
                it.update(transcript_source="captions_track", transcript=got["text"])
            else:
                it["captions_error"] = got.get("error")
        if not (it.get("transcript") or "").strip():
            it["transcript"] = NONE_PUBLISHED
            it["transcript_source"] = None
        out.append(it)
    return out


def transcripts_root() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "news_corpus" / "media_transcripts"


def store_items(items: list[dict], *, reached_by: dict | None = None,
                root: Path | None = None, now: datetime | None = None) -> list[dict]:
    """Append one row per item to `<root>/<host>/<day>.jsonl` (locked), skipping
    an item already stored for that page url and title. Returns the rows written."""
    now = now or datetime.now(timezone.utc)
    base = Path(root) if root else transcripts_root()
    written = []
    for it in items:
        page = str(it.get("page_url") or "")
        host = (urlsplit(page).hostname or "unknown").lower().removeprefix("www.")
        path = base / host / f"{now.date().isoformat()}.jsonl"
        key = f"{page}|{it.get('title') or ''}|{it.get('media_kind')}"
        seen = set()
        if path.exists():
            for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    seen.add(json.loads(ln).get("key"))
                except ValueError:
                    continue
        if key in seen:
            continue
        tr = str(it.get("transcript") or NONE_PUBLISHED)
        row = {"key": key, "url": page, "media_kind": it.get("media_kind"),
               "title": it.get("title"), "duration_s": it.get("duration_s"),
               "published": it.get("published"), "transcript_source": it.get("transcript_source"),
               "captions_host": it.get("captions_host"), "caption_url": it.get("caption_url"),
               "captions_error": it.get("captions_error"),
               "transcript": tr, "chars": 0 if tr == NONE_PUBLISHED else len(tr),
               "read_utc": now.isoformat(timespec="seconds"), "reached_by": reached_by}
        DG.locked_append_line(path, json.dumps(row, ensure_ascii=False, default=str))
        written.append(row)
    return written
