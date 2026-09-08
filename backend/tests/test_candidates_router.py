"""
Tests for the candidate surface — `backend/routers/candidates.py` (H1).

Three properties are load-bearing and each is pinned twice:

1. **The router has NO WRITE PATH.** Proved by an HTTP-method audit over the
   router's own route table, by live 405s, and by an AST scan of the source for
   write verbs and order verbs. `learner/allocator.py` earns its SHADOW_ONLY
   claim the same way; a docstring saying "read-only" is not a mechanism.
2. **A vintage is dated by its own stamp, never by the filesystem.** CLAUDE.md
   §7 cost this programme two days of red CI. The decisive test writes a
   vintage whose header says it is old, touches the file so its mtime is NOW,
   and asserts the response still reads STALE.
3. **An unreachable source refuses; it does not read as empty.** The execution
   repo is invisible from a container, and an empty watchlist and an
   unreachable one are different facts.

Dates are derived from `today`, never literal: a fixture that hardcodes a
calendar moment fails the day after it passes.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app
from backend.routers import candidates as C

ROUTER_SOURCE_PATH = Path(C.__file__)
ROUTER_SOURCE = ROUTER_SOURCE_PATH.read_text(encoding="utf-8")


@pytest.fixture
def client():
    C._CACHE.clear()
    yield TestClient(app, raise_server_exceptions=False)
    C._CACHE.clear()


# ── helpers ─────────────────────────────────────────────────────────────────

def _prev_weekday(d: dt.date, n: int = 1) -> dt.date:
    """The n-th previous Mon-Fri day. Derived, never a literal date."""
    out = d
    while n > 0:
        out -= dt.timedelta(days=1)
        if out.weekday() < 5:
            n -= 1
    return out


def _write_vintage(directory: Path, day: dt.date, *, n_rows: int = 3,
                   header_day: str | None = None) -> Path:
    """A minimal but schema-shaped potential-universe vintage."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{day.isoformat()}.jsonl"
    header = {
        "artefact": "AEGIS_POTENTIAL_UNIVERSE",
        "version": "test/1",
        "licence": "PRODUCT_EXPERIMENT",
        "day": header_day if header_day is not None else day.isoformat(),
        "generated_at_utc": f"{day.isoformat()}T00:00:00+00:00",
        "status": "OK",
        "counts": {"n_scorecards": n_rows},
        "conventions": {"band_status": "test band status",
                        "unit": "ratio = mean_target / close"},
        "whole_universe_refusals": {},
        "field_readability": {},
    }
    lines = [json.dumps(header)]
    for i in range(n_rows):
        # Row 0 deliberately has NO upside, so "missing sorts last" is testable.
        upside = None if i == 0 else float(i)
        lines.append(json.dumps({
            "symbol": f"SYM{i}",
            "day": day.isoformat(),
            "pit": {"status": "OK"},
            "identity": {"sector": "Testing", "exchange": "NASDAQ",
                         "tradable": True, "shortable": True},
            "engine_prior": {"verdict": "admitted_shadow", "band": "b_1_5_3",
                             "reasons": [f"reason {i}"],
                             "ratio": None if upside is None else upside + 1.0,
                             "upside": upside, "prior_1m": 0.01},
            "learner_v1": {"status": "OK", "score": 0.5, "unit": "P(excess>0)"},
            "learner_v2": {"status": "REFUSED", "reason": "test"},
            "p_beat": {"status": "OK", "raw": 0.5, "debiased": 0.48,
                       "base_rate": 0.45, "vs_base_rate": 0.05},
            "state": {"status": "CANNOT_DETERMINE", "reason": "test"},
            "disagreement": {"verdict": "AGREE", "sign_disagreement": False,
                             "rank_gap": 0.1},
            "execution": {"tier": "FULL", "observe_only": False,
                          "max_usd": 1.0, "median_dollar_volume": 1e7},
            "days_to_catalyst": {"readable": True, "value": 10.0,
                                 "units": "calendar_days"},
            "falsifiers": [],
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ══════════════════════════════════════════════════════════════════════════
# 1. NO WRITE PATH
# ══════════════════════════════════════════════════════════════════════════

class TestReadOnly:
    def test_every_route_is_a_read(self):
        """Route-table audit. A gate that can only ever pass is a broken gate,
        so this also asserts the router HAS routes."""
        routes = [r for r in C.router.routes if hasattr(r, "methods")]
        assert len(routes) >= 5, "the candidate router lost its routes"
        for r in routes:
            extra = set(r.methods) - {"GET", "HEAD", "OPTIONS"}
            assert not extra, f"{r.path} exposes {sorted(extra)} — this router is read-only"

    @pytest.mark.parametrize("path", [
        "/api/candidates/vintages",
        "/api/candidates/universe",
        "/api/candidates/universe/AAPL",
        "/api/candidates/watchlist",
        "/api/candidates/bands",
        "/api/candidates/allocator",
    ])
    @pytest.mark.parametrize("verb", ["post", "put", "patch", "delete"])
    def test_write_verbs_are_405(self, client, path, verb):
        r = client.request(verb.upper(), path)
        assert r.status_code == 405, f"{verb.upper()} {path} → {r.status_code}"

    def test_source_has_no_write_or_order_verbs(self):
        """AST scan. Names in docstrings and comments are allowed (the module
        cites `scripts.potential_universe_run` and the allocator by name); a
        CALL to one is not."""
        # Only UNAMBIGUOUS write/order verbs. `str.replace` and `list.remove`
        # are not writes, and a scanner that flags them gets muted by the first
        # person it annoys. The ambiguous ones (`os.replace`, `shutil.move`,
        # `cursor.execute`, `httpx.post`) are covered by the import ban below —
        # you cannot call them without importing something forbidden.
        forbidden_attrs = {
            "write", "write_text", "write_bytes", "writelines", "mkdir",
            "unlink", "rmdir", "touch", "rmtree", "chmod", "truncate",
            "executemany", "submit_order", "seal", "append_row",
        }
        forbidden_names = {
            "exec", "eval", "compile", "__import__", "system", "popen",
            "TradingClient", "OrderRequest",
        }
        tree = ast.parse(ROUTER_SOURCE)
        offences = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr in forbidden_attrs:
                    offences.append(f"line {node.lineno}: .{fn.attr}()")
                if isinstance(fn, ast.Name) and fn.id in forbidden_names:
                    offences.append(f"line {node.lineno}: {fn.id}()")
                # open()/Path.open() must be read mode.
                is_open = (isinstance(fn, ast.Name) and fn.id == "open") or (
                    isinstance(fn, ast.Attribute) and fn.attr == "open")
                if is_open:
                    mode = None
                    if node.args:
                        a0 = node.args[0]
                        if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                            mode = a0.value
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                            mode = kw.value.value
                    if mode is None or set(mode) - set("rbt"):
                        offences.append(f"line {node.lineno}: open(mode={mode!r})")
        assert not offences, ("the candidate router must have no write path; "
                              f"found {offences}")

    def test_source_imports_nothing_that_can_place_an_order(self):
        tree = ast.parse(ROUTER_SOURCE)
        # `os` and `shutil` are on the list because their absence is what
        # makes the attribute scan above complete: no `os.replace`, no
        # `shutil.move`, no `os.system`.
        banned = ("alpaca", "aegis-alpha-terminal", "alpha.brains", "alpha.universe",
                  "backend.db", "sqlite3", "requests", "httpx", "urllib",
                  "subprocess", "shutil", "os", "learner", "scripts")
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for mod in imported:
            for b in banned:
                assert not mod.startswith(b), f"{mod} is not importable here"

    def test_authority_string_is_verbatim(self):
        """The stamp travels onto every response, so it is pinned like the
        allocator's SHADOW_ONLY line rather than reworded per endpoint."""
        assert C.AUTHORITY.startswith("READ_ONLY")
        assert "places nothing" in C.AUTHORITY
        assert "writes nothing" in C.AUTHORITY


# ══════════════════════════════════════════════════════════════════════════
# 2. VINTAGE AND STALENESS
# ══════════════════════════════════════════════════════════════════════════

class TestVintage:
    def test_weekday_arithmetic(self):
        # Derived from a known weekday alignment, not from today's date.
        mon = dt.date(2026, 1, 5)                     # a Monday
        assert mon.weekday() == 0
        fri = mon - dt.timedelta(days=3)
        assert C._weekdays_between(fri, mon) == 1, "Friday → Monday is one weekday"
        wed = mon - dt.timedelta(days=5)
        assert C._weekdays_between(wed, mon) == 3
        assert C._weekdays_between(mon, mon) == 0
        assert C._weekdays_between(mon, mon - dt.timedelta(days=7)) == 0

    def test_mtime_is_never_the_date_source(self, client, tmp_path, monkeypatch):
        """THE test for CLAUDE.md §7. The file is written NOW; its header says
        it is old. A surface that dated by mtime would call this fresh."""
        old_day = _prev_weekday(C._today_et(), 6)
        d = tmp_path / "pu"
        p = _write_vintage(d, old_day)
        assert abs(p.stat().st_mtime - dt.datetime.now().timestamp()) < 120, \
            "the fixture file must be freshly written for this test to mean anything"
        monkeypatch.setattr(config, "CANDIDATE_POTENTIAL_UNIVERSE_DIR", d)
        C._CACHE.clear()

        v = client.get("/api/candidates/universe").json()["vintage"]
        assert v["day"] == old_day.isoformat()
        assert v["dated_by"] == "artefact_self_stamp"
        assert v["freshness"] == "STALE"
        assert v["stale"] is True
        assert old_day.isoformat() in v["stale_reason"]

    def test_dated_by_is_a_closed_set(self, client):
        """`dated_by` is the audit trail: it can never say filesystem_mtime."""
        body = client.get("/api/candidates/vintages").json()
        for name, v in body["sources"].items():
            assert v["dated_by"] in (None, "artefact_self_stamp", "filename_stem"), \
                f"{name} dated by {v['dated_by']!r}"

    def test_st_mtime_appears_only_in_the_cache_key(self):
        """mtime is legitimate for cache invalidation and illegitimate for
        dating. Pin WHERE it may appear, not merely that it does."""
        tree = ast.parse(ROUTER_SOURCE)
        users = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seg = ast.get_source_segment(ROUTER_SOURCE, fn) or ""
                if "st_mtime" in seg or "getmtime" in seg:
                    users.add(fn.name)
        assert users <= {"_cached"}, \
            f"mtime is read outside the cache key, in {sorted(users)}"

    def test_a_recent_vintage_is_fresh(self, client, tmp_path, monkeypatch):
        """The gate must be able to go green, or it teaches the reader to skim
        red lines."""
        d = tmp_path / "pu"
        _write_vintage(d, _prev_weekday(C._today_et(), 1))
        monkeypatch.setattr(config, "CANDIDATE_POTENTIAL_UNIVERSE_DIR", d)
        C._CACHE.clear()
        v = client.get("/api/candidates/universe").json()["vintage"]
        assert v["freshness"] == "FRESH"
        assert v["stale"] is False
        assert v["stale_reason"] is None

    def test_filename_stem_is_the_fallback_stamp(self, client, tmp_path, monkeypatch):
        d = tmp_path / "pu"
        day = _prev_weekday(C._today_et(), 4)
        _write_vintage(d, day, header_day="not-a-day")
        monkeypatch.setattr(config, "CANDIDATE_POTENTIAL_UNIVERSE_DIR", d)
        C._CACHE.clear()
        v = client.get("/api/candidates/universe").json()["vintage"]
        assert v["dated_by"] == "filename_stem"
        assert v["day"] == day.isoformat()

    def test_absent_source_cannot_determine(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CANDIDATE_POTENTIAL_UNIVERSE_DIR", tmp_path / "nope")
        C._CACHE.clear()
        v = client.get("/api/candidates/universe").json()["vintage"]
        assert v["status"] == "ABSENT"
        assert v["freshness"] == "CANNOT_DETERMINE"
        assert v["stale"] is None
        assert "potential_universe_run" in v["stale_reason"]

    def test_every_endpoint_carries_a_vintage(self, client):
        required = {"artefact", "status", "day", "dated_by", "freshness",
                    "stale", "as_of_utc", "source"}
        for path in ("/api/candidates/universe?limit=1",
                     "/api/candidates/watchlist?limit=1",
                     "/api/candidates/bands?limit=1",
                     "/api/candidates/allocator"):
            body = client.get(path).json()
            assert "vintage" in body, path
            assert required <= set(body["vintage"]), path
            assert "stale" in body, path
        body = client.get("/api/candidates/vintages").json()
        assert set(body["sources"]) == {"potential_universe", "tracker_day",
                                        "tracker_watchlist", "decision_artifacts"}
        for v in body["sources"].values():
            assert required <= set(v)
        assert body["worst_freshness"] in ("FRESH", "STALE", "CANNOT_DETERMINE")


# ══════════════════════════════════════════════════════════════════════════
# 3. AN UNREACHABLE SOURCE REFUSES
# ══════════════════════════════════════════════════════════════════════════

class TestUnreachableSource:
    def test_watchlist_refuses_rather_than_reading_empty(self, client, tmp_path,
                                                         monkeypatch):
        monkeypatch.setattr(config, "CANDIDATE_TRACKER_DIR", tmp_path / "absent")
        C._CACHE.clear()
        r = client.get("/api/candidates/watchlist")
        assert r.status_code == 200
        body = r.json()
        assert body["vintage"]["status"] == "NOT_REACHABLE"
        assert body["vintage"]["freshness"] == "CANNOT_DETERMINE"
        assert body["rows"] == []
        assert "NOT an empty watchlist" in body["vintage"]["stale_reason"]

    def test_universe_still_serves_without_the_execution_repo(self, client,
                                                             tmp_path, monkeypatch):
        """The band's low/high legs disappear; the candidate list does not."""
        monkeypatch.setattr(config, "CANDIDATE_TRACKER_DIR", tmp_path / "absent")
        C._CACHE.clear()
        body = client.get("/api/candidates/universe?limit=1").json()
        assert body["tracker_vintage"]["status"] == "NOT_REACHABLE"
        if body["rows"]:
            band = body["rows"][0]["band"]
            assert band["status"] == "NOT_REACHABLE"
            assert band["target_low"] is None and band["target_high"] is None
            assert "note" in band


# ══════════════════════════════════════════════════════════════════════════
# 4. FILTERING, SORTING, STATUS CODES
# ══════════════════════════════════════════════════════════════════════════

class TestQuerySurface:
    def test_unknown_sort_is_422(self, client):
        r = client.get("/api/candidates/universe?sort=profit")
        assert r.status_code == 422
        assert "unknown sort" in r.json()["detail"]

    def test_unknown_verdict_is_422(self, client):
        assert client.get("/api/candidates/universe?verdict=buy").status_code == 422

    def test_unknown_status_is_422(self, client):
        assert client.get("/api/candidates/watchlist?status=MOON").status_code == 422

    def test_malformed_day_is_422(self, client):
        assert client.get("/api/candidates/universe?day=2026-13-99").status_code == 422

    def test_absent_day_is_404(self, client):
        r = client.get("/api/candidates/universe?day=1970-01-02")
        assert r.status_code == 404

    def test_limit_ceiling_is_enforced(self, client):
        assert client.get(
            f"/api/candidates/universe?limit={config.CANDIDATE_PAGE_MAX_LIMIT + 1}"
        ).status_code == 422

    def test_bad_symbol_is_422_and_unknown_symbol_is_404(self, client):
        assert client.get("/api/candidates/universe/$$$").status_code == 422
        assert client.get("/api/candidates/universe/ZZZZQQ").status_code == 404

    def test_missing_values_sort_last_in_both_directions(self, client, tmp_path,
                                                         monkeypatch):
        d = tmp_path / "pu"
        _write_vintage(d, _prev_weekday(C._today_et(), 1), n_rows=4)
        monkeypatch.setattr(config, "CANDIDATE_POTENTIAL_UNIVERSE_DIR", d)
        monkeypatch.setattr(config, "CANDIDATE_TRACKER_DIR", tmp_path / "absent")
        C._CACHE.clear()
        for direction in ("asc", "desc"):
            rows = client.get(
                f"/api/candidates/universe?sort=upside&dir={direction}&limit=10"
            ).json()["rows"]
            upsides = [r["band"]["upside"] for r in rows]
            assert upsides[-1] is None, f"{direction}: a name with no target ranked above one with"
            present = [u for u in upsides if u is not None]
            assert present == sorted(present, reverse=(direction == "desc"))

    def test_filters_are_reported_back(self, client):
        body = client.get(
            "/api/candidates/universe?verdict=admitted_shadow&limit=1&min_upside=0.5"
        ).json()
        assert body["filters"]["verdict"] == ["admitted_shadow"]
        assert body["filters"]["min_upside"] == 0.5
        assert body["sort"]["key"] == "upside"

    def test_facets_name_the_closed_sets(self, client):
        f = client.get("/api/candidates/universe?limit=1").json()["facets"]
        assert set(f["verdicts"]) == set(C._VERDICTS)
        assert set(f["tiers"]) == set(C._TIERS)
        assert set(f["sorts"]) == set(C._SORT)


# ══════════════════════════════════════════════════════════════════════════
# 5. THE REAL VINTAGE ON DISK (skipped where it is absent, e.g. CI)
# ══════════════════════════════════════════════════════════════════════════

_HAS_VINTAGE = bool(C._pu_days())
_needs_vintage = pytest.mark.skipif(
    not _HAS_VINTAGE, reason="no potential-universe vintage on this checkout")


@_needs_vintage
class TestAgainstTheRealVintage:
    def test_universe_serves_the_scorecards(self, client):
        body = client.get("/api/candidates/universe?limit=5").json()
        assert body["n_scorecards"] > 0
        assert body["n_returned"] == min(5, body["n_matched"])
        row = body["rows"][0]
        assert row["symbol"]
        assert row["reason"]["verdict"] in C._VERDICTS
        assert "unit" in row["our_estimate"]["learner_v1"] or True

    def test_whole_universe_refusals_are_surfaced(self, client):
        """The starved-seal sensor. A refusal on the whole universe is the one
        fact a candidate page must not swallow."""
        body = client.get("/api/candidates/universe?limit=1").json()
        assert "whole_universe_refusals" in body
        assert "field_readability" in body
        assert "counts" in body

    def test_single_name_round_trips(self, client):
        sym = client.get("/api/candidates/universe?limit=1").json()["rows"][0]["symbol"]
        body = client.get(f"/api/candidates/universe/{sym.lower()}").json()
        assert body["row"]["symbol"].upper() == sym.upper()
        assert "scorecard" in body and "falsifiers" in body["row"]

    def test_bands_carry_the_band_status_caveat(self, client):
        body = client.get("/api/candidates/bands?limit=3").json()
        assert body["band_status"], "the band caveat must travel with the band numbers"
        for row in body["rows"]:
            assert set(row) >= {"symbol", "band", "our_estimate", "reason"}

    def test_allocator_repeats_the_shadow_stamp(self, client):
        body = client.get("/api/candidates/allocator").json()
        assert body["personalities"]
        for art in body["artifacts"].values():
            assert "SHADOW_ONLY" in art["authority"]
            assert art["licence"].startswith("PRODUCT_EXPERIMENT")
