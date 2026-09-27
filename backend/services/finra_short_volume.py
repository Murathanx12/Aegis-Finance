"""FINRA Reg SHO daily short-SALE volume: a free, point-in-time, daily source.

WHAT IT IS
==========
FINRA publishes, for every trading day, the consolidated (all FINRA-reporting
venues: TRFs + ADF + ORF) off-exchange share volume of each symbol and how much
of it was executed as a SHORT SALE:

    https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt

(verified 2026-09-27 by one fetch per case: 2026-09-25 -> 200 text/plain,
12,349 rows, `last-modified: Fri, 25 Sep 2026 21:18:01 GMT` = 17:18 ET on the
trade date itself; 2018-08-01 -> 200 text/plain; a weekend (2026-09-26) and a
holiday (2018-12-25) -> **403 application/xml `AccessDenied`**, i.e. "no file
for that day" is a 403 from the CDN, not a 404.)

Format: pipe-delimited, header
``Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`` and, on
recent files, a trailing line holding the record count only. Volumes are
fractional on recent files (FINRA prorates odd-lot and fractional reports).

WHAT IT IS NOT
==============
Short SALE volume is NOT short INTEREST. It counts executions flagged short on
the day, and most of it is market makers and liquidity providers shorting to
fill customer buys (they are flat by the close), so a typical name prints a
ratio of 0.4-0.5 with no directional view behind it. The literature that finds
information in it (Boehmer, Jones & Zhang 2008, JF 63(2) "Which Shorts Are
Informed?"; Diether, Lee & Werner 2009, RFS 22(2) "Short-Sale Strategies and
Return Predictability"; Engelberg, Reed & Ringgenberg 2012, JFE 105(2) "How
Are Shorts Informed?") reads it cross-sectionally and relative to the name's
own normal level -- which is why `pit_features` carries a z-score and a change
next to the level. Only the OFF-EXCHANGE (FINRA-reported) slice is covered;
exchange-printed short volume (Nasdaq/NYSE own files) is not in these files.

THE PIT RULE (printed on every receipt)
=======================================
A day's file is public after that day's close (observed ~17:20 ET). It is
therefore usable for decisions from the NEXT session: a decision on day D
reads files dated STRICTLY BEFORE D. `pit_features.short_volume_features`
enforces it with a strict as-of join; the factory scores month-end t's close
and enters at t+1's open, so its decision date is t+1 and t's file is (just)
admissible -- it was published before the open it trades at.

STORAGE
=======
``<OPTIMUS>/finra_short_volume/``:
  ``_days/<YYYYMMDD>.parquet``   one parsed day (the resumable unit)
  ``year_<YYYY>.parquet``        the compact per-year file (consolidated)
  ``state.json``                 dates FINRA did not publish (403), older than
                                 ``RETRY_RECENT_DAYS`` -- a recent 403 is retried
  ``manifest.json``              TRACKED: per-year rows, dates, symbols, sha256
Parquets are gitignored (repo-wide ``*.parquet``); the manifest is committed.

Idempotent: a date already in a year file, in ``_days/`` or recorded as not
published is never fetched again. Resumable: kill it anywhere; the next run
continues from the first missing date. Polite: >= ``PACE_S`` between requests.
Refuses (raises) on a 200 that is not text (HTML/XML error page, a captive
portal), on a header it does not recognise, and on a file whose Date column
is not the requested date. A 5xx / 429 / network error stops the pull (the
receipt names it); nothing partial is written for that day.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

URL_TEMPLATE = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
START_DATE = date(2018, 8, 1)
PACE_S = 0.5
TIMEOUT_S = 30.0
#: A 403 for a date younger than this is "not published YET", retried next run.
RETRY_RECENT_DAYS = 5
HEADER = ("Date", "Symbol", "ShortVolume", "ShortExemptVolume", "TotalVolume", "Market")
COLUMNS = ("date", "symbol", "short_volume", "short_exempt_volume", "total_volume", "market")
DIR_NAME = "finra_short_volume"
PIT_RULE = ("a day's FINRA file is public after that day's close (~17:20 ET, CDN "
            "last-modified); a decision on day D reads only files dated STRICTLY BEFORE D "
            "(usable from the NEXT session)")
USER_AGENT = "aegis-finance research (FINRA Reg SHO daily files; polite 0.5s pacing)"


class FinraShortVolumeError(RuntimeError):
    """The FINRA pull could not produce a trustworthy day (named, never swallowed)."""


class FinraRefused(FinraShortVolumeError):
    """A response that is not a FINRA short-volume text file (HTML/XML, bad header, wrong date)."""


def default_root() -> Path:
    from backend import config as _cfg
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / DIR_NAME


def url_for(d: date) -> str:
    return URL_TEMPLATE.format(d=d.strftime("%Y%m%d"))


# ── parsing ──────────────────────────────────────────────────────────────────

def _looks_like_markup(body: bytes) -> bool:
    head = body.lstrip()[:64].lower()
    return head.startswith(b"<") or b"<html" in head or b"<!doctype" in head


def parse_file(body: bytes | str, expect: date | None = None) -> pd.DataFrame:
    """One FINRA daily file -> long frame with COLUMNS. Refuses anything else.

    The trailing record-count line (recent files) is checked against the row
    count and dropped; a mismatch refuses (a truncated download).
    """
    raw = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    if not raw.strip():
        raise FinraRefused("empty body")
    if _looks_like_markup(raw):
        raise FinraRefused(f"markup, not a FINRA text file: {raw[:80]!r}")
    text = raw.decode("utf-8", errors="strict")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if tuple(lines[0].strip().split("|")) != HEADER:
        raise FinraRefused(f"unrecognised header {lines[0][:120]!r}")
    body_lines = lines[1:]
    trailer = None
    if body_lines and "|" not in body_lines[-1]:
        tail = body_lines.pop().strip()
        if not tail.isdigit():
            raise FinraRefused(f"unrecognised trailer {tail[:40]!r}")
        trailer = int(tail)
    if trailer is not None and trailer != len(body_lines):
        raise FinraRefused(f"trailer says {trailer} records, file has {len(body_lines)}")
    df = pd.read_csv(io.StringIO("\n".join([lines[0]] + body_lines)), sep="|",
                     dtype={"Date": str, "Symbol": str, "Market": str}, keep_default_na=False,
                     na_values={"ShortVolume": [""], "ShortExemptVolume": [""], "TotalVolume": [""]})
    df.columns = list(COLUMNS)
    df = df[df["symbol"].astype(str).str.len() > 0]
    dates = set(df["date"].unique())
    if len(dates) != 1:
        raise FinraRefused(f"file carries {len(dates)} dates: {sorted(dates)[:3]}")
    d = datetime.strptime(next(iter(dates)), "%Y%m%d").date()
    if expect is not None and d != expect:
        raise FinraRefused(f"asked for {expect}, file is dated {d}")
    out = pd.DataFrame({
        "date": pd.Timestamp(d),
        "symbol": df["symbol"].astype(str).str.strip(),
        "short_volume": pd.to_numeric(df["short_volume"], errors="coerce").astype("float64"),
        "short_exempt_volume": pd.to_numeric(df["short_exempt_volume"], errors="coerce").astype("float64"),
        "total_volume": pd.to_numeric(df["total_volume"], errors="coerce").astype("float64"),
        "market": df["market"].astype(str),
    })
    if out["short_volume"].isna().all():
        raise FinraRefused("no numeric ShortVolume in the file")
    # one row per symbol per day; FINRA does not repeat a symbol, but if it ever
    # did, the sum is the consolidated number
    if out["symbol"].duplicated().any():
        out = (out.groupby(["date", "symbol"], as_index=False)
               .agg(short_volume=("short_volume", "sum"),
                    short_exempt_volume=("short_exempt_volume", "sum"),
                    total_volume=("total_volume", "sum"), market=("market", "first")))
    return out.reset_index(drop=True)


def classify(status: int, content_type: str, body: bytes, d: date) -> tuple[str, Optional[pd.DataFrame]]:
    """('ok', frame) | ('not_published', None). Raises on anything untrustworthy."""
    ct = (content_type or "").lower()
    if status == 200:
        if "text/plain" not in ct and "octet-stream" not in ct:
            raise FinraRefused(f"{d}: 200 with content-type {content_type!r} (not text)")
        return "ok", parse_file(body, expect=d)
    if status in (403, 404) and (b"AccessDenied" in body or b"NoSuchKey" in body or status == 404):
        return "not_published", None
    raise FinraShortVolumeError(f"{d}: HTTP {status} {content_type!r} {body[:120]!r}")


# ── fetching ─────────────────────────────────────────────────────────────────

def http_fetch(url: str) -> tuple[int, str, bytes]:
    import requests
    r = requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    return r.status_code, r.headers.get("Content-Type", ""), r.content


# ── storage ──────────────────────────────────────────────────────────────────

def _days_dir(root: Path) -> Path:
    return root / "_days"


def _read_state(root: Path) -> dict:
    p = root / "state.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"not_published": []}


def _write_json(path: Path, obj) -> None:
    from backend.services.disk_guard import atomic_write_json
    atomic_write_json(path, obj, indent=1)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise FinraShortVolumeError(f"{path.name}: empty parquet write")
    tmp.replace(path)


def year_file(root: Path, year: int) -> Path:
    return root / f"year_{year}.parquet"


def dates_on_disk(root: Path) -> set[date]:
    """Every trade date already parsed (year files + staged days)."""
    got: set[date] = set()
    for f in sorted(root.glob("year_*.parquet")):
        s = pd.read_parquet(f, columns=["date"])["date"]
        got |= {x.date() for x in pd.to_datetime(s.unique())}
    dd = _days_dir(root)
    if dd.exists():
        for f in dd.glob("*.parquet"):
            got.add(datetime.strptime(f.stem, "%Y%m%d").date())
    return got


def weekdays(start: date, end: date) -> list[date]:
    return [x.date() for x in pd.bdate_range(start, end)]


def pull(start: date = START_DATE, end: date | None = None, *, root: Path | None = None,
         fetch: Callable[[str], tuple[int, str, bytes]] = http_fetch,
         sleep: Callable[[float], None] = time.sleep, pace_s: float = PACE_S,
         today: date | None = None, max_files: int | None = None,
         progress_every: int = 100) -> dict:
    """Fetch every missing weekday file in [start, end]; stage each parsed day.

    Returns a receipt dict. Raises `FinraRefused` on a non-text 200 (nothing is
    written for that day; earlier days stay staged, so a re-run resumes).
    """
    root = Path(root or default_root())
    today = today or datetime.now(timezone.utc).date()
    end = end or (today - timedelta(days=1))
    _days_dir(root).mkdir(parents=True, exist_ok=True)
    state = _read_state(root)
    known_missing = {date.fromisoformat(x) for x in state.get("not_published", [])}
    have = dates_on_disk(root)
    todo = [d for d in weekdays(start, end) if d not in have and d not in known_missing]
    rec = {"schema": "finra_short_volume/pull/1", "url_template": URL_TEMPLATE, "pit_rule": PIT_RULE,
           "start": str(start), "end": str(end), "already_on_disk": len(have),
           "known_not_published": len(known_missing), "to_fetch": len(todo),
           "fetched_ok": 0, "not_published": [], "not_published_recent_retry": [],
           "rows_fetched": 0, "stopped": None}
    n = 0
    try:
        for d in todo:
            if max_files is not None and n >= max_files:
                rec["stopped"] = f"max_files={max_files}"
                break
            if n:
                sleep(pace_s)
            n += 1
            status, ct, body = fetch(url_for(d))
            kind, df = classify(status, ct, body, d)
            if kind == "ok":
                _write_parquet(df, _days_dir(root) / f"{d:%Y%m%d}.parquet")
                rec["fetched_ok"] += 1
                rec["rows_fetched"] += int(len(df))
            elif (today - d).days > RETRY_RECENT_DAYS:
                known_missing.add(d)
                rec["not_published"].append(str(d))
            else:
                rec["not_published_recent_retry"].append(str(d))
            if progress_every and n % progress_every == 0:
                logger.info("finra: %d/%d (%s)", n, len(todo), d)
                print(f"  finra {n}/{len(todo)} through {d}  ok={rec['fetched_ok']}", flush=True)
    except FinraShortVolumeError as e:
        rec["stopped"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        state["not_published"] = sorted(str(x) for x in known_missing)
        _write_json(root / "state.json", state)
    return rec


def consolidate(root: Path | None = None) -> dict:
    """Fold staged days into `year_<YYYY>.parquet` and write the manifest.

    A year file is rewritten atomically with its old rows + the staged days;
    the staged day files are removed only after the year file is on disk.
    """
    root = Path(root or default_root())
    dd = _days_dir(root)
    staged = sorted(dd.glob("*.parquet")) if dd.exists() else []
    by_year: dict[int, list[Path]] = {}
    for f in staged:
        by_year.setdefault(int(f.stem[:4]), []).append(f)
    for y, files in sorted(by_year.items()):
        parts = [pd.read_parquet(f) for f in files]
        yf = year_file(root, y)
        if yf.exists():
            parts.insert(0, pd.read_parquet(yf))
        df = pd.concat(parts, ignore_index=True)
        df = (df.drop_duplicates(["date", "symbol"], keep="last")
              .sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True))
        df["market"] = df["market"].astype("category")
        _write_parquet(df, yf)
        for f in files:
            f.unlink()
    return write_manifest(root)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(root: Path | None = None) -> dict:
    root = Path(root or default_root())
    state = _read_state(root)
    years = {}
    tot_rows = 0
    all_dates: list[pd.Timestamp] = []
    for f in sorted(root.glob("year_*.parquet")):
        df = pd.read_parquet(f, columns=["date", "symbol"])
        ds = pd.to_datetime(df["date"].unique())
        all_dates += list(ds)
        years[f.stem[5:]] = {"file": f.name, "rows": int(len(df)), "dates": int(len(ds)),
                             "symbols": int(df["symbol"].nunique()),
                             "first": str(min(ds).date()), "last": str(max(ds).date()),
                             "bytes": f.stat().st_size, "sha256": _sha256(f)}
        tot_rows += len(df)
    man = {"schema": "finra_short_volume/manifest/1",
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": URL_TEMPLATE, "pit_rule": PIT_RULE,
           "not_short_interest": ("short SALE volume (executions flagged short, incl. market-"
                                  "maker hedging), off-exchange FINRA-reported venues only"),
           "rows": int(tot_rows), "dates": len(all_dates),
           "first": str(min(all_dates).date()) if all_dates else None,
           "last": str(max(all_dates).date()) if all_dates else None,
           "not_published_weekdays": len(state.get("not_published", [])),
           "years": years}
    _write_json(root / "manifest.json", man)
    return man


def load(root: Path | None = None, *, symbols: Iterable[str] | None = None,
         start: date | str | None = None, columns=("date", "symbol", "short_volume",
                                                    "total_volume")) -> pd.DataFrame:
    """Long frame from the year files (+ any staged days), optionally filtered."""
    root = Path(root or default_root())
    files = sorted(root.glob("year_*.parquet"))
    dd = _days_dir(root)
    if dd.exists():
        files += sorted(dd.glob("*.parquet"))
    if not files:
        raise FinraShortVolumeError(f"no FINRA short-volume files under {root} "
                                    f"(python -m scripts.pull_finra_short_volume)")
    keep = set(symbols) if symbols is not None else None
    t0 = pd.Timestamp(start) if start is not None else None
    parts = []
    for f in files:
        if t0 is not None and f.stem.startswith("year_") and int(f.stem[5:]) < t0.year:
            continue
        df = pd.read_parquet(f, columns=list(columns))
        if keep is not None:
            df = df[df["symbol"].isin(keep)]
        if t0 is not None:
            df = df[pd.to_datetime(df["date"]) >= t0]
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out.drop_duplicates(["date", "symbol"], keep="last").reset_index(drop=True)
