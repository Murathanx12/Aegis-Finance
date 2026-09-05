"""Labor Day Lab — lane D. `scripts/connection_check.py`, OFFLINE.

Every test here runs with the network blocked (`backend/tests/conftest.py`
covers Python sockets AND curl_cffi). Nothing below opens one: the HTTP layer is
stubbed, and the classification logic — which is the part that has been wrong in
five separate sessions — is exercised directly.

The three things pinned, in order of how much they cost when they broke:

1. **A 403 beside a 200 from the same credential is ENTITLEMENT, not a dead
   key.** Finnhub's free tier, FMP's retired `/api/v3` surface and Polygon's
   paid trade endpoint all produce this shape, and reading it as a dead key
   sends someone to re-mint a working credential.
2. **No probe output ever contains a credential.** Fingerprints are one-way and
   URLs are redacted before they enter a receipt.
3. **A name that code builds at runtime is not an unused key.**
   `alpha/config.py` reads `AAT_HACK4_KEY_ID` through an f-string, so a
   grep-only inventory calls all twelve fleet credentials dead weight — and the
   action that verdict invites would disarm the fleet.
"""

from __future__ import annotations

import json

import pytest

from scripts import connection_check as cc


# ── 1. credentials never leave the process ───────────────────────────────────

def test_key_fingerprint_never_contains_the_key():
    # Deliberately NOT key-shaped: a secrets sweep over this repo must
    # not have to decide whether a test fixture is a real credential.
    secret = "NOT-A-KEY-fixture-value-for-the-fingerprint-test"
    fp = cc.key_fp(secret)
    assert secret not in fp
    for n in (4, 6, 8, 12):
        assert secret[:n] not in fp, f"first {n} chars leaked"
        assert secret[-n:] not in fp, f"last {n} chars leaked"
    assert fp.startswith("sha256:")
    assert fp.endswith(f"/len{len(secret)}")


def test_key_fingerprint_is_none_for_absent_and_for_empty():
    # `ANTHROPIC_API_KEY=` with an empty value has read as "configured" in this
    # repo's provider resolver for months. Absent and empty are one thing here.
    assert cc.key_fp(None) is None
    assert cc.key_fp("") is None
    assert cc.key_fp("   ") is None


def test_key_fingerprint_distinguishes_two_different_keys_of_equal_length():
    a, b = "A" * 40, "B" * 40
    assert cc.key_fp(a) != cc.key_fp(b)
    assert cc.key_fp(a) == cc.key_fp("A" * 40)


@pytest.mark.parametrize("param", ["api_key", "apikey", "token", "apiKey",
                                   "secret", "access_token", "api_token"])
def test_redact_url_strips_every_credential_query_parameter(param):
    url = f"https://vendor.example/v1/thing?symbol=AAPL&{param}=SECRETVALUE123"
    out = cc._redact_url(url)
    assert "SECRETVALUE123" not in out
    assert "symbol=AAPL" in out, "non-secret parameters must survive"


def test_redact_url_keeps_a_pathless_query_free_url_intact():
    assert cc._redact_url("https://a.example/b/c") == "https://a.example/b/c"


def test_markdown_table_carries_no_fingerprint_and_no_query_string():
    receipt = {
        "rows": [{"provider": "X", "status": "ok", "latency_ms": 12.3,
                  "entitlement": "granted", "failure_class": None,
                  "key_fingerprint": "sha256:deadbeef/len40",
                  "detail": "", "endpoints": []}],
        "counts": {"ok": 1, "fail": 0, "cannot_determine": 0, "total": 1},
    }
    md = cc.to_markdown(receipt)
    assert "deadbeef" not in md
    assert "sha256" not in md
    assert "| X | ok |" in md


# ── 2. the classifier ────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    (401, cc.AUTH),
    (403, cc.ENTITLEMENT),
    (429, cc.QUOTA),
    (402, cc.QUOTA),
    (500, cc.NETWORK),
    (503, cc.NETWORK),
    (404, cc.CANNOT),
])
def test_http_codes_map_to_the_right_failure_class(code, expected):
    assert cc._classify_http(code, "")[0] == expected


def test_a_403_whose_body_says_the_key_is_invalid_is_auth_not_entitlement():
    klass, _ = cc._classify_http(403, '{"error":"Invalid API key supplied"}')
    assert klass == cc.AUTH


def _stub_http(monkeypatch, table):
    """Replace the HTTP layer with a lookup. NO SOCKET IS OPENED."""
    def fake(url, **kw):
        for needle, code in table.items():
            if needle in url:
                break
        else:
            raise AssertionError(f"probe requested an unstubbed url: {url}")
        if code is None:
            return {"ok": False, "code": None, "ms": 1.0, "body": "",
                    "class": cc.NETWORK, "why": "TimeoutError: stub",
                    "url": cc._redact_url(url)}
        if 200 <= code < 300:
            return {"ok": True, "code": code, "ms": 1.0, "body": "{}",
                    "headers": {}, "class": None, "url": cc._redact_url(url)}
        klass, why = cc._classify_http(code, "")
        return {"ok": False, "code": code, "ms": 1.0, "body": "",
                "class": klass, "why": why, "url": cc._redact_url(url)}
    monkeypatch.setattr(cc, "http", fake)


def test_a_403_beside_a_200_is_entitlement_and_the_probe_stays_ok(monkeypatch):
    """THE LESSON. Finnhub free tier: `/quote` 200, `/price-target` 403."""
    _stub_http(monkeypatch, {"/quote": 200, "/price-target": 403})
    p = cc.Probe("stub", group="data", why="")
    out = cc._multi(p, [("free", "https://v.example/quote", None),
                        ("premium", "https://v.example/price-target", None)],
                   free={"free"})
    assert out.status == cc.OK
    assert out.failure_class is None
    assert "NOT entitled(403)" in out.entitlement
    assert "premium" in out.entitlement


def test_every_endpoint_refusing_the_credential_is_a_dead_key(monkeypatch):
    _stub_http(monkeypatch, {"/a": 401, "/b": 403})
    p = cc.Probe("stub", group="data", why="")
    out = cc._multi(p, [("a", "https://v.example/a", None),
                        ("b", "https://v.example/b", None)], free={"a"})
    assert out.status == "FAIL"
    assert out.failure_class == cc.DEAD_KEY


def test_a_401_beside_a_200_is_reported_separately_from_a_403(monkeypatch):
    """EODHD: `/user` answers 200 and `/eod` answers 401 — a lapsed data
    subscription. Folding it into 'not entitled' hides which one a renewal
    would fix."""
    _stub_http(monkeypatch, {"/user": 200, "/eod": 401})
    p = cc.Probe("stub", group="data", why="")
    out = cc._multi(p, [("user", "https://v.example/user", None),
                        ("eod", "https://v.example/eod", None)], free={"eod"})
    assert out.status == cc.OK
    assert "401 on: eod" in out.entitlement
    assert "NOT entitled(403)" not in out.entitlement


def test_a_timeout_everywhere_is_network_and_never_reads_as_no_data(monkeypatch):
    _stub_http(monkeypatch, {"/a": None, "/b": None})
    p = cc.Probe("stub", group="data", why="")
    out = cc._multi(p, [("a", "https://v.example/a", None),
                        ("b", "https://v.example/b", None)], free={"a"})
    assert out.failure_class == cc.NETWORK
    assert out.status == "FAIL"


def test_rate_limited_everywhere_is_quota_not_absence(monkeypatch):
    _stub_http(monkeypatch, {"/a": 429, "/b": 429})
    p = cc.Probe("stub", group="data", why="")
    out = cc._multi(p, [("a", "https://v.example/a", None),
                        ("b", "https://v.example/b", None)], free={"a"})
    assert out.failure_class == cc.QUOTA


def test_a_probe_that_cannot_answer_says_so_instead_of_guessing_ok(monkeypatch):
    """A guard DERIVES its inputs or REFUSES. 404 everywhere is neither a
    working provider nor a refused credential."""
    _stub_http(monkeypatch, {"/a": 404, "/b": 404})
    p = cc.Probe("stub", group="data", why="")
    out = cc._multi(p, [("a", "https://v.example/a", None),
                        ("b", "https://v.example/b", None)], free={"a"})
    assert out.status == "CANNOT_DETERMINE"
    assert out.failure_class == cc.CANNOT


def test_a_fresh_probe_defaults_to_cannot_determine_not_to_ok():
    """The default must be the honest one: a probe that never ran has not
    passed. Every `ok` in a receipt was written by a measurement."""
    p = cc.Probe("never ran", group="?", why="?")
    assert p.status == "CANNOT_DETERMINE"
    assert p.failure_class == cc.CANNOT
    assert p.as_dict()["status"] != cc.OK


# ── 3. the D2 inventory ──────────────────────────────────────────────────────

def test_env_names_reads_names_and_lengths_but_no_values(tmp_path):
    f = tmp_path / ".env"
    f.write_text('A_KEY=abcdef\n# comment\n\nB_KEY=""\nC=x\nNOEQUALS\n',
                 encoding="utf-8")
    got = cc._env_names(f)
    assert set(got) == {"A_KEY", "B_KEY", "C"}
    assert got["A_KEY"]["length"] == 6
    assert got["B_KEY"]["empty"] is True
    blob = json.dumps(got)
    assert "abcdef" not in blob, "a value reached the inventory structure"


def test_env_names_on_a_missing_file_is_empty_not_an_error(tmp_path):
    assert cc._env_names(tmp_path / "nope.env") == {}


@pytest.mark.parametrize("refs,expected", [
    ([], "UNREFERENCED"),
    (["finance:backend/services/x.py:10"], "READ_IN_CODE"),
    (["finance:backend/tests/test_x.py:3"], "TESTS_ONLY"),
    (["terminal:tests_smoke_x.py:3"], "TESTS_ONLY"),
    (["finance:docs/NOTES.md:1"], "DOCS_ONLY"),
    (["terminal:.env.example:2"], "TEMPLATE_ONLY"),
    (["finance:docs/NOTES.md:1", "finance:backend/x.py:2"], "READ_IN_CODE"),
])
def test_reference_class_is_decided_by_where_not_by_how_many(refs, expected):
    assert cc._classify_refs(refs) == expected


def test_a_runtime_constructed_name_is_not_dead_weight(tmp_path):
    """`AAT_HACK4_KEY_ID` appears in no source file: `alpha/config.py` builds it
    from the role. A grep-only inventory calls all twelve fleet credentials
    unused, and 'delete the unused keys' would disarm every book."""
    root = tmp_path / "terminal"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "config.py").write_text(
        'key_id = os.getenv(f"{prefix}_KEY_ID", "").strip()\n', encoding="utf-8")
    ev = cc._constructed_name_evidence("AAT_HACK4_KEY_ID", {"terminal": root})
    assert ev is not None
    assert "AAT_<ROLE>_KEY_ID" in ev


def test_the_constructed_name_rule_is_derived_and_not_an_exemption_list(tmp_path):
    """No `getenv` on a built name in the tree means no claim. The rule must
    stop asserting itself the moment the code it describes is gone."""
    root = tmp_path / "terminal"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "config.py").write_text("x = 1\n", encoding="utf-8")
    assert cc._constructed_name_evidence("AAT_HACK4_KEY_ID", {"terminal": root}) is None


def test_a_name_that_is_not_role_shaped_is_never_excused(tmp_path):
    root = tmp_path / "terminal"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "config.py").write_text(
        'key_id = os.getenv(f"{prefix}_KEY_ID", "")\n', encoding="utf-8")
    assert cc._constructed_name_evidence("SOME_RANDOM_TOKEN", {"terminal": root}) is None


def test_the_reference_scan_never_opens_a_real_env_file(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".env").write_text("MY_SECRET_NAME=value\n", encoding="utf-8")
    (root / "app.py").write_text("print('hello')\n", encoding="utf-8")
    hits = cc._references({"repo": root}, ["MY_SECRET_NAME"])
    assert hits["MY_SECRET_NAME"] == [], (
        "the scanner read a real .env and counted it as a caller")


def test_the_reference_scan_does_not_count_the_probe_itself_as_a_caller(tmp_path):
    """A PROBE IS NOT A CALLER. `connection_check.py` names variables in its own
    comments; counting those made a runtime-built name read as READ_IN_CODE
    because a comment about it being grep-invisible was grep-visible."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "connection_check.py").write_text(
        "# mentions SOME_TOKEN_NAME in a comment\n", encoding="utf-8")
    hits = cc._references({"repo": root}, ["SOME_TOKEN_NAME"])
    assert hits["SOME_TOKEN_NAME"] == []


# ── 4. the registry is coherent ──────────────────────────────────────────────

def test_every_paid_probe_is_registered_and_accepts_the_llm_switch():
    for n in cc.LLM_PROBES:
        assert n in cc.PROBES, f"{n} is billed for but not registered"
        assert "llm" in cc.PROBES[n].__code__.co_varnames, (
            f"{n} is in LLM_PROBES but cannot be switched off with --no-llm")


def test_the_paid_probes_carry_a_justification_naming_a_decision():
    why = cc.LLM_PROBE_WHY
    assert len(why) >= 60
    assert any(v in why.lower() for v in
               ("decide", "decides", "keep", "delete", "drop", "refuse", "rank"))


def test_no_probe_name_collides_and_every_probe_is_callable():
    assert len(cc.PROBES) == len(set(cc.PROBES))
    for n, fn in cc.PROBES.items():
        assert callable(fn), n


def test_var_to_probe_only_points_at_probes_that_exist():
    for var, probe in cc.VAR_TO_PROBE.items():
        if probe is None:
            continue
        assert probe in cc.PROBES, f"{var} maps to unknown probe {probe!r}"
        assert probe in cc._PROBE_DISPLAY, f"{probe} has no display name to join on"


def test_the_revoked_finance_alpaca_names_are_covered_by_a_probe():
    """Session 36 recorded the mirror and arena key pairs as revoked. A record
    is not a measurement; the inventory must be able to join a live result."""
    for name in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY",
                 "ALPACA_ARENA_API_KEY_ID", "ALPACA_ARENA_API_SECRET_KEY"):
        assert cc.VAR_TO_PROBE.get(name) == "alpaca_revoked"


def test_run_checks_is_importable_as_a_callable_entry_point():
    """It becomes a nightly job by being CALLED, not by this file scheduling it."""
    import inspect
    sig = inspect.signature(cc.run_checks)
    assert set(sig.parameters) == {"only", "llm", "workers"}
    assert sig.parameters["llm"].default is True
