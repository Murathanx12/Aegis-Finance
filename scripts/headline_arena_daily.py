"""M6 — Headline Arena: lock the row in OUR ledger first, then (maybe) post.

WHY THIS EXISTS
===============
Every number this programme quotes about itself is settled by this programme.
Headline Arena settles daily macro direction challenges, publicly, and is not
us. That is the entire point: a record adjudicated by a third party on shared
targets is the one instrument self-measurement cannot provide.

THE ORDER IS THE CONTRACT
=========================
1. compute the direction and the confidence from the FROZEN mapping
   (`backend/data/headline_arena_mapping.yaml`, with its `prereg_hash`);
2. write the `PredictionRecord` into our own ledger;
3. only then, and only if credentials exist, POST it.

Never the other way round. A submission made before the row exists can be
reconciled against whatever we later say we forecast, and the whole exercise is
worth exactly nothing. The script enforces the order in code: the POST helper
takes an already-written record and refuses a payload that is not one.

CREDIT-EARNING NEVER TOUCHES THE CONFIDENCE
===========================================
The arena's financial track scores `50 +- 50 * confidence`, which pays for
overstatement. The confidence posted is the probability already written into
our ledger, verbatim. `arena_payload` reads it off the record rather than
recomputing it, so there is no place for a scoring-aware adjustment to live.

CREDENTIALS ARE ATTENDED AND ABSENT
===================================
`HEADLINE_ARENA_AGENT_ID` and `HEADLINE_ARENA_CLIENT_SECRET` are the names; no
value for either exists in this environment and this script never creates one.
Registration is a magic link to Murat's e-mail. With them absent the run writes
its ledger rows and a receipt saying `posted: false` with the reason -- which is
a complete, useful run, not a failure.

    python -m scripts.headline_arena_daily --dry-run
    python -m scripts.headline_arena_daily --verify-prereg
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("headline_arena")

#: The credential NAMES. Absent here, and the script says so rather than
#: pretending it could have posted.
AGENT_ID_ENV = "HEADLINE_ARENA_AGENT_ID"
CLIENT_SECRET_ENV = "HEADLINE_ARENA_CLIENT_SECRET"

MECHANISM_ID = "headline_arena_v1"

#: The benchmark field names the SETTLING PARTY, not a price series. A row whose
#: benchmark is "us" would make the third-party settlement decorative.
BENCHMARK = "headline_arena_settlement"

SPECIALIST = "headline_arena"
MODEL = "engine"
MODEL_VERSION = "headline_arena_v1"

#: The reasoning text submitted with a prediction. Their terms take a perpetual,
#: sublicensable licence to it, so it says nothing about a book, a holding or a
#: thesis -- only which pre-registered rule fired.
PUBLIC_REASONING = ("pre-registered rule from a frozen sensor mapping "
                    "(prereg_hash {hash}); rule: {rule}")


def _repo_root() -> Path:
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def mapping_path() -> Path:
    from backend.config import BACKEND_DIR
    return BACKEND_DIR / "data" / "headline_arena_mapping.yaml"


def receipt_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "headline_arena"


# --------------------------------------------------------------------------
# the frozen mapping


def load_mapping(path: Path | None = None) -> dict:
    import yaml
    p = path or mapping_path()
    if not p.is_file():
        raise FileNotFoundError(
            f"the pre-registered mapping is missing: {p}. A submission without "
            f"one is a forecast whose rule was chosen after the fact.")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def prereg_hash(mapping: dict) -> str:
    """sha256 over the rules that decide a direction, canonicalised.

    Only `sensors`, `confidence` and `targets` go in: the API block and the
    prose may be corrected without re-registering, but a rule may not.
    """
    payload = {k: mapping.get(k) for k in ("sensors", "confidence", "targets")}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def verify_prereg(mapping: dict) -> dict:
    want = str(mapping.get("prereg_hash") or "")
    got = prereg_hash(mapping)
    return {"declared": want, "computed": got, "match": want == got,
            "note": ("a mismatch means a rule changed without being "
                     "re-registered; the fix is to state the change, not to "
                     "paste the new hash")}


# --------------------------------------------------------------------------
# sensors, from the local bars


def _spy_frame(bars, symbol: str):
    import pandas as pd
    sub = bars[bars["symbol"] == symbol].sort_values("date")
    if sub.empty:
        return None
    return pd.Series(sub["close"].to_numpy(dtype=float),
                     index=pd.to_datetime(sub["date"].to_numpy()))


def sensor_values(bars, asof: date) -> dict[str, dict]:
    """{sensor: {"z": float, "raw": float}} or a refusal note per sensor.

    A sensor the bars cannot support is REPORTED BY NAME and its targets are
    skipped. Substituting a proxy would mean the forecast was not produced by
    the rule that was pre-registered.
    """
    import pandas as pd

    out: dict[str, dict] = {}
    ts = pd.Timestamp(asof)
    spy = _spy_frame(bars, "SPY")
    nvda = _spy_frame(bars, "NVDA")
    if spy is not None:
        spy = spy[spy.index <= ts]
    if nvda is not None:
        nvda = nvda[nvda.index <= ts]

    if spy is None or len(spy) < 253:
        note = ("SPY has fewer than 253 sessions on or before "
                f"{asof} in the local bars")
        out["spy_mom_21"] = {"unavailable": note}
        out["vol_regime"] = {"unavailable": note}
    else:
        mom = spy.iloc[-1] / spy.iloc[-22] - 1.0
        hist = (spy / spy.shift(21) - 1.0).dropna().iloc[-252:]
        sd = float(hist.std())
        out["spy_mom_21"] = {"raw": float(mom),
                             "z": float(mom / sd) if sd > 0 else 0.0,
                             "sd": sd, "n": int(len(hist))}
        rets = spy.pct_change(fill_method=None).dropna()
        v21 = float(rets.iloc[-21:].std())
        v252 = float(rets.iloc[-252:].std())
        ratio = (v21 / v252) if v252 > 0 else 1.0
        out["vol_regime"] = {"raw": ratio, "z": float((ratio - 1.0) / 0.25),
                             "vol_21": v21, "vol_252": v252}

    if spy is None or nvda is None or len(spy) < 253 or len(nvda) < 253:
        out["nvda_vs_spy_5"] = {"unavailable": "SPY or NVDA is short of 253 sessions"}
    else:
        joined = pd.concat([spy.rename("spy"), nvda.rename("nvda")], axis=1).dropna()
        spread = ((joined["nvda"] / joined["nvda"].shift(5) - 1.0)
                  - (joined["spy"] / joined["spy"].shift(5) - 1.0)).dropna()
        sd = float(spread.iloc[-252:].std())
        raw = float(spread.iloc[-1])
        out["nvda_vs_spy_5"] = {"raw": raw,
                                "z": (raw / sd) if sd > 0 else 0.0,
                                "sd": sd, "n": int(len(spread.iloc[-252:]))}
    for v in out.values():
        if "z" in v and not math.isfinite(v["z"]):
            v["z"] = 0.0
    return out


def confidence_from_z(z: float, mapping: dict) -> float:
    c = mapping.get("confidence") or {}
    floor = float(c.get("floor", 0.05))
    ceiling = float(c.get("ceiling", 0.60))
    return max(floor, min(ceiling, abs(float(z)) / 2.0))


def direction_for(target: dict, z: float) -> int:
    """+1 / -1 from the target's declared rule. 0 is never produced: a rule that
    can abstain has to say so in the mapping, and none of the five does."""
    rule = str(target.get("direction", "sign(z)")).strip()
    s = 1 if z >= 0 else -1
    if rule == "sign(z)":
        return s
    if rule == "-sign(z)":
        return -s
    raise ValueError(f"target {target.get('id')} declares direction rule "
                     f"{rule!r}, which this script does not implement. A rule "
                     f"nobody implements would silently become sign(z).")


# --------------------------------------------------------------------------
# the rows


def build_rows(mapping: dict, sensors: dict, asof: date) -> tuple[list, list[dict]]:
    """(PredictionRecords, skipped) — one row per target whose sensor exists."""
    from backend.services.belief_state import Observable, make_prediction

    rows, skipped = [], []
    phash = prereg_hash(mapping)
    for target in mapping.get("targets") or []:
        sname = target["sensor"]
        sensor = sensors.get(sname) or {}
        if "z" not in sensor:
            skipped.append({"target": target["id"], "sensor": sname,
                            "reason": sensor.get("unavailable", "no sensor value"),
                            "note": ("skipped rather than substituted: a "
                                     "different sensor is a different "
                                     "pre-registration")})
            continue
        z = float(sensor["z"])
        d = direction_for(target, z)
        conf = confidence_from_z(z, mapping)
        # `probability` is the graded quantity: P(the target rises). A DOWN
        # call at confidence c is P(up) = 0.5 - c/2, which is the same claim
        # stated so that one Brier can score both directions.
        p = 0.5 + (d * conf) / 2.0
        rows.append(make_prediction(
            ticker=str(target["grade_symbol"]), specialist=SPECIALIST,
            observable=Observable.RETURN_SIGN, horizon_days=1,
            probability=p,
            thesis=(f"{target['id']} ({target['name']}) closes "
                    f"{'up' if d > 0 else 'down'} tomorrow. Rule: "
                    f"{target['direction']} on {sname} (z={z:.3f}); prior: "
                    f"{target.get('prior', '')}"),
            counter_thesis=("the sensor is a one-month equity trend and the "
                            "target is a different asset on a one-day horizon; "
                            "the honest prior is a coin flip and the arena's "
                            "own top agent is near one."),
            next_observable=f"tomorrow's settlement of {target['id']}",
            model=MODEL, model_version=MODEL_VERSION,
            prompt=f"{MECHANISM_ID}|{phash}|{target['id']}",
            input_snapshot={"asof": str(asof), "sensor": sname,
                            "z": round(z, 6), "prereg_hash": phash},
            benchmark=BENCHMARK,
            made_at=f"{asof}T21:00:00+00:00", session_as_of=str(asof),
            mechanism_id=MECHANISM_ID, decision_date=str(asof),
            policy_hash=phash,
            inputs_used={"source": "backend/data/optimus/prices_2025_26/bars.parquet",
                         "as_of": str(asof), "mapping": str(mapping_path().name)},
            confidence=conf,
            # No transaction happens: this is a stated forecast, not a position.
            # Saying `costs_charged=True` here would be a lie about a trade that
            # does not exist.
            costs_charged=False,
            licence=str(mapping.get("licence") or "PRODUCT_EXPERIMENT"),
            notes_text=(f"arena target {target['id']}; direction "
                        f"{'up' if d > 0 else 'down'}; confidence {conf:.3f}")))
    return rows, skipped


def arena_payload(record, target_id: str, prereg: str) -> dict:
    """The POST body, read OFF the already-written record.

    The confidence is `abs(2*probability - 1)`, which inverts exactly the
    construction in `build_rows`. It is derived from the ledger row rather than
    recomputed from the sensor so that there is nowhere for a scoring-aware
    adjustment to live: the arena pays `50 +- 50*confidence`, and the only
    defence against that is that the number was already committed elsewhere.
    """
    if getattr(record, "prediction_id", None) is None:
        raise ValueError("arena_payload takes a written PredictionRecord; a "
                         "payload built from anything else could be posted "
                         "before the ledger row exists, which is the one "
                         "ordering this job is for")
    p = float(record.probability)
    return {
        "target": target_id,
        "direction": "up" if p >= 0.5 else "down",
        "confidence": round(abs(2.0 * p - 1.0), 6),
        "reasoning": PUBLIC_REASONING.format(hash=prereg, rule=record.notes_text),
        "external_id": record.prediction_id,
    }


# --------------------------------------------------------------------------
# the run


def credentials() -> dict:
    agent = os.getenv(AGENT_ID_ENV, "").strip()
    secret = os.getenv(CLIENT_SECRET_ENV, "").strip()
    return {"agent_id_present": bool(agent), "client_secret_present": bool(secret),
            "present": bool(agent and secret),
            "env_names": [AGENT_ID_ENV, CLIENT_SECRET_ENV]}


def run(*, dry_run: bool = True, today: date | None = None,
        bars=None, predictions_path: Path | None = None,
        http_post: Callable[[str, dict], Any] | None = None,
        write_receipt: bool = True) -> dict:
    """Write the rows, then post only if allowed to. Returns the receipt."""
    from backend.services.belief_state import append

    today = today or date.today()
    mapping = load_mapping()
    creds = credentials()
    receipt: dict = {
        "job": "headline_arena_daily",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": str(today), "dry_run": bool(dry_run),
        "mechanism_id": MECHANISM_ID,
        "prereg": verify_prereg(mapping),
        "credentials": creds,
        "posted": False, "n_posted": 0, "rows": [], "skipped": [],
        "caveats": [
            "their terms take a perpetual, sublicensable licence to submitted "
            "text: `reasoning` names only the rule and the prereg hash",
            "the financial track scores 50 +- 50*confidence and is NOT Brier; "
            "our own Brier is computed in our ledger",
            "registration is attended (a magic link to Murat's e-mail)",
        ],
    }
    if not receipt["prereg"]["match"]:
        receipt["refused"] = (
            "the mapping's declared prereg_hash does not match its rules. "
            "Nothing was written and nothing was posted: a forecast whose rule "
            "changed without being re-registered is not a pre-registered "
            "forecast.")
        return _finish(receipt, write_receipt)

    if bars is None:
        from backend.services.paper_books import load_bars
        bars = load_bars()
    from backend.services.book_cadence import latest_bar_date
    asof = latest_bar_date(bars, today)
    if asof is None:
        receipt["refused"] = "the local bars hold no session on or before today"
        return _finish(receipt, write_receipt)
    receipt["bar_date"] = str(asof)

    sensors = sensor_values(bars, asof)
    receipt["sensors"] = {k: {kk: (round(vv, 6) if isinstance(vv, float) else vv)
                              for kk, vv in v.items()} for k, v in sensors.items()}
    rows, skipped = build_rows(mapping, sensors, asof)
    receipt["skipped"] = skipped
    if not rows:
        receipt["nothing_to_do"] = True
        receipt["reason"] = ("no target had a usable sensor; nothing was "
                             "forecast and nothing was posted")
        return _finish(receipt, write_receipt)

    # ── STEP 2: the ledger, BEFORE any network call ────────────────────────
    append(rows, predictions_path)
    receipt["rows"] = [{"prediction_id": r.prediction_id, "ticker": r.ticker,
                        "probability": r.probability, "confidence": r.confidence,
                        "direction": "up" if r.probability >= 0.5 else "down"}
                       for r in rows]
    receipt["n_rows"] = len(rows)
    receipt["ledger_written_before_post"] = True

    # ── STEP 3: the post, only if allowed ──────────────────────────────────
    if dry_run:
        receipt["reason_not_posted"] = (
            "--dry-run: the rows are in our ledger and nothing was sent")
        return _finish(receipt, write_receipt)
    if not creds["present"]:
        receipt["reason_not_posted"] = (
            "credentials absent (registration is attended)")
        return _finish(receipt, write_receipt)

    poster = http_post or _default_post
    phash = receipt["prereg"]["computed"]
    targets = {t["grade_symbol"]: t for t in (mapping.get("targets") or [])}
    posted = []
    for r in rows:
        target = targets.get(r.ticker) or {}
        body = arena_payload(r, str(target.get("id") or r.ticker), phash)
        url = (mapping["api"]["base_url"].rstrip("/")
               + mapping["api"]["submit"].format(challenge_id=body["target"]))
        try:
            posted.append({"target": body["target"], "url": url,
                           "confidence_sent": body["confidence"],
                           "response": poster(url, body)})
        except Exception as exc:                                   # noqa: BLE001
            posted.append({"target": body["target"], "url": url,
                           "error": f"{type(exc).__name__}: {exc}"[:300]})
    receipt["posted"] = any("response" in p for p in posted)
    receipt["n_posted"] = sum(1 for p in posted if "response" in p)
    receipt["submissions"] = posted
    return _finish(receipt, write_receipt)


def _default_post(url: str, body: dict) -> dict:
    """The real POST. Reached only with credentials present, which they are not."""
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "X-Agent-Id": os.getenv(AGENT_ID_ENV, ""),
                 "X-Client-Secret": os.getenv(CLIENT_SECRET_ENV, "")},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as fh:            # noqa: S310
        return json.loads(fh.read() or b"{}")


def _finish(receipt: dict, write_receipt: bool) -> dict:
    if write_receipt:
        try:
            d = receipt_dir()
            d.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            path = d / f"{stamp}.json"
            path.write_text(json.dumps(receipt, indent=2, default=str),
                            encoding="utf-8")
            receipt["receipt_path"] = str(path)
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("arena receipt not written: %s", exc)
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="write the ledger rows and the receipt; post nothing")
    ap.add_argument("--verify-prereg", action="store_true",
                    help="recompute the mapping's prereg_hash and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.verify_prereg:
        v = verify_prereg(load_mapping())
        print(json.dumps(v, indent=2))
        return 0 if v["match"] else 1

    rep = run(dry_run=bool(args.dry_run))
    print(json.dumps({k: v for k, v in rep.items()
                      if k not in ("sensors",)}, indent=2, default=str))
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
