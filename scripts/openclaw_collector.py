"""Web intelligence collector — the browser's output becomes typed evidence.

    python -m scripts.openclaw_collector --job edgar_8k
    python -m scripts.openclaw_collector --job edgar_8k --dry-run

WHY THIS EXISTS RATHER THAN "ASK THE AGENT WHAT IT THINKS"
==========================================================
`NEGATIVE_RESULTS.md` §59 closed price/volume at a 21-session horizon, and the
amplitude test returned GO on fundamentals -- 38.4-39.5 bps/month against a
20 bps floor -- while the fundamental panel ends 2024-12-31. The gap is not a
model; it is the last mile of public information that does not arrive as an API:
filings, IR releases, guidance language, supplier statements.

A browser agent is good at that last mile and terrible at being trusted with a
conclusion. So this collector is shaped to take only the first half:

    browser -> STRICT JSON -> web_events.validate() -> the ledger -> features

`web_events` refuses a row that carries an expected return, a rank or an action,
so the collector CANNOT emit a decision even if the model tried. That refusal is
the design; the prompt asking for evidence is only the polite version of it.

EVERY JOB DECLARES ITS SOURCE TYPE
==================================
`source_type` decides which domains are allowed and which event types may be
carried, and the ledger checks both. A job that wandered off its own registry
entry produces refusals rather than attributed evidence, and the refusal count
travels in the receipt -- a silent zero would look identical to a quiet night.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402
from backend.services import openclaw_client as OC          # noqa: E402
from backend.services import web_events as WE               # noqa: E402

logger = logging.getLogger("openclaw_collector")
OUT = _cfg.OPTIMUS_LEDGER_DIR / "web_events"

JOBS: dict[str, dict] = {
    "edgar_8k": {
        "source_type": "sec",
        "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include&count=40",
        "event_type": "filing_8k",
        "confidence_source": "REGULATOR",
        "prompt": """Your browser is on the SEC EDGAR "Latest Filings" page.

Read the RENDERED page. For each 8-K filing listed, extract the company name,
the CIK, and the filing date.

Return STRICT JSON only, no prose, no markdown fence:
{"n":0,"filings":[{"company":"","cik":"","filed":"YYYY-MM-DD"}],
 "observed":"one sentence on what you actually saw","blocked":false}

At most 40. Do NOT invent a company or a CIK. If a field is not on the page
leave it empty. If the page did not load, set blocked=true and say so.
Accuracy matters far more than how many rows you return.""",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_json(reply: str) -> dict | None:
    """The model was asked for strict JSON. Take it, or take the widest braces."""
    reply = reply.strip()
    for candidate in (reply, *re.findall(r"\{.*\}", reply, re.S)):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    return None


def run(job_name: str, *, dry_run: bool = False) -> dict:
    if job_name not in JOBS:
        raise SystemExit(f"REFUSED: unknown job {job_name!r}. Known: {sorted(JOBS)}")
    job = JOBS[job_name]

    health = OC.health()
    if not health.ok:
        return {"receipt": "openclaw_collector", "job": job_name,
                "status": "REFUSED_UNHEALTHY", "health": health.as_dict(),
                "why": ("the browser is not in a state to be trusted with a "
                        "research run; a red health gate means DO NOT BROWSE, "
                        "not browse with something else")}

    OC.browser("open", url=job["url"])
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(job["prompt"])
        prompt_path = fh.name
    try:
        res = OC.agent(prompt_path)
    finally:
        Path(prompt_path).unlink(missing_ok=True)

    payload = _parse_json(res.get("reply", ""))
    if payload is None:
        return {"receipt": "openclaw_collector", "job": job_name,
                "status": "NO_JSON", "rc": res.get("rc"),
                "reply_head": (res.get("reply") or "")[:400],
                "why": "the agent did not return parseable JSON; nothing written"}
    if payload.get("blocked"):
        return {"receipt": "openclaw_collector", "job": job_name,
                "status": "BLOCKED", "observed": payload.get("observed"),
                "why": ("the source blocked the read and the agent said so "
                        "rather than inventing rows — that is the behaviour "
                        "that matters in an unattended agent")}

    rows = []
    for f in (payload.get("filings") or [])[:60]:
        company = (f.get("company") or "").strip()
        cik = (f.get("cik") or "").strip()
        filed = (f.get("filed") or "").strip()[:10] or str(date.today())
        if not company:
            continue
        rows.append({
            "ticker": "*",              # EDGAR's index gives CIK, not a ticker
            "entity": company,
            "source_type": job["source_type"],
            "source_url": job["url"],
            "event_type": job["event_type"],
            "claim": f"{company} (CIK {cik}) filed an 8-K on {filed}",
            "evidence_date": filed,
            "confidence_source": job["confidence_source"],
            "horizon_prior": "1-21d",
            "retrieved_by": f"openclaw:{OC.profile()}",
        })

    out = {"receipt": "openclaw_collector", "job": job_name, "at": _now(),
           "profile": OC.profile(), "n_parsed": len(rows),
           "observed": payload.get("observed"),
           "read_me_first": ("Evidence only. `web_events` refuses any row that "
                             "carries an expected return, a rank or an action, "
                             "so this path cannot emit a decision.")}
    if dry_run:
        out["status"] = "DRY_RUN"
        out["sample"] = rows[:3]
        return out

    out["status"] = "OK"
    out["ledger"] = WE.append(rows)
    out["summary"] = WE.summary()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="edgar_8k", choices=sorted(JOBS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    res = run(a.job, dry_run=a.dry_run)
    OUT.mkdir(parents=True, exist_ok=True)
    p = Path(a.out) if a.out else OUT / f"collector_{a.job}_{date.today()}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str)[:1800])
    print(f"-> {p}")
    return 0 if res.get("status") in ("OK", "DRY_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
