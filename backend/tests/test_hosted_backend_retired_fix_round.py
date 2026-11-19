"""CH-65 fix round (review of PR #170): B1, B2, S1-S5.

* B1: the NOT IN THE COUNTS line never names an owner-personal account on a public surface
  (the same `legibility.is_personal` predicate every other public row uses); the private line
  still names it.
* B2: a frozen or vanished account stays named on EVERY later run, from ONE derived memory file
  (`frozen_sources.json`) the ROI step maintains -- however many receipts later.
* S1 / S2: the day file and Telegram /status: FROZEN lanes and RETIRED_BY_OWNER rows are not red.
* S3: the frozen lanes cite the run-stamped receipt, never the date-named copy.
* S4: the railway_fleet row keeps its 2026-09-29 stop beside the later retirement.
* S5: book_dna reads the retirement declaration itself, and ROI `main()` passes no flag.

Every fixture is synthetic under tmp_path; dates are derived from today. No network.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import book_dna as BD
from backend.services import legibility as L
from backend.services import legibility_sanitise as SAN
from backend.services import results_voice as RV
from backend.services import telegram_readonly as TRO
from backend.tests import test_hosted_backend_retired as T1
from backend.tests import test_hosted_backend_retired_surfaces as T2
from scripts import day_file as DF
from scripts import paper_accounts_roi as PA
from scripts import system_status as S

TODAY = date.today()
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _stamp(days_ago: int, hhmmss: str = "003000") -> str:
    return f"{_d(days_ago)}T{hhmmss}Z"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv(C.HOSTED_BACKEND_ACTIVE_ENV, raising=False)
    monkeypatch.setattr(C, "LABEL_FALSE_FIRE_MEASURED",
                        {**C.LABEL_FALSE_FIRE_MEASURED, "measured_utc": NOW.isoformat()})
    monkeypatch.setattr(C, "PAPER_ACCOUNTS_RETIRED_EXPLICITLY", {}, raising=False)


retired = T1.retired          # the same declaration fixture (dates derived from today)


# ── B1: privacy ─────────────────────────────────────────────────────────────

def _personal_rows(roi: dict, mark: str) -> dict:
    """Two owner-personal accounts: one by the `murat_` prefix, one by the `murat_book` family."""
    out = copy.deepcopy(roi)
    out["rows"] += [
        {"account": "murat_live", "family": "murat_book", "status": "LIVE", "roi_pct": -18.123,
         "spy_same_window_pct": 1.3, "vs_spy_pp": -19.445, "last_mark": mark},
        {"account": "owner_brokerage_x", "family": "murat_book", "status": "LIVE", "roi_pct": 2.0,
         "spy_same_window_pct": 1.0, "vs_spy_pp": -7.771, "last_mark": mark}]
    return out


def test_b1_a_personal_account_leaving_the_counts_is_named_privately_and_never_publicly(tmp_path):
    base = T2._fixture_roi()
    mark = next(r["last_mark"] for r in base["rows"] if r.get("last_mark"))
    prev = _personal_rows(base, mark)
    cur = T2._without(prev, T2._is_lane)                  # the four lanes vanish (a public fact)
    for r in cur["rows"]:
        if r["family"] == "murat_book":                    # both personal books leave the counts
            r.update(status="UNPRICED", roi_pct=None, vs_spy_pp=None, note="bars panel missing")
    v = T2._voice(T2._folder(tmp_path, cur, prev))
    priv = T2._cov_line(v)
    assert "murat_live" in priv and "owner_brokerage_x" in priv and "-19.45" in priv
    pub = RV.public_view(v, L.is_personal)
    clean = SAN.sanitise(pub, SAN.SPEC["arena"]["results_voice"])
    blob = json.dumps(clean)
    for token in ("murat", "owner_brokerage_x", "-19.45", "-7.77", "murat_book"):
        assert token not in blob, token
    cov_pub = [ln for ln in clean["headline_lines"] if ln.startswith(RV.COVERAGE_PREFIX)]
    assert len(cov_pub) == 1, "the website-lane disclosure stays public"
    assert "website_lane" in cov_pub[0] and "mirror" in cov_pub[0]
    n_priv = sum(1 for x in v["coverage"]["items"])
    assert f"{n_priv - 2} account(s)" in cov_pub[0], "the count of personal accounts is not published either"


def test_b1_only_a_personal_account_missing_leaves_no_public_line(tmp_path):
    base = T2._without(T2._fixture_roi(), T2._is_hack3)
    mark = next(r["last_mark"] for r in base["rows"] if r.get("last_mark"))
    prev = _personal_rows(base, mark)
    cur = copy.deepcopy(prev)
    cur["rows"] = [r for r in cur["rows"] if r["account"] != "murat_live"]     # ABSENT
    v = T2._voice(T2._folder(tmp_path, cur, prev))
    assert "murat_live" in T2._cov_line(v)
    pub = RV.public_view(v, L.is_personal)
    assert not any(ln.startswith(RV.COVERAGE_PREFIX) for ln in pub["headline_lines"])
    assert "murat" not in json.dumps(pub["headline_lines"])


# ── B2: memory ──────────────────────────────────────────────────────────────

def _rc(days_ago: int, rows: list, *, broker: bool = True) -> dict:
    gen = f"{_d(days_ago)}T00:30:00+00:00"
    return {"schema": PA.SCHEMA, "generated_utc": gen, "run_id": _stamp(days_ago), "rows": rows,
            "broker_read": {"performed": broker}}


def _run(folder: Path, rc: dict) -> dict:
    """One ROI run: the stamped receipt is written, then the memory is maintained (main()'s order)."""
    folder.mkdir(parents=True, exist_ok=True)
    name = f"roi_{rc['run_id']}.json"
    (folder / name).write_text(json.dumps(rc), encoding="utf-8")
    (folder / f"roi_{rc['run_id'][:10]}.json").write_text(json.dumps(rc), encoding="utf-8")   # the date copy
    out = PA.update_frozen_sources(folder, rc, name)
    assert out["status"] == "ok", out
    return out


def _acct(a: str, fam: str, vs: float, mark: str, **kw) -> dict:
    return {"account": a, "family": fam, "status": "LIVE", "roi_pct": vs + 1.0, "spy_same_window_pct": 1.0,
            "vs_spy_pp": vs, "last_mark": mark, "inception": _d(60), **kw}


def _cov(folder: Path, rc: dict) -> dict:
    prev = RV.previous_roi(folder, rc["run_id"])
    return RV.coverage_changes(rc, prev, memory=RV.frozen_memory(folder), run_id=rc["generated_utc"])


def test_b2_a_vanished_account_is_named_on_run2_run3_and_every_later_run(tmp_path):
    keep = _acct("hack1", "alpaca_fleet", 1.0, _d(10))
    run1 = _rc(10, [keep, _acct("hack2", "alpaca_fleet", 7.588, _d(10))])
    _run(tmp_path, run1)
    for k in (9, 8, 7):                                    # run2, run3, run4: hack2 has no row
        rc = _rc(k, [_acct("hack1", "alpaca_fleet", 1.0, _d(k))])
        _run(tmp_path, rc)
        line = _cov(tmp_path, rc)["line"]
        assert line and "hack2 (alpaca_fleet) absent from this receipt" in line, (k, line)
        assert f"since {_d(9)}" in line and "+7.59 pp vs SPY" in line, (k, line)
    mem = json.loads((tmp_path / "frozen_sources.json").read_text(encoding="utf-8"))
    e = mem["accounts"]["hack2"]
    assert e["state"] == "MISSING" and e["since"] == _d(9) and e["first_missing_run"] == _stamp(9)
    assert e["source_receipt"] == f"roi_{_stamp(10)}.json", "the stamped receipt, never the date copy"
    assert e["source_sha256"] == PA._sha256(tmp_path / e["source_receipt"])
    # it reappears: the entry leaves, and the line no longer names it
    rc = _rc(6, [keep, _acct("hack2", "alpaca_fleet", 2.0, _d(6))])
    out = _run(tmp_path, rc)
    assert "hack2" in out["removed"] and "hack2" not in (_cov(tmp_path, rc)["line"] or "")


def test_b2_an_explicit_retirement_is_the_only_other_way_out(tmp_path, monkeypatch):
    _run(tmp_path, _rc(5, [_acct("hack2", "alpaca_fleet", 3.0, _d(5))]))
    _run(tmp_path, _rc(4, []))
    rc = _rc(3, [])
    _run(tmp_path, rc)
    assert "hack2" in _cov(tmp_path, rc)["line"]
    monkeypatch.setattr(C, "PAPER_ACCOUNTS_RETIRED_EXPLICITLY", {"hack2": "owner retired the role"})
    rc = _rc(2, [])
    out = _run(tmp_path, rc)
    assert "explicitly retired" in out["removed"]["hack2"]
    assert (_cov(tmp_path, rc)["line"] or "").count("hack2") == 0


def test_b2_a_run_without_the_broker_read_does_not_touch_broker_accounts(tmp_path):
    _run(tmp_path, _rc(5, [_acct("hack2", "alpaca_fleet", 3.0, _d(5))]))
    out = _run(tmp_path, _rc(4, [], broker=False))
    assert "hack2" not in out["added"]
    assert "hack2" not in json.loads((tmp_path / "frozen_sources.json").read_text(encoding="utf-8"))["accounts"]


def test_b2_a_broker_401_is_seeded_with_the_date_it_went_missing(tmp_path):
    bad = {"account": "hack3", "family": "alpaca_fleet", "status": "CREDENTIAL_INVALID", "roi_pct": None,
           "vs_spy_pp": None, "broker_error": "HTTP_401: credential refused on /v2/account"}
    never = {"account": "hack5", "family": "alpaca_fleet", "status": "CREDENTIAL_INVALID", "roi_pct": None,
             "vs_spy_pp": None, "broker_error": "HTTP_401: credential refused on /v2/account"}
    for k, h3 in ((12, _acct("hack3", "alpaca_fleet", -4.25, _d(12))), (11, bad), (10, bad)):
        p = tmp_path / f"roi_{_stamp(k)}.json"           # older receipts written before the memory existed
        tmp_path.mkdir(exist_ok=True)
        p.write_text(json.dumps(_rc(k, [h3, never])), encoding="utf-8")
    rc = _rc(9, [bad, never])
    out = _run(tmp_path, rc)
    assert set(out["seeded"]) == {"hack3", "hack5"}
    mem = json.loads((tmp_path / "frozen_sources.json").read_text(encoding="utf-8"))["accounts"]
    assert mem["hack3"]["since"] == _d(11) and mem["hack3"]["vs_spy_pp"] == -4.25
    assert mem["hack3"]["source_receipt"] == f"roi_{_stamp(12)}.json"
    assert mem["hack5"]["since"] is None and mem["hack5"]["since_at_or_before"] == _d(12)
    assert "3 earlier local ROI receipt(s)" in mem["hack5"]["since_note"]
    line = _cov(tmp_path, rc)["line"]
    assert f"hack3 (alpaca_fleet) unreadable since {_d(11)}" in line and "-4.25 pp vs SPY" in line
    assert f"hack5 (alpaca_fleet) unreadable since {_d(12)} or earlier" in line


def test_b2_an_unreadable_memory_is_refused_and_said(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    p = tmp_path / "frozen_sources.json"
    p.write_text("{truncated", encoding="utf-8")
    rc = _rc(3, [])
    (tmp_path / f"roi_{rc['run_id']}.json").write_text(json.dumps(rc), encoding="utf-8")
    out = PA.update_frozen_sources(tmp_path, rc, f"roi_{rc['run_id']}.json")
    assert out["status"] == "REFUSED" and "NOT overwritten" in out["why"]
    assert p.read_text(encoding="utf-8") == "{truncated"
    line = RV.coverage_changes(rc, None, memory=RV.frozen_memory(tmp_path))["line"]
    assert line and "CANNOT BE DETERMINED" in line and "frozen_sources.json unreadable" in line


def _lane_run(folder: Path, retired: dict, days_ago: int) -> dict:
    """One ROI run of the lane path as main() does it (memory read -> frozen record -> build)."""
    mem, err = PA.read_frozen_sources(folder)
    assert err is None
    tr, frozen = PA.frozen_track_record(folder, retired, memory=mem)
    rc = T1._build(tr, frozen["source"], False, frozen, folder, bm=T1._spy())
    rc["generated_utc"] = f"{_d(days_ago)}T00:31:00+00:00"
    rc["run_id"] = _stamp(days_ago, "003100")
    name = f"roi_{rc['run_id']}.json"
    (folder / name).write_text(json.dumps(rc, default=str), encoding="utf-8")
    assert PA.update_frozen_sources(folder, rc, name)["status"] == "ok"
    return rc


def test_b2_the_frozen_figure_survives_run25_after_many_lane_less_receipts(retired, tmp_path):
    origin = T1._write(tmp_path, T1._d(5), T1._live_receipt())
    (tmp_path / f"roi_{T1._d(5)}.json").write_bytes(origin.read_bytes())        # the date copy too
    rc1 = _lane_run(tmp_path, retired, 4)
    down1 = next(r for r in rc1["rows"] if r["account"] == "down")
    mem = json.loads((tmp_path / "frozen_sources.json").read_text(encoding="utf-8"))["accounts"]
    assert mem["down"]["state"] == PA.FROZEN and mem["down"]["source_receipt"] == origin.name
    assert mem["down"]["source_sha256"] == PA._sha256(origin)
    assert mem["down"]["vs_spy_pp"] == down1["frozen_standing"]["vs_spy_pp"] < 0
    assert mem["down"]["nav_end"] == 64000.0 and mem["down"]["last_mark"] == T1.LAST_REAL
    # 50 lane-less receipts (more than the 40-receipt lookback), as the old code wrote them
    for i in range(50):
        p = tmp_path / f"roi_{T1._d(3)}T{i:02d}0000Z.json"
        p.write_text(json.dumps(T1._dead_receipt()), encoding="utf-8")
    rc25 = _lane_run(tmp_path, retired, 0)
    down = next(r for r in rc25["rows"] if r["account"] == "down")
    assert down["status"] == PA.FROZEN and down["frozen_standing"]["vs_spy_pp"] == pytest.approx(
        down1["frozen_standing"]["vs_spy_pp"])
    assert down["frozen_origin_receipt"] == origin.name and down["equity"] == 64000.0
    assert rc25["sources"]["website_lanes"]["frozen"] is True
    line = RV.coverage_changes(rc25, None, memory=RV.frozen_memory(tmp_path), run_id=rc25["generated_utc"])["line"]
    assert "down, up (website_lane) FROZEN" in line
    assert f"{down1['frozen_standing']['vs_spy_pp']:+.2f} pp vs SPY was the worst of them" in line
    # and a voice read only from a lane-less receipt (no FROZEN rows at all) still names them
    dead = T1._dead_receipt()
    line2 = RV.coverage_changes(dead, None, memory=RV.frozen_memory(tmp_path), run_id=dead["generated_utc"])["line"]
    assert "down, up (website_lane) FROZEN" in line2 and "pp vs SPY was the worst of them" in line2


# ── S3: the stamped receipt, never the date copy ───────────────────────────

def test_s3_the_origin_is_the_stamped_receipt_when_both_exist(retired, tmp_path):
    stamped = T1._write(tmp_path, T1._d(5), T1._live_receipt())
    (tmp_path / f"roi_{T1._d(5)}.json").write_bytes(stamped.read_bytes())
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    assert frozen["origin_receipt"] == stamped.name == frozen["carried_from"]
    names = [p.name for p in PA._roi_receipts_newest_first(tmp_path)]
    assert f"roi_{T1._d(5)}.json" not in names
    # a day with ONLY a date copy (older receipts) is still read
    (tmp_path / f"roi_{T1._d(30)}.json").write_text("{}", encoding="utf-8")
    assert f"roi_{T1._d(30)}.json" in [p.name for p in PA._roi_receipts_newest_first(tmp_path)]


# ── S1: the day file's frozen lanes ────────────────────────────────────────

def test_s1_the_day_file_prints_frozen_lanes_as_info_with_their_figure(retired, tmp_path):
    rec = T1._live_receipt()
    rec["rows"][0]["account"], rec["rows"][1]["account"] = "balanced", "mirror"
    rec["lane_nav_series"]["lanes"] = {"balanced": rec["lane_nav_series"]["lanes"]["up"],
                                       "mirror": rec["lane_nav_series"]["lanes"]["down"]}
    T1._write(tmp_path, T1._d(5), rec)
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    roi = T1._build(tr, frozen["source"], False, frozen, tmp_path, bm=T1._spy())
    roi = json.loads(json.dumps(roi, default=str))
    sec = DF.books_section(tmp_path, NOW, "x", roi, {"books": []}, "")
    reds = [ln["text"] for ln in sec["lines"] if ln["status"] == DF.RED]
    assert not any("mirror" in t or "balanced" in t for t in reds), reds
    info = [ln["text"] for ln in sec["lines"] if ln["status"] == DF.INFO and "MAIN mirror" in ln["text"]]
    vs = next(r for r in roi["rows"] if r["account"] == "mirror")["frozen_standing"]["vs_spy_pp"]
    assert len(info) == 1 and f"FROZEN at {T1.LAST_REAL}" in info[0] and f"{vs:+.2f} pp vs SPY" in info[0]
    assert "in no count" in info[0]


# ── S2 / S4: RETIRED_BY_OWNER on the day file and Telegram; the fleet's own history ──

def _status_rec() -> dict:
    fleet = S.map_probe_row(T2._probe("railway_fleet", "STOPPED_BY_OPERATOR"), NOW)
    back = S.map_probe_row(T2._probe("railway_backend", "DEAD"), NOW)
    down = S.row("tasks", "night_job", "DOWN", "the task exited 1", now=NOW)
    rows = [S.row(k, "x", "OK", "d", now=NOW) for k, _ in S.SECTIONS] + [fleet, back, down]
    secs = {k: {"title": t, "rows": [r for r in rows if r["section"] == k], "error": None} for k, t in S.SECTIONS}
    counted = [r for r in rows if not (r.get("extra") or {}).get("retired")]
    rec = {"receipt": S.SCHEMA, "generated_utc": S.iso(NOW), "sections": secs,
           "counts": {k: sum(1 for r in counted if r["status"] == k) for k in S.STATUSES}}
    rb = S.hosted_retired()
    rec["retired_by_owner"] = {"rows": ["infrastructure/railway_backend", "infrastructure/railway_fleet"],
                               "since_utc": rb["since_utc"], "consequence": S.retired_consequence(rb)}
    return rec


def test_s2_the_day_file_lists_retired_rows_as_their_own_state(retired):
    sec = DF.red_section(_status_rec(), "", NOW, replay=False)
    texts = [(ln["status"], ln["text"]) for ln in sec["lines"]]
    assert not any(st == DF.RED and "railway" in t for st, t in texts), texts
    ret = [t for st, t in texts if st == DF.INFO and t.startswith("[RETIRED_BY_OWNER, not counted]")]
    assert len(ret) == 2 and all(f"since {retired['since_utc']}" in t for t in ret)
    assert any("website lanes frozen" in t for t in ret)
    head = sec["lines"][0]["text"]
    assert "1 non-OK rows listed below" in head and "2 retired by the owner (not counted, listed)" in head
    assert any(st == DF.RED and "night_job" in t for st, t in texts), "a real red stays red"


def test_s2_telegram_status_names_retired_rows_once_not_as_not_ok(retired, tmp_path):
    p = tmp_path / "system_status"
    p.mkdir()
    (p / "status.json").write_text(json.dumps(_status_rec()), encoding="utf-8")
    text = TRO.status_text(root=tmp_path, now=NOW)
    lines = text.splitlines()
    assert not any(ln.startswith("RETIRED_BY_OWNER infrastructure/") for ln in lines), text
    one = [ln for ln in lines if ln.startswith("RETIRED_BY_OWNER (not counted):")]
    assert len(one) == 1 and "railway_backend" in one[0] and "railway_fleet" in one[0]
    assert f"since {retired['since_utc']}" in one[0] and "website lanes frozen" in one[0]
    assert any(ln.startswith("DOWN tasks/night_job") for ln in lines)


def test_s4_the_fleet_row_keeps_its_own_stop_date(retired, monkeypatch):
    monkeypatch.setattr(C, "RAILWAY_FLEET_STOPPED_SINCE", "2026-09-29")
    fleet = S.map_probe_row(T2._probe("railway_fleet", "STOPPED_BY_OPERATOR"), NOW)
    assert fleet["status"] == S.RETIRED_STATUS
    assert fleet["detail"].startswith("STOPPED since 2026-09-29 (" + C.RAILWAY_FLEET_STOPPED_REASON)
    assert f"RETIRED_BY_OWNER since {retired['since_utc']}" in fleet["detail"]
    assert fleet["extra"]["stopped_since"] == "2026-09-29" and fleet["extra"]["retired_since"] == retired["since_utc"]
    back = S.map_probe_row(T2._probe("railway_backend", "DEAD"), NOW)
    assert "STOPPED since" not in back["detail"] and "stopped_since" not in back["extra"]


# ── S5: book_dna decides from the declaration; ROI main() passes no flag ────

class _Spy:
    def __init__(self):
        self.urls: list = []

    def __call__(self, url):
        self.urls.append(url)

        class R:
            status_code = 200

            def json(self):
                return {"positions": [{"ticker": "SPY", "shares": 1}]}
        return R()


def test_s5_book_dna_reads_the_shipped_declaration_itself():
    assert C.hosted_backend_retired() is not None, "the shipped declaration says retired"
    spy, gaps = _Spy(), {}
    lp = BD.lane_positions(["mirror", "balanced"], gaps, http_get=spy)            # no flag passed
    assert spy.urls == [] and lp == {} and "retired" in gaps["lane_positions"]
    spy, gaps = _Spy(), {}
    BD.lane_positions(["mirror"], gaps, http_get=spy, fetch_lanes=True)           # a forced True too
    assert spy.urls == []


def test_s5_with_the_override_the_read_happens(monkeypatch):
    monkeypatch.setenv(C.HOSTED_BACKEND_ACTIVE_ENV, "1")
    spy, gaps = _Spy(), {}
    lp = BD.lane_positions(["mirror"], gaps, http_get=spy)
    assert spy.urls == [f"{BD.PROD}/api/pi/lane/mirror/positions"] and "mirror" in lp


def test_s5_roi_main_wiring_sends_nothing_to_the_retired_host(monkeypatch, tmp_path):
    """main() -> attach_book_dna -> book_dna.run -> load_inputs: the flag that reaches the lane
    read is whatever main() passes, and the lane read decides from the config."""
    spy, seen = _Spy(), {}

    def fake_inputs(receipt, *, http_get=None, fetch_lanes=None, read_only_db=False):
        seen["fetch_lanes"] = fetch_lanes
        lanes = [r["account"] for r in receipt["rows"] if r.get("family") == "website_lane"]
        seen["gaps"] = {}
        BD.lane_positions(lanes, seen["gaps"], http_get=spy, fetch_lanes=fetch_lanes)
        raise RuntimeError("stop after the lane read")
    rc = {"generated_utc": NOW.isoformat(), "rows": [{"account": "mirror", "family": "website_lane",
                                                      "status": "FROZEN", "roi_pct": None,
                                                      "spy_same_window_pct": None, "equity": 1.0}],
          "aggregate": {"honest_sentence": "s", "n_ahead_of_spy": 0}, "sources": {}}
    monkeypatch.setattr(PA, "resolve_lanes", lambda **k: (None, "x", False, {"status": PA.FROZEN}))
    monkeypatch.setattr(PA, "load_spy", lambda *a, **k: (None, "offline"))
    monkeypatch.setattr(PA, "build", lambda **k: rc)
    monkeypatch.setattr(PA, "write_outputs", lambda *a, **k: {"receipt": tmp_path / "r.json",
                                                              "receipt_run": tmp_path / "roi_x.json"})
    monkeypatch.setattr(PA, "update_frozen_sources", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(BD, "load_inputs", fake_inputs)
    assert PA.main(["--no-broker", "--no-chart"]) == 0
    assert "fetch_lanes" in seen, "main() reached book_dna's lane read"
    assert spy.urls == [] and "retired" in seen["gaps"]["lane_positions"]
    assert seen["fetch_lanes"] is None, "main() passes no flag: book_dna reads the declaration"


# ── the length of the line (Telegram 4096) ────────────────────────────────

def test_the_coverage_line_stays_within_its_character_budget():
    rows = [{"account": f"acct_{i:03d}_{'x' * 30}", "family": f"fam_{i % 40}", "status": "CREDENTIAL_INVALID",
             "broker_error": f"HTTP_401: refused {'y' * 200} {i}"} for i in range(300)]
    cov = RV.coverage_changes({"rows": rows}, None)
    line = cov["line"]
    assert len(line) <= int(C.RESULTS_VOICE_COVERAGE_MAX_CHARS) + 400 < 4096
    assert "more group(s)" in line and "account(s)) in the `coverage` block" in line
