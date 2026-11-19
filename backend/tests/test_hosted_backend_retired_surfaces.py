"""CH-65: the surfaces that print counts say who is NOT in them, and the status page says
RETIRED_BY_OWNER instead of DOWN / UNKNOWN.

* results voice: one NOT IN THE COUNTS line, derived from this run's ROI receipt and the
  previous run's -- a dropped family and a broker-error account are named, nothing dropped
  prints nothing, an unreadable previous receipt prints CANNOT DETERMINE;
* family scorecard: the same line, from the same function;
* status page: the hosted rows are RETIRED_BY_OWNER, counted in neither the header nor the
  exit code, and no request goes to the retired host.

Receipts are small copies under tmp_path; no test depends on today's date.
"""
from __future__ import annotations

import dataclasses
import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import family_scorecard as FS
from backend.services import legibility as L
from backend.services import legibility_sanitise as SAN
from backend.services import results_voice as RV
from backend.tests import test_family_scorecard as TFS
from scripts import family_scorecard as FS_CLI
from scripts import system_status as S

FIX = Path(__file__).parent / "fixtures" / "results_voice"
RID = "2026-10-06T235345Z"            # the committed, trimmed roi + book_dna pair
PREV = "2026-10-05T235000Z"           # a hand-written previous run, one day earlier
NOW = datetime.now(timezone.utc).replace(microsecond=0)
WHY = "hosted backend retired by the owner since 2026-10-04: hosting stopped on purpose"


@pytest.fixture(autouse=True)
def _dated_now(monkeypatch):
    monkeypatch.setattr(C, "LABEL_FALSE_FIRE_MEASURED",
                        {**C.LABEL_FALSE_FIRE_MEASURED, "measured_utc": NOW.isoformat()})
    monkeypatch.delenv(C.HOSTED_BACKEND_ACTIVE_ENV, raising=False)


def _fixture_roi() -> dict:
    return json.loads((FIX / f"roi_{RID}.json").read_text(encoding="utf-8"))


def _folder(tmp_path: Path, cur: dict, prev) -> Path:
    """A receipts folder: the current pair, and `prev` as the previous run's ROI receipt
    (a dict, raw text for an unreadable file, or None for no earlier run)."""
    d = tmp_path / "paper_accounts"
    d.mkdir(parents=True)
    (d / f"roi_{RID}.json").write_text(json.dumps(cur), encoding="utf-8")
    (d / f"book_dna_{RID}.json").write_bytes((FIX / f"book_dna_{RID}.json").read_bytes())
    if prev is not None:
        (d / f"roi_{PREV}.json").write_text(prev if isinstance(prev, str) else json.dumps(prev), encoding="utf-8")
    return d


def _without(roi: dict, pred) -> dict:
    out = json.loads(json.dumps(roi))
    out["rows"] = [r for r in out["rows"] if not pred(r)]
    return out


def _is_lane(r: dict) -> bool:
    return r.get("family") == "website_lane"


def _is_hack3(r: dict) -> bool:
    return r.get("account") == "hack3"


def _voice(folder: Path) -> dict:
    return RV.run(RID, folder, write_files=False)["voice"]


def _cov_line(v: dict):
    hits = [ln for ln in v["headline_lines"] if ln.startswith(RV.COVERAGE_PREFIX)]
    assert len(hits) <= 1
    return hits[0] if hits else None


# ── results voice ─────────────────────────────────────────────────────────

def test_a_dropped_family_and_a_broker_error_account_are_named(tmp_path):
    prev = _fixture_roi()                      # four website lanes priced, hack3 unreadable
    cur = _without(prev, _is_lane)
    cur["rows"].append({"account": "website lanes (all ten)", "family": "website_lane", "status": "UNPRICED",
                        "note": "prod track-record unreachable and the local NAV store is empty",
                        "roi_pct": None, "vs_spy_pp": None})
    next(r for r in cur["rows"] if _is_hack3(r))["broker_error"] = "HTTP_401: credential refused on /v2/account"
    v = _voice(_folder(tmp_path, cur, prev))
    before = RV.build(prev, json.loads((FIX / f"book_dna_{RID}.json").read_text(encoding="utf-8")),
                      roi_path="r", dna_path="d")
    assert v["headline"]["n_strategy_accounts"] == before["headline"]["n_strategy_accounts"] - 3
    assert before["losers"][0]["account"] == "mirror" and v["losers"][0]["account"] != "mirror"
    line = _cov_line(v)
    assert line is not None, "the worst book left the scoreboard and the headline must say so"
    lines = v["headline_lines"]
    assert lines.index(line) == 5 and lines[4].startswith("BEHIND:") and lines[-1].startswith("CLAIMS PROMOTED:")
    assert "5 account(s) in 2 family(ies) exist and are in none of the counts above" in line
    assert "4 website_lane account(s) absent from this receipt" in line
    assert "source unreadable: prod track-record unreachable" in line
    assert "mirror -29.50 pp vs SPY was the worst of them, worse than the worst book counted above" in line
    assert "0 of 4 were ahead of SPY at the 2026-10-06 marks" in line
    assert "hack3 (alpaca_fleet) unreadable (broker error: http 401: credential refused" in line
    assert f"compared with run {PREV}" in line
    cov = v["coverage"]
    assert cov["status"] == "OK" and cov["n_accounts"] == 5 and cov["compared_with"]["run_id"] == PREV
    kinds = {x["account"]: x["kind"] for x in cov["items"]}
    assert kinds["mirror"] == "ABSENT" and kinds["hack3"] == "BROKER_ERROR"
    md = RV.render_md(v)
    assert "## Not in the counts" in md and "| mirror | website_lane | ABSENT |" in md


def test_frozen_lanes_are_named_with_their_last_known_standing(tmp_path):
    prev = _fixture_roi()
    cur = json.loads(json.dumps(prev))
    for r in cur["rows"]:
        if _is_lane(r):
            r["frozen_standing"] = {"roi_pct": r["roi_pct"], "vs_spy_pp": r["vs_spy_pp"],
                                    "spy_same_window_pct": r.get("spy_same_window_pct")}
            r.update(status="FROZEN", frozen=True, frozen_since=r["last_mark"], frozen_reason=WHY,
                     roi_pct=None, vs_spy_pp=None, spy_same_window_pct=None)
    cur["rows"] = [r for r in cur["rows"] if not _is_hack3(r)]
    v = _voice(_folder(tmp_path, cur, _without(prev, _is_hack3)))
    assert not any(x["family"] == "website_lane" for x in v["leaders"] + v["losers"] + v["flags_rows"])
    line = _cov_line(v)
    assert "4 website_lane account(s) FROZEN at the 2026-10-06 marks" in line
    assert f"source retired: {WHY}" in line
    assert "mirror -29.50 pp vs SPY was the worst of them" in line and "none of the counts above" in line
    # the same line the day after: the frozen rows are present in BOTH receipts and still named
    v2 = _voice(_folder(tmp_path / "next", cur, cur))
    assert "4 website_lane account(s) FROZEN" in _cov_line(v2)
    # a placeholder row of the previous run that never had a standing is not an account that left
    prev2 = json.loads(json.dumps(cur))
    prev2["rows"].append({"account": "website lanes (all ten)", "family": "website_lane", "status": "UNPRICED",
                          "roi_pct": None, "vs_spy_pp": None, "note": "unreachable"})
    v3 = _voice(_folder(tmp_path / "after", cur, prev2))
    assert "all ten" not in _cov_line(v3) and v3["coverage"]["n_accounts"] == 4


def test_a_source_retired_family_with_no_local_copy_is_named(tmp_path):
    prev = _without(_fixture_roi(), _is_hack3)
    cur = _without(prev, _is_lane)
    cur["rows"].append({"account": "website lanes", "family": "website_lane", "status": "SOURCE_RETIRED",
                        "note": f"SOURCE RETIRED, not priced: {WHY}", "retired_reason": WHY,
                        "roi_pct": None, "vs_spy_pp": None})
    line = _cov_line(_voice(_folder(tmp_path, cur, prev)))
    assert "4 website_lane account(s) absent from this receipt" in line and f"source retired: {WHY}" in line
    # and when the previous run already had only the placeholder, the family is still named
    line2 = _cov_line(_voice(_folder(tmp_path / "next", cur, cur)))
    assert "the website_lane family SOURCE_RETIRED, not priced" in line2 and WHY in line2


def test_nothing_dropped_prints_no_extra_line(tmp_path):
    cur = _without(_fixture_roi(), _is_hack3)
    v = _voice(_folder(tmp_path, cur, cur))
    assert _cov_line(v) is None and v["coverage"]["line"] is None
    assert v["coverage"]["status"] == "OK" and v["coverage"]["items"] == []
    assert len(v["headline_lines"]) == 9
    assert "## Not in the counts" not in RV.render_md(v)


def test_no_earlier_run_and_nothing_missing_prints_no_line(tmp_path):
    v = _voice(_folder(tmp_path, _without(_fixture_roi(), _is_hack3), None))
    assert _cov_line(v) is None and v["coverage"]["status"] == "NO_EARLIER_RUN"


@pytest.mark.parametrize("bad", ["{truncated", json.dumps({"rows": []}), json.dumps([1, 2])])
def test_an_unreadable_previous_receipt_says_cannot_determine(tmp_path, bad):
    v = _voice(_folder(tmp_path, _without(_fixture_roi(), _is_hack3), bad))
    line = _cov_line(v)
    assert line is not None, "never print nothing when the comparison could not run"
    assert line.startswith(f"{RV.COVERAGE_PREFIX} CANNOT DETERMINE which accounts left the counts")
    assert f"roi_{PREV}.json" in line and "unreadable" in line
    assert v["coverage"]["status"] == "CANNOT DETERMINE"
    assert "## Not in the counts" in RV.render_md(v)


def test_an_account_that_stops_being_counted_is_named_with_the_status_that_removed_it(tmp_path):
    prev = _without(_fixture_roi(), _is_hack3)
    cur = json.loads(json.dumps(prev))
    row = next(r for r in cur["rows"] if r["account"] == "hack6")
    row.update(status="UNPRICED", roi_pct=None, vs_spy_pp=None, note="HTTP 500 on /v2/account")
    line = _cov_line(_voice(_folder(tmp_path, cur, prev)))
    assert "hack6 (alpaca_fleet) no longer counted (other: status UNPRICED (HTTP 500 on /v2/account))" in line
    assert "last known -19.69 pp vs SPY at the 2026-10-06 marks" in line


def test_the_line_is_read_back_from_the_md_and_survives_the_public_sanitiser(tmp_path):
    prev = _fixture_roi()
    cur = _without(prev, _is_lane)
    next(r for r in cur["rows"] if _is_hack3(r))["broker_error"] = "NO_CREDENTIAL: no AAT_HACK*_KEY_ID/SECRET pair"
    folder = _folder(tmp_path, cur, prev)
    out = RV.run(RID, folder)
    _, lines = RV.headline_block(folder)
    assert lines == out["voice"]["headline_lines"] and any(ln.startswith(RV.COVERAGE_PREFIX) for ln in lines)
    pub = RV.public_view(out["voice"], L.is_personal)
    clean = SAN.sanitise(pub, SAN.SPEC["arena"]["results_voice"])
    assert clean == pub, "a reason code must not read differently on the public page"
    assert any(ln.startswith(RV.COVERAGE_PREFIX) for ln in clean["headline_lines"])


# ── family scorecard: the same function, the same sentence ────────────────

def test_the_scorecard_header_carries_the_same_line(tmp_path, capsys):
    roi, dna = TFS._world()
    pa = tmp_path / "optimus" / "paper_accounts"
    pa.mkdir(parents=True)
    rid = TFS.RID
    prev_id = (TFS.NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H%M%SZ")
    (pa / f"roi_{rid}.json").write_text(json.dumps(roi), encoding="utf-8")
    (pa / f"book_dna_{rid}.json").write_text(json.dumps(dna), encoding="utf-8")
    mark = roi["rows"][0]["last_mark"]
    prev = json.loads(json.dumps(roi))
    prev["rows"] += [{"account": "lane_up", "family": "website_lane", "status": "LIVE", "roi_pct": 3.0,
                      "vs_spy_pp": 1.0, "last_mark": mark},
                     {"account": "lane_down", "family": "website_lane", "status": "LIVE", "roi_pct": -30.0,
                      "vs_spy_pp": -33.0, "last_mark": mark}]
    (pa / f"roi_{prev_id}.json").write_text(json.dumps(prev), encoding="utf-8")
    out = tmp_path / "out"
    rc = FS_CLI.main(["--data-root", str(tmp_path / "optimus"), "--out", str(out), "--now", TFS.NOW.isoformat()])
    assert rc == 0
    sc = json.loads((out / f"family_scorecard_{rid}.json").read_text(encoding="utf-8"))
    voice = json.loads((out / f"results_voice_{rid}.json").read_text(encoding="utf-8"))
    assert sc["coverage_line"] == voice["coverage"]["line"] and sc["coverage"] == voice["coverage"]
    assert sc["coverage_line"].startswith(RV.COVERAGE_PREFIX)
    assert "lane_down, lane_up (website_lane) absent from this receipt" in sc["coverage_line"]
    assert "lane_down -33.00 pp vs SPY was the worst of them" in sc["coverage_line"]
    md = (out / f"family_scorecard_{rid}.md").read_text(encoding="utf-8")
    top = md.index("FAMILY SCORECARD as of")
    assert top < md.index(RV.COVERAGE_PREFIX) < md.index("## How many bets these families are")
    assert RV.COVERAGE_PREFIX in capsys.readouterr().out


def test_the_scorecard_prints_nothing_extra_when_nothing_is_missing(tmp_path):
    roi, dna = TFS._world()
    sc = FS.build(roi, dna, roi_path="roi.json", dna_path="book_dna.json", now=TFS.NOW, run_id=TFS.RID)
    assert sc["coverage_line"] is None and RV.COVERAGE_PREFIX not in FS.render_md(sc)


# ── status page ───────────────────────────────────────────────────────────

def _decl(days_ago: int = 3) -> dict:
    return {"since_utc": (NOW - timedelta(days=days_ago)).date().isoformat(), "by": "owner",
            "reason": "hosting stopped on purpose",
            "last_lane_mark": (NOW - timedelta(days=days_ago + 3)).date().isoformat(),
            "hosts": ("dead.example.invalid",), "consequence": "hosted API off"}


@pytest.fixture
def retired(monkeypatch) -> dict:
    d = _decl()
    monkeypatch.setattr(C, "HOSTED_BACKEND_RETIRED", d)
    return d


def _probe(probe: str, verdict: str) -> dict:
    return {"name": probe, "probe": probe, "verdict": verdict, "detail": "GET failed: HTTPError", "where": "external",
            "evidence_utc": None, "proof": "p", "cadence_s": 86400}


def _full_rec(extra_rows: list) -> dict:
    rows = [S.row(k, "x", "OK", "d", now=NOW) for k, _ in S.SECTIONS] + extra_rows
    secs = {k: {"title": t, "rows": [r for r in rows if r["section"] == k], "error": None} for k, t in S.SECTIONS}
    counted = [r for r in rows if not (r.get("extra") or {}).get("retired")]
    names = sorted(f"{r['section']}/{r['name']}" for r in rows if r["status"] == S.RETIRED_STATUS)
    return {"receipt": S.SCHEMA, "generated_utc": S.iso(NOW), "sections": secs, "read_me_first": "x",
            "counts": {k: sum(1 for r in counted if r["status"] == k) for k in S.STATUSES},
            "retired_by_owner": {"rows": names, "since_utc": "d", "reason": "r", "consequence": "c"} if names else None}


def test_hosted_rows_read_retired_by_owner_with_the_date_and_the_consequence(retired):
    for probe, verdict in (("railway_backend", "DEAD"), ("railway_fleet", "UNKNOWN"),
                           ("railway_fleet", "STOPPED_BY_OPERATOR")):
        r = S.map_probe_row(_probe(probe, verdict), NOW)
        assert r["status"] == "RETIRED_BY_OWNER" and r["required"] is False and r["action"] == ""
        assert r["extra"]["retired"] is True and r["extra"]["retired_since"] == retired["since_utc"]
        # the date is compared with now: its age is printed (3 whole days plus the time of day)
        assert any(f"RETIRED_BY_OWNER since {retired['since_utc']} ({n} days ago" in r["detail"] for n in (3, 4))
        assert f"website lanes frozen at their {retired['last_lane_mark']} marks; hosted API off" in r["detail"]
        assert "no request made" in r["detail"] and r["age_s"] == pytest.approx(3 * 86400, abs=86400)


def test_retired_rows_do_not_change_the_counts_or_the_exit_code(retired, tmp_path):
    hosted = [S.map_probe_row(_probe("railway_backend", "DEAD"), NOW),
              S.map_probe_row(_probe("railway_fleet", "UNKNOWN"), NOW)]
    base, with_retired = _full_rec([]), _full_rec(hosted)
    for strict in (False, True):
        assert S.exit_code(with_retired, strict=strict) == S.exit_code(base, strict=strict) == 0
    assert with_retired["counts"] == base["counts"]
    assert S.undetermined(with_retired) == [] and S.reds(with_retired) == []
    assert S.header_line(with_retired) == S.header_line(base) + " · 2 retired by owner (not counted)"
    text, page = S.render_text(with_retired), S.render_html(with_retired, now=NOW)
    assert "RETIRED BY OWNER since" in text and "RETIRED_BY_OWNER railway_backend" in text
    assert "class='b RETIRED_BY_OWNER'>RETIRED_BY_OWNER<" in page and "id=retired" in page
    # the whole collector, with the same two probe rows injected: nothing new is undetermined
    opt = tmp_path / "optimus"
    opt.mkdir()
    kw = dict(optimus_dir=opt, repo=tmp_path, now=NOW, ctx=None, run=lambda a, t: (1, ""))
    a = S.collect(probe_rows_in=[], **kw)
    b = S.collect(probe_rows_in=[_probe("railway_backend", "DEAD"), _probe("railway_fleet", "UNKNOWN")], **kw)
    assert a["exit_code"] == b["exit_code"] and a["counts"] == b["counts"] and a["undetermined"] == b["undetermined"]
    assert b["retired_by_owner"]["rows"] == ["infrastructure/railway_backend", "infrastructure/railway_fleet"]
    assert a["retired_by_owner"] is None


def test_the_fred_row_says_cannot_determine_and_is_never_green(retired):
    r = S.map_probe_row(_probe("fred_macro_inputs", "DEAD"), NOW)
    assert r["status"] == "UNKNOWN" and r["required"] is False
    assert r["detail"].startswith("CANNOT DETERMINE: this row reads FRED health through the hosted backend")
    assert "No request was made" in r["detail"] and r["action"].startswith("Fix:")
    assert not (r.get("extra") or {}).get("retired"), "it is counted: UNKNOWN, not excused"
    rec = _full_rec([r])
    assert rec["counts"]["UNKNOWN"] == 1 and S.exit_code(rec) == 0 and S.reds(rec) == [r]


def test_no_request_goes_to_the_retired_host(retired, monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("a request was sent to the retired host")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    body, elapsed, err = S._short_http_json("https://dead.example.invalid/api/health/full", 45)
    assert body is None and elapsed == 0.0 and err.startswith("HOSTED_BACKEND_RETIRED")
    # and the probes themselves are not run: neither the GET nor the `railway status` shell-out
    from backend.services import system_health as SH
    ran: list = []

    def fn(ctx):
        ran.append(1)
        raise AssertionError("a hosted probe ran while the host is retired")
    probes = [dataclasses.replace(p, fn=fn) for p in SH.PROBES
              if p.name in S.HOSTED_PROBES + S.HOSTED_DEPENDENT_PROBES]
    assert {p.name for p in probes} == {"railway_backend", "railway_fleet", "fred_macro_inputs"}
    monkeypatch.setattr(SH, "PROBES", probes)
    rows = S.raw_probe_rows(types.SimpleNamespace(allow_proc=True, now=NOW))
    assert ran == [] and len(rows) == 3
    assert all(r["verdict"] == "UNKNOWN" and "retired by the owner" in r["detail"] for r in rows)
    mapped = {r["name"]: S.map_probe_row(r, NOW)["status"] for r in rows}
    assert mapped == {"railway_backend": "RETIRED_BY_OWNER", "railway_fleet": "RETIRED_BY_OWNER",
                      "fred_macro_inputs": "UNKNOWN"}


def test_the_override_restores_the_old_rows_and_the_request(retired, monkeypatch):
    monkeypatch.setenv(C.HOSTED_BACKEND_ACTIVE_ENV, "1")
    r = S.map_probe_row(_probe("railway_backend", "DEAD"), NOW)
    assert r["status"] == "UNKNOWN" and r["required"] is False and "offline or asleep" in r["action"]
    assert S.map_probe_row(_probe("railway_fleet", "STOPPED_BY_OPERATOR"), NOW)["status"] == "DEGRADED"
    assert S.map_probe_row(_probe("fred_macro_inputs", "DEAD"), NOW)["status"] == "DOWN"
    import urllib.request
    seen: list = []

    def opened(req, timeout=None):
        seen.append(req.full_url)
        raise OSError("offline in tests")
    monkeypatch.setattr(urllib.request, "urlopen", opened)
    body, _, err = S._short_http_json("https://dead.example.invalid/api/health/full", 45)
    assert seen == ["https://dead.example.invalid/api/health/full"] and body is None and err == "OSError"


@pytest.mark.parametrize("since", [None, "not a date", (NOW + timedelta(days=30)).date().isoformat()])
def test_a_retirement_that_cannot_be_dated_is_not_accepted(monkeypatch, since):
    monkeypatch.setattr(C, "HOSTED_BACKEND_RETIRED", {**_decl(), "since_utc": since})
    r = S.map_probe_row(_probe("railway_backend", "DEAD"), NOW)
    assert r["status"] == "UNKNOWN" and r["required"] is True
    assert r["detail"].startswith("CANNOT DETERMINE: config.HOSTED_BACKEND_RETIRED carries no readable past date")
    assert S.exit_code(_full_rec([r])) == 3


def test_the_shipped_declaration_drives_the_real_rows():
    ret = C.hosted_backend_retired()
    assert ret is not None, "the declaration ships active; the override is an env var"
    now = datetime.now(timezone.utc)
    r = S.map_probe_row(_probe("railway_backend", "DEAD"), now)
    assert r["status"] == "RETIRED_BY_OWNER" and ret["since_utc"] in r["detail"]
    assert ret["last_lane_mark"] in r["detail"]
