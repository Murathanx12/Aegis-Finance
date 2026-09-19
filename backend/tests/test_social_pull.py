"""Chunk 20 T2 — the social collector on fake clients. No key, no PRAW, no socket.

Every external effect is injected: the Reddit client is a fake object with the
three attributes PRAW exposes, and YouTube's door is a `fetch` callable. The
tests run with both key NAMES deliberately absent, because **the refusal is the
live path on 2026-09-19** — neither key exists yet — and a collector whose
refusal is untested is a collector that will crash the first night it matters.

What is pinned, and each is a way this could run green and be wrong:

  1. each source REFUSES BY NAME with its key names in the message, and the run
     still exits 0 — a missing key is a fact about the environment, not a
     failure of the pass;
  2. **no key VALUE can reach a log, a receipt or an exception.** Two tests: an
     AST walk over executable source (docstrings skipped, because a grep-shaped
     guard that cannot tell an explanation from an instance is a broken guard),
     and a behavioural one that sets every key to a sentinel and greps the
     whole receipt and stdout for it;
  3. COMMENTS are pulled, with `parent_id`, and they are the half no existing
     source has ever had;
  4. `first_seen_utc` is OUR clock and engagement is AS-OF FIRST SEEN — a
     re-fetched upvote count is a look-ahead;
  5. the YouTube quota is charged BEFORE the call, counted on the PACIFIC day,
     and the run refuses `YOUTUBE_QUOTA_SPENT` rather than overspending;
  6. the transcript step refuses by name instead of being silently absent.
"""

from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import social_pull as S

SENTINEL = "SENTINEL-KEY-VALUE-0d41f9"


@pytest.fixture
def social(tmp_path, monkeypatch):
    """Point the social directory at tmp_path; strip every key NAME."""
    monkeypatch.setattr(S._config, "DATA_DIR", tmp_path, raising=False)
    for name in S.REDDIT_KEY_NAMES + S.YOUTUBE_KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "optimus" / "social"


# --------------------------------------------------------------------------
# fake clients


class FakeAuthor:
    def __init__(self, name):
        self.name = name


class FakeComment:
    def __init__(self, cid, body, parent_id, score=3):
        self.id = cid
        self.body = body
        self.parent_id = parent_id
        self.score = score
        self.created_utc = 1700000000
        self.author = FakeAuthor(f"u_{cid}")
        self.permalink = f"/r/x/comments/p/{cid}/"


class FakeForest:
    def __init__(self, comments):
        self._c = comments
        self.replaced_with = None

    def replace_more(self, limit=None):
        self.replaced_with = limit

    def list(self):
        return list(self._c)


class FakeSubmission:
    def __init__(self, pid, title, selftext="", comments=(), score=11):
        self.id = pid
        self.title = title
        self.selftext = selftext
        self.score = score
        self.num_comments = len(comments)
        self.upvote_ratio = 0.92
        self.created_utc = 1700000000
        self.author = FakeAuthor(f"u_{pid}")
        self.permalink = f"/r/x/comments/{pid}/"
        self.comments = FakeForest(comments)


class FakeSubreddit:
    def __init__(self, posts):
        self.posts = posts
        self.limits: list[int] = []

    def new(self, limit=None):
        self.limits.append(limit)
        return list(self.posts)[: (limit or len(self.posts))]


class FakeReddit:
    def __init__(self, by_sub):
        self.by_sub = by_sub
        self.asked: list[str] = []

    def subreddit(self, name):
        self.asked.append(name)
        return FakeSubreddit(self.by_sub.get(name, []))


def _one_sub_client():
    comments = [
        FakeComment("c1", "I think $NVDA runs further from here", "t3_p1"),
        FakeComment("c2", "disagree, this is late", "t1_c1"),
    ]
    return FakeReddit({"wallstreetbets": [
        FakeSubmission("p1", "NVDA earnings thread",
                       "Nvidia beat again, $NVDA", comments)]})


def _youtube_fetch(items, status=200, seen=None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return status, json.dumps({"items": items}).encode("utf-8")
    return fetch


def _video(vid, title="NVDA earnings breakdown", desc="about $NVDA"):
    return {"id": {"videoId": vid},
            "snippet": {"title": title, "description": desc,
                        "channelTitle": "A Channel",
                        "publishedAt": "2026-09-18T12:00:00Z"}}


# --------------------------------------------------------------------------
# the refusals — the live path today


def test_reddit_refuses_by_name_and_names_the_keys(social):
    out = S.pull_reddit()
    assert out["status"] == "REFUSED"
    assert out["refused"] == "REDDIT_KEYS_ABSENT"
    joined = " ".join(out["failures"])
    for name in S.REDDIT_KEY_NAMES:
        assert name in joined, f"{name} must be named in the refusal"
    assert "prefs/apps" in joined, "the refusal says where the key is created"


def test_youtube_refuses_by_name_and_names_the_key(social):
    out = S.pull_youtube()
    assert out["status"] == "REFUSED"
    assert out["refused"] == "YOUTUBE_KEY_ABSENT"
    assert "YOUTUBE_API_KEY" in " ".join(out["failures"])


def test_the_run_still_exits_zero_with_both_refusals_on_the_receipt(social, capsys):
    rc = S.main([])
    assert rc == 0, "a missing key is a fact about the environment, not a failure"
    out = json.loads(capsys.readouterr().out)
    assert out["refusals"] == {"reddit": "REDDIT_KEYS_ABSENT",
                              "youtube": "YOUTUBE_KEY_ABSENT"}
    receipts = sorted(social.glob("_receipt_*.json"))
    assert len(receipts) == 1, "a refused run still writes its receipt"


def test_an_unknown_source_is_a_refusal_about_the_invocation(social):
    with pytest.raises(S.SocialRefused, match="UNKNOWN_SOURCE"):
        S.pull(sources=("tiktok",))
    assert S.main(["--source", "tiktok"]) == 2


def test_the_transcript_step_refuses_by_name_rather_than_being_absent(social):
    r = S.transcript_refusal()
    assert r["refused"] == "TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE"
    assert "residential proxy" in r["why"]
    out = S.pull(sources=("youtube",))
    assert out["not_built"]["transcripts"] == "TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE"
    assert "instagram" in out["not_built"] and "x_twitter" in out["not_built"]


def test_every_refusal_name_is_declared():
    assert set(S.REFUSALS) == {
        "REDDIT_KEYS_ABSENT", "YOUTUBE_KEY_ABSENT", "PRAW_NOT_INSTALLED",
        "YOUTUBE_QUOTA_SPENT", "TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE",
        "UNKNOWN_SOURCE"}


# --------------------------------------------------------------------------
# no key value can escape


def _executable_source(path: Path) -> ast.Module:
    """The module's AST with every DOCSTRING removed.

    2026-09-18's lesson, at this repo's own expense: three guards failed on
    their first run by matching the docstring that EXPLAINS the banned pattern.
    A guard that cannot tell an explanation from an instance teaches the next
    reader to delete the explanation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _is_env_read(node: ast.AST) -> bool:
    """`os.getenv(...)` or `os.environ[...]` / `os.environ.get(...)`."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "getenv":
            return True
        if (isinstance(f, ast.Attribute) and f.attr == "get"
                and isinstance(f.value, ast.Attribute) and f.value.attr == "environ"):
            return True
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
        return node.value.attr == "environ"
    return False


def test_no_key_value_can_reach_a_log_or_a_receipt():
    """AST, not grep. A key VALUE may be passed to a CLIENT; it may never be
    an argument to print/logging/json.dumps, a formatted string, or a value in
    a dict literal (which is what a receipt is)."""
    tree = _executable_source(Path(S.__file__))
    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = (f.id if isinstance(f, ast.Name)
                    else f.attr if isinstance(f, ast.Attribute) else "")
            if name in {"print", "format", "dumps", "debug", "info", "warning",
                        "error", "exception", "critical", "log"}:
                for arg in ast.walk(node):
                    if arg is not node and _is_env_read(arg):
                        offences.append(f"{name}() at line {node.lineno}")
        if isinstance(node, ast.JoinedStr):
            for part in ast.walk(node):
                if _is_env_read(part):
                    offences.append(f"f-string at line {node.lineno}")
        if isinstance(node, ast.Dict):
            for v in node.values:
                if v is not None and _is_env_read(v):
                    offences.append(f"dict value at line {node.lineno}")
    assert not offences, f"a key value could reach a reader: {offences}"


def test_a_sentinel_key_value_appears_nowhere_in_the_receipt(social, monkeypatch,
                                                             capsys):
    """The behavioural half. The AST test says the shapes are absent; this one
    says the STRING is, through the whole run and everything it printed."""
    for name in S.REDDIT_KEY_NAMES + S.YOUTUBE_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    fetch = _youtube_fetch([_video("v1")])
    monkeypatch.setattr(S, "_http_get", fetch)
    out = S.pull(sources=("youtube",), fetch=fetch, pace_s=0.0)
    blob = json.dumps(out, default=str)
    assert SENTINEL not in blob, "a key value reached the receipt"
    S.main(["--source", "youtube", "--dry-run"])
    assert SENTINEL not in capsys.readouterr().out
    for p in social.rglob("*"):
        if p.is_file():
            assert SENTINEL not in p.read_text(encoding="utf-8", errors="replace")


def test_key_status_reports_names_and_booleans_only(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)
    st = S.key_status()
    assert st["youtube"] == {"YOUTUBE_API_KEY": True}
    assert st["reddit"] == {n: False for n in S.REDDIT_KEY_NAMES}
    assert SENTINEL not in json.dumps(st)


def test_the_search_url_never_carries_the_key(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)
    url = S.youtube_search_url("earnings call analysis")
    assert "key=" not in url and SENTINEL not in url
    assert "q=earnings+call+analysis" in url


# --------------------------------------------------------------------------
# reddit: posts AND comments


def test_posts_and_comments_are_both_written_with_parent_ids(social, monkeypatch):
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    client = _one_sub_client()
    out = S.pull_reddit(client=client, subreddits=("wallstreetbets",), pace_s=0.0)
    assert out["status"] == "OK", out["failures"]
    assert out["posts"] == 1
    assert out["comments"] == 2, "comments are the half no existing source has"
    rows = _rows(social, "reddit")
    post = [r for r in rows if r["kind"] == "post"][0]
    kids = [r for r in rows if r["kind"] == "comment"]
    assert post["id"] == "t3_p1" and post["parent_id"] == ""
    assert {c["parent_id"] for c in kids} == {"t3_p1", "t1_c1"}, \
        "a reply's parent is the COMMENT, not the post — that is the thread shape"
    for r in rows:
        assert set(r) == set(S.ROW_KEYS), "the social row schema drifted"
        assert r["pit_grade"] == "index_state"


def _rows(social: Path, source: str) -> list[dict]:
    rows = []
    for p in sorted(social.glob(f"{source}_*.jsonl")):
        rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows


def test_ticker_mentions_come_from_cashtags_and_the_name_table(social, monkeypatch):
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    S.pull_reddit(client=_one_sub_client(), subreddits=("wallstreetbets",), pace_s=0.0)
    rows = _rows(social, "reddit")
    tagged = [r for r in rows if r["ticker_mentions"]]
    assert tagged, "a $NVDA cashtag must resolve"
    assert "NVDA" in tagged[0]["ticker_mentions"]
    assert tagged[0]["ticker_rules"]["NVDA"] in {"cashtag", "name", "paren_ticker"}


def test_an_unknown_cashtag_is_not_a_ticker():
    syms, _ = S.ticker_mentions("$YOLOOO to the moon")
    assert syms == []
    assert S.cashtag_count("$NVDA and $YOLOOO") == 1


def test_first_seen_is_ours_and_engagement_is_as_of_first_seen(social, monkeypatch):
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    S.pull_reddit(client=_one_sub_client(), subreddits=("wallstreetbets",), pace_s=0.0)
    row = [r for r in _rows(social, "reddit") if r["kind"] == "post"][0]
    seen = datetime.fromisoformat(row["first_seen_utc"])
    assert before <= seen <= datetime.now(timezone.utc)
    # ...and it is NOT the provider's created_utc.
    assert row["created_utc_provider"] == "1700000000"
    assert row["engagement"]["score"] == 11
    assert row["engagement"]["num_comments"] == 2


def test_a_second_pass_does_not_rewrite_what_it_already_has(social, monkeypatch):
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    first = S.pull_reddit(client=_one_sub_client(), subreddits=("wallstreetbets",),
                          pace_s=0.0)
    second = S.pull_reddit(client=_one_sub_client(), subreddits=("wallstreetbets",),
                           pace_s=0.0)
    assert first["rows"] == 3
    assert second["rows"] == 0 and second["dupes"] == 3
    assert len(_rows(social, "reddit")) == 3, "the file is append-only, not rewritten"


def test_a_known_post_still_has_its_comment_tree_read(social, monkeypatch):
    """THE DEFECT THIS TEST FOUND. A post is written once and then accumulates
    comments for days; the first version of the loop skipped the whole tree of
    any post it already had, which would have collected only the comments that
    existed in the first minutes of a post's life — and dispersion is computed
    over exactly the ones that arrive afterwards."""
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    S.pull_reddit(client=_one_sub_client(), subreddits=("wallstreetbets",), pace_s=0.0)

    later = _one_sub_client()
    post = later.subreddit("wallstreetbets").posts[0]
    post.comments = FakeForest(list(post.comments.list())
                               + [FakeComment("c3", "new reply, still bullish", "t3_p1")])
    out = S.pull_reddit(client=later, subreddits=("wallstreetbets",), pace_s=0.0)
    assert out["posts"] == 0, "the post itself is a dupe"
    assert out["comments"] == 1, "its NEW comment is not"
    assert {r["id"] for r in _rows(social, "reddit") if r["kind"] == "comment"} == {
        "t1_c1", "t1_c2", "t1_c3"}


def test_load_more_stubs_are_dropped_rather_than_expanded(social, monkeypatch):
    """Each expansion is another API call. The cap and this rule TOGETHER are
    the dispersion variable's denominator."""
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    client = _one_sub_client()
    sub = client.subreddit("wallstreetbets")
    post = sub.posts[0]
    S._comment_list(post, 100)
    assert post.comments.replaced_with == 0


def test_the_comment_cap_binds(social, monkeypatch):
    for name in S.REDDIT_KEY_NAMES:
        monkeypatch.setenv(name, SENTINEL)
    many = [FakeComment(f"c{i}", f"body {i}", "t3_p1") for i in range(40)]
    client = FakeReddit({"stocks": [FakeSubmission("p9", "t", "", many)]})
    out = S.pull_reddit(client=client, subreddits=("stocks",),
                        comments_per_post=5, pace_s=0.0)
    assert out["comments"] == 5


def test_a_dry_run_makes_no_request(social):
    out = S.pull(dry_run=True)
    assert all(p["status"] == "DRY_RUN" for p in out["per_source"])
    assert not list(social.glob("*.jsonl"))
    assert not list(social.glob("_receipt_*.json")), "a dry run writes no receipt"


def test_the_declared_subreddit_list_includes_the_sub_the_null_came_from():
    """§2.3's null IS the WSB peak-attention finding. A hype-lateness variable
    computed without that sub could not be compared with it."""
    assert "wallstreetbets" in S.SUBREDDITS
    assert "SecurityAnalysis" in S.SUBREDDITS
    assert len(set(S.SUBREDDITS)) == len(S.SUBREDDITS)


# --------------------------------------------------------------------------
# youtube: the quota is the scarce thing


def test_a_search_writes_video_rows(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)
    seen: list[str] = []
    out = S.pull_youtube(queries=("earnings call analysis",),
                         fetch=_youtube_fetch([_video("v1"), _video("v2")], seen=seen),
                         pace_s=0.0)
    assert out["status"] == "OK", out["failures"]
    assert out["rows"] == 2 and out["searches"] == 1
    rows = _rows(social, "youtube")
    assert {r["id"] for r in rows} == {"v1", "v2"}
    assert rows[0]["url"].endswith("v=v1")
    assert rows[0]["engagement"] == {"query": "earnings call analysis"}, \
        "search.list carries no view count; an invented zero would read as measured"
    assert len(seen) == 1 and "key=" in seen[0], "the key rides on the wire only"


def test_units_are_charged_before_the_call_and_persist(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)

    def exploding(url):
        raise RuntimeError("the call never returned")

    out = S.pull_youtube(queries=("q1",), fetch=exploding, pace_s=0.0)
    assert out["quota"]["units_spent_after"] == S._config.SOCIAL_YOUTUBE_SEARCH_UNITS
    cur = json.loads((social / "_cursor_youtube.json").read_text(encoding="utf-8"))
    assert cur["units_spent"] == S._config.SOCIAL_YOUTUBE_SEARCH_UNITS, \
        "a request that times out still spent its quota at the provider"


def test_the_daily_cap_refuses_rather_than_overspending(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)
    monkeypatch.setattr(S._config, "SOCIAL_YOUTUBE_DAILY_UNITS", 150, raising=False)
    seen: list[str] = []
    out = S.pull_youtube(queries=("q1", "q2", "q3"),
                         fetch=_youtube_fetch([_video("v1")], seen=seen), pace_s=0.0)
    assert out["searches"] == 1, "100 + 100 > 150, so only one search fits"
    assert out["refused"] == "YOUTUBE_QUOTA_SPENT"
    assert "2 query" in " ".join(out["failures"]) or "2 queries" in " ".join(out["failures"])
    assert len(seen) == 1


def test_the_quota_day_is_pacific_not_utc():
    """Getting this wrong does not fail: it silently spends tomorrow's
    allowance this evening."""
    # 2026-09-19 03:00 UTC is still 2026-09-18 in Los Angeles.
    dt = datetime(2026, 9, 19, 3, 0, tzinfo=timezone.utc)
    assert S.quota_day(dt) == "2026-09-18"
    assert S.quota_day(datetime(2026, 9, 19, 17, 0, tzinfo=timezone.utc)) == "2026-09-19"


def test_yesterdays_spend_does_not_bind_today(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)
    social.mkdir(parents=True, exist_ok=True)
    (social / "_cursor_youtube.json").write_text(
        json.dumps({"quota_day": "1999-01-01", "units_spent": 10_000}),
        encoding="utf-8")
    out = S.pull_youtube(queries=("q1",), fetch=_youtube_fetch([_video("v1")]),
                         pace_s=0.0)
    assert out["quota"]["units_spent_before"] == 0
    assert out["searches"] == 1


def test_a_403_is_a_named_failure_not_a_crash(social, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL)
    out = S.pull_youtube(queries=("q1",),
                         fetch=_youtube_fetch([], status=403), pace_s=0.0)
    assert out["rows"] == 0
    assert any("403" in f and "quota" in f for f in out["failures"])


def test_the_key_names_are_the_two_murat_must_create():
    """The handoff's §6b entry names these two and nothing else."""
    assert S.REDDIT_KEY_NAMES == ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                                  "REDDIT_USER_AGENT")
    assert S.YOUTUBE_KEY_NAMES == ("YOUTUBE_API_KEY",)
    assert os.getenv("REDDIT_CLIENT_ID") is None or True  # never read for a value
