"""The loop as it runs today, read from receipts and configuration only (ROADMAP CH-56).

WHY IT EXISTS
=============
Aegis is meant to be a closed loop: SENSE -> UNIVERSE -> DECIDE -> ACT -> LEARN -> back
into SENSE and DECIDE. Every stage writes receipts, and on 2026-11-16 a council found
by hand that the loop is not closed: consumers gated by flags that are False, a book
that never stepped, learners nothing reads. Nobody could see that from one place.
This module is that place. It adds no mechanism: a DECLARED table of links (`LINKS`)
and a reader that gives each link ONE status from real state.

STATUSES (one per link)
=======================
* ``FLOWING``          the producer's newest receipt is fresh by its OWN stamp AND the
                       consumer's newest receipt cites a producer id that exists and
                       is itself fresh.
* ``STALE``            the producer (or the producer receipt the consumer cites) is
                       older than the link's limit; the age is printed.
* ``OFF``              a config flag that gates the consumer is not True; the flag,
                       its value and the config file it was read from are printed.
* ``NO_CONSUMER``      the producer is fresh and nothing is declared or PROVEN to read
                       it (no consumer, a consumer that cites nothing, a consumer
                       receipt that does not exist, or a cited id no producer wrote).
* ``ABSENT``           there is no producer receipt.
* ``CANNOT_DETERMINE`` a receipt or config is unreadable or undateable. Never fresh.

RULES IT KEEPS
==============
* A receipt is dated by the stamp INSIDE it (or, where declared, the producer's
  own stamp in its file name). Never by file mtime. No stamp -> CANNOT_DETERMINE.
* "Newest" is the last file by NAME; an unreadable newest file is CANNOT_DETERMINE
  (it never falls back to an older readable one).
* Flags are read from the config of the checkout the consuming task actually ran
  from: the `clone` in `runtime_switch/runtime_task_runs.jsonl` for that module,
  else the newest clone there, else `system_status/status.json`'s `repo`, else the
  data root's own checkout, else this checkout (marked as a fallback). The config
  file is PARSED (ast), never imported: no code of another checkout is executed.
  Every flag reading prints "per <path>".
* Read only. No network, no subprocess, no LLM, no broker.

REUSE: `scripts.system_status` (`parse_ts`, `tail_rows`, `fmt_age`, `iso`) and
`backend.services.task_receipts` (`_read`). No second set of readers.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from backend import config as C
from backend.services import task_receipts as TR

SCHEMA = "loop_map/1"
STATUSES = ("FLOWING", "STALE", "OFF", "NO_CONSUMER", "ABSENT", "CANNOT_DETERMINE")
STAGES = ("SENSE", "UNIVERSE", "DECIDE", "ACT", "LEARN")
#: The stage pairs that make the loop. It is CLOSED only when every pair has a FLOWING link.
LOOP_PAIRS = (("SENSE", "UNIVERSE"), ("UNIVERSE", "DECIDE"), ("DECIDE", "ACT"),
              ("ACT", "LEARN"), ("LEARN", "DECIDE"), ("LEARN", "SENSE"))
STATUS_LABEL = {"FLOWING": "flowing", "STALE": "stale", "OFF": "off", "NO_CONSUMER": "no consumer",
                "ABSENT": "absent", "CANNOT_DETERMINE": "cannot determine"}

_EVENT_NODES = {"task": "AegisEventNodes", "path": "optimus/event_nodes/daily_latest.json",
                "kind": "json", "stamp": ["now"], "id": ["build_id"], "show": ["n_events", "chain.ok"]}
_DIGEST = {"task": "AegisWorldDigest", "path": "optimus/digest/world_digest_*.json",
           "kind": "json", "stamp": ["stamp"], "id": ["@name"], "show": ["n_items"]}
_TYPED = {"task": "AegisLabNight (job L2_typed_events)", "status_row": "AegisLabNight",
          "path": "optimus/typed_events/_cursor.json", "kind": "json",
          "stamp": ["last_run_utc"], "id": ["runs"], "show": ["rows_written_total"]}
_CALENDAR = {"task": "AegisForwardCalendar", "path": "optimus/forward_calendar/snapshots/fc_*_receipt.json",
             "kind": "json", "stamp": ["finished_utc", "started_utc"], "id": ["pull_id"], "show": ["status"]}
_GRAPH = {"task": "none scheduled (built by hand)", "path": "optimus/universe_graph/latest.json",
          "kind": "json", "stamp": ["built_utc"], "id": ["build_id"], "show": ["as_of"]}
_FUNNEL = {"task": "AegisSimOwner (sim_run.u_funnel)", "status_row": "AegisSimOwner",
           "path": "funnel_night10.json", "kind": "json", "stamp": ["generated_at"],
           "id": ["generated_at"], "show": ["stages.stage4_candidates"]}
_OVERLAY_ROWS = {"task": "AegisNewsOverlayBook", "path": "optimus/news_overlay_book/decisions.jsonl",
                 "kind": "jsonl", "stamp": ["written_utc"], "id": ["digest_id"]}
_SELECTOR_ROWS = {"task": "AegisLLMSelectorBook", "path": "optimus/llm_selector/decisions.jsonl",
                  "kind": "jsonl", "stamp": ["written_utc"], "id": ["book_ids.llm"],
                  "show": ["decision_date", "entry_session"]}

#: THE DECLARED LINKS. One row per link of the loop. Paths are relative to the data
#: root (`backend/data`). `producer.stamp` are the fields that carry the receipt's own
#: time (first readable wins; "@name" = the stamp in the file name); `producer.id` the
#: fields a consumer may cite ("@name" = the file stem). `consumer.proof`:
#:   "cites" -- `consumer.path` + `consumer.cite` (dotted paths; `x[*].y` walks a list;
#:              a dict collects every leaf string) must name a fresh producer id;
#:   "flag"  -- `consumer.flag` gates it; `flag_module` is the scheduled module whose
#:              checkout decides the value, `flag_home` "release" or "data_checkout";
#:   "none"  -- nothing proves consumption. With a `module` the reason is "consumer
#:              cites nothing" (`note` says what its receipt carries instead); without
#:              one, "no consumer declared".
#: `objects` = (from object, to object, the id field that joins them or None).
LINKS: tuple[dict, ...] = (
    {"id": "reader->typed_events", "from": "SENSE", "to": "SENSE", "src": "reader pool", "dst": "typed events",
     "roadmap": "CH-09", "limit": "reader",
     "producer": {"task": "AegisReaderSupervisor", "path": "optimus/dowjones/pool_*.json", "kind": "json",
                  "stamp": ["receipt_utc"], "id": ["@name"], "show": ["finalization_status", "pages"]},
     "consumer": {"module": "scripts.always_on_lab (L2_typed_events)", "proof": "none",
                  "note": "typed_events/_cursor.json holds a per-source (first_seen_utc, raw_id) cursor, no pool id"},
     "objects": None},
    {"id": "typed_events->event_nodes", "from": "SENSE", "to": "SENSE", "src": "typed events", "dst": "event nodes",
     "roadmap": "CH-35", "limit": "typed_events", "producer": _TYPED,
     "consumer": {"module": "backend.services.event_nodes", "proof": "none",
                  "note": "event_nodes/daily_latest.json `read` carries counts (files, rows_read), no typed-run id"},
     "objects": ("EVENT", "NODE_ISSUER", None)},
    {"id": "digest->news_tilt", "from": "SENSE", "to": "LEARN", "src": "world digest", "dst": "news tilt trust",
     "roadmap": "CH-14", "limit": "world_digest", "producer": _DIGEST,
     "consumer": {"module": "backend.services.world_state (news tilt)", "proof": "cites",
                  "path": "optimus/world_state/news_tilt_state.json", "kind": "json",
                  "stamp": ["written_utc"], "cite": ["digest_file"]},
     "objects": ("EVENT", "LEARNED_WEIGHT", "digest_file")},
    {"id": "news_tilt->plan", "from": "LEARN", "to": "DECIDE", "src": "news tilt trust", "dst": "PC plan",
     "roadmap": "CH-14", "limit": "news_tilt",
     "producer": {"task": "AegisWorldDigest", "path": "optimus/world_state/news_tilt_state.json", "kind": "json",
                  "stamp": ["written_utc"], "id": ["digest_file"], "show": ["enabled", "applied"]},
     "consumer": {"module": "backend.services.world_state -> plan", "proof": "flag",
                  "flag": "NEWS_TILT_IN_PLAN", "flag_module": "scripts.world_digest", "flag_home": "release"},
     "objects": ("LEARNED_WEIGHT", "DECISION", None)},
    {"id": "forward_calendar->event_nodes", "from": "SENSE", "to": "SENSE", "src": "forward calendar",
     "dst": "event nodes", "roadmap": "CH-35", "limit": "forward_calendar", "producer": _CALENDAR,
     "consumer": {"module": "backend.services.event_nodes", "proof": "cites",
                  "path": "optimus/event_nodes/daily_latest.json", "kind": "json", "stamp": ["now"],
                  "cite": ["calendar.file"]},
     "objects": ("EVENT", "NODE_ISSUER", "calendar.file")},
    {"id": "forward_calendar->dynamic_books", "from": "SENSE", "to": "DECIDE", "src": "forward calendar",
     "dst": "dynamic books", "roadmap": "CH-45", "limit": "forward_calendar", "producer": _CALENDAR,
     "consumer": {"module": "scripts.dynamic_books", "proof": "cites",
                  "path": "optimus/dynamic_books/runs.jsonl", "kind": "jsonl", "stamp": ["utc"],
                  "cite": ["forward_calendar.freshness.detail"]},
     "objects": ("EVENT", "BOOK", "forward_calendar.freshness.detail")},
    {"id": "universe_graph->event_nodes", "from": "UNIVERSE", "to": "SENSE", "src": "universe graph",
     "dst": "event nodes", "roadmap": "CH-30", "limit": "universe_graph", "producer": _GRAPH,
     "consumer": {"module": "backend.services.event_nodes", "proof": "cites",
                  "path": "optimus/event_nodes/daily_latest.json", "kind": "json", "stamp": ["now"],
                  "cite": ["graph.build_id"]},
     "objects": None},
    {"id": "universe_graph->one_event", "from": "UNIVERSE", "to": "DECIDE", "src": "universe graph",
     "dst": "one_event chain", "roadmap": "CH-31", "limit": "universe_graph", "producer": _GRAPH,
     "consumer": {"module": "scripts.one_event", "proof": "cites",
                  "path": "optimus/one_event/receipts/one_event_*.json", "kind": "json",
                  "stamp": ["run_at"], "cite": ["stages"]},
     "objects": ("NODE_ISSUER", "DECISION", None)},
    {"id": "event_nodes->autopsy", "from": "SENSE", "to": "LEARN", "src": "event nodes", "dst": "discovery autopsy",
     "roadmap": "CH-35", "limit": "event_nodes", "producer": _EVENT_NODES,
     "consumer": {"module": "backend.services.discovery_autopsy", "proof": "flag",
                  "flag": "EVENT_NODES_AUTOPSY_JOIN_ENABLED", "flag_module": "scripts.discovery_autopsy",
                  "flag_home": "release"},
     "objects": ("NODE_ISSUER", "OUTCOME_GRADE", "event_id")},
    {"id": "event_nodes->selector_packet", "from": "SENSE", "to": "DECIDE", "src": "event nodes",
     "dst": "LLM selector book", "roadmap": "CH-35", "limit": "event_nodes", "producer": _EVENT_NODES,
     "consumer": {"module": "backend.services.llm_selector_book", "proof": "flag",
                  "flag": "EVENT_NODES_SELECTOR_PACKET_ENABLED", "flag_module": "scripts.llm_selector_book",
                  "flag_home": "release"},
     "objects": ("NODE_ISSUER", "BOOK", "event_id")},
    {"id": "event_nodes->funnel", "from": "SENSE", "to": "UNIVERSE", "src": "event nodes", "dst": "funnel",
     "roadmap": "CH-35", "limit": "event_nodes", "producer": _EVENT_NODES,
     "consumer": {"module": "backend.services.funnel_news_source", "proof": "flag",
                  "flag": "EVENT_NODES_FUNNEL_SOURCE_ENABLED", "flag_module": None, "flag_home": "data_checkout"},
     "objects": ("NODE_ISSUER", "UNIVERSE_CANDIDATE", "event_id")},
    {"id": "typed_news->funnel", "from": "SENSE", "to": "UNIVERSE", "src": "typed events", "dst": "funnel",
     "roadmap": "CH-14a", "limit": "typed_events", "producer": _TYPED,
     "consumer": {"module": "backend.services.funnel_news_source", "proof": "flag",
                  "flag": "FUNNEL_NEWS_SOURCE_ENABLED", "flag_module": None, "flag_home": "data_checkout"},
     "objects": ("EVENT", "UNIVERSE_CANDIDATE", "added_by_source")},
    {"id": "prediction_markets->decide", "from": "SENSE", "to": "DECIDE", "src": "prediction markets",
     "dst": "no consumer", "roadmap": "CH-37", "limit": "prediction_markets",
     "producer": {"task": "hosted pi_prediction_markets",
                  "path": "optimus/prediction_markets/receipts/[0-9]*-[0-9][0-9].json", "kind": "json",
                  "stamp": ["ran_at"], "id": ["day"], "show": ["status", "rows_written"]},
     "consumer": {"module": None, "proof": "none"},
     "objects": ("EVENT", "DECISION", None)},
    {"id": "funnel->decision_contract", "from": "UNIVERSE", "to": "DECIDE", "src": "funnel",
     "dst": "decision contract", "roadmap": "CH-58", "limit": "funnel", "producer": _FUNNEL,
     "consumer": {"module": "backend.services.decision_contract", "proof": "cites",
                  "path": "optimus/decisions/[0-9]*-[0-9][0-9].json", "kind": "json",
                  "stamp": ["written_utc"], "cite": ["candidate_set.candidates_generated_at"]},
     "objects": ("UNIVERSE_CANDIDATE", "DECISION", "candidate_set.candidates_generated_at")},
    {"id": "funnel->llm_selector", "from": "UNIVERSE", "to": "DECIDE", "src": "funnel", "dst": "LLM selector book",
     "roadmap": "CH-58", "limit": "funnel", "producer": _FUNNEL,
     "consumer": {"module": "backend.services.llm_selector_book", "proof": "cites",
                  "path": "optimus/llm_selector/decisions.jsonl", "kind": "jsonl",
                  "stamp": ["written_utc"], "cite": ["candidate_set.generated_at"]},
     "objects": ("UNIVERSE_CANDIDATE", "BOOK", "candidate_set.generated_at")},
    {"id": "digest->news_overlay_book", "from": "SENSE", "to": "DECIDE", "src": "world digest",
     "dst": "news overlay book", "roadmap": "CH-14b", "limit": "world_digest", "producer": _DIGEST,
     "consumer": {"module": "scripts.news_overlay_book", "proof": "cites",
                  "path": "optimus/news_overlay_book/decisions.jsonl", "kind": "jsonl",
                  "stamp": ["written_utc"], "cite": ["digest_id"]},
     "objects": ("EVENT", "BOOK", "digest_id")},
    {"id": "decision_contract->fleet_manager", "from": "DECIDE", "to": "ACT", "src": "decision contract",
     "dst": "fleet manager orders", "roadmap": "CH-55", "limit": "daily_pass",
     "producer": {"task": "AegisDailyPass", "path": "optimus/decisions/ledger.jsonl", "kind": "jsonl",
                  "stamp": ["utc"], "id": ["decision_id"], "show": ["state", "asof"]},
     "consumer": {"module": "scripts.fleet_manager", "proof": "none",
                  "note": "fleet_manager/decisions.jsonl rows carry run_id, policy_hash, story_id and coid, "
                          "no decision_id of the daily contract"},
     "objects": ("DECISION", "ORDER", None)},
    {"id": "dynamic_books->grades", "from": "DECIDE", "to": "LEARN", "src": "dynamic books", "dst": "no consumer",
     "roadmap": "CH-45", "limit": "dynamic_books",
     "producer": {"task": "AegisDynamicBooks", "path": "optimus/dynamic_books/runs.jsonl", "kind": "jsonl",
                  "stamp": ["utc"], "id": ["run_id"], "show": ["action", "cohorts_total"]},
     "consumer": {"module": None, "proof": "none"},
     "objects": ("BOOK", "OUTCOME_GRADE", None)},
    {"id": "rolling_cohorts->scoreboard", "from": "DECIDE", "to": "LEARN", "src": "rolling cohorts",
     "dst": "cohort scoreboard", "roadmap": "CH-47", "limit": "rolling_cohorts",
     "producer": {"task": "AegisRollingCohorts", "path": "optimus/rolling_cohorts/runs.jsonl", "kind": "jsonl",
                  "stamp": ["utc"], "id": ["run_id"], "show": ["action", "cohorts_forward"]},
     "consumer": {"module": "scripts.rolling_cohorts (scoreboard)", "proof": "cites",
                  "path": "optimus/rolling_cohorts/scoreboard_*.json", "kind": "json",
                  "stamp": [], "cite": ["@name"]},
     "objects": ("BOOK", "OUTCOME_GRADE", "run_id")},
    {"id": "news_overlay_book->grades", "from": "DECIDE", "to": "LEARN", "src": "news overlay book",
     "dst": "no consumer", "roadmap": "CH-14b", "limit": "news_overlay_book", "producer": _OVERLAY_ROWS,
     "consumer": {"module": None, "proof": "none"},
     "objects": ("BOOK", "OUTCOME_GRADE", None)},
    {"id": "llm_selector->leaderboard", "from": "DECIDE", "to": "LEARN", "src": "LLM selector book",
     "dst": "book leaderboard", "roadmap": "CH-20", "limit": "llm_selector", "producer": _SELECTOR_ROWS,
     "consumer": {"module": "backend.services.llm_portfolio (leaderboard)", "proof": "cites",
                  "path": "optimus/llm_portfolio/leaderboard_*.json", "kind": "json",
                  "stamp": ["graded_utc"], "cite": ["books[*].book_id"]},
     "objects": ("BOOK", "OUTCOME_GRADE", "book_id")},
    {"id": "fleet_manager->grades", "from": "ACT", "to": "LEARN", "src": "fleet manager orders",
     "dst": "fleet grades", "roadmap": "CH-55", "limit": "fleet_manager",
     "producer": {"task": "AegisFleetManagerOpen / AegisFleetManagerPreclose",
                  "status_row": "AegisFleetManagerPreclose",
                  "path": "optimus/paper_accounts/fleet_manager/decisions.jsonl", "kind": "jsonl",
                  "stamp": ["t"], "id": ["session"], "show": ["session", "pass", "mode"]},
     "consumer": {"module": "scripts.fleet_manager (grade)", "proof": "cites",
                  "path": "optimus/paper_accounts/fleet_manager/grades.jsonl", "kind": "jsonl",
                  "stamp": ["written_utc"], "cite": ["session"]},
     "objects": ("ORDER", "OUTCOME_GRADE", "session")},
    {"id": "grades->learned_rules", "from": "LEARN", "to": "LEARN", "src": "daily grading", "dst": "learned rules",
     "roadmap": "CH-42", "limit": "daily_pass",
     "producer": {"task": "AegisDailyPass", "path": "optimus/night_factory_*/daily_pass_*.json", "kind": "json",
                  "stamp": ["finished_utc", "started_utc"], "id": ["date"], "show": ["headline"]},
     "consumer": {"module": "backend.services.ledger_distill", "proof": "cites",
                  "path": "optimus/brain/learn_runs.jsonl", "kind": "jsonl",
                  "stamp": ["written_utc"], "cite": ["input.resolved_through"]},
     "objects": ("OUTCOME_GRADE", "LEARNED_WEIGHT", "input.resolved_through")},
    {"id": "learned_rules->policy_state", "from": "LEARN", "to": "DECIDE", "src": "learned rules",
     "dst": "policy state", "roadmap": "CH-59", "limit": "learner",
     "producer": {"task": "ledger_distill (daily pass / lab)", "path": "optimus/brain/learn_runs.jsonl",
                  "kind": "jsonl", "stamp": ["written_utc"], "id": ["as_of"], "show": ["status", "n_rules_written"]},
     "consumer": {"module": "backend.services.policy_state", "proof": "cites",
                  "path": "optimus/pc_book/policy_state.json", "kind": "json",
                  "stamp": ["refreshed_utc"], "cite": ["sources"]},
     "objects": ("LEARNED_WEIGHT", "DECISION", "sources")},
    {"id": "source_scorecard->sense", "from": "LEARN", "to": "SENSE", "src": "source scorecard",
     "dst": "no consumer", "roadmap": "CH-59", "limit": "source_scorecard",
     "producer": {"task": "source scorecard (hourly)", "path": "optimus/source_scorecard/source_scorecard_*.json",
                  "kind": "json", "stamp": ["generated_utc"], "id": ["run_id"],
                  "show": ["proposed_source_weights_status"]},
     "consumer": {"module": None, "proof": "none"},
     "objects": ("LEARNED_WEIGHT", "EVENT", None)},
    {"id": "autopsy->decide", "from": "LEARN", "to": "DECIDE", "src": "discovery autopsy", "dst": "no consumer",
     "roadmap": "CH-59", "limit": "autopsy",
     "producer": {"task": "AegisDiscoveryAutopsy", "path": "optimus/discovery_autopsy/index.jsonl", "kind": "jsonl",
                  "stamp": ["written_utc"], "id": ["run_id"], "show": ["session", "receipt"]},
     "consumer": {"module": None, "proof": "none"},
     "objects": ("OUTCOME_GRADE", "DECISION", None)},
    {"id": "iif1->decide", "from": "LEARN", "to": "DECIDE", "src": "IIF-1 night", "dst": "no consumer",
     "roadmap": "CH-59", "limit": "iif1_night",
     "producer": {"task": "AegisIIF1NightLauncher", "path": "optimus/iif1_nights/[0-9]*-[0-9][0-9].json",
                  "kind": "json", "stamp": ["actual_start_utc"], "id": ["night"],
                  "show": ["status", "records_written"]},
     "consumer": {"module": None, "proof": "none"},
     "objects": ("OUTCOME_GRADE", "DECISION", None)},
)

#: The layered architecture: roadmap module -> the scheduled tasks that belong to it. A
#: task the status receipt lists and this table does not is drawn under UNASSIGNED.
LAYERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("M0", "FOUNDATION", ("AegisCatchUp", "AegisBrainRefresh", "AegisLocalRuntimeDigest", "OpenClaw Gateway",
                          "AegisCodexDaemonAtLogon")),
    ("M1", "SENSE", ("AegisReaderSupervisor", "AegisWorldDigest", "AegisEventNodes", "AegisForwardCalendar",
                     "AegisAnalystPull", "AegisAnalystPanelDaily", "AegisRawSecCollection", "AegisPublicFlow",
                     "AegisOwnerCallsRecord", "AegisOwnerEventWarning")),
    ("M2", "UNIVERSE", ("AegisSimOwner",)),
    ("M3", "DECIDE", ("AegisDailyPass", "daily_pass", "AegisDynamicBooks", "AegisRollingCohorts",
                      "AegisNewsOverlayBook", "AegisLLMSelectorBook", "AegisLocalBranchingPrivateGrade",
                      "AegisStraddleForward")),
    ("M4", "ACT", ("AegisFleetManagerOpen", "AegisFleetManagerPreclose", "AegisFleetDailyCheck",
                   "AegisFleetProtectSweep", "AegisContestDesk", "AegisContestRehearsal")),
    ("M5", "LEARN", ("AegisLabNight", "AegisDiscoveryAutopsy", "AegisIIF1NightLauncher", "AegisNNLabNightly",
                     "AegisHypLabNightly", "AegisResearchLane")),
    ("M6", "SHOW", ("AegisSystemStatus", "AegisTickerHub", "AegisAlerts", "AegisTelegramAgent",
                    "AegisDataCatalog", "AegisPublicAssetsWeekly")),
)

_NONLITERAL = "<not a literal>"


def _ss():
    """`scripts.system_status`, imported late (it imports this package's config)."""
    from scripts import system_status as SS  # noqa: PLC0415
    return SS


# ═══════════════════════════════════════════════════════════════ field access

def collect(obj: Any, path: str) -> list[Any]:
    """Values at a dotted path; `x[*]` walks a list. Missing -> []."""
    cur = [obj]
    for part in path.split("."):
        star = part.endswith("[*]")
        key = part[:-3] if star else part
        nxt: list[Any] = []
        for o in cur:
            v = o.get(key) if isinstance(o, dict) else None
            if v is None:
                continue
            if star:
                nxt.extend(v if isinstance(v, list) else [])
            else:
                nxt.append(v)
        cur = nxt
    return cur


def leaf_strings(v: Any) -> list[str]:
    """Every scalar under `v` as a string (a dict or list is walked)."""
    if isinstance(v, dict):
        return [s for x in v.values() for s in leaf_strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in leaf_strings(x)]
    if v is None or isinstance(v, bool):
        return []
    return [str(v)]


def _values(data: Any, path: Optional[Path], fields: list[str]) -> list[str]:
    out: list[str] = []
    for f in fields:
        if f == "@name":
            if path is not None:
                out.append(Path(path).stem)
        else:
            for v in collect(data, f):
                out.extend(leaf_strings(v))
    return [s for s in out if s]


def same_id(pid: str, cited: str) -> bool:
    """A producer id equals a cited value, is contained in it (a file name or a
    sentence that quotes it), or both are the same instant written two ways."""
    if pid == cited:
        return True
    if len(pid) >= 8 and pid in cited:
        return True
    if len(pid) > 10 and len(cited) > 10 and len(cited) <= 40:
        SS = _ss()
        a, b = SS.parse_ts(pid), SS.parse_ts(cited)
        return a is not None and a == b
    return False


# ═══════════════════════════════════════════════════════════════ reading receipts

def _files(root: Path, pattern: str) -> list[Path]:
    try:
        return sorted((p for p in Path(root).glob(pattern) if p.is_file()), key=lambda p: str(p))
    except (OSError, ValueError):
        return []


def _stamp(data: Any, path: Optional[Path], fields: list[str], now: datetime
           ) -> tuple[Optional[datetime], str, str]:
    """(stamp, the field it came from, why not). Never mtime."""
    SS = _ss()
    if not fields:
        return None, "", "no stamp field declared"
    for f in fields:
        raw = [Path(path).stem] if (f == "@name" and path is not None) else collect(data, f)
        for v in raw:
            t = SS.parse_ts(v)
            if t is None:
                continue
            # a date-only stamp names a local day and may be up to a day ahead of UTC
            slack = 86400.0 if isinstance(t, SS.DateOnly) else float(C.LOOP_MAP_FUTURE_SLACK_S)
            if (t - now).total_seconds() > slack:
                return None, f, f"stamp {v} at `{f}` is in the future"
            return t, f, ""
    return None, "", "no readable stamp at " + ", ".join(f"`{f}`" for f in fields)


def read_source(root: Path, src: dict, now: datetime) -> dict:
    """The newest receipt of one declared source.

    state: OK (dated) / ABSENT / UNREADABLE / UNDATED. A source with no stamp
    field declared comes back UNDATED with its data (a consumer may still be read).
    """
    SS = _ss()
    rel, kind = src["path"], src.get("kind", "json")
    out = {"state": "ABSENT", "path": str(Path(root) / rel), "data": None, "stamp": None,
           "stamp_field": "", "why": ""}
    if kind == "jsonl":
        p = Path(root) / rel
        try:
            size = p.stat().st_size if p.is_file() else -1
        except OSError:
            size = -1
        if size < 0:
            out["why"] = f"no file at {rel}"
            return out
        if size == 0:
            out["why"] = f"{rel} is empty (no row was ever written)"
            return out
        rows = SS.tail_rows(p, n=1, nbytes=int(C.LOOP_MAP_JSONL_TAIL_BYTES))
        if not rows:
            out.update(state="UNREADABLE", why=f"no JSON row parses at the end of {rel}")
            return out
        data, path = rows[-1], p
    else:
        files = _files(root, rel)
        if not files:
            out["why"] = f"no file matches {rel}"
            return out
        path = files[-1]                     # newest by NAME; never an older readable fallback
        out["path"] = str(path)
        data = TR._read(path)
        if not isinstance(data, dict):
            out.update(state="UNREADABLE", why=f"{path.name} is not a readable JSON object")
            return out
    t, field, why = _stamp(data, path, list(src.get("stamp") or []), now)
    out.update(data=data, stamp=t, stamp_field=field, path=str(path),
               state="OK" if t is not None else "UNDATED", why=why)
    return out


def _producer_candidates(root: Path, src: dict) -> Iterator[tuple[Path, Any]]:
    """Producer receipts newest first: (path, row) for a journal, (path, None) for a
    file (read lazily by the caller)."""
    SS = _ss()
    if src.get("kind", "json") == "jsonl":
        p = Path(root) / src["path"]
        rows = SS.tail_rows(p, n=int(C.LOOP_MAP_JSONL_SCAN_ROWS), nbytes=int(C.LOOP_MAP_JSONL_TAIL_BYTES))
        for r in reversed(rows):
            yield p, r
    else:
        for f in reversed(_files(root, src["path"])[-int(C.LOOP_MAP_ID_SCAN_FILES):]):
            yield f, None


def find_cited_producer(root: Path, src: dict, cited: list[str], now: datetime) -> Optional[dict]:
    """The NEWEST producer receipt whose id a consumer cites, or None."""
    ids = list(src.get("id") or [])
    for path, row in _producer_candidates(root, src):
        if row is None and "@name" in ids and any(same_id(path.stem, c) for c in cited):
            data = TR._read(path)
            pid = path.stem
        else:
            data = row if row is not None else (TR._read(path) if [i for i in ids if i != "@name"] else None)
            if not isinstance(data, dict):
                continue
            pid = next((p for p in _values(data, path, [i for i in ids if i != "@name"])
                        if any(same_id(p, c) for c in cited)), None)
            if pid is None:
                continue
        t, field, why = _stamp(data, path, list(src.get("stamp") or []), now) if isinstance(data, dict) \
            else (None, "", f"{path.name} is not a readable JSON object")
        return {"path": str(path), "id": pid, "stamp": t, "stamp_field": field, "why": why}
    return None


# ═══════════════════════════════════════════════════════════════ flags

_FLAG_CACHE: dict[str, tuple[Optional[dict], str]] = {}


def read_config_literals(config_path: Path) -> tuple[Optional[dict], str]:
    """Top-level `NAME = <literal>` of a config file, PARSED (never imported).
    A name assigned something else maps to `_NONLITERAL`. (None, why) when unreadable."""
    key = str(config_path)
    if key in _FLAG_CACHE:
        return _FLAG_CACHE[key]
    try:
        tree = ast.parse(Path(config_path).read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, ValueError) as exc:
        res: tuple[Optional[dict], str] = (None, f"{type(exc).__name__}: {str(exc)[:120]}")
        _FLAG_CACHE[key] = res
        return res
    vals: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name, value = node.target.id, node.value
        else:
            continue
        vals[name] = value.value if isinstance(value, ast.Constant) else _NONLITERAL
    _FLAG_CACHE[key] = (vals, "")
    return _FLAG_CACHE[key]


def _row_module(r: dict) -> Optional[str]:
    if r.get("module"):
        return str(r["module"])
    argv = r.get("argv") or []
    for i, a in enumerate(argv):
        if a == "-m" and i + 1 < len(argv):
            return str(argv[i + 1])
    return None


def resolve_runtimes(root: Path, now: datetime, fallback_config: Path) -> dict:
    """Which checkouts the scheduled tasks run from, from receipts only.

    {"by_module": {module: {clone, utc}}, "newest": {clone, utc, how} | None,
     "data_checkout": config path | None, "fallback": config path}
    """
    SS = _ss()
    root = Path(root)
    by_module: dict[str, dict] = {}
    newest: Optional[dict] = None
    journal = root / "optimus" / "runtime_switch" / "runtime_task_runs.jsonl"
    for r in SS.tail_rows(journal, n=int(C.LOOP_MAP_JSONL_SCAN_ROWS), nbytes=int(C.LOOP_MAP_JSONL_TAIL_BYTES)):
        t = SS.parse_ts(r.get("utc"))
        if not r.get("clone") or t is None or r.get("event") == "refused":
            continue
        rec = {"clone": str(r["clone"]), "utc": SS.iso(t), "head": r.get("head"),
               "how": f"runtime_switch/runtime_task_runs.jsonl row of {SS.iso(t)}"}
        m = _row_module(r)
        if m and (m not in by_module or by_module[m]["utc"] <= rec["utc"]):
            by_module[m] = rec
        if newest is None or newest["utc"] <= rec["utc"]:
            newest = rec
    if newest is None:
        st = TR._read(root / "optimus" / "system_status" / "status.json")
        t = SS.parse_ts(st.get("generated_utc")) if isinstance(st, dict) else None
        if isinstance(st, dict) and st.get("repo") and t is not None:
            newest = {"clone": str(st["repo"]), "utc": SS.iso(t), "head": None,
                      "how": f"system_status/status.json `repo` (generated {SS.iso(t)})"}
    dc = root.parent / "config.py" if (root.name == "data" and root.parent.name == "backend") else None
    return {"by_module": by_module, "newest": newest,
            "data_checkout": str(dc) if dc is not None and dc.is_file() else None,
            "fallback": str(fallback_config)}


def read_flag(name: str, consumer: dict, runtimes: dict) -> dict:
    """One flag, read from the config of the checkout that decides it.

    {"name", "value" (True/False/None=undefined/"<not a literal>"), "config", "source",
     "how", "others": [{config, value, source}], "error"}
    """
    cands: list[tuple[str, str, str]] = []      # (source, config path, how)
    mod = consumer.get("flag_module")
    rel = runtimes["by_module"].get(mod) if mod else None
    if rel:
        cands.append(("release_of_module", str(Path(rel["clone"]) / "backend" / "config.py"),
                      f"{mod} last ran from this clone: {rel['how']}"))
    if runtimes.get("newest"):
        n = runtimes["newest"]
        cands.append(("newest_release", str(Path(n["clone"]) / "backend" / "config.py"),
                      f"the newest clone any task ran from: {n['how']}"))
    if runtimes.get("data_checkout"):
        cands.append(("data_checkout", runtimes["data_checkout"],
                      "the checkout that owns the data root (tasks not yet repointed run from it)"))
    if consumer.get("flag_home") == "data_checkout":
        cands.sort(key=lambda c: c[0] != "data_checkout")
    cands.append(("FALLBACK_THIS_CHECKOUT", runtimes["fallback"],
                  "FALLBACK: no runtime checkout could be determined from receipts"))
    readings, seen = [], set()
    for source, path, how in cands:
        if path in seen:
            continue
        seen.add(path)
        vals, err = read_config_literals(Path(path))
        readings.append({"source": source, "config": path, "how": how, "error": err,
                         "value": None if vals is None else vals.get(name),
                         "defined": bool(vals is not None and name in vals), "readable": vals is not None})
    # the deciding reading: the first READABLE runtime config in order; the fallback
    # only when no runtime config is readable at all
    runtime = [r for r in readings if r["source"] != "FALLBACK_THIS_CHECKOUT"]
    chosen = next((r for r in runtime if r["readable"]), None) or readings[-1]
    return {"name": name, **chosen,
            "others": [{k: r[k] for k in ("source", "config", "value", "defined", "readable")}
                       for r in readings if r is not chosen]}


# ═══════════════════════════════════════════════════════════════ judging

def _age(now: datetime, t: datetime) -> float:
    return max(0.0, (now - t).total_seconds())


def judge_link(link: dict, root: Path, now: datetime, runtimes: dict,
               limits: Optional[dict] = None, tasks: Optional[dict] = None) -> dict:
    """ONE status for one declared link, with the evidence for it."""
    SS = _ss()
    limits = C.LOOP_MAP_LIMITS_H if limits is None else limits
    prod, cons = link["producer"], link["consumer"]
    lim_h = limits.get(link.get("limit"))
    res: dict[str, Any] = {
        "id": link["id"], "from": link["from"], "to": link["to"], "src": link["src"], "dst": link["dst"],
        "roadmap": link.get("roadmap"), "limit_h": lim_h, "status": "CANNOT_DETERMINE", "reason": "",
        "reason_code": "", "evidence_path": "",
        "producer": {"task": prod.get("task"), "pattern": prod["path"]},
        "consumer": {"module": cons.get("module"), "proof": cons.get("proof", "none")},
        "objects": list(link["objects"]) if link.get("objects") else None,
    }
    trow = (tasks or {}).get(prod.get("status_row") or prod.get("task"))
    if trow:
        res["producer"]["task_status"] = trow

    def done(status: str, code: str, reason: str, evidence: str) -> dict:
        res.update(status=status, reason_code=code, reason=reason, evidence_path=evidence)
        return res

    P = read_source(root, prod, now)
    res["producer"].update(path=P["path"], stamp_field=P["stamp_field"], stamp_utc=SS.iso(P["stamp"]),
                           age_s=None if P["stamp"] is None else _age(now, P["stamp"]),
                           id=(_values(P["data"], Path(P["path"]), list(prod.get("id") or [])) or [None])[0],
                           show={f: (collect(P["data"], f) or [None])[0] for f in prod.get("show") or []})
    if P["state"] == "ABSENT":
        return done("ABSENT", "NO_PRODUCER_RECEIPT", f"no producer receipt: {P['why']}", P["path"])
    if P["state"] != "OK":
        return done("CANNOT_DETERMINE", "PRODUCER_" + P["state"],
                    f"producer receipt {P['state'].lower()}: {P['why']} (never dated by file time)", P["path"])
    if lim_h is None:
        return done("CANNOT_DETERMINE", "NO_LIMIT", f"no freshness limit declared for `{link.get('limit')}`",
                    P["path"])
    lim_s = float(lim_h) * 3600.0
    age = _age(now, P["stamp"])
    age_txt = f"producer {SS.fmt_age(age)} old by `{P['stamp_field']}` (limit {SS.fmt_age(lim_s)})"

    if cons.get("flag"):
        F = read_flag(cons["flag"], cons, runtimes)
        res["consumer"]["flag"] = F
        per = f"per {F['config']}" + (" [FALLBACK: no runtime checkout determined from receipts]"
                                      if F["source"] == "FALLBACK_THIS_CHECKOUT" else "")
        if not F["readable"]:
            return done("CANNOT_DETERMINE", "FLAG_CONFIG_UNREADABLE",
                        f"flag {F['name']}: config unreadable ({F['error']}) {per}", F["config"])
        if F["value"] == _NONLITERAL:
            return done("CANNOT_DETERMINE", "FLAG_NOT_LITERAL",
                        f"flag {F['name']} is not a literal in the config, its value cannot be read {per}",
                        F["config"])
        if F["value"] is not True:
            val = "undefined (the code that reads it is not in that checkout or defaults to off)" \
                if not F["defined"] else repr(F["value"])
            also = "; ".join(f"{'undefined' if not o['defined'] else o['value']!r} per {o['config']}"
                             for o in F["others"] if o["readable"] and o["source"] != "FALLBACK_THIS_CHECKOUT")
            return done("OFF", "FLAG_OFF", f"flag {F['name']} = {val} {per}"
                        + (f" (also {also})" if also else "") + f"; {age_txt}", F["config"])

    stale_note = ""
    if cons.get("proof") == "none" or (cons.get("proof") == "flag" and not cons.get("cite")):
        if cons.get("module"):
            stale_note = "consumer cites nothing" + (f" ({cons['note']})" if cons.get("note") else "")
        else:
            stale_note = "no consumer declared"
    if age > lim_s:
        return done("STALE", "PRODUCER_STALE", age_txt + (f"; {stale_note}" if stale_note else ""), P["path"])
    if stale_note:
        code = "CONSUMER_CITES_NOTHING" if cons.get("module") else "NO_CONSUMER_DECLARED"
        return done("NO_CONSUMER", code, f"{stale_note}; {age_txt}", P["path"])

    K = read_source(root, cons, now)
    res["consumer"].update(path=K["path"], stamp_utc=SS.iso(K["stamp"]),
                           age_s=None if K["stamp"] is None else _age(now, K["stamp"]))
    if K["state"] == "ABSENT":
        return done("NO_CONSUMER", "CONSUMER_RECEIPT_ABSENT",
                    f"consumer receipt absent ({K['why']}): the consumer has never written a row; {age_txt}",
                    K["path"])
    if K["state"] == "UNREADABLE":
        return done("CANNOT_DETERMINE", "CONSUMER_UNREADABLE", f"consumer receipt unreadable: {K['why']}", K["path"])
    cited = _values(K["data"], Path(K["path"]), list(cons.get("cite") or []))
    res["consumer"]["cited"] = cited[:5]
    res["consumer"]["n_cited"] = len(cited)
    fields = ", ".join(f"`{c}`" for c in cons.get("cite") or [])
    if not cited:
        return done("NO_CONSUMER", "CONSUMER_CITES_NOTHING",
                    f"consumer cites nothing: its newest receipt has no value at {fields}; {age_txt}", K["path"])
    hit = find_cited_producer(root, prod, cited, now)
    if hit is None:
        return done("NO_CONSUMER", "CITED_ID_NOT_FOUND",
                    f"consumer cites {cited[0][:80]!r} at {fields}, which matches no producer receipt "
                    f"(id fields {prod.get('id')}); {age_txt}", K["path"])
    res["consumer"]["cited_producer"] = {"path": hit["path"], "id": hit["id"], "stamp_utc": SS.iso(hit["stamp"]),
                                         "age_s": None if hit["stamp"] is None else _age(now, hit["stamp"])}
    if hit["stamp"] is None:
        return done("CANNOT_DETERMINE", "CITED_PRODUCER_UNDATED",
                    f"the cited producer receipt {hit['id']} cannot be dated: {hit['why']}", hit["path"])
    cage = _age(now, hit["stamp"])
    if cage > lim_s:
        return done("STALE", "CITED_PRODUCER_STALE",
                    f"consumer's newest citation is producer {hit['id']}, {SS.fmt_age(cage)} old "
                    f"(limit {SS.fmt_age(lim_s)}); newest {age_txt}", K["path"])
    left = lim_s - max(cage, age)
    res["near_limit"] = bool(left < float(C.LOOP_MAP_NEAR_LIMIT_SHARE) * lim_s)
    near = f"NEAR LIMIT: stale in {SS.fmt_age(left)}; " if res["near_limit"] else ""
    return done("FLOWING", "CITED_FRESH",
                f"{near}consumer cites producer {hit['id']} ({SS.fmt_age(cage)} old, limit {SS.fmt_age(lim_s)}) "
                f"at {fields}; newest {age_txt}", K["path"])


# ═══════════════════════════════════════════════════════════════ the record

def status_tasks(root: Path, now: datetime) -> dict:
    """The task rows of the newest systems receipt (`system_status/status.json`)."""
    SS = _ss()
    p = Path(root) / "optimus" / "system_status" / "status.json"
    st = TR._read(p)
    out = {"path": str(p), "generated_utc": None, "age_s": None, "state": "ABSENT", "why": "", "tasks": {}}
    if not isinstance(st, dict):
        out["why"] = "no readable system_status/status.json"
        return out
    t = SS.parse_ts(st.get("generated_utc"))
    if t is None or (t - now).total_seconds() > float(C.LOOP_MAP_FUTURE_SLACK_S):
        out.update(state="CANNOT_DETERMINE", why="status.json has no usable generated_utc")
    else:
        age = _age(now, t)
        lim = float(C.LOOP_MAP_STATUS_STALE_HOURS) * 3600.0
        out.update(generated_utc=SS.iso(t), age_s=age, state="STALE" if age > lim else "OK",
                   why=f"{SS.fmt_age(age)} old (limit {SS.fmt_age(lim)})")
    rows = ((st.get("sections") or {}).get("tasks") or {}).get("rows") or []
    for r in rows:
        if isinstance(r, dict) and r.get("name"):
            x = r.get("extra") or {}
            out["tasks"][str(r["name"])] = {"status": r.get("status"), "state": x.get("state"),
                                            "retired": bool(x.get("retired")),
                                            "evidence_utc": r.get("evidence_utc")}
    return out


def root_is_empty(root: Path) -> Optional[str]:
    """Why the input root cannot be mapped at all, or None."""
    root = Path(root)
    if not root.is_dir():
        return f"data root {root} is missing or not a directory"
    try:
        if not any(root.iterdir()):
            return f"data root {root} is empty"
    except OSError as exc:
        return f"data root {root} cannot be listed ({type(exc).__name__})"
    return None


def build(data_root: Path, *, now: Optional[datetime] = None, links: tuple[dict, ...] = LINKS,
          limits: Optional[dict] = None, fallback_config: Optional[Path] = None) -> dict:
    """The loop map record. Raises nothing for open links: they are the finding."""
    SS = _ss()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    root = Path(data_root)
    fallback = fallback_config or (Path(__file__).resolve().parents[1] / "config.py")
    runtimes = resolve_runtimes(root, now, fallback)
    st = status_tasks(root, now)
    rows = [judge_link(l, root, now, runtimes, limits, st["tasks"]) for l in links]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    top = f"{len(rows)} links: " + ", ".join(f"{counts[s]} {STATUS_LABEL[s]}" for s in STATUSES)
    pairs = []
    for a, b in LOOP_PAIRS:
        ls = [r for r in rows if r["from"] == a and r["to"] == b]
        pairs.append({"from": a, "to": b, "n_links": len(ls),
                      "n_flowing": sum(1 for r in ls if r["status"] == "FLOWING"),
                      "links": [f"{r['id']}: {r['status']}" for r in ls]})
    open_pairs = [f"{p['from']}->{p['to']}" for p in pairs if p["n_flowing"] == 0]
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return {
        "receipt": SCHEMA, "generated_utc": SS.iso(now), "run": stamp, "data_root": str(root),
        "top_line": top, "counts": counts, "n_links": len(rows),
        "n_open": len(rows) - counts["FLOWING"],
        "loop_closed": not open_pairs, "open_pairs": open_pairs, "pairs": pairs,
        "links": rows, "runtimes": runtimes, "status_receipt": {k: v for k, v in st.items() if k != "tasks"},
        "layers": layers(st),
        "read_me_first": ("Generated from receipts and config only. A receipt is dated by the stamp inside "
                          "it, never by file time. FLOWING requires the consumer's newest receipt to cite a "
                          "fresh producer id. Open links are the finding, not an error of this map."),
    }


def layers(st: dict) -> list[dict]:
    """M0..M6 with their tasks' rows from the status receipt; undeclared tasks under UNASSIGNED."""
    tasks = dict(st.get("tasks") or {})
    out, used = [], set()
    for code, name, names in LAYERS:
        rows = []
        for n in names:
            used.add(n)
            t = tasks.get(n)
            rows.append({"task": n, **(t if t else {"status": "NOT_IN_STATUS_RECEIPT", "state": None,
                                                   "retired": False, "evidence_utc": None})})
        out.append({"code": code, "name": name, "tasks": rows})
    rest = [{"task": n, **t} for n, t in sorted(tasks.items()) if n not in used]
    if rest:
        out.append({"code": "UNASSIGNED", "name": "tasks no layer declares", "tasks": rest})
    return out


# ═══════════════════════════════════════════════════════════════ diagrams

def _mid(s: str) -> str:
    return "n_" + "".join(ch if ch.isalnum() else "_" for ch in s)


def _q(s: Any) -> str:
    return str(s).replace('"', "'").replace("\n", " ")


def mermaid_feedback(rec: dict) -> str:
    """Diagram 1: the feedback loop; every edge is a declared link labelled by its status."""
    stage_nodes: dict[str, list[str]] = {s: [] for s in STAGES}
    placed: dict[str, str] = {}
    edges = []
    for r in rec["links"]:
        dst = r["dst"] if r["dst"] != "no consumer" else f"nobody reads it ({r['to']})"
        for node, stage in ((r["src"], r["from"]), (dst, r["to"])):
            if node not in placed:
                placed[node] = stage
                stage_nodes[stage].append(node)
        arrow = "==>" if r["status"] == "FLOWING" else "-.->"
        edges.append(f'  {_mid(r["src"])} {arrow}|"{_q(r["status"])}"| {_mid(dst)}')
    out = ["flowchart LR"]
    for s in STAGES:
        out.append(f"  subgraph {s}")
        out += [f'    {_mid(n)}["{_q(n)}"]' for n in stage_nodes[s]]
        out.append("  end")
    return "\n".join(out + edges) + "\n"


def mermaid_layers(rec: dict) -> str:
    """Diagram 2: M0 foundation up to M6 show, each layer listing its tasks from the status receipt."""
    sr = rec["status_receipt"]
    out = ["flowchart BT"]
    prev = None
    for L in rec["layers"]:
        lines = []
        for t in L["tasks"]:
            tag = "retired" if t.get("retired") else str(t.get("status"))
            lines.append(f"{t['task']}: {tag}")
        body = "<br/>".join(_q(x) for x in lines) or "no task declared"
        nid = "L_" + L["code"]
        out.append(f'  {nid}["<b>{L["code"]} {_q(L["name"])}</b><br/>{body}"]')
        if prev and L["code"] != "UNASSIGNED":
            out.append(f"  {prev} --> {nid}")
        if L["code"] != "UNASSIGNED":
            prev = nid
    out.append(f'  SR["status receipt: {_q(sr.get("state"))} {_q(sr.get("why"))}"]')
    return "\n".join(out) + "\n"


def mermaid_objects(rec: dict) -> str:
    """Diagram 3: object relationships; each edge is a declared link with the id field that
    joins the pair (or 'no id written') and the link's status."""
    out = ["erDiagram"]
    for r in rec["links"]:
        if not r.get("objects"):
            continue
        a, b, join = r["objects"]
        label = f"{join or 'no id written'} [{r['status']}] {r['id']}"
        out.append(f'  {a} }}o--o{{ {b} : "{_q(label)}"')
    return "\n".join(out) + "\n"


def render_markdown(rec: dict) -> str:
    SS = _ss()
    L = [f"# Loop map {rec['run']}", "", f"**{rec['top_line']}**", "",
         f"Loop closed: **{'YES' if rec['loop_closed'] else 'NO'}**"
         + ("" if rec["loop_closed"] else " (no FLOWING link on: " + ", ".join(rec["open_pairs"]) + ")"),
         "", f"Data root `{rec['data_root']}`, generated {rec['generated_utc']}. {rec['read_me_first']}", "",
         "## Stage pairs", "", "| pair | links | flowing | links |", "|---|---|---|---|"]
    for p in rec["pairs"]:
        L.append(f"| {p['from']} -> {p['to']} | {p['n_links']} | {p['n_flowing']} | {'; '.join(p['links']) or '-'} |")
    L += ["", "## Links", "", "| link | stages | status | producer age / limit | reason | evidence |",
          "|---|---|---|---|---|---|"]
    for r in rec["links"]:
        age = r["producer"].get("age_s")
        lim = r.get("limit_h")
        a = (SS.fmt_age(age) if age is not None else "-") + " / " + (f"{lim:g} h" if lim is not None else "-")
        L.append(f"| `{r['id']}` ({r.get('roadmap') or '-'}) | {r['from']} -> {r['to']} | **{r['status']}** | {a} "
                 f"| {str(r['reason']).replace('|', '/')} | `{r['evidence_path']}` |")
    L += ["", "## Flags read", "", "| flag | value | per config | how the checkout was determined |", "|---|---|---|---|"]
    for r in rec["links"]:
        F = r["consumer"].get("flag")
        if F:
            val = "undefined" if not F["defined"] else F["value"]
            L.append(f"| {F['name']} | {val} | `{F['config']}` | {F['how']} |")
    sr = rec["status_receipt"]
    L += ["", "## Diagram 1: the feedback loop", "", "```mermaid", mermaid_feedback(rec).rstrip(), "```", "",
          "## Diagram 2: layered architecture",
          "", f"Tasks from `{sr.get('path')}`: {sr.get('state')} {sr.get('why')}", "",
          "```mermaid", mermaid_layers(rec).rstrip(), "```", "",
          "## Diagram 3: object relationships", "",
          "```mermaid", mermaid_objects(rec).rstrip(), "```", ""]
    return "\n".join(L)
