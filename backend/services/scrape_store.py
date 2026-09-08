"""A resumable raw-document store: cursor, log, PID file, incremental receipt.

    from backend.services.scrape_store import ScrapeStore
    store = ScrapeStore("gdelt")
    store.begin()                       # writes the PID file and opens the log
    store.put(url, status, body)        # one raw document, with provenance
    store.advance("2026-09-07T12:15Z")  # the cursor moves AFTER the write
    store.finish()

WHY RESUMABILITY IS THE REQUIREMENT AND NOT A NICETY
====================================================
The news backfill died on 2026-09-07 at 03:18, 112 of 134 months in -- **83.6%**
-- and every one of those months had to be re-fetched, because the job kept its
progress in a local variable, wrote its coverage receipt only at the end, and
left no log. A pull that cannot resume is a pull whose cost is multiplied by the
probability that anything interrupts it, and over 6 hours on a laptop that
probability is not small.

So the invariant is: **after every single document, the disk knows enough to
continue.** Not after every page, not after every month. The cursor is written
after the document it describes, never before -- a cursor ahead of its data
skips work silently, which is worse than doing it twice.

THE RAW BODY IS THE ARTEFACT
============================
`put` stores the bytes that came off the wire, gzipped, with the URL, the fetch
timestamp, the HTTP status and the SHA-256 of the body. Parsing is a SEPARATE,
re-runnable step. Every time this repo has stored a parsed summary instead, the
next question needed a field the parser dropped and the fetch had to be paid
again -- and a re-fetch of news is not even the same data, because the source
edits and expires it.

`status` is stored for non-200s too. A 404 or a 429 is a FACT about coverage; a
store that keeps only successes cannot tell "we looked and it was not there"
from "we never looked", which is the shape of the WRDS pull that reported
COMPLETE with seven tables never attempted.

WHAT THIS DOES NOT DO
=====================
It does not parse, rank, size or decide. It is a disk with provenance.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: Everything lands under the repo's data dir, one directory per source.
ROOT = Path(__file__).resolve().parents[1] / "data" / "scrape"

#: Named so a fetcher cannot invent its own. A site that blocks a generic agent
#: is telling us something; a site that blocks THIS one can mail the address.
USER_AGENT = ("AegisFinanceResearchBot/1.0 (+https://github.com/Murathanx12/"
              "Aegis-Finance; research use; contact via repo issues)")

SCHEMA_VERSION = 1


class ScrapeRefusal(RuntimeError):
    """An input the store needs was not supplied. It refuses rather than guesses.

    A store handed an empty URL, an empty source name or a body of `None` and
    carrying on is a store that writes rows nobody can trace back to a fetch.
    Provenance that is optional is provenance that is absent exactly when it
    matters.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_of(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class DocRecord:
    """One row of the index. The BODY is not here -- it is the file this names.

    Keeping the index separate from the bodies is what lets a resume read
    100,000 rows of provenance in a second without touching a gigabyte of HTML.
    """
    doc_id: str
    source: str
    url: str
    fetched_at: str
    http_status: int
    sha256: str
    n_bytes: int
    path: str
    cursor: str | None = None
    meta: dict | None = None


class ScrapeStore:
    """One source's store: bodies, an index, a cursor, a log, a PID, a receipt."""

    def __init__(self, source: str, root: Path | None = None) -> None:
        if not (source or "").strip():
            raise ScrapeRefusal(
                "a store needs a SOURCE name: it names the directory, the cursor "
                "and the receipt. An unnamed store is one that cannot be resumed "
                "because nothing can find it.")
        self.source = source.strip()
        self.dir = (root or ROOT) / self.source
        self.bodies = self.dir / "bodies"
        self.index_path = self.dir / "index.jsonl"
        self.cursor_path = self.dir / "cursor.json"
        self.log_path = self.dir / "pull.log"
        self.pid_path = self.dir / "pull.pid"
        self.receipt_path = self.dir / "coverage.json"
        self._log_fh = None
        self._t0 = time.monotonic()
        self._seen: set[str] | None = None

    # ── lifecycle ───────────────────────────────────────────────────────────
    def begin(self, *, argv: list[str] | None = None) -> "ScrapeStore":
        """Create the directories, claim the PID file, open the log.

        The PID file is written so a human can find and stop THIS process by its
        number. Killing by image name once took out two other agents' jobs, a
        test suite, ~1,676 already-billed extractions and the MCP server; the
        cheap half of the fix is that every long job writes down its own pid.
        """
        self.bodies.mkdir(parents=True, exist_ok=True)
        stale = self._stale_pid()
        self.pid_path.write_text(json.dumps({
            "pid": os.getpid(), "started_at": _now(), "argv": argv or [],
            "previous": stale}, indent=1), encoding="utf-8")
        self._log_fh = self.log_path.open("a", encoding="utf-8")
        self.log(f"BEGIN pid={os.getpid()} source={self.source} "
                 f"cursors={self.cursors()} already_stored={len(self.seen())}")
        if stale:
            self.log(f"NOTE previous run left pid={stale.get('pid')} "
                     f"started_at={stale.get('started_at')} -- if that process "
                     "is gone this is a RESUME after a crash")
        return self

    def _stale_pid(self) -> dict | None:
        if not self.pid_path.exists():
            return None
        try:
            return json.loads(self.pid_path.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            return {"pid": None, "note": "unreadable pid file"}

    def log(self, msg: str) -> None:
        """A line on disk, not only in a terminal nobody was watching.

        The 83.6% failure had no log, so the only evidence of where it stopped
        was the absence of files -- which cannot distinguish "died here" from
        "was never asked for that".
        """
        line = f"{_now()} {msg}"
        logger.info("[%s] %s", self.source, msg)
        if self._log_fh is not None:
            self._log_fh.write(line + "\n")
            self._log_fh.flush()

    def finish(self, *, note: str = "") -> dict:
        rec = self.receipt(note=note)
        self.log(f"END docs={rec['n_docs']} bytes={rec['n_bytes']} "
                 f"cursors={rec['cursors']} {note}")
        if self._log_fh is not None:
            self._log_fh.close()
            self._log_fh = None
        # The PID file is REMOVED on a clean finish and LEFT on a crash. Its
        # presence at the next `begin` is therefore evidence of a crash, which
        # is the one thing the previous puller could not tell anybody.
        self.pid_path.unlink(missing_ok=True)
        return rec

    # ── the cursor ──────────────────────────────────────────────────────────
    #
    # CURSORS ARE NAMED, and the reason is a bug this file's author wrote on the
    # first pass. With ONE cursor per source, a rolling "last hour" run left the
    # cursor at 09:45, and a later backfill asked for 04:00-08:00, fast-forwarded
    # itself to 10:00, fetched ZERO stamps and reported success. A cursor that
    # skips work while reporting success is precisely the failure this store
    # exists to prevent, wearing a resume's clothes. A cursor answers "how far
    # did THIS traversal get", so it is keyed by the traversal.
    def _cursors(self) -> dict:
        if not self.cursor_path.exists():
            return {}
        try:
            d = json.loads(self.cursor_path.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            self.log("WARN cursor file unreadable; treating as NO cursor. That "
                     "re-does work, which is the safe direction -- a corrupt "
                     "cursor read optimistically silently skips it instead.")
            return {}
        return d.get("cursors", {}) if isinstance(d, dict) else {}

    def cursor(self, key: str = "default") -> str | None:
        row = self._cursors().get(key)
        return None if row is None else row.get("cursor")

    def cursors(self) -> dict:
        """Every traversal this source has a position for."""
        return self._cursors()

    def advance(self, cursor: str, *, key: str = "default",
                n_docs: int | None = None) -> None:
        """Move one named cursor. Call AFTER its documents are on disk.

        A cursor written before its data is a cursor that skips work silently on
        the next run. Doing a page twice is cheap and visible; missing one is
        neither -- so the write order is body, index, cursor, always.
        """
        cur = self._cursors()
        cur[key] = {"cursor": cursor, "updated_at": _now(),
                    "n_docs_total": self.count() if n_docs is None else n_docs}
        self.cursor_path.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION, "source": self.source,
            "cursors": cur}, indent=1), encoding="utf-8")

    # ── the documents ───────────────────────────────────────────────────────
    def seen(self) -> set[str]:
        """The doc_ids already stored. Read once, kept in memory, updated on put."""
        if self._seen is None:
            self._seen = set()
            if self.index_path.exists():
                with self.index_path.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            self._seen.add(json.loads(line)["doc_id"])
                        except Exception:                       # noqa: BLE001
                            # A torn last line is the NORMAL shape of a crash
                            # mid-append. It is skipped, counted and logged --
                            # never silently repaired, because a repaired index
                            # is an index whose gaps are invisible.
                            self.log("WARN unreadable index line skipped")
        return self._seen

    def count(self) -> int:
        return len(self.seen())

    def doc_id_for(self, url: str) -> str:
        if not (url or "").strip():
            raise ScrapeRefusal(
                "a document needs its SOURCE URL. Provenance that is optional "
                "is provenance that is absent exactly when somebody asks where "
                "a number came from.")
        return hashlib.sha256(f"{self.source}|{url.strip()}".encode()).hexdigest()[:24]

    def has(self, url: str) -> bool:
        return self.doc_id_for(url) in self.seen()

    def put(self, url: str, http_status: int, body: bytes, *,
            cursor: str | None = None, meta: dict | None = None) -> DocRecord:
        """Store one RAW body plus its provenance. Idempotent by (source, url)."""
        if body is None:
            raise ScrapeRefusal(
                f"body is None for {url!r}. A missing body is not an empty "
                "document: store b'' with the status that explains it, so the "
                "difference between 'we looked and got nothing' and 'we never "
                "looked' survives to the next reader.")
        doc_id = self.doc_id_for(url)
        digest = sha256_of(body)
        # Sharded two levels: 65,536 leaf directories, so a million documents
        # never put more than a few dozen files in one folder. NTFS degrades
        # badly well before a million entries in a single directory.
        rel = Path(doc_id[:2]) / doc_id[2:4] / f"{doc_id}.gz"
        path = self.bodies / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(body))
        rec = DocRecord(doc_id=doc_id, source=self.source, url=url,
                        fetched_at=_now(), http_status=int(http_status),
                        sha256=digest, n_bytes=len(body),
                        path=str(rel).replace("\\", "/"),
                        cursor=cursor, meta=meta or {})
        # BODY FIRST, THEN INDEX. The reverse order produces an index row
        # pointing at a file that does not exist, and a resume that trusts its
        # index then reports coverage it does not have.
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec)) + "\n")
        self.seen().add(doc_id)
        return rec

    def read_body(self, rec: DocRecord | dict) -> bytes:
        rel = rec["path"] if isinstance(rec, dict) else rec.path
        return gzip.decompress((self.bodies / rel).read_bytes())

    def records(self):
        """Every index row, in the order written."""
        if not self.index_path.exists():
            return
        with self.index_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:                               # noqa: BLE001
                    continue

    # ── the receipt, written AS IT GOES ─────────────────────────────────────
    def receipt(self, *, note: str = "", write: bool = True) -> dict:
        """Coverage by day and by status, written incrementally.

        Written every N documents by the puller rather than once at the end,
        because a receipt that only exists at the end is a receipt that does not
        exist for any run that fails -- and the runs that fail are the ones whose
        coverage somebody urgently needs to know.
        """
        by_day: dict[str, int] = {}
        by_status: dict[str, int] = {}
        n = 0
        n_bytes = 0
        for r in self.records():
            n += 1
            n_bytes += int(r.get("n_bytes") or 0)
            by_day[str(r.get("fetched_at", ""))[:10]] = \
                by_day.get(str(r.get("fetched_at", ""))[:10], 0) + 1
            k = str(r.get("http_status"))
            by_status[k] = by_status.get(k, 0) + 1
        rec = {
            "source": self.source,
            "schema_version": SCHEMA_VERSION,
            "written_at": _now(),
            "cursors": self.cursors(),
            "n_docs": n,
            "n_bytes": n_bytes,
            "by_fetch_day": dict(sorted(by_day.items())),
            "by_http_status": dict(sorted(by_status.items())),
            "elapsed_s": round(time.monotonic() - self._t0, 1),
            "user_agent": USER_AGENT,
            "note": note,
        }
        if write:
            self.receipt_path.write_text(json.dumps(rec, indent=1),
                                         encoding="utf-8")
        return rec
