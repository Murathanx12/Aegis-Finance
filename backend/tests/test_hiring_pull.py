"""N-G — the hiring collector, on stubbed boards. No network, ever.

Every test drives `hiring_pull._fetch` through an injected callable. The three
real endpoint shapes were verified with one live request each on 2026-09-13 and
are quoted in the module's docstring with their byte counts; nothing here
repeats that, because a test that hits an ATS is a test that fails when somebody
else's rate limit says so.

What is pinned, and each of these is a way the collector could be convincingly
wrong while every line of it ran green:

  1. the THREE SHAPES, including the two the spec got wrong (Lever returns a
     bare array; Greenhouse's `location` is an object);
  2. a malformed payload is a MISS, never an empty board — otherwise every
     parse failure is recorded as a company that stopped hiring;
  3. the probe's BUDGET is a contract: at most three requests per symbol, one
     token guess per platform, first hit wins;
  4. `first_seen_utc` is OUR clock and never the source's stamp;
  5. `n_new_since_last` is None on a first observation, not `n_open` — or the
     series carries a spike on the day we started looking;
  6. coverage is quoted with its DENOMINATOR, and a miss is not "no board".
"""

from __future__ import annotations

import json

import pytest

from scripts import hiring_pull as H


# --------------------------------------------------------------------------
# fixtures


@pytest.fixture
def hiring_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(H._config, "DATA_DIR", tmp_path, raising=False)
    return tmp_path / "optimus" / "hiring"


def _greenhouse(n=3, titles=None):
    titles = titles or [f"Engineer {i}" for i in range(n)]
    return {"jobs": [{"id": 100 + i, "title": titles[i],
                      "location": {"name": "Remote"},
                      "updated_at": "2020-01-01T00:00:00-05:00"}
                     for i in range(n)],
            "meta": {"total": n}}


def _lever(n=2, titles=None):
    """A BARE ARRAY. Verified 2026-09-13; the spec assumed an object."""
    titles = titles or [f"Designer {i}" for i in range(n)]
    return [{"id": f"uuid-{i}", "text": titles[i],
             "categories": {"location": "NYC", "team": "Design"},
             "createdAt": 1600000000000} for i in range(n)]


def _ashby(n=2, titles=None, listed=True):
    titles = titles or [f"Scientist {i}" for i in range(n)]
    return {"apiVersion": "1", "jobs": [
        {"id": f"a-{i}", "title": titles[i], "department": "R&D",
         "team": "Core", "location": "SF", "publishedAt": "2024-03-04T14:29:08Z",
         "isListed": listed} for i in range(n)]}


def _fetcher(routes: dict, calls: list | None = None):
    """`{url_substring: (status, payload)}` -> a `_fetch` stand-in."""
    def fetch(url):
        if calls is not None:
            calls.append(url)
        for frag, (status, payload) in routes.items():
            if frag in url:
                body = b"" if payload is None else json.dumps(payload).encode("utf-8")
                return status, body
        return 404, b""
    return fetch


# --------------------------------------------------------------------------
# 1. the three shapes


def test_greenhouse_location_is_an_OBJECT_not_a_string():
    jobs = H.parse_jobs("greenhouse", _greenhouse(2))
    assert [j["title"] for j in jobs] == ["Engineer 0", "Engineer 1"]
    assert jobs[0]["location"] == "Remote"
    assert jobs[0]["job_id"] == "100"


def test_lever_returns_a_BARE_ARRAY_and_the_title_lives_in_text():
    """The spec assumed `{"postings": [...]}`. A parser written to that would
    have counted zero jobs on every Lever board and looked like a coverage
    problem rather than a parsing one."""
    jobs = H.parse_jobs("lever", _lever(2))
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Designer 0"
    assert jobs[0]["location"] == "NYC"
    assert H.parse_jobs("lever", {"postings": []}) is None, "an object is NOT a Lever board"


def test_ashby_drops_unlisted_postings_and_keeps_the_rest():
    assert len(H.parse_jobs("ashby", _ashby(2))) == 2
    assert H.parse_jobs("ashby", _ashby(2, listed=False)) == []


def test_a_malformed_payload_is_a_MISS_and_never_an_empty_board():
    """The difference decides whether a parse failure is recorded as a company
    that stopped hiring."""
    for platform, bad in (("greenhouse", {"data": []}), ("lever", {"x": 1}),
                          ("ashby", ["not", "a", "board"])):
        assert H.parse_jobs(platform, bad) is None


def test_an_unknown_platform_refuses_by_name():
    with pytest.raises(H.ProbeRefused, match="unknown platform"):
        H.parse_jobs("workday", {})


# --------------------------------------------------------------------------
# 2. the token guesses


@pytest.mark.parametrize("name,greenhouse,lever", [
    ("Airbnb, Inc.", "airbnb", "airbnb"),
    ("Palo Alto Networks, Inc.", "paloaltonetworks", "palo-alto-networks"),
    ("NVIDIA Corporation", "nvidia", "nvidia"),
    ("The Walt Disney Company", "waltdisney", "walt-disney"),
    ("Agilent Technologies, Inc.", "agilenttechnologies", "agilent-technologies"),
])
def test_two_token_SHAPES_so_three_requests_are_three_questions(name, greenhouse, lever):
    assert H.token_guess(name, "greenhouse") == greenhouse
    assert H.token_guess(name, "ashby") == greenhouse
    assert H.token_guess(name, "lever") == lever


def test_a_name_that_is_only_a_suffix_guesses_nothing_rather_than_something():
    assert H.token_guess("Inc.", "greenhouse") == ""
    assert H.token_guess("", "lever") == ""
    assert H.token_guess("   ", "ashby") == ""


# --------------------------------------------------------------------------
# 3. the probe budget, which is a CONTRACT


def test_the_probe_makes_at_most_three_requests_and_the_first_hit_wins():
    calls: list[str] = []
    rec = H.probe_symbol("ABNB", "Airbnb, Inc.", pace_s=0,
                         fetch=_fetcher({"greenhouse": (200, _greenhouse(4))}, calls))
    assert len(calls) == 1, "greenhouse answered; lever and ashby were never asked"
    assert rec["board"] == {"platform": "greenhouse", "token": "airbnb",
                            "n_open_at_probe": 4,
                            "first_seen_utc": rec["board"]["first_seen_utc"]}
    assert len(rec["attempts"]) <= H.REQUESTS_PER_SYMBOL


def test_a_full_miss_costs_exactly_three_requests_and_records_all_three():
    calls: list[str] = []
    rec = H.probe_symbol("AA", "Alcoa Corporation", pace_s=0,
                         fetch=_fetcher({}, calls))
    assert len(calls) == H.REQUESTS_PER_SYMBOL == 3
    assert rec["board"] is None
    assert [a["platform"] for a in rec["attempts"]] == list(H.PLATFORMS)
    assert all(a["why"] == "HTTP 404" for a in rec["attempts"])
    assert all(a["token"] for a in rec["attempts"]), (
        "the token that was TRIED is recorded, so a later pass can tell a wrong "
        "guess from an absent board")


def test_the_platforms_are_probed_cheapest_first():
    """Ashby ships every posting's description -- 2.1 MB for 71 jobs, measured
    -- so a bounded probe spends its cheap requests first."""
    assert H.PLATFORMS[-1] == "ashby"


def test_a_board_with_zero_roles_is_a_HIT_not_a_miss():
    res = H.fetch_board("greenhouse", "x", fetch=_fetcher({"greenhouse": (200, {"jobs": []})}))
    assert res["hit"] is True and res["n_open"] == 0


def test_an_oversized_body_is_refused_unparsed():
    def fetch(url):
        return 200, b"x" * (H.MAX_BYTES + 1)
    res = H.fetch_board("greenhouse", "x", fetch=fetch)
    assert res["hit"] is False and "bytes" in res["why"]


def test_a_200_that_is_not_a_board_is_a_miss_with_that_reason():
    res = H.fetch_board("greenhouse", "x",
                        fetch=_fetcher({"greenhouse": (200, {"error": "nope"})}))
    assert res["hit"] is False
    assert res["why"] == "200 but not a board response shape"


# --------------------------------------------------------------------------
# 4. the map, its coverage and its dry run


def test_the_dry_run_makes_no_request_and_prints_the_plan(hiring_dir):
    calls: list[str] = []
    out = H.build_board_map(dry_run=True, fetch=_fetcher({}, calls),
                            symbols=["ABNB", "AA"],
                            names={"ABNB": "Airbnb, Inc.", "AA": "Alcoa Corporation"})
    assert calls == []
    assert out["ran"] is False and out["dry_run"] is True
    assert out["plan"]["requests_planned"] == 2 * H.REQUESTS_PER_SYMBOL
    assert not H.board_map_path().exists()
    assert "DRY RUN" in out["headline"]


def test_coverage_is_quoted_with_its_denominator(hiring_dir):
    out = H.build_board_map(
        pace_s=0, fetch=_fetcher({"boards/airbnb": (200, _greenhouse(5))}),
        symbols=["ABNB", "AA", "AAL"],
        names={"ABNB": "Airbnb, Inc.", "AA": "Alcoa Corporation",
               "AAL": "American Airlines Group, Inc."})
    c = out["coverage"]
    assert c["symbols_with_a_board"] == 1
    assert c["symbols_probed"] == 3
    assert c["rate_of_probed"] == pytest.approx(1 / 3, abs=1e-4)
    assert "is NOT 'this company has no board'" in c["denominator_note"]
    assert "1 board(s) over 3 probed" in out["headline"]


def test_a_symbol_with_no_company_name_is_a_recorded_miss_not_a_skip(hiring_dir):
    """A silently skipped symbol is a coverage gap nobody can see."""
    H.build_board_map(pace_s=0, fetch=_fetcher({}),
                      symbols=["ABNB", "ZZZZ"], names={"ABNB": "Airbnb, Inc."})
    state = H.load_board_map()
    assert "ZZZZ" in state["misses"]
    assert "no company name" in state["misses"]["ZZZZ"]["why"]
    assert "ZZZZ" in state["probed"]


def test_the_probe_RESUMES_rather_than_starting_again_at_the_first_name(hiring_dir):
    """An hour of somebody else's rate limit must survive a kill. The lesson is
    `G3_evolve_v2`'s 340 lost generations; the fix is the same one."""
    names = {"ABNB": "Airbnb, Inc.", "AA": "Alcoa Corporation"}
    H.build_board_map(pace_s=0, fetch=_fetcher({}), symbols=["ABNB"], names=names)
    calls: list[str] = []
    out = H.build_board_map(pace_s=0, fetch=_fetcher({}, calls),
                            symbols=["ABNB", "AA"], names=names)
    assert out["plan"]["already_probed"] == 1
    assert out["names_probed_this_pass"] == 1
    assert all("alcoa" in u for u in calls), "ABNB was not asked again"


def test_no_resume_probes_everything_again(hiring_dir):
    names = {"ABNB": "Airbnb, Inc."}
    H.build_board_map(pace_s=0, fetch=_fetcher({}), symbols=["ABNB"], names=names)
    calls: list[str] = []
    H.build_board_map(pace_s=0, fetch=_fetcher({}, calls), resume=False,
                      symbols=["ABNB"], names=names)
    assert len(calls) == H.REQUESTS_PER_SYMBOL


def test_an_empty_band_REFUSES_rather_than_writing_an_empty_map(hiring_dir):
    with pytest.raises(H.ProbeRefused, match="zero symbols"):
        H.build_board_map(symbols=[], names={})


# --------------------------------------------------------------------------
# 5. the daily rows, the cursor and the PIT rule


def test_a_snapshot_without_a_map_REFUSES_and_says_which_command_to_run(hiring_dir):
    out = H.snapshot(day="2026-09-13")
    assert out["ran"] is False
    assert "--probe" in out["refused"]
    assert "is not an empty day" in out["refused"]


def _seed_map(hiring_dir, n=5):
    H.build_board_map(pace_s=0,
                      fetch=_fetcher({"boards/airbnb": (200, _greenhouse(n))}),
                      symbols=["ABNB"], names={"ABNB": "Airbnb, Inc."})


def test_the_first_observation_has_n_new_None_not_n_open(hiring_dir):
    """Otherwise the series carries a spike on the day we started looking."""
    _seed_map(hiring_dir)
    out = H.snapshot(day="2026-09-13", pace_s=0,
                     fetch=_fetcher({"greenhouse": (200, _greenhouse(5))}))
    rows = [json.loads(x) for x in
            H.snapshot_path("2026-09-13").read_text(encoding="utf-8").splitlines() if x]
    assert out["rows"] == 1
    assert rows[0]["symbol"] == "ABNB"
    assert rows[0]["board"] == "greenhouse:airbnb"
    assert rows[0]["n_open"] == 5
    assert rows[0]["n_new_since_last"] is None
    assert rows[0]["first_observation"] is True


def test_the_second_day_counts_only_ids_absent_from_OUR_cursor(hiring_dir):
    _seed_map(hiring_dir)
    H.snapshot(day="2026-09-13", pace_s=0,
               fetch=_fetcher({"greenhouse": (200, _greenhouse(3))}))
    out = H.snapshot(day="2026-09-14", pace_s=0,
                     fetch=_fetcher({"greenhouse": (200, _greenhouse(6))}))
    rows = [json.loads(x) for x in
            H.snapshot_path("2026-09-14").read_text(encoding="utf-8").splitlines() if x]
    assert rows[0]["n_open"] == 6
    assert rows[0]["n_new_since_last"] == 3
    assert rows[0]["first_observation"] is False
    assert "absent from OUR cursor" in out["n_new_is_new_to_us"]


def test_first_seen_utc_is_OUR_clock_and_survives_every_later_day(hiring_dir):
    """The one thing that could silently poison a label. `updated_at` is an
    index-state field an ATS can backfill; a feature stamped on it would read
    the future in a way no test would catch."""
    _seed_map(hiring_dir)
    H.snapshot(day="2026-09-13", pace_s=0,
               fetch=_fetcher({"greenhouse": (200, _greenhouse(3))}))
    first = json.loads(H.snapshot_path("2026-09-13").read_text(encoding="utf-8").splitlines()[0])
    H.snapshot(day="2026-09-20", pace_s=0,
               fetch=_fetcher({"greenhouse": (200, _greenhouse(9))}))
    later = json.loads(H.snapshot_path("2026-09-20").read_text(encoding="utf-8").splitlines()[0])
    assert later["first_seen_utc"] == first["first_seen_utc"]
    assert "2020-01-01" not in later["first_seen_utc"], "the SOURCE stamp, not ours"
    assert later["first_seen_utc"].startswith("20")


def test_a_board_that_stops_answering_is_an_error_row_not_a_zero(hiring_dir):
    """A silent zero is a hiring freeze that never happened."""
    _seed_map(hiring_dir)
    H.snapshot(day="2026-09-13", pace_s=0,
               fetch=_fetcher({"greenhouse": (200, _greenhouse(3))}))
    out = H.snapshot(day="2026-09-14", pace_s=0, fetch=_fetcher({}))
    rows = [json.loads(x) for x in
            H.snapshot_path("2026-09-14").read_text(encoding="utf-8").splitlines() if x]
    assert rows[0]["n_open"] is None and rows[0]["status"] == "error"
    assert out["by_status"]["error"] == 1


def test_the_snapshot_dry_run_polls_nothing(hiring_dir):
    _seed_map(hiring_dir)
    calls: list[str] = []
    out = H.snapshot(day="2026-09-13", dry_run=True, fetch=_fetcher({}, calls))
    assert calls == [] and out["ran"] is False
    assert not H.snapshot_path("2026-09-13").exists()


# --------------------------------------------------------------------------
# 6. what it must not do


def test_the_collector_labels_nothing_and_says_so(hiring_dir):
    _seed_map(hiring_dir)
    out = H.snapshot(day="2026-09-13", pace_s=0,
                     fetch=_fetcher({"greenhouse": (200, _greenhouse(3))}))
    assert "TRIAL-HIRING-PIVOT-1 is not written" in out["labels"]
    from backend.services import news_registry
    assert news_registry.get("greenhouse_lever_ashby_ats").label_source is False


def test_no_linkedin_anywhere_in_the_collector():
    src = (H.__file__)
    text = open(src, encoding="utf-8").read().lower()
    # The word appears only in the sentences that BAN it.
    for line in text.splitlines():
        if "linkedin" in line:
            assert "banned" in line or "no linkedin" in line or "not linkedin" in line, line
    assert "linkedin.com" not in text
    assert all("linkedin" not in u.lower() for u in H.ENDPOINTS.values())


def test_the_ai_title_vocabulary_is_recorded_and_leads_no_selection(hiring_dir):
    assert H.is_ai_titled("Senior Machine Learning Engineer")
    assert H.is_ai_titled("Applied Scientist, LLM")
    assert H.is_ai_titled("AI Product Manager")
    assert not H.is_ai_titled("Retail Associate")
    assert not H.is_ai_titled("Mail Room Clerk"), "'ml' inside a word is not a match"
    _seed_map(hiring_dir)
    H.snapshot(day="2026-09-13", pace_s=0,
               fetch=_fetcher({"greenhouse": (200, _greenhouse(
                   2, titles=["ML Engineer", "Barista"]))}))
    row = json.loads(H.snapshot_path("2026-09-13").read_text(encoding="utf-8").splitlines()[0])
    assert row["n_ai_titled"] == 1 and row["ai_title_share"] == 0.5


def test_the_band_is_the_one_the_other_jobs_use_not_a_third_definition():
    """Three copies of the $10M/$5/ETF filter would be three things to keep in
    step. This is the second CALLER of the one definition, not a second one."""
    import inspect
    src = inspect.getsource(H.tradable_band)
    assert "analyst_snapshot" in src and "_symbols" in src
    assert "10_000_000" not in src and "median_dollar_volume" not in src


def test_the_job_is_registered_and_its_stage_is_raw():
    from scripts.night_factory_jobs import JOB_STAGES, JOBS
    assert "H1_hiring_pull" in JOBS
    assert JOB_STAGES["H1_hiring_pull"] == "raw"


def test_a_smoke_run_is_a_dry_run_of_both_steps(hiring_dir, monkeypatch):
    """This job's only side effect is traffic against somebody else's rate
    limit, so 'prove it runs' must not mean 7,000 requests."""
    # 2026-09-14: the band is READ from the execution repo's stored universe,
    # which no CI checkout has (red on 85546ba0). A synthetic band here.
    monkeypatch.setattr(H, "tradable_band", lambda: (["ACME", "WIDG"], {"source": "synthetic"}))
    out = H.H1_hiring_pull(smoke=True, probe=True)
    assert out["dry_run"] is True and out["ran"] is False
    assert not H.board_map_path().exists()
