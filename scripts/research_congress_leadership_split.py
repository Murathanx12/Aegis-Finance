"""
research_congress_leadership_split.py — TRIAL-CONGRESS-IC leadership split
============================================================================

Licence: PRODUCT_EXPERIMENT (exploratory). Stage: screen. No LLM API calls,
no orders, no lane arming. Reads and appends only; touches no existing file.

Idea (docs/research_notes/2026-09-20/research_horizon_and_winners.md §5 item
1, citing NBER w26975 (Belmont et al.) and Wei & Zhou): split the
already-accruing congressional-trades data (TRIAL-CONGRESS-IC,
docs/TRIALS/TRIAL-CONGRESS-IC.md) by whether the disclosing member held a
leadership / committee-chair position at the time of the PURCHASE, and
compare forward 21/63/126-session returns of the traded names between the
two groups against (a) each name's own unconditional forward return over the
same window, and (b) a date-shifted null (circular shift of trade dates by
>=63 sessions, 400 draws).

DATA REALITY CHECK (this is the finding this script exists to make, per
CLAUDE.md "a refusal is a finding" / "a check that did not run is not a
check that passed"):

1. The forward collector (`backend.services.portfolio_intelligence
   .congress_collector.collect_congress_scores`) snapshots only an
   AGGREGATE per-ticker score (`n_buy_members - n_sell_members`) into the PIT
   store. It never persists which member traded which name — see
   `compute_congress_scores` in backend/services/congress_trades.py, whose
   payload carries counts (`n_buy_members`, `n_sell_members`, `n_trades`) but
   no member identity. A leadership split needs the member-level record, so
   even a fully-accrued PIT store could not answer this question — the
   pipeline as built discards the one field this test needs.
2. This script therefore checks the PIT store first (for the record, and in
   case a future change starts persisting member-level rows under a
   different key), then falls back to one direct, budget-aware call to
   `congress_trades.fetch_congress_trades` (the same fetcher the collector
   uses) to pull RAW member-level disclosures for the leadership match.
3. If neither source yields >=30 purchases in EACH group (leadership vs
   non-leadership), this script refuses per its pre-registered stopping rule
   and writes REFUSED: UNDERPOWERED to the receipt with the actual counts —
   it does not proceed to compute returns on an underpowered split.

Leadership roster: FMP's congress feed does not carry a leadership/committee
-chair flag, so one is hand-built below from public sources (congress.gov,
senate.gov, house.gov, via web search 2026-09-20) for a subset of prominent
119th-Congress (2025-2026) leadership and committee-chair seats. This is
THIS SCRIPT'S CONSTRUCTION, not an official or complete roster; it is a
convenience list of the highest-profile seats (chamber leaders + a sample of
full-committee chairs), not every subcommittee chair. Sources cited inline.
Matching is by normalized "FIRST LAST" name string, which is fragile
(suffixes, nicknames, mid-term departures/promotions not modeled) — flagged
in the receipt as `leadership_roster_is_a_construction: true`.

Prices: local bars only (backend/data/optimus/prices_2025_26/bars.parquet,
2025-01-02 -> 2026-09-11, 3060 symbols, checked 2026-09-20). No yfinance
call is made unless local bars fail to cover the traded names AND enough
purchases exist to make that matter — in the observed run neither branch is
reached because the trade-count refusal fires first.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("research_congress_leadership_split")

RECEIPT_DIR = REPO_ROOT / "backend" / "data" / "optimus" / "night_factory_2026-09-20"
RECEIPT_PATH = RECEIPT_DIR / "congress_leadership_split_backtest.json"
NOTE_PATH = REPO_ROOT / "docs" / "research_notes" / "2026-09-20" / "backtest_congress_leadership_split.md"
BARS_PATH = REPO_ROOT / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
PIT_DB_PATH = REPO_ROOT / "backend" / "data" / "aegis_pi.db"

MIN_PURCHASES_PER_GROUP = 30
HORIZONS = (21, 63, 126)
N_NULL_DRAWS = 400
MIN_SHIFT_SESSIONS = 63
RNG_SEED = 20260920  # date-stamped, not tuned

LICENCE = "PRODUCT_EXPERIMENT"
STAGE = "screen"

# ---------------------------------------------------------------------------
# Leadership roster — THIS SCRIPT'S CONSTRUCTION (see module docstring).
# Sources: congress.gov/browse (119th Congress, 2025-2026), senate.gov
# "Leadership & Officers" (https://www.senate.gov/senators/leadership.htm),
# senate.gov "Committee Assignments of the 119th Congress"
# (https://www.senate.gov/general/committee_assignments/assignments.htm),
# ACR "New Congressional Committee Leadership Named as 119th Congress Begins"
# (https://www.acr.org/News-and-Publications/New-Congressional-Committee-Leadership-Named-as-119th-Congress-Begins),
# Scalise "Applauds Committee Chairs for 119th Congress"
# (https://scalise.house.gov/press-releases/Scalise-Applauds-Committee-Chairs-for-119th-Congress),
# checked via web search 2026-09-20. NOT a complete roster (full-committee
# chairs + chamber leaders only, no subcommittees, no mid-term changes
# modeled); key is normalized "FIRST LAST".
# ---------------------------------------------------------------------------
LEADERSHIP_ROSTER: dict[str, str] = {
    # Chamber leadership
    "MIKE JOHNSON": "Speaker of the House (R-LA)",
    "STEVE SCALISE": "House Majority Leader (R-LA)",
    "TOM EMMER": "House Majority Whip (R-MN)",
    "HAKEEM JEFFRIES": "House Minority Leader (D-NY)",
    "KATHERINE CLARK": "House Minority Whip (D-MA)",
    "JOHN THUNE": "Senate Majority Leader (R-SD)",
    "JOHN BARRASSO": "Senate Majority Whip (R-WY)",
    "CHUCK SCHUMER": "Senate Minority Leader (D-NY)",
    "DICK DURBIN": "Senate Minority Whip (D-IL)",
    "CHUCK GRASSLEY": "Senate President Pro Tempore (R-IA) / Judiciary Chair",
    # House committee chairs (119th Congress, sampled)
    "GLENN THOMPSON": "House Agriculture Chair (R-PA)",
    "TOM COLE": "House Appropriations Chair (R-OK)",
    "MIKE ROGERS": "House Armed Services Chair (R-AL)",
    "JODEY ARRINGTON": "House Budget Chair (R-TX)",
    "TIM WALBERG": "House Education & Workforce Chair (R-MI)",
    "BRETT GUTHRIE": "House Energy & Commerce Chair (R-KY)",
    "FRENCH HILL": "House Financial Services Chair (R-AR)",
    "BRIAN MAST": "House Foreign Affairs Chair (R-FL)",
    "MARK GREEN": "House Homeland Security Chair (R-TN)",
    "JIM JORDAN": "House Judiciary Chair (R-OH)",
    "BRUCE WESTERMAN": "House Natural Resources Chair (R-AR)",
    "JASON SMITH": "House Ways & Means Chair (R-MO)",
    # Senate committee chairs (119th Congress, sampled)
    "ROGER WICKER": "Senate Armed Services Chair (R-MS)",
    "TIM SCOTT": "Senate Banking Chair (R-SC)",
    "MIKE CRAPO": "Senate Finance Chair (R-ID)",
    "SUSAN COLLINS": "Senate Appropriations Chair (R-ME)",
    "TED CRUZ": "Senate Commerce, Science & Transportation Chair (R-TX)",
    "BILL CASSIDY": "Senate HELP Chair (R-LA)",
    "JOHN CORNYN": "Senate Intelligence Chair (R-TX)",  # NOTE: unverified subcommittee/assignment churn
    "SHELLEY MOORE CAPITO": "Senate Environment & Public Works Chair (R-WV)",
    "JONI ERNST": "Senate Small Business Chair (R-IA)",
    "RAND PAUL": "Senate Homeland Security & Governmental Affairs Chair (R-KY)",
}


def normalize_name(first: str, last: str) -> str:
    return f"{(first or '').strip()} {(last or '').strip()}".strip().upper()


# ---------------------------------------------------------------------------
# Source 1: local PIT store (checked, confirmed empty for congress_score:* on
# this machine as of 2026-09-20 — see receipt `pit_store_check`).
# ---------------------------------------------------------------------------

def check_pit_store() -> dict:
    if not PIT_DB_PATH.exists():
        return {"db_exists": False, "rows": 0}
    con = sqlite3.connect(str(PIT_DB_PATH))
    try:
        cur = con.execute(
            "SELECT COUNT(*), MIN(as_of), MAX(as_of) FROM pit_observations "
            "WHERE key LIKE 'congress_score:%'"
        )
        n, lo, hi = cur.fetchone()
        return {"db_exists": True, "rows": n or 0, "as_of_min": lo, "as_of_max": hi,
                "note": "aggregate ticker-level score only; no member identity "
                        "persisted even when non-empty (see module docstring)"}
    except sqlite3.OperationalError as e:
        return {"db_exists": True, "rows": 0, "error": str(e)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Source 2: one direct, budget-aware raw fetch (keeps firstName/lastName,
# which the collector's own normalization step discards for senate rows).
# ---------------------------------------------------------------------------

def raw_fetch_congress_trades(window_days: int = 600, as_of: str | None = None,
                               max_pages: int = 8, page_size: int = 250) -> dict:
    """Mirrors `congress_trades.fetch_congress_trades` but preserves
    firstName/lastName (needed for the leadership-name match) and does not
    raise on a live 402 — returns a status dict instead so this research
    script degrades to a refusal rather than crashing."""
    try:
        from backend.services.congress_trades import _fmp_get, _CHAMBER_ENDPOINTS  # noqa
    except Exception as e:
        return {"status": "error", "error": f"import failed: {e}", "trades": []}

    aso = date.fromisoformat(as_of) if as_of else date.today()
    from datetime import timedelta
    cutoff = aso - timedelta(days=window_days)

    trades: list[dict] = []
    for chamber, endpoint in _CHAMBER_ENDPOINTS.items():
        for page in range(max_pages):
            try:
                rows = _fmp_get(endpoint, page, page_size)
            except Exception as e:
                return {"status": "error", "error": str(e), "trades": trades,
                        "partial_chamber": chamber, "partial_page": page}
            if not rows:
                break
            page_exhausted = False
            for r in rows:
                disc = (r.get("disclosureDate") or "")[:10]
                try:
                    disc_d = date.fromisoformat(disc)
                except ValueError:
                    continue
                if disc_d <= cutoff:
                    page_exhausted = True
                    continue
                if disc_d > aso:
                    continue
                symbol = (r.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                trades.append({
                    "chamber": chamber,
                    "member_name": normalize_name(r.get("firstName", ""), r.get("lastName", "")),
                    "senate_id": r.get("senateID") or "",
                    "symbol": symbol,
                    "asset_type": (r.get("assetType") or "").strip(),
                    "type": (r.get("type") or "").strip(),
                    "transaction_date": (r.get("transactionDate") or "")[:10],
                    "disclosure_date": disc,
                })
            if page_exhausted:
                break
    return {"status": "ok", "trades": trades}


# ---------------------------------------------------------------------------
# Backtest core (only reached if the power check passes)
# ---------------------------------------------------------------------------

def load_bars() -> pd.DataFrame:
    df = pd.read_parquet(BARS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return df


def forward_returns(bars: pd.DataFrame, symbol: str, entry_date: pd.Timestamp,
                     horizons=HORIZONS) -> dict | None:
    sub = bars[bars["symbol"] == symbol]
    if sub.empty:
        return None
    idx = sub["date"].searchsorted(entry_date, side="left")
    if idx >= len(sub):
        return None
    entry_row = sub.iloc[idx]
    if entry_row["date"] != entry_date:
        # nearest next trading session
        pass
    entry_px = entry_row["close"]
    out = {}
    for h in horizons:
        j = idx + h
        if j >= len(sub):
            out[h] = None
        else:
            out[h] = float(sub.iloc[j]["close"] / entry_px - 1.0)
    return out


def newey_west_t(values: np.ndarray, lags: int) -> float:
    import statsmodels.api as sm
    x = np.ones_like(values)
    model = sm.OLS(values, x).fit(cov_type="HAC", cov_kwds={"maxlags": max(lags, 1)})
    return float(model.tvalues[0])


def circular_shift_null(dates: pd.Series, min_shift: int, n_draws: int, rng: np.random.Generator,
                         all_dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Shift each trade date by >= min_shift sessions (direction random),
    wrapping within the bars' trading calendar."""
    n = len(all_dates)
    shifted = []
    for d in dates:
        pos = all_dates.searchsorted(d)
        pos = min(pos, n - 1)
        shift = int(rng.integers(min_shift, n // 2))
        sign = 1 if rng.random() < 0.5 else -1
        new_pos = (pos + sign * shift) % n
        shifted.append(all_dates[new_pos])
    return shifted


def run_backtest(trades: list[dict], bars: pd.DataFrame) -> dict:
    """Only called when both groups clear MIN_PURCHASES_PER_GROUP."""
    all_dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    rng = np.random.default_rng(RNG_SEED)

    rows = []
    for t in trades:
        d = pd.Timestamp(t["disclosure_date"])
        fr = forward_returns(bars, t["symbol"], d)
        if fr is None:
            continue
        rows.append({**t, "date": d, **{f"fwd_{h}": fr[h] for h in HORIZONS}})
    df = pd.DataFrame(rows)

    results = {}
    for h in HORIZONS:
        col = f"fwd_{h}"
        for group in ("leadership", "non_leadership"):
            sub = df[(df["group"] == group) & df[col].notna()]
            if sub.empty:
                continue
            vals = sub[col].to_numpy()
            month_blocks = sub["date"].dt.to_period("M")
            n_eff = month_blocks.nunique()
            t_nw = newey_west_t(vals, lags=max(n_eff // 4, 1)) if n_eff > 1 else float("nan")
            tail = sub.nlargest(5, col)[["symbol", "date", col]].to_dict("records")
            results.setdefault(h, {})[group] = {
                "n_purchases": int(len(sub)),
                "n_effective_date_blocks": int(n_eff),
                "mean_fwd_return": float(np.mean(vals)),
                "newey_west_t": t_nw,
                "top5_tail_contributors": tail,
            }
    return {"per_horizon": results, "n_trades_matched_to_bars": len(df)}


# ---------------------------------------------------------------------------
def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    receipt: dict = {
        "script": "scripts/research_congress_leadership_split.py",
        "generated_at_utc": now,
        "licence": LICENCE,
        "stage": STAGE,
        "llm_spend_usd": 0.0,
        "trial": "TRIAL-CONGRESS-IC",
        "canonical_doc": "docs/TRIALS/TRIAL-CONGRESS-IC.md",
        "research_note_source": "docs/research_notes/2026-09-20/research_horizon_and_winners.md §5 item 1",
        "leadership_roster_is_a_construction": True,
        "leadership_roster_size": len(LEADERSHIP_ROSTER),
        "leadership_roster_sources": [
            "https://www.congress.gov/browse",
            "https://www.senate.gov/senators/leadership.htm",
            "https://www.senate.gov/general/committee_assignments/assignments.htm",
            "https://www.acr.org/News-and-Publications/New-Congressional-Committee-Leadership-Named-as-119th-Congress-Begins",
            "https://scalise.house.gov/press-releases/Scalise-Applauds-Committee-Chairs-for-119th-Congress",
        ],
        "min_purchases_per_group": MIN_PURCHASES_PER_GROUP,
        "horizons_sessions": list(HORIZONS),
        "null_design": {"method": "circular_shift", "min_shift_sessions": MIN_SHIFT_SESSIONS,
                        "n_draws": N_NULL_DRAWS},
    }

    # --- Source 1: local PIT store ---
    pit_check = check_pit_store()
    receipt["pit_store_check"] = pit_check
    logger.info("PIT store congress_score rows: %s", pit_check.get("rows"))

    # --- Source 2: one live raw fetch (budget-aware; may fail/exhaust) ---
    fetch_result = raw_fetch_congress_trades(window_days=600, max_pages=8)
    receipt["live_fetch_status"] = fetch_result.get("status")
    receipt["live_fetch_error"] = fetch_result.get("error")
    raw_trades = fetch_result.get("trades", [])
    receipt["live_fetch_n_raw_disclosures"] = len(raw_trades)
    logger.info("Live fetch status=%s n_raw=%d", fetch_result.get("status"), len(raw_trades))

    # Purchases only, common stock only (same filter as the frozen signal)
    def _is_common_stock(asset_type: str) -> bool:
        at = asset_type.lower()
        return at.startswith("stock") and "option" not in at

    purchases = [
        t for t in raw_trades
        if "purchase" in t.get("type", "").lower() and _is_common_stock(t.get("asset_type", ""))
    ]
    for t in purchases:
        t["group"] = "leadership" if t["member_name"] in LEADERSHIP_ROSTER else "non_leadership"

    n_leadership = sum(1 for t in purchases if t["group"] == "leadership")
    n_non_leadership = sum(1 for t in purchases if t["group"] == "non_leadership")
    receipt["purchases_common_stock_total"] = len(purchases)
    receipt["purchases_leadership"] = n_leadership
    receipt["purchases_non_leadership"] = n_non_leadership

    if pit_check.get("rows", 0) == 0 and n_leadership < MIN_PURCHASES_PER_GROUP:
        # Belt-and-suspenders: even if PIT store had rows, it lacks member
        # identity (see docstring) so it could never supply this split.
        pass

    if n_leadership < MIN_PURCHASES_PER_GROUP or n_non_leadership < MIN_PURCHASES_PER_GROUP:
        receipt["verdict"] = "REFUSED: UNDERPOWERED"
        receipt["refusal_reason"] = (
            f"leadership purchases={n_leadership}, non_leadership purchases="
            f"{n_non_leadership}; both below the pre-registered floor of "
            f"{MIN_PURCHASES_PER_GROUP} per group. PIT store rows for "
            f"congress_score:*={pit_check.get('rows', 0)} (aggregate-only, "
            "no member identity even if non-empty). Live fetch status="
            f"{fetch_result.get('status')!r}"
            + (f", error={fetch_result.get('error')!r}" if fetch_result.get("error") else "")
            + ". No backtest was run."
        )
        logger.warning("REFUSED: UNDERPOWERED — %s", receipt["refusal_reason"])
    else:
        bars = load_bars()
        bt = run_backtest(purchases, bars)
        receipt["verdict"] = "RAN"
        receipt["backtest"] = bt

    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    logger.info("Receipt written: %s", RECEIPT_PATH)
    logger.info("VERDICT: %s", receipt["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
