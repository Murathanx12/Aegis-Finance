"""Six-role fleet as frozen v3 CONTRACTS -- PREPARED, NOT SEEDED (CHUNK C20).

Roadmap 2026-10-06 §6 D2. The owner asked for six strategies on six paper
accounts. "No new book before 2026-10-26" binds (§7), and resetting an Alpaca
account is the owner's broker-UI act. So this module writes the six contracts,
hashes them, and stops: every body carries `status: PREPARED_NOT_SEEDED` and
the owner steps that would activate it.

Why no seed path can act on them (pinned by test_fleet_v3_contracts.py):
* they live in `config.FLEET_V3_CONTRACTS_DIR` (`fleet_manager/contracts_v3/`),
  a folder `fleet_manager.load_contract` never reads;
* `fleet_manager.load_contract` and `freeze_contract` REFUSE any body whose
  status is PREPARED, so a hand copy into `contracts/` refuses too;
* `scripts/fleet_manager_run.py` resolves only v1/v2 (setting modes.json to
  "v3" today would fall back to v1 terms -- printed in the C20 note as an owner
  trap, not changed here: the runner is the live path).

Activation is the owner's act: a re-freeze whose ONLY differences are
`status`, `owner_action_required` and the `seed` block (`activation_diff`).
`rule_hash` excludes exactly those, so the prepared rule and the activated rule
can be shown to be the same rule.

Licence: PRODUCT_EXPERIMENT for all six. No claim of skill anywhere.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from backend import config as _cfg
from backend.services import fleet_manager as FM

SCHEMA = "fleet_manager_contract/3-prepared"
VERSION = "v3"

#: role -> account slot. hack3 is retired (key answers 401): the innovation lane
#: has no account until the owner regenerates hack3's keys or opens a new one.
ACCOUNT: dict[str, str] = {
    "thematic": "hack1",
    "revision_snowball": "hack2",
    "world_news": "hack6",
    "quant_ensemble": "hack4",
    "innovation": "UNASSIGNED",
    "spy_control": "hack5",
}
ROLES: tuple[str, ...] = tuple(ACCOUNT)

#: Fields that may differ between the PREPARED body and the owner's activated
#: body. Everything else is the rule.
ACTIVATION_FIELDS: tuple[str, ...] = ("status", "owner_action_required", "seed",
                                      "policy_hash", "frozen_utc", "rule_hash")

PERSONALITY = {
    "thematic": "aggressive",
    "revision_snowball": "balanced",
    "world_news": "balanced",
    "quant_ensemble": "balanced",
    "innovation": "extreme growth",
    "spy_control": "market control (no personality: the benchmark itself)",
}


#: Thin, small names cost more to trade than the fleet's 10 bps default.
COST_BPS_OVERRIDE: dict[str, float] = {"innovation": 30.0}


class PreparedRefusal(RuntimeError):
    """A v3 step that cannot be completed honestly."""


# ─────────────────────────────── hashing ────────────────────────────────────

def rule_hash(body: dict) -> str:
    core = {k: v for k, v in body.items() if k not in ACTIVATION_FIELDS}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def contracts_dir(base: Optional[Path] = None) -> Path:
    return Path(base) if base else Path(_cfg.FLEET_V3_CONTRACTS_DIR)


def contract_path(role: str, base: Optional[Path] = None) -> Path:
    return contracts_dir(base) / f"{role}_{VERSION}.json"


def freeze_prepared(body: dict, base: Optional[Path] = None) -> dict:
    """Write once into the PREPARED folder. A different rule under the same
    name refuses (a changed rule is a new version, never an edit)."""
    if body.get("status") != _cfg.FLEET_V3_STATUS_PREPARED:
        raise PreparedRefusal(f"REFUSED: {body.get('role')}: only a "
                              f"{_cfg.FLEET_V3_STATUS_PREPARED} body is written here")
    out = dict(body)
    out["rule_hash"] = rule_hash(out)
    h = FM.policy_hash(out)
    p = contract_path(out["role"], base)
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        if old.get("policy_hash") != h:
            raise PreparedRefusal(
                f"REFUSED: {p.name} is frozen as {old.get('policy_hash')}; the body now hashes "
                f"to {h}. A changed rule is a new version (v3b), not an edit.")
        return old
    out["policy_hash"] = h
    out["frozen_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    FM.atomic_write_json(p, out)
    return out


def load_prepared(role: str, base: Optional[Path] = None) -> dict:
    p = contract_path(role, base)
    if not p.exists():
        raise PreparedRefusal(f"REFUSED: no prepared contract {p.name}")
    c = json.loads(p.read_text(encoding="utf-8"))
    if FM.policy_hash(c) != c.get("policy_hash") or rule_hash(c) != c.get("rule_hash"):
        raise PreparedRefusal(f"REFUSED: {p.name} does not match its hashes (edited after freeze)")
    return c


def activation_diff(prepared: dict, activated: dict) -> dict:
    """The owner's check: an activation may change ONLY `ACTIVATION_FIELDS`."""
    keys = (set(prepared) | set(activated)) - set(ACTIVATION_FIELDS)
    changed = sorted(k for k in keys if prepared.get(k) != activated.get(k))
    return {"same_rule": not changed and rule_hash(prepared) == rule_hash(activated),
            "changed_rule_fields": changed}


# ─────────────────────────────── inputs ─────────────────────────────────────

def v2_lineage(account: str, base: Optional[Path] = None) -> Optional[dict]:
    """The live v2 contract this role descends from, read-only and hash-checked."""
    if account not in {"hack1", "hack2", "hack4", "hack5", "hack6"}:
        return None
    p = FM.contract_file(account, "v2", base)
    if not p.exists():
        return {"account": account, "v2": "ABSENT"}
    c = json.loads(p.read_text(encoding="utf-8"))
    ok = FM.policy_hash(c) == c.get("policy_hash")
    if not ok:
        raise PreparedRefusal(f"REFUSED: {p.name} does not match its own policy hash")
    return {"account": account, "v2_policy_hash": c.get("policy_hash"),
            "v2_alpha_source": c.get("alpha_source"), "v2_frozen_utc": c.get("frozen_utc")}


def _load_board(paths: Iterable[Path]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["rule"]] = r      # a later supplement supersedes by rule
    return rows


def _t(row: dict, col: str, window: str) -> Optional[float]:
    try:
        v = row[col][window]["t_blocks"]
        return float(v) if v is not None and math.isfinite(float(v)) else None
    except (KeyError, TypeError, ValueError):
        return None


QUANT_RULE = ("eligible = status OK on BOTH boards AND pure_selection t >= 2 (full sample) on "
              "the basket fair twin AND on the sticky twin (TWIN_STICKY_v1) AND net_minus_market "
              "t >= 2 in the validation window (2009-2016, the 'validate' block). The book holds "
              "the eligible rules' current picks equally across rules; no eligible rule -> HOLD "
              "CASH, by rule, until a re-run board makes one eligible (a new board is read only "
              "at the monthly rebalance and its id is recorded on the decision)")


def quant_eligibility(fair_paths: Iterable[Path], sticky_paths: Iterable[Path]) -> dict:
    """Which library rules the quant-ensemble role may hold. Derived from the
    boards, never typed in; an unreadable board REFUSES (a check that did not
    run is not a check that passed)."""
    fair_paths, sticky_paths = list(fair_paths), list(sticky_paths)
    try:
        ft, st = _load_board(fair_paths), _load_board(sticky_paths)
    except (OSError, ValueError, KeyError) as exc:
        raise PreparedRefusal(f"REFUSED: twin boards unreadable: {type(exc).__name__}: {exc}")
    if not ft or not st:
        raise PreparedRefusal("REFUSED: a twin board is empty")
    both_ok = [k for k in st if k in ft and st[k].get("status") == "OK"
               and ft[k].get("status") == "OK"]
    pure2 = [k for k in both_ok
             if (_t(st[k], "pure_selection", "full") or -9) >= 2
             and (_t(ft[k], "pure_selection", "full") or -9) >= 2]
    eligible = [k for k in pure2 if (_t(st[k], "net_minus_market", "validate") or -9) >= 2]
    return {"rule": QUANT_RULE,
            "boards": {"fair": [p.name for p in fair_paths], "sticky": [p.name for p in sticky_paths]},
            "n_rules_both_ok": len(both_ok), "n_pure_selection_t2_both_twins": len(pure2),
            "pure_selection_t2_both_twins": sorted(pure2),
            "eligible": sorted(eligible), "n_eligible": len(eligible),
            "today": ("HOLD_CASH" if not eligible else "HOLD_ELIGIBLE")}


# ─────────────────────────────── worst case ─────────────────────────────────

def stop_block(*, k: float, min_frac: float, max_frac: float, sigmas: dict[str, float],
               why: str, quoted: str = "daily sigma") -> dict:
    """A stop quoted in SIGMA and in PERCENT, with worked examples."""
    ex = []
    for label, s in sigmas.items():
        d, how = FM.sigma_stop_frac(s, max_frac=max_frac, k=k, min_frac=min_frac)
        ex.append({"at": label, "daily_sigma": s, "stop_pct": d,
                   "stop_in_sigma": (d / s) if s else None, "how": how})
    return {"quoted_in": quoted,
            "sigma": ("63-session sd of close-to-close returns on the bar-defect-screened panel "
                      "(Alpaca daily bars when a name is not in the panel)"),
            "k_sigma": k, "min_frac": min_frac, "max_frac": max_frac,
            "distance": "clip(k_sigma x sigma, min_frac, max_frac) of the reference price",
            "never_loosen": "a replaced stop is never below the stop it replaces",
            "order": ("GTC sell stop for the full long quantity; renewed within "
                      f"{_cfg.FLEET_MANAGER_STOP_RENEW_DAYS} days of its expiry"),
            "examples": ex, "why": why}


def worst_case_block(*, equity: float, n_names: int, name_cap: float, gross_cap: float,
                     sigma_ref: float, sigma_ref_source: str, k: float, stop_max: float,
                     binary: Optional[dict] = None, core: Optional[dict] = None) -> dict:
    """Session protocol item 4 at `equity`: n x notional% x stop%, the k-sigma
    day (rho = 1), the cap that scales gross down, and sum|notional| / equity."""
    gross = min(float(gross_cap), int(n_names) * float(name_cap))
    ksig_frac = gross * k * float(sigma_ref)
    limit = float(_cfg.FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC)
    scale = min(1.0, limit / ksig_frac) if ksig_frac > 0 else 1.0
    out = {
        "equity_usd": float(equity), "n_names": int(n_names), "notional_pct": float(name_cap),
        "gross_over_equity": gross, "k_sigma": k, "sigma_ref": float(sigma_ref),
        "sigma_ref_source": sigma_ref_source,
        "k_sigma_day_usd_uncapped": -ksig_frac * equity,
        "k_sigma_day_limit_frac": limit,
        "entry_gross_scale_at_sigma_ref": scale,
        "k_sigma_day_usd_after_cap": -min(ksig_frac, limit) * equity,
        "all_stops_hit_usd": -gross * float(stop_max) * equity,
        "no_stop_ceiling_usd": -gross * equity,
        "gap_note": "a stop is not a floor: an overnight gap fills below it",
    }
    if binary:
        out["binary_gap_usd"] = -float(binary["n"]) * float(binary["weight"]) * float(
            binary["gap"]) * equity
        out["binary_gap_case"] = binary
    if core:
        out.update(core)
    out["line"] = (f"{n_names} x {name_cap:.2%} x {stop_max:.0%} stop = "
                   f"-${gross * stop_max * equity:,.0f} if every stop fills at its distance; "
                   f"{k:g}-sigma day at {sigma_ref:.2%} = -${ksig_frac * equity:,.0f} "
                   f"(capped at {limit:.0%} -> -${min(ksig_frac, limit) * equity:,.0f} by scaling "
                   f"gross x{scale:.2f}); sum|notional|/equity {gross:.2f}; "
                   f"no-stop ceiling -${gross * equity:,.0f}"
                   + (f"; binary gap -${-out['binary_gap_usd']:,.0f}" if binary else ""))
    return out


# ─────────────────────────────── bodies ─────────────────────────────────────

def _common(role: str, ref: dict) -> dict:
    acct = ACCOUNT[role]
    return {
        "schema": SCHEMA, "role": role, "version": VERSION, "account": acct,
        "licence": "PRODUCT_EXPERIMENT",
        "status": _cfg.FLEET_V3_STATUS_PREPARED,
        "earliest_seed": _cfg.FLEET_V3_EARLIEST_SEED,
        "lineage": ref.get("lineage", {}).get(role),
        "personality": PERSONALITY[role],
        "objective": ("terminal wealth under the declared personality (docs/OPTIMUS_OBJECTIVE.md "
                      "§0), graded daily vs SPY and vs the frozen twin; the question is whether this "
                      "alpha source's errors differ from the other five accounts'; no claim of skill"),
        "costs": {**FM.costs_block(), "assumed_bps_per_side": float(
            COST_BPS_OVERRIDE.get(role, _cfg.FLEET_MANAGER_COST_BPS_PER_SIDE))},
        "reference_asof": ref["asof"],
        "llm_authority": "none: an LLM proposes; deterministic code sizes, stops and exits",
        "owner_action_required": owner_steps(role),
    }


def owner_steps(role: str) -> list[str]:
    acct = ACCOUNT[role]
    pre = [f"not before {_cfg.FLEET_V3_EARLIEST_SEED} (roadmap §7: no new paper book before then)",
           "archive first: python -m scripts.fleet_v3_prepare --archive (copies fleet_manager "
           "state/, decisions.jsonl, grades.jsonl, modes.json, contracts/ with a sha256 manifest; "
           "copies, never moves)",
           "write a last broker-truth read: python -m scripts.fleet_manager_run --pass open "
           f"--roles {acct} (no --live: DRY, reads and records only)"]
    if acct == "UNASSIGNED":
        acct_step = ["assign an account: regenerate hack3's keys in the broker UI (hack3 is retired, "
                     "401) or open a new paper account; name it here by a new version"]
    else:
        acct_step = [f"reset {acct} in the broker UI if wanted (paper reset = the owner's act)"]
    post = ["teach scripts/fleet_manager_run.py a v3 path FIRST (today it resolves only v1/v2 and "
            "would silently fall back to v1 terms for 'v3')",
            "activate = re-freeze this body into fleet_manager/contracts/ with status changed and "
            "the seed block filled; check fleet_v3_contracts.activation_diff(...)['same_rule']",
            f"set modes.json {acct} contract=v3, maintenance/entries DRY first, LIVE after one "
            "clean DRY pass"]
    return pre + acct_step + post


def build_bodies(ref: dict) -> dict[str, dict]:
    """The six PREPARED bodies from a reference block (sigmas, receipts,
    eligibility, lineage). Deterministic in `ref`: the same reference gives the
    same hashes, a different reference is a different version."""
    eq = float(_cfg.FLEET_V3_WORST_CASE_EQUITY)
    u = ref["universe_sigma"]
    k = float(_cfg.FLEET_MANAGER_STOP_K_SIGMA)
    ex = {"universe p50": u["p50"], "universe p90": u["p90"]}
    sticky_twin = {
        "kind": "sticky_matched_twin", "construction": "TWIN_STICKY_v1",
        "declaration": "docs/research_notes/2026-10-06/DECLARATION_TWIN_STICKY_v1.json",
        "rule": ("for each name entered, one partner drawn from that name's size x vol x 12-1 cell "
                 "as of the entry date, held until the role exits the name; redrawn on death or "
                 "collision; partner carries the name's weight; 21 draws seeded seed_for(role, j); "
                 "both legs pay the same cost; graded daily as a virtual book (not executed)"),
    }
    b: dict[str, dict] = {}

    # (1) human + AI thematic -- hack1 lineage, Explorer lists as the candidate source
    sig1 = ref["candidate_sigma"].get("thematic", u["p90"])
    b["thematic"] = {**_common("thematic", ref),
        "alpha_source": ("human + AI thematic curation: the owner's themes, candidates from the "
                         "Opportunity Explorer's curated lists"),
        "inputs": [{"name": "Opportunity Explorer receipt",
                    "path": "backend/data/optimus/opportunities/opportunities_<asof>_<runid>.json",
                    "read": "services.opportunities.load_latest (newest by the stamp in the NAME)",
                    "lists": ["human_ai_thematic_v2", "roi_v3"], "max_age_days": 7}],
        "selection": {"kind": "explorer_thematic_book",
                      "rule": ("at seed, the owner names ONE Explorer list (default human_ai_thematic_v2) "
                               "and its receipt; its weights are frozen as the v3 book, each clipped at "
                               "max_name_frac and never renormalised (what is clipped stays cash); "
                               "bar-defect / stitched names and a second share class of one issuer are "
                               "dropped; a later list is a new version"),
                      "horizon_sessions": 21},
        "caps": {**FM.caps_block(), "max_gross_frac": 1.0, "max_name_frac": 0.10, "max_names": 20},
        "exits": "horizon (21 sessions from the first v3 fill) -> cash; resting sigma stops",
        "stop_rule": stop_block(k=k, min_frac=0.04, max_frac=0.12, sigmas=ex,
                                why="the v2 rule carried forward: noise-scaled, inside 12%"),
        "twin": sticky_twin,
        "worst_case": worst_case_block(equity=eq, n_names=10, name_cap=0.10, gross_cap=1.0,
                                       sigma_ref=max(u["p90"], sig1),
                                       sigma_ref_source="max(universe p90, the v2 book's highest sigma)",
                                       k=3.0, stop_max=0.12),
        "kill_rule": ("account drawdown >= 20% from its v3 high-water -> flatten to cash, "
                      "DEPRIORITIZED; at 63 sessions, excess <= 0 vs BOTH the twin and SPY -> "
                      "DEPRIORITIZED (no new entries; held names run to horizon). MECHANISM_REJECTED "
                      "is never issued by this rule"),
    }

    # (2) analyst revision flow + snowball follow-through -- hack2 lineage
    sig2 = ref["candidate_sigma"].get("revision_snowball", u["p90"])
    b["revision_snowball"] = {**_common("revision_snowball", ref),
        "alpha_source": ("analyst revision flow (net raises x firms, 90 days, >= 3 firms) with the "
                         "snowball follow-through as an ORDER only, never a weight"),
        "inputs": [{"name": "dated analyst target actions", "read": "services.revision_flow.compute",
                    "max_age_days": 7},
                   {"name": "snowball shadow", "read": "services.snowball_shadow (analyst/snowball_shadow.jsonl)",
                    "use": "tie-break order among equal flow scores: a name with an open snowball t0 "
                           "(>= 90-day quiet spell ended by a raise) ranks first; probability is NOT a size"}],
        "excluded_inputs": [{"name": "analyst reputation weights",
                             "why": ("REPUTATION_WEIGHT: NOT_PERSISTENT_OOS (rho -0.32; "
                                     "docs/research_notes/2026-10-07/analyst_reputation_build_2026-10-07.md); "
                                     "plumbing only, never an input to this book")}],
        "selection": {"kind": "revision_flow_book",
                      "rule": ("at each 21-session rebalance: names with net raises >= 3 distinct firms in "
                               "90 days, ranked by net raises x firms, top 20 equal weight; bar-defect "
                               "names dropped; one line per issuer"),
                      "horizon_sessions": 21},
        "caps": {**FM.caps_block(), "max_gross_frac": 1.0, "max_name_frac": 0.05, "max_names": 20},
        "exits": "rebalance every 21 sessions; a name leaving the top 20 is sold; resting sigma stops",
        "stop_rule": stop_block(k=k, min_frac=0.04, max_frac=0.12, sigmas=ex,
                                why="post-event drift needs room; a 1-sigma stop is noise"),
        "twin": sticky_twin,
        "worst_case": worst_case_block(equity=eq, n_names=20, name_cap=0.05, gross_cap=1.0,
                                       sigma_ref=max(u["p90"], sig2),
                                       sigma_ref_source="max(universe p90, the v2 book's highest sigma)",
                                       k=3.0, stop_max=0.12),
        "kill_rule": ("account drawdown >= 20% -> flatten, DEPRIORITIZED; at 63 sessions excess <= 0 "
                      "vs both twin and SPY -> DEPRIORITIZED; revision file older than 7 days -> no "
                      "rebalance that day (REFUSE, not kill)"),
    }

    # (3) world / news causal -- hack6 lineage, SHADOW_NEWS tilt with the trust rule
    b["world_news"] = {**_common("world_news", ref),
        "alpha_source": ("world-digest typed implications through SHADOW_NEWS_v0's frozen news_signal "
                         "(d > 0 only), sized by the TRUST RULE"),
        "inputs": [{"name": "world digest", "read": "services.world_digest.news_signal over the newest "
                    "digest's typed implications", "max_age_h": 36},
                   {"name": "trust", "read": "services.world_digest.trust_from",
                    "rule": str(getattr(_cfg, "NEWS_TILT_TRUST_RULE", "world_digest.trust_from()"))}],
        "selection": {"kind": "news_sleeve_trust_sized",
                      "rule": ("long only: names with d_i > 0, strongest first, excluding bar-defect names "
                               "and names that already moved > 2 five-session sigma; weight = 1% x (1 + 2 x "
                               "usable_trust), usable_trust = 0 unless KEY 1 holds for the arm (n dates >= "
                               "N_MDE, posterior lower bound > 0); at most 3%/name, 10 names, 30% gross; "
                               "held 5 sessions then exited unless re-signalled. Trust is read, never edited; "
                               "today usable_trust = 0 on both arms, so every name is 1%"),
                      "horizon_sessions": 5},
        "llm_authority": "none: only typed, validated fields reach this rule; social-only never originates",
        "caps": {**FM.caps_block(), "max_gross_frac": 0.30, "max_name_frac": 0.03, "max_names": 10},
        "exits": "5 sessions -> cash unless re-signalled; resting sigma stops",
        "stop_rule": stop_block(k=k, min_frac=0.04, max_frac=0.10, sigmas=ex,
                                why="a 5-session news hold; the v2 rule"),
        "twin": {"kind": "v1_matched_random_twin_plus_cash",
                 "rule": "the sleeve's own random twin from the same size x vol cell, drawn at entry "
                         "with seed = hash(role, day); the rest of the account is cash in both"},
        "worst_case": worst_case_block(equity=eq, n_names=10, name_cap=0.03, gross_cap=0.30,
                                       sigma_ref=u["p90"], sigma_ref_source="universe p90",
                                       k=3.0, stop_max=0.10),
        "kill_rule": ("account drawdown >= 10% -> flatten, DEPRIORITIZED; digest older than 36 h -> "
                      "no entries that day; at 63 sessions excess <= 0 vs both twin and SPY -> "
                      "DEPRIORITIZED"),
    }

    # (4) quant ensemble -- hack4 re-purposed; fair/sticky-twin library winners only
    qe = ref["quant"]
    b["quant_ensemble"] = {**_common("quant_ensemble", ref),
        "alpha_source": "strategy-library rules that survive BOTH twins and the validation market line",
        "inputs": [{"name": "twin boards", "fair": qe["boards"]["fair"], "sticky": qe["boards"]["sticky"],
                    "read": "services.fleet_v3_contracts.quant_eligibility"}],
        "selection": {"kind": "quant_ensemble_or_cash", "rule": QUANT_RULE,
                      "eligible_at_prepare": qe["eligible"], "n_eligible_at_prepare": qe["n_eligible"],
                      "n_pure_selection_t2_both_twins_at_prepare": qe["n_pure_selection_t2_both_twins"],
                      "today": qe["today"],
                      "rebalance_sessions": 21},
        "caps": {**FM.caps_block(), "max_gross_frac": 1.0, "max_name_frac": 0.10, "max_names": 30},
        "exits": "monthly rebalance to the eligible rules' picks; no eligible rule -> cash",
        "stop_rule": stop_block(k=k, min_frac=0.04, max_frac=0.12, sigmas=ex,
                                why="library rules are monthly; the stop is a disaster stop for them"),
        "twin": {"kind": "the rule's own boards",
                 "rule": "each held rule is graded against its basket fair twin and its sticky twin "
                         "(TWIN_STICKY_v1); while the book is cash, the twin is cash"},
        "worst_case": worst_case_block(equity=eq, n_names=10, name_cap=0.10, gross_cap=1.0,
                                       sigma_ref=u["p90"], sigma_ref_source="universe p90",
                                       k=3.0, stop_max=0.12),
        "worst_case_today": {"usd": 0.0, "why": "HOLD_CASH: no rule is eligible"
                             if qe["today"] == "HOLD_CASH" else "eligible rules exist"},
        "kill_rule": ("account drawdown >= 20% -> flatten, DEPRIORITIZED; a rule whose re-run board "
                      "drops it below the eligibility rule is sold at the next rebalance"),
    }

    # (5) high-risk innovation lane -- Explorer's three-flag names
    sig5 = ref["candidate_sigma"].get("innovation", u["p90"])
    b["innovation"] = {**_common("innovation", ref),
        "alpha_source": ("the Opportunity Explorer's HIGH_RISK_INNOVATION names (>= 2 of 3 flags: "
                         "COVERAGE, BINARY_EVENT, RUNWAY), deliberately small"),
        "inputs": [{"name": "Opportunity Explorer receipt", "read": "services.opportunities.load_latest",
                    "filter": "row.lane == 'HIGH_RISK_INNOVATION' (config.OPPORTUNITIES_* thresholds)",
                    "max_age_days": 7}],
        "selection": {"kind": "innovation_flags",
                      "rule": ("all HIGH_RISK_INNOVATION names from the newest receipt, one line per issuer, "
                               "ranked by the Explorer's list_score; base weight 2%; THIN-COVERAGE PENALTY: "
                               "x0.5 when the COVERAGE flag fires; BINARY-EVENT SIZING: a name with a "
                               "binary event inside the horizon is sized so a 70% gap costs <= 0.7% of "
                               "equity, i.e. <= 1%; HARD 2% per name; at most 15 names, 30% gross"),
                      "horizon_sessions": 63},
        "caps": {**FM.caps_block(), "max_gross_frac": 0.30, "max_name_frac": 0.02, "max_names": 15,
                 "binary_event_max_name_frac": 0.01, "thin_coverage_multiplier": 0.5},
        "exits": "63 sessions -> cash; resting sigma stops; a binary event is NOT stopped through by design",
        "stop_rule": stop_block(k=k, min_frac=0.06, max_frac=0.20, sigmas={**ex, "pool max": sig5},
                                why=("small names need room; a stop cannot protect a binary gap, so "
                                     "the binary-event cap is the protection, not the stop")),
        "twin": {**sticky_twin, "second_twin": (
            "a random draw from the SAME flagged pool at the same weights (separates 'picking among "
            "flagged names' from 'holding flagged names')")},
        "worst_case": worst_case_block(
            equity=eq, n_names=15, name_cap=0.02, gross_cap=0.30, sigma_ref=max(u["p90"], sig5),
            sigma_ref_source="max(universe p90, the flagged pool's highest sigma)", k=3.0,
            stop_max=0.20, binary={"n": 15, "weight": 0.01, "gap": 0.70,
                                   "case": "every name binary at its 1% cap, all gap -70% on one day"}),
        "kill_rule": ("account drawdown >= 15% -> flatten, DEPRIORITIZED; at 63 sessions excess <= 0 vs "
                      "both twins and SPY -> DEPRIORITIZED; Explorer receipt older than 7 days -> no "
                      "entries"),
    }

    # (6) SPY control -- hack5 lineage
    spy = float(ref["spy_sigma"])
    b["spy_control"] = {**_common("spy_control", ref),
        "alpha_source": "market-like CONTROL: 95% SPY, the rest cash (no selection, no view)",
        "inputs": [{"name": "SPY quote", "read": "broker"}],
        "selection": {"kind": "market_control", "symbol": "SPY", "weight": 0.95,
                      "rule": "hold 95% of equity in SPY, the rest cash; no view; no drift trades below "
                              "the minimum order", "horizon_sessions": None},
        "caps": {**FM.caps_block(), "max_gross_frac": 1.0, "max_name_frac": 0.10,
                 "daily_turnover_frac": 1.0, "name_cap_overrides": {"SPY": 0.95}},
        "exits": "none (the control holds); the disaster stop only",
        "stop_rule": stop_block(k=3.0, min_frac=0.10, max_frac=0.10, sigmas={"SPY": spy},
                                why="a DISASTER stop far outside noise: a control stopped by a wiggle "
                                    "stops being the market"),
        "twin": {"kind": "ideal_control", "weights": {"SPY": 0.95}},
        "worst_case": worst_case_block(
            equity=eq, n_names=1, name_cap=0.95, gross_cap=0.95, sigma_ref=spy,
            sigma_ref_source="SPY 63-session panel sigma", k=3.0, stop_max=0.10,
            core={"spy_worst_panel_day": ref.get("spy_worst_day"),
                  "spy_worst_panel_day_usd": (0.95 * float(ref["spy_worst_day"]) * eq
                                              if ref.get("spy_worst_day") is not None else None)}),
        "kill_rule": "never killed: the control is the yardstick; only the disaster stop acts",
    }
    return b


# ─────────────────────────────── archive (an owner step) ────────────────────

def archive_snapshot(dest_root: Path, base: Optional[Path] = None) -> dict:
    """COPY the fleet manager's local record before any broker reset (D2).

    Copies state/, decisions.jsonl, grades.jsonl, modes.json and contracts/
    into `dest_root/<stamp>/` with a sha256 manifest; never moves or deletes.
    Called only by `scripts.fleet_v3_prepare --archive` (the owner's step)."""
    src = FM.root(base)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = Path(dest_root) / stamp
    if dest.exists():
        raise PreparedRefusal(f"REFUSED: {dest} exists; an archive is never overwritten")
    manifest: list[dict[str, Any]] = []
    for name in ("state", "contracts", "decisions.jsonl", "grades.jsonl", "modes.json"):
        s = src / name
        if not s.exists():
            manifest.append({"path": name, "absent": True})
            continue
        files = [s] if s.is_file() else sorted(f for f in s.rglob("*") if f.is_file())
        for f in files:
            rel = f.relative_to(src)
            d = dest / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, d)
            h = hashlib.sha256(d.read_bytes()).hexdigest()
            if h != hashlib.sha256(f.read_bytes()).hexdigest():
                raise PreparedRefusal(f"REFUSED: copy of {rel} does not match its source")
            manifest.append({"path": rel.as_posix(), "sha256": h, "bytes": d.stat().st_size})
    FM.atomic_write_json(dest / "MANIFEST.json", {"stamp": stamp, "files": manifest})
    return {"dest": dest.as_posix(), "n_files": sum(1 for m in manifest if "sha256" in m),
            "manifest": manifest}
