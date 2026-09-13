"""N-G — THE HIRING COLLECTOR. Public ATS job boards, no key, no LinkedIn, ever.

    python -m scripts.hiring_pull --probe --dry-run        # what it WOULD ask
    python -m scripts.hiring_pull --probe                  # build the board map
    python -m scripts.hiring_pull                          # today's snapshot
    python -m scripts.night_factory_jobs H1_hiring_pull

This is the file `backend/data/news_sources.yaml` has promised since the N-B
registry landed. Its row `greenhouse_lever_ashby_ats` says, in its own
`implemented_note`, that the collector "`scripts/hiring_pull.py`, not built
here" does not exist and that "a company -> board-token mapping table ... does
not exist yet", and `backend/services/lab_themes.py` reports the
`hiring_pivot_ai_v1` stream as `registered_awaiting_collector` for exactly that
reason. A registry row is a PROMISE to pull, not a puller. This file is the
puller and the mapping; the stream's readiness flips to `collector_present`
because the file exists, and NOT to "live" -- a collector that has run once is
not a graded hypothesis stream.

WHY AN ATS AND NOT LINKEDIN
===========================
LinkedIn is banned outright (roadmap lane N; the 2026-09-11 survey), so the
public applicant-tracking-system boards are the legal substitute: they are
unauthenticated read-only JSON, they are the company's own postings, and a
posting is a decision a firm made about the future before it shows up anywhere
in a filing.

THE THREE ENDPOINT SHAPES, VERIFIED LIVE ON 2026-09-13
======================================================
One request each, against a well-known board, before a line of parsing was
written. Shapes are READ, never assumed (`docs/TRIALS` house rule; the roadmap's
"every external claim carries a URL"):

| platform | request that was made | HTTP | shape |
|---|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/airbnb/jobs` | 200 | `{"jobs": [...], "meta": {...}}`, **164** jobs; job keys `id, title, updated_at, first_published, location{name}, absolute_url, company_name, internal_job_id, requisition_id` |
| Lever | `https://api.lever.co/v0/postings/leverdemo?mode=json` | 200 | a **bare JSON array**, 13 postings; keys `id, text (the title), categories{team,location,commitment}, createdAt, hostedUrl, workplaceType` |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/ashby` | 200 | `{"apiVersion": ..., "jobs": [...]}`, **71** jobs; keys `id, title, department, team, location, publishedAt, isListed, descriptionHtml` |

Three corrections to the spec's assumed shapes, found by making the requests:

1. **Lever returns an ARRAY, not an object.** A parser written against
   `{"postings": [...]}` would have counted zero jobs on every board and looked
   like a coverage problem rather than a parsing one.
2. **Greenhouse's `location` is an OBJECT** (`{"name": "..."}`), not a string,
   and `departments`/`offices` are absent without `?content=true` -- which this
   collector does not request, because it counts roles and does not need bodies.
3. **Ashby returns the full description HTML whether or not you want it**: the
   `ashby` board alone is **2,118,913 bytes** for 71 jobs (~30 KB a job). That
   is the single largest cost in the probe and it is why `MAX_BYTES` exists and
   why Ashby is probed LAST of the three.

These three requests are the only live calls this docstring's claims rest on.
**The tests never make one**: every test drives `_fetch` through an injected
stub, and the network guard in `backend/tests/conftest.py` would fail the suite
if one leaked.

THE BOARD MAP, AND WHY ITS MISSES ARE WRITTEN DOWN
==================================================
No company -> board-token table exists anywhere, and there is no registry of ATS
tenants to buy. So the map is built by PROBING a guessed token per platform, and
the receipt reports **probe attempts vs confirmed hits**, not hits alone: a
collector that printed "we cover 118 names" without the denominator would hide
its own false-negative rate, which here is large and structural. A company can
run Greenhouse under a token no rule generates (`spotifyjobs`, `acme-hq`), and
that is a MISS this file cannot distinguish from "has no board".

The probe is bounded on purpose, and the bound is the contract:

* **3 requests per symbol**, one per platform, one token guess each;
* **0.5 s between requests**, single-threaded;
* every request inside `news_pull.call_with_timeout`, because `urllib`'s own
  timeout bounds a socket READ and not the call -- 2026-09-13 paid for that with
  a two-hour TLS handshake to Alpaca;
* a response larger than `MAX_BYTES` is a MISS, not a parse.

So the whole band is one pass of 3 x N requests and its wall time is
`N * 3 * (0.5 + latency)`, which is stated in the receipt rather than estimated
in prose.

TWO TOKEN SHAPES, NOT ONE
=========================
`token_guess` emits the platform-idiomatic form, so the three requests are not
three copies of one guess:

* Greenhouse and Ashby: squashed lowercase alphanumerics (`airbnb`,
  `paloaltonetworks`);
* Lever: lowercase hyphenated (`palo-alto-networks`).

Both drop a trailing corporate suffix (`Inc`, `Corporation`, `Holdings`, `plc`,
...), because no ATS tenant is called `nvidia-corporation`.

THE PIT RULE, WHICH IS THE ONLY PART THAT COULD SILENTLY POISON A LABEL
=======================================================================
`first_seen_utc` is **this collector's own ingest clock**, the first time THIS
file observed that board -- never `updated_at` / `createdAt` / `publishedAt`.
Those are index-state fields an ATS can backfill or edit silently, exactly as
`news_sources.yaml` already records for Google News RSS, and a feature stamped
on one of them would be reading the future in a way no test would catch. The
registry row's `pit_grade` is `first_seen_only` and this file is what makes that
true rather than aspirational.

WHAT THIS FILE DOES NOT DO
==========================
It computes no feature, fits nothing, labels nothing and ranks nothing. N-G
(TRIAL-HIRING-PIVOT-1) is not written yet, and `label_source` stays `false` in
the registry until it is. The AI-title vocabulary below is stated here for the
first time and is frozen HERE so the prereg can cite it rather than re-derive
it; the flag is recorded per row and no selection uses it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from scripts.news_pull import call_with_timeout  # noqa: E402

JOB = "H1_hiring_pull"

#: The three platforms, probed in this order. Ashby is LAST because it returns
#: every posting's full description whether asked or not (2.1 MB for 71 jobs,
#: measured 2026-09-13) and a bounded probe should spend its cheap requests
#: first.
PLATFORMS = ("greenhouse", "lever", "ashby")

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}

#: Named, and honest about what it is: a research crawler with a contact URL.
USER_AGENT = ("aegis-finance-research/1.0 "
              "(+https://github.com/Murathanx12/Aegis-Finance)")

#: Per-request wall bound, inside `call_with_timeout` (a thread box, so a hung
#: TLS handshake is abandoned rather than waited on).
REQUEST_TIMEOUT_S = 20.0

#: Seconds between requests. Single-threaded, so this IS the rate limit. The
#: registry row records `min_interval_s: 1.0` as a per-SOURCE courtesy; 0.5 s
#: across three different hosts is 1.5 s per host per symbol.
PACE_S = 0.5

#: Requests per symbol in the probe. One token guess per platform, and the
#: number is a CONTRACT, not a default: `probe_symbol` asserts it.
REQUESTS_PER_SYMBOL = 3

#: A response bigger than this is refused unparsed. Ashby's own board is 2.1 MB,
#: so the cap has to clear that with room; what it stops is a board that would
#: swap the probe's wall time for one company's blog.
MAX_BYTES = 12 * 1024 * 1024

#: Corporate suffixes dropped before a token is guessed. No ATS tenant is called
#: `nvidia-corporation`.
_SUFFIXES = (
    "incorporated", "corporation", "company", "holdings", "holding", "group",
    "limited", "ltd", "llc", "plc", "nv", "sa", "ag", "co", "corp", "inc",
    "class a", "class b", "class c", "the",
)

#: THE AI-TITLE VOCABULARY, STATED HERE FIRST. `TRIAL-HIRING-PIVOT-1` does not
#: exist on disk yet (checked 2026-09-13: no file under `docs/TRIALS/` names it),
#: so there is nothing to reuse and this is the first statement of it. It is
#: frozen here so the prereg can CITE it rather than re-derive a second list
#: that would quietly differ. Matched case-insensitively on word boundaries.
AI_TITLE_TERMS = (
    "ai", "a.i.", "ml", "machine learning", "artificial intelligence",
    "deep learning", "data scientist", "data science", "llm",
    "large language model", "applied scientist", "research scientist",
    "nlp", "natural language processing", "computer vision", "mlops",
    "generative ai", "genai",
)
_AI_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in AI_TITLE_TERMS)
    + r")(?![a-z0-9])", re.IGNORECASE)


class ProbeRefused(RuntimeError):
    """The probe cannot run and says why. Never a silent empty pass."""


# --------------------------------------------------------------------- paths

def hiring_dir() -> Path:
    return Path(_config.DATA_DIR) / "optimus" / "hiring"


def board_map_path() -> Path:
    return hiring_dir() / "board_map.json"


def cursor_path() -> Path:
    return hiring_dir() / "cursor.json"


def snapshot_path(day: str) -> Path:
    return hiring_dir() / f"{day}.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


# ------------------------------------------------------------------ the band

def tradable_band() -> tuple[list[str], dict]:
    """The symbols to probe: the tradable band, READ from its one definition.

    `scripts/analyst_snapshot._symbols(None, "tradable")` reads
    `night_f_seasonality_export.load_universe`, which applies the $10M
    median-dollar-volume floor, the $5 price minimum and the ETF flag to the
    execution repo's own stored universe. Three copies of that filter would be
    three things to keep in step; this is the second CALLER, not a second
    definition.
    """
    from scripts.analyst_snapshot import _symbols

    return _symbols(None, "tradable")


def issuer_names() -> dict[str, str]:
    """{SYMBOL: company name} from the version-controlled name table."""
    from backend.services import news_entities as entities

    path = entities.entities_dir() / "issuers.csv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("symbol") or "").strip().upper()
            name = (row.get("primary_name") or "").strip()
            if sym and name:
                out[sym] = name
    return out


# ---------------------------------------------------------------- the guesses

def _core_words(name: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    words = [w for w in cleaned.split() if w]
    while words and words[-1] in _SUFFIXES:
        words.pop()
    # "The Walt Disney Company" -> drop a leading article too
    if words and words[0] == "the":
        words = words[1:]
    return words


def token_guess(name: str, platform: str) -> str:
    """One platform-idiomatic token guess, or `""` when nothing is guessable.

    Greenhouse and Ashby tenants are squashed lowercase (`airbnb`); Lever's are
    hyphenated (`palo-alto-networks`). Emitting one SHAPE per platform is what
    makes three requests three different questions instead of three copies of
    one -- and the shape used is recorded beside every hit and every miss, so a
    later pass can tell "guessed wrong" from "has no board".
    """
    words = _core_words(name)
    if not words:
        return ""
    if platform == "lever":
        return "-".join(words)
    return "".join(words)


def is_ai_titled(title: str) -> bool:
    return bool(_AI_RE.search(title or ""))


# ------------------------------------------------------------------ fetching

def _fetch(url: str) -> tuple[int, bytes]:
    """`(status, body)`. THE network door -- every test replaces this one name.

    A non-200 comes back as its status with an empty body rather than an
    exception, because a 404 from an ATS is the ANSWER to the probe's question
    ("does this company run a board under this token?") and not an error.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
            return int(r.status), r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def parse_jobs(platform: str, payload) -> list[dict] | None:
    """The three shapes, normalised to `[{job_id, title, location, stamp}]`.

    `None` means "this is not a board response" -- which is a MISS, never an
    empty board. The difference matters: a parser that returned `[]` for a
    malformed payload would record every parse failure as a company that is not
    hiring.
    """
    if platform == "greenhouse":
        if not isinstance(payload, dict) or "jobs" not in payload:
            return None
        raw = payload.get("jobs") or []
        return [{"job_id": str(j.get("id") or ""),
                 "title": str(j.get("title") or ""),
                 "location": str((j.get("location") or {}).get("name") or ""),
                 "source_stamp": str(j.get("updated_at") or "")}
                for j in raw if isinstance(j, dict)]
    if platform == "lever":
        # VERIFIED 2026-09-13: a bare ARRAY, not an object. The spec assumed an
        # object; a parser written to that would have read every board as empty.
        if not isinstance(payload, list):
            return None
        return [{"job_id": str(j.get("id") or ""),
                 "title": str(j.get("text") or ""),
                 "location": str((j.get("categories") or {}).get("location") or ""),
                 "source_stamp": str(j.get("createdAt") or "")}
                for j in payload if isinstance(j, dict)]
    if platform == "ashby":
        if not isinstance(payload, dict) or "jobs" not in payload:
            return None
        raw = payload.get("jobs") or []
        return [{"job_id": str(j.get("id") or ""),
                 "title": str(j.get("title") or ""),
                 "location": str(j.get("location") or ""),
                 "source_stamp": str(j.get("publishedAt") or "")}
                for j in raw if isinstance(j, dict)
                if j.get("isListed") is not False]
    raise ProbeRefused(f"unknown platform {platform!r}")


def fetch_board(platform: str, token: str, *,
                fetch: Callable[[str], tuple[int, bytes]] | None = None) -> dict:
    """One board, one request. Never raises; every outcome is named."""
    fetch = fetch or _fetch
    url = ENDPOINTS[platform].format(token=token)
    try:
        status, body = call_with_timeout(lambda: fetch(url), REQUEST_TIMEOUT_S,
                                         f"{platform}:{token}")
    except Exception as exc:  # noqa: BLE001 -- the outcome IS the record
        return {"platform": platform, "token": token, "url": url, "hit": False,
                "status": None, "why": f"{type(exc).__name__}: {exc}"}
    if status != 200:
        return {"platform": platform, "token": token, "url": url, "hit": False,
                "status": status, "why": f"HTTP {status}"}
    if len(body) > MAX_BYTES:
        return {"platform": platform, "token": token, "url": url, "hit": False,
                "status": status, "why": f"body > {MAX_BYTES} bytes; refused unparsed"}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"platform": platform, "token": token, "url": url, "hit": False,
                "status": status, "why": f"unparseable JSON: {exc}"}
    jobs = parse_jobs(platform, payload)
    if jobs is None:
        return {"platform": platform, "token": token, "url": url, "hit": False,
                "status": status, "why": "200 but not a board response shape"}
    if not jobs:
        # A REAL board with zero open roles is a hit with n_open 0. It is also
        # indistinguishable from a tenant that was deleted, so it is recorded as
        # a hit and the count carries the ambiguity rather than a boolean.
        return {"platform": platform, "token": token, "url": url, "hit": True,
                "status": status, "jobs": [], "n_open": 0,
                "why": "board responded with zero open roles"}
    return {"platform": platform, "token": token, "url": url, "hit": True,
            "status": status, "jobs": jobs, "n_open": len(jobs), "why": "ok"}


# -------------------------------------------------------------------- probing

def probe_symbol(symbol: str, name: str, *, pace_s: float = PACE_S,
                 fetch: Callable[[str], tuple[int, bytes]] | None = None,
                 platforms: tuple[str, ...] = PLATFORMS) -> dict:
    """At most `REQUESTS_PER_SYMBOL` requests, and the first hit wins.

    Stopping at the first hit is a saving, not a policy: a company with boards on
    two platforms is vanishingly rare and the probe's budget is the scarce thing.
    Every attempt -- hit or miss -- is recorded with the token that was tried, so
    a later pass can tell a wrong guess from an absent board.
    """
    attempts, board = [], None
    for i, platform in enumerate(platforms):
        token = token_guess(name, platform)
        if not token:
            attempts.append({"platform": platform, "token": "", "hit": False,
                             "why": "no token could be guessed from the name"})
            continue
        if i and pace_s:
            time.sleep(pace_s)
        res = fetch_board(platform, token, fetch=fetch)
        attempts.append({k: v for k, v in res.items() if k != "jobs"})
        if res["hit"]:
            board = {"platform": platform, "token": token,
                     "n_open_at_probe": res["n_open"],
                     "first_seen_utc": _iso()}
            break
    assert len(attempts) <= REQUESTS_PER_SYMBOL, (
        f"{symbol}: {len(attempts)} attempts exceeds the declared budget of "
        f"{REQUESTS_PER_SYMBOL} per symbol")
    return {"symbol": symbol, "name": name, "board": board,
            "attempts": attempts, "requests": sum(1 for a in attempts
                                                  if a.get("status") is not None
                                                  or a.get("why", "").startswith(
                                                      ("HTTPError", "CallTimeout",
                                                       "FetchError")))}


def load_board_map() -> dict:
    p = board_map_path()
    if not p.is_file():
        return {"boards": {}, "misses": {}, "probed": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"boards": {}, "misses": {}, "probed": []}
    d.setdefault("boards", {})
    d.setdefault("misses", {})
    d.setdefault("probed", [])
    return d


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def build_board_map(*, limit: int | None = None, pace_s: float = PACE_S,
                    dry_run: bool = False, resume: bool = True,
                    fetch: Callable[[str], tuple[int, bytes]] | None = None,
                    symbols: list[str] | None = None,
                    names: dict[str, str] | None = None,
                    checkpoint_every: int = 50) -> dict:
    """Probe the band and write `board_map.json`. Bounded, resumable, honest.

    RESUMABLE because the pass is an hour of somebody else's rate limit: a kill,
    a reboot or a crash must not make it start again from ADBE. The lesson is
    `G3_evolve_v2`'s (2026-09-10, 340 generations lost to a job that only wrote
    at exit); the fix is the same one -- checkpoint per unit of work.
    """
    t0 = time.time()
    if symbols is None:
        symbols, band_prov = tradable_band()
    else:
        band_prov = {"universe": "explicit", "n_available": len(symbols),
                     "source": "passed in by the caller",
                     "filter": "none -- the caller chose these names"}
    names = issuer_names() if names is None else names
    if not symbols:
        raise ProbeRefused("the tradable band resolved to zero symbols")

    state = load_board_map() if resume else {"boards": {}, "misses": {}, "probed": []}
    done = set(state["probed"])
    todo = [s for s in symbols if s not in done]
    if limit:
        todo = todo[:limit]

    named = [s for s in todo if names.get(s)]
    unnamed = [s for s in todo if not names.get(s)]

    plan = {
        "symbols_in_band": len(symbols),
        "already_probed": len(done & set(symbols)),
        "to_probe_this_pass": len(named),
        "no_company_name_so_unprobeable": len(unnamed),
        "requests_planned": len(named) * REQUESTS_PER_SYMBOL,
        "pace_s": pace_s,
        "projected_wall_min_at_pace_only": round(
            len(named) * REQUESTS_PER_SYMBOL * pace_s / 60.0, 1),
        "projected_wall_min_with_300ms_latency": round(
            len(named) * REQUESTS_PER_SYMBOL * (pace_s + 0.3) / 60.0, 1),
    }
    if dry_run:
        return {
            "job": JOB, "step": "probe", "dry_run": True, "ran": False,
            "universe": band_prov, "plan": plan,
            "sample_guesses": [
                {"symbol": s, "name": names[s],
                 **{p: token_guess(names[s], p) for p in PLATFORMS}}
                for s in named[:8]],
            "headline": (f"DRY RUN: would make {plan['requests_planned']:,} "
                         f"requests over {plan['to_probe_this_pass']:,} names "
                         f"(~{plan['projected_wall_min_with_300ms_latency']} min)"),
            "written_utc": _iso(),
        }

    hits = 0
    for i, sym in enumerate(named):
        rec = probe_symbol(sym, names[sym], pace_s=pace_s, fetch=fetch)
        state["probed"].append(sym)
        if rec["board"]:
            state["boards"][sym] = rec["board"]
            hits += 1
        else:
            state["misses"][sym] = {
                "name": names[sym],
                "tried": [{"platform": a["platform"], "token": a["token"],
                           "why": a.get("why")} for a in rec["attempts"]],
                "probed_utc": _iso(),
            }
        if i and pace_s:
            time.sleep(pace_s)
        if checkpoint_every and (i + 1) % checkpoint_every == 0:
            state["checkpoint_utc"] = _iso()
            _write_json(board_map_path(), state)
            print(f"  probe {i + 1}/{len(named)} names, {hits} board(s) found "
                  f"({(time.time() - t0) / (i + 1):.2f}s/name)", flush=True)

    for sym in unnamed:
        state["misses"].setdefault(sym, {
            "name": "", "tried": [],
            "why": "no company name in issuers.csv, so no token could be guessed",
            "probed_utc": _iso()})
        state["probed"].append(sym)

    state["updated_utc"] = _iso()
    _write_json(board_map_path(), state)

    covered = len(state["boards"])
    probed = len(set(state["probed"]) & set(symbols))
    by_platform: dict[str, int] = {}
    for b in state["boards"].values():
        by_platform[b["platform"]] = by_platform.get(b["platform"], 0) + 1
    return {
        "job": JOB, "step": "probe", "dry_run": False, "ran": True,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "universe": band_prov, "plan": plan,
        "path": str(board_map_path()),
        "names_probed_this_pass": len(named),
        "boards_found_this_pass": hits,
        "coverage": {
            "symbols_with_a_board": covered,
            "symbols_probed": probed,
            "symbols_in_band": len(symbols),
            "rate_of_probed": round(covered / probed, 4) if probed else None,
            "rate_of_band": round(covered / len(symbols), 4) if symbols else None,
            "by_platform": by_platform,
            "denominator_note": (
                "attempts vs confirmed hits, never hits alone. A MISS here is "
                "'no board answered ONE guessed token on three platforms' and "
                "is NOT 'this company has no board' -- a tenant under an "
                "unguessable token (spotifyjobs, acme-hq) is indistinguishable "
                "from an absent one at this budget, so the false-negative rate "
                "is structural and unmeasured."),
        },
        "wall_s": round(time.time() - t0, 1),
        "rate_s_per_name": round((time.time() - t0) / len(named), 3) if named else None,
        "written_utc": _iso(),
        "headline": (f"{covered:,} board(s) over {probed:,} probed of "
                     f"{len(symbols):,} band names "
                     f"({(covered / probed * 100 if probed else 0):.1f}% of probed)"),
    }


# ------------------------------------------------------------ the daily rows

def load_cursor() -> dict:
    p = cursor_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def snapshot(*, day: str | None = None, limit: int | None = None,
             pace_s: float = PACE_S, dry_run: bool = False,
             fetch: Callable[[str], tuple[int, bytes]] | None = None) -> dict:
    """One row per (symbol, board) into `<date>.jsonl`, plus the cursor.

    The row is `{symbol, board, n_open, n_new_since_last, first_seen_utc}` plus
    provenance. `n_new_since_last` is computed against the CURSOR's set of job
    ids for that board -- so it is "new to us", which is the only kind of new a
    `first_seen_only` source can honestly claim. On a board's first ever
    observation `n_new_since_last` is `None`, not `n_open`: every role is new to
    us and none of them is news, and writing `n_open` there would put a spike in
    the series on the day we started looking.
    """
    t0 = time.time()
    observed = _now()
    day = day or observed.date().isoformat()
    state = load_board_map()
    boards = state.get("boards") or {}
    if not boards:
        return {"job": JOB, "step": "snapshot", "ran": False,
                "refused": (f"no boards in {board_map_path()}; run "
                            f"`python -m scripts.hiring_pull --probe` first. A "
                            f"snapshot over zero boards is not an empty day, it "
                            f"is a missing map."),
                "headline": "REFUSED: no board map", "written_utc": _iso()}

    syms = sorted(boards)
    if limit:
        syms = syms[:limit]
    cursor = load_cursor()

    if dry_run:
        return {"job": JOB, "step": "snapshot", "dry_run": True, "ran": False,
                "boards": len(syms),
                "requests_planned": len(syms),
                "projected_wall_min": round(len(syms) * (pace_s + 0.3) / 60.0, 1),
                "path": str(snapshot_path(day)),
                "headline": f"DRY RUN: would poll {len(syms):,} board(s) for {day}",
                "written_utc": _iso()}

    rows, errors = [], []
    counts = {"ok": 0, "empty": 0, "error": 0, "first_observation": 0}
    for i, sym in enumerate(syms):
        b = boards[sym]
        if i and pace_s:
            time.sleep(pace_s)
        res = fetch_board(b["platform"], b["token"], fetch=fetch)
        key = f"{sym}:{b['platform']}:{b['token']}"
        prev = cursor.get(key) or {}
        seen_before = set(prev.get("job_ids") or [])
        if not res["hit"]:
            counts["error"] += 1
            if len(errors) < 20:
                errors.append(f"{sym}: {res.get('why')}")
            rows.append({
                "symbol": sym, "board": f"{b['platform']}:{b['token']}",
                "n_open": None, "n_new_since_last": None,
                "first_seen_utc": prev.get("first_seen_utc") or b.get("first_seen_utc"),
                "observed_date": day, "observed_utc": _iso(observed),
                "status": "error", "error": res.get("why"),
            })
            continue
        jobs = res.get("jobs") or []
        ids = [j["job_id"] for j in jobs if j.get("job_id")]
        first_time = not prev
        if first_time:
            counts["first_observation"] += 1
            n_new = None
        else:
            n_new = len([j for j in ids if j not in seen_before])
        counts["ok" if jobs else "empty"] += 1
        first_seen = prev.get("first_seen_utc") or b.get("first_seen_utc") or _iso(observed)
        rows.append({
            "symbol": sym, "board": f"{b['platform']}:{b['token']}",
            "n_open": len(jobs), "n_new_since_last": n_new,
            "first_seen_utc": first_seen,
            "observed_date": day, "observed_utc": _iso(observed),
            "platform": b["platform"], "token": b["token"],
            "n_ai_titled": sum(1 for j in jobs if is_ai_titled(j.get("title", ""))),
            "ai_title_share": (round(sum(1 for j in jobs
                                         if is_ai_titled(j.get("title", ""))) / len(jobs), 4)
                               if jobs else None),
            "status": "ok",
            "first_observation": first_time,
        })
        cursor[key] = {"job_ids": ids, "last_date": day,
                       "first_seen_utc": first_seen,
                       "last_observed_utc": _iso(observed)}

    path = snapshot_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n",
                    encoding="utf-8")
    _write_json(cursor_path(), cursor)

    probed = len(set(state.get("probed") or []))
    band_n = probed or len(boards)
    receipt = {
        "job": JOB, "step": "snapshot", "ran": True,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "date": day, "observed_utc": _iso(observed),
        "rows": len(rows), "by_status": counts,
        "path": str(path), "cursor": str(cursor_path()),
        "coverage": {
            "symbols_with_a_board": len(boards),
            "symbols_probed": probed,
            "rate_of_probed": round(len(boards) / probed, 4) if probed else None,
            "denominator_note": ("names with a board / names probed. The "
                                 "denominator travels with the number every "
                                 "time it is quoted."),
        },
        "pit_rule": (
            "first_seen_utc is THIS collector's own ingest clock, never the "
            "source's updated_at/createdAt/publishedAt -- those are index-state "
            "fields an ATS can backfill silently, and a feature stamped on one "
            "would read the future in a way no test would catch."),
        "n_new_is_new_to_us": (
            "n_new_since_last counts job ids absent from OUR cursor, and is "
            "None on a board's first observation rather than n_open -- "
            "otherwise the series carries a spike on the day we started "
            "looking."),
        "labels": ("none. TRIAL-HIRING-PIVOT-1 is not written; `label_source` "
                   "stays false in news_sources.yaml. `n_ai_titled` is recorded "
                   "and used by nothing."),
        "errors_first_20": errors,
        "wall_s": round(time.time() - t0, 1),
        "written_utc": _iso(),
        "headline": (f"{len(rows):,} board row(s) for {day}; "
                     f"{counts['ok']:,} answered, {counts['error']:,} failed; "
                     f"coverage {len(boards):,}/{band_n:,} probed"),
    }
    _write_json(hiring_dir() / f"{day}_receipt.json", receipt)
    return receipt


# ------------------------------------------------------------------- the job

def H1_hiring_pull(*, smoke: bool = False, probe: bool = False,   # noqa: N802
                   limit: int | None = None, dry_run: bool = False) -> dict:
    """The night-factory entry point. Snapshot by default; `probe` rebuilds the map.

    A smoke run is the DRY RUN of both steps: this job's only side effect is
    network traffic against somebody else's rate limit, so "prove it runs" must
    not mean "make 7,000 requests".
    """
    if smoke:
        dry_run = True
    if probe:
        return build_board_map(limit=limit, dry_run=dry_run)
    return snapshot(limit=limit, dry_run=dry_run)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--probe", action="store_true",
                    help="build/extend the board-token map instead of snapshotting")
    ap.add_argument("--limit", type=int, default=None,
                    help="bound the pass to this many symbols/boards")
    ap.add_argument("--pace", type=float, default=PACE_S,
                    help="seconds between requests (single-threaded)")
    ap.add_argument("--no-resume", action="store_true",
                    help="probe every name again rather than continuing the map")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and the guesses; make no request")
    a = ap.parse_args(argv)
    if a.probe:
        out = build_board_map(limit=a.limit, pace_s=a.pace, dry_run=a.dry_run,
                              resume=not a.no_resume)
    else:
        out = snapshot(limit=a.limit, pace_s=a.pace, dry_run=a.dry_run)
    print(json.dumps(out, indent=1, default=str))
    return 0


__all__ = ["AI_TITLE_TERMS", "ENDPOINTS", "H1_hiring_pull", "MAX_BYTES",
           "PACE_S", "PLATFORMS", "REQUESTS_PER_SYMBOL", "ProbeRefused",
           "board_map_path", "build_board_map", "cursor_path", "fetch_board",
           "hiring_dir", "is_ai_titled", "issuer_names", "load_board_map",
           "load_cursor", "parse_jobs", "probe_symbol", "snapshot",
           "snapshot_path", "token_guess", "tradable_band"]


if __name__ == "__main__":
    raise SystemExit(main())
