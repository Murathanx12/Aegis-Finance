"""The operator's paste inbox -- Murat reads, Aegis files. The PRIMARY Dow Jones path.

    backend/data/optimus/digest_inbox/
        README.md                 the format, in three lines (tracked)
        WEEKEND_READING_LIST.md   clickable links + what each is for (tracked)
        DIGEST.md                 one file he appends to (gitignored)
        *.txt / *.md              a page saved as text (gitignored)

WHY THIS AND NOT THE BROWSER READER
===================================
Murat's worry (2026-09-26): automated reads can get a subscription flagged, and
the Dow Jones agreement (§9.4.1, quoted in `web_reader`) names "browser
automation tool" and "AI agent or assistant" explicitly. A human who selects
the article and pastes it is a subscriber reading his own paper. This module
only parses what he pasted, stores it beside the reader's articles in the same
layout with `origin: pasted_by_operator`, and hands it to the same claim
extractor.

THE FORMAT (forgiving on purpose -- he pastes at 1 a.m.)
========================================================
Entries are separated by a line that starts with `===`, optionally followed by
`url | date | source` in any order and any subset:

    === https://www.wsj.com/finance/... | 2026-09-25 | WSJ
    <select-all of the article>

Text before the first `===` in DIGEST.md is the instructions and is ignored. A
separate file with no `===` is ONE entry. Missing header fields are recovered
from the text: the publisher from "The Wall Street Journal" / "Barron's" /
"MarketWatch", the dateline from the first "Sept. 25, 2026 9:00 pm ET"-shaped
date, the title from the first substantial line.

PIT
===
`first_seen_utc` is the INGEST time -- when Aegis first held the text -- never
the article's date and never the file's mtime (a gate that reads mtime is a gate
on checkout time, CLAUDE.md protocol 7). The article's own date is
`published_utc`; a gap over 30 days grades the row `archive`, which records its
claims but writes no forecast.

Idempotent by content hash: pasting the same article twice, or re-running the
ingest, stores and forecasts it once.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend import config as _config

ORIGIN = "pasted_by_operator"
SEPARATOR = re.compile(r"^===(.*)$")
SKIP_FILES = {"readme.md", "weekend_reading_list.md"}
_URL = re.compile(r"https?://\S+")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")

README = """# Digest inbox -- paste Dow Jones articles here

Open an article in the MuratClaw (Work) Chrome, select all (Ctrl+A), copy, and paste it into
`DIGEST.md` under a separator line `=== url | date | source` (every field optional), or save the
page as a `.txt` file into this folder. Then run `python -m scripts.digest_ingest --once --claims`:
each entry is stored locally (never committed), its claims become `source:<column>` forecast rows,
and they are graded from the next session. Links worth pasting: `WEEKEND_READING_LIST.md`.
"""

DIGEST_HEADER = """# DIGEST -- paste below. Everything above the first line starting with === is ignored.
# One entry = a separator line, then the pasted article:
#   === https://www.wsj.com/... | 2026-09-25 | WSJ
#   <paste>
"""


def inbox_dir() -> Path:
    return Path(getattr(_config, "DIGEST_INBOX_DIR",
                        Path(_config.OPTIMUS_LEDGER_DIR) / "digest_inbox"))


def ensure_inbox(d: Path | None = None) -> Path:
    d = Path(d) if d else inbox_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "README.md").exists():
        (d / "README.md").write_text(README, encoding="utf-8")
    if not (d / "DIGEST.md").exists():
        (d / "DIGEST.md").write_text(DIGEST_HEADER, encoding="utf-8")
    return d


# ───────────────────────────────── parsing ──────────────────────────────────

def parse_header(h: str) -> dict:
    out: dict[str, Any] = {}
    for tok in [t.strip() for t in (h or "").split("|")]:
        if not tok:
            continue
        low = tok.lower()
        if _URL.match(tok):
            out["url"] = _URL.match(tok).group(0)
        elif _ISO_DAY.match(tok):
            out["date"] = tok[:10]
        elif any(k in low for k in ("wsj", "wall street journal", "barron", "marketwatch")):
            out["source"] = tok
        else:
            from backend.services import web_reader as WR
            if WR.parse_published(tok):
                out["date"] = WR.parse_published(tok)
    return out


def split_entries(text: str, *, header_zone: bool) -> list[tuple[dict, str]]:
    """[(header, body)]. `header_zone`: text before the first `===` is
    instructions (DIGEST.md) rather than an entry (a saved page)."""
    entries: list[tuple[dict, list[str]]] = []
    cur_h: dict | None = None
    cur: list[str] = []
    seen_sep = False
    for line in (text or "").splitlines():
        m = SEPARATOR.match(line.strip())
        if m:
            if seen_sep or (not header_zone and "".join(cur).strip()):
                entries.append((cur_h or {}, cur))
            cur_h, cur, seen_sep = parse_header(m.group(1)), [], True
            continue
        cur.append(line)
    if seen_sep or not header_zone:
        entries.append((cur_h or {}, cur))
    return [(h, "\n".join(b).strip()) for h, b in entries if "\n".join(b).strip()]


def _publisher(header: dict, text: str, url: str) -> str | None:
    from backend.services import dowjones_claims as DC
    src = (header.get("source") or "").lower()
    if "barron" in src:
        return "barrons"
    if "marketwatch" in src:
        return "marketwatch"
    if "wsj" in src or "wall street journal" in src:
        return "wsj"
    return DC.publisher_of(url, text)


def to_article(header: dict, body: str, *, ingest_utc: str) -> dict:
    from backend.services import dowjones_claims as DC
    from backend.services import web_reader as WR
    url = header.get("url") or ""
    if not url:
        m = _URL.search(body[:2000])
        url = m.group(0) if m and WR.host_ok(m.group(0)) else ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    title = next((ln for ln in lines if len(ln) >= 25 and ln.lower() not in WR.NAV_LINES
                  and not _URL.match(ln)), lines[0] if lines else "")
    text = WR.clean_text(body, title)
    published = None
    if header.get("date"):
        hd = header["date"]
        published = hd if "T" in hd else f"{hd}T00:00:00+00:00"
    published = published or WR.parse_published(text)
    # Publisher and column from the RAW paste: the lines above the headline
    # ("Heard on the Street", "The Wall Street Journal") are exactly what
    # `clean_text` cuts, and exactly what names the column.
    pub = _publisher(header, body, url)
    art = {"url": url or None, "title": title[:300], "byline": WR.parse_byline(text),
           "published_utc": published, "text": text, "first_seen_utc": ingest_utc,
           "publisher": pub or "dowjones", "origin": ORIGIN,
           "column": DC.column_of(url, title, body, pub)}
    art["sha"] = DC.text_sha(text)
    return art


def ingest(d: Path | None = None, *, now_utc: str | None = None,
           root: Path | None = None) -> dict:
    """Parse every inbox file, store every NEW entry. Returns the receipt
    (metadata only -- no article text)."""
    from backend.services import web_reader as WR
    d = ensure_inbox(d)
    now = now_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    per, n_new, n_dup, n_short = [], 0, 0, 0
    for f in sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in (".md", ".txt")):
        if f.name.lower() in SKIP_FILES:
            continue
        raw = f.read_text(encoding="utf-8", errors="replace")
        for h, body in split_entries(raw, header_zone=(f.name.lower() == "digest.md")):
            art = to_article(h, body, ingest_utc=now)
            if len(art["text"]) < 200:
                n_short += 1
                per.append({"file": f.name, "status": "SKIPPED_TOO_SHORT",
                            "chars": len(art["text"])})
                continue
            st = WR.store_article(art, root=root)
            n_dup += bool(st["duplicate"])
            n_new += not st["duplicate"]
            per.append({"file": f.name, "status": "DUPLICATE" if st["duplicate"] else "STORED",
                        "sha": st["sha"], "publisher": art["publisher"], "column": art["column"],
                        "url": art["url"], "title": art["title"][:160],
                        "published_utc": art["published_utc"], "chars": len(art["text"]),
                        "pit_grade": st.get("pit_grade")})
    return {"receipt": "digest_ingest", "ingest_utc": now, "inbox": str(d),
            "origin": ORIGIN, "n_entries": len(per), "n_new": n_new, "n_duplicate": n_dup,
            "n_too_short": n_short, "entries": per}


# ───────────────────────────── the reading list ─────────────────────────────

def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(y, month, day)


def _nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    d = date(y, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y: int, month: int, weekday: int) -> date:
    d = date(y, month + 1, 1) - timedelta(days=1) if month < 12 else date(y, 12, 31)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 5 else (
        d + timedelta(days=1) if d.weekday() == 6 else d)


def nyse_holidays(y: int) -> set[date]:
    return {_observed(date(y, 1, 1)), _nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3),
            _easter(y) - timedelta(days=2), _last_weekday(y, 5, 0), _observed(date(y, 6, 19)),
            _observed(date(y, 7, 4)), _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 11, 3, 4),
            _observed(date(y, 12, 25))}


def trading_days_back(today: date, weeks: int = 8) -> list[date]:
    start = today - timedelta(weeks=weeks)
    hol = nyse_holidays(today.year) | nyse_holidays(start.year)
    out, d = [], today - timedelta(days=1)
    while d >= start:
        if d.weekday() < 5 and d not in hol:
            out.append(d)
        d -= timedelta(days=1)
    return out


def book_names() -> dict[str, list[str]]:
    """personal (murat_book.yaml), competition (human_ai_thematic_v2), probe
    (the latest decision contract's PROBE rows). Each empty on a missing file."""
    out: dict[str, list[str]] = {"personal": [], "competition": [], "probe": []}
    try:
        import yaml
        d = yaml.safe_load((Path(_config.BACKEND_DIR) / "data" / "murat_book.yaml")
                           .read_text(encoding="utf-8")) or {}
        out["personal"] = [str(p.get("ticker")).upper() for p in d.get("positions") or []
                           if isinstance(p, dict) and p.get("ticker")]
    except (OSError, ValueError):
        pass
    try:
        from scripts.source_reads import thematic_tickers
        out["competition"] = thematic_tickers()
    except Exception:  # noqa: BLE001
        pass
    try:
        dec = sorted((Path(_config.OPTIMUS_LEDGER_DIR) / "decisions").glob("20*.json"))
        if dec:
            rows = json.loads(dec[-1].read_text(encoding="utf-8")).get("rows") or []
            out["probe"] = sorted({str(r.get("ticker")).upper() for r in rows
                                   if r.get("direction") == "PROBE" and r.get("ticker")})
    except (OSError, ValueError):
        pass
    return out


def build_reading_list(today: date | None = None, names: dict[str, list[str]] | None = None
                       ) -> str:
    today = today or datetime.now(timezone.utc).date()
    names = names if names is not None else book_names()
    allt: list[str] = []
    for k in ("personal", "competition", "probe"):
        for t in names.get(k, []):
            if t not in allt:
                allt.append(t)

    def who(t: str) -> str:
        return "/".join(k for k in ("personal", "competition", "probe") if t in names.get(k, []))

    L = [f"# Weekend reading list -- generated {today.isoformat()} from the books",
         "",
         "**How to paste.** Click a link (MuratClaw (Work) Chrome, signed in). On an article: Ctrl+A, "
         "Ctrl+C, then in `DIGEST.md` add a line `=== <url> | <date> | <source>` and paste under it "
         "(or save the page as a .txt into this folder). On a list or search page, open the "
         "articles it shows and paste each one. When done: "
         "`python -m scripts.digest_ingest --once --claims`.",
         "",
         "**What happens after ingest.** Each entry is stored locally (never committed); DeepSeek "
         "extracts the claims (ticker, up/down, horizon, magnitude, the quote); each claim becomes a "
         "`source:<column>` forecast row dated at ingest time, and the existing grader scores it "
         "from the next session against SPY at 1/5/20 sessions. The column (Heard on the Street, "
         "Barron's picks, ...) earns or loses its weight from those grades.",
         "",
         f"Names: personal {len(names.get('personal', []))}, competition "
         f"{len(names.get('competition', []))}, PROBE {len(names.get('probe', []))} "
         f"({len(allt)} distinct).",
         "",
         "## (a) WSJ news archive, one day per trading day, last 8 weeks",
         "Why: the dated record of what WSJ said, to grade against what happened. "
         "Extract: every headline naming a listed stock -> open it -> paste. Fields: ticker, "
         "direction, horizon, magnitude, quote.", ""]
    for d in trading_days_back(today, 8):
        L.append(f"- [{d.isoformat()} ({d:%a})](https://www.wsj.com/news/archive/{d:%Y/%m/%d})")
    L += ["", "## (b) Barron's picks, pans, scorecard, polls, lists",
          "Why: Barron's publishes named, dated calls and grades them itself -- the cleanest "
          "external track record to beat. Extract: ticker, buy/sell, target if stated, date.", ""]
    bq = [("Barron's stock picks page", "https://www.barrons.com/market-data/stocks/stock-picks"),
          ("Barron's picks topic", "https://www.barrons.com/topics/barrons-picks"),
          ("Picks-and-pans scorecard (search)", "https://www.barrons.com/search?query=" + quote("picks and pans scorecard")),
          ("Big Money poll (search)", "https://www.barrons.com/search?query=" + quote("Big Money poll")),
          ("Roundtable (search)", "https://www.barrons.com/search?query=" + quote("Barron's Roundtable")),
          ("10 favorite stocks for 2026 (search)", "https://www.barrons.com/search?query=" + quote("10 favorite stocks for 2026")),
          ("10 favorite stocks for 2025 (search)", "https://www.barrons.com/search?query=" + quote("10 favorite stocks for 2025"))]
    L += [f"- [{t}]({u})" for t, u in bq]
    L += ["", "## (c) Heard on the Street, per name (WSJ search)",
          "Why: HOTS is WSJ's directional column; every piece on a name we hold or probe is a "
          "gradeable call. Extract: ticker, direction, horizon, quote.", ""]
    L += [f"- [{t}](https://www.wsj.com/search?query={quote('Heard on the Street ' + t)}) -- {who(t)}"
          for t in allt]
    L += ["", "## (d) MarketWatch analyst estimates + overview (earnings date), per name",
          "Why: consensus rating, target and EPS estimates, dated -- a claim with a natural "
          "resolution (the next report). Extract: rating, mean/high/low target, next-quarter EPS "
          "estimate, earnings date.", ""]
    L += [f"- {t}: [analyst estimates](https://www.marketwatch.com/investing/stock/{t.lower()}/analystestimates)"
          f" | [overview](https://www.marketwatch.com/investing/stock/{t.lower()}) -- {who(t)}"
          for t in allt]
    L += ["", "## (e) WSJ research ratings, per name",
          "Why: dated consensus rating and price-target range. Extract: rating counts, "
          "mean/high/low target, as-of date.", ""]
    L += [f"- [{t}](https://www.wsj.com/market-data/quotes/{t}/research-ratings) -- {who(t)}"
          for t in allt]
    return "\n".join(L) + "\n"


def write_reading_list(d: Path | None = None, **kw: Any) -> Path:
    d = ensure_inbox(d)
    p = d / "WEEKEND_READING_LIST.md"
    p.write_text(build_reading_list(**kw), encoding="utf-8")
    return p
