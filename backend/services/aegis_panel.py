"""AEGIS-PANEL-1 — the canonical PIT monthly training panel (Order 28 §2).

The panel is a JOIN, not an acquisition: the PIT spine
(`crsp_pit_monthly_v1`, delisting returns compounded, frozen $5/$100M
filters) supplies membership and the delist-safe forward label; the JKP
characteristics file (`jkp_global_factor_usa`, formation-date stamped per
JKP construction) supplies ~400 characteristics in declared, separable
families; the CRSP daily files supply the price-only floor features the
incumbent instrument used, so every new claim is priced against the floor
that already exists.

Row = (permno, formation month-end). Labels:

    ret_1m_fwd      next CALENDAR month's ret_incl_delist from the spine —
                    the PRIMARY label. Delisting months keep their label;
                    a gap in the spine's month sequence yields NaN, never
                    a later month masquerading as "next".
    fwd_ret_21d_px  21-trading-day price return (no delist) — reported.
    fwd_vol_21d     21-trading-day forward realized vol — reported.

Determinism: same source bytes, same rows; no RNG anywhere. Coverage is a
deliverable: per year × family non-null fractions, plus the columns the
family map failed to claim (printed, never silently pooled).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services.lane_factory_sim import Panel, load_panel

PANEL = "AEGIS-PANEL-1"
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
JKP_PATH = _config.OPTIMUS_LEDGER_DIR / "wrds" / "jkp_global_factor_usa.parquet"
PIT_PATH = (_config.OPTIMUS_LEDGER_DIR / "crsp_pit"
            / "crsp_pit_monthly_v1.parquet")

#: The incumbent price-only floor (UNIVERSE-SURVIVAL-STRESS-1, verbatim).
FLOOR_FEATURES = ("mom_21", "mom_63", "mom_126", "mom_252_21",
                  "vol_21", "vol_63", "dd_252")

#: JKP columns that are identity/meta/returns — never features. A return
#: column left in the feature set is the classic self-label leak; the list
#: is explicit so the leak check is a set difference, not a hope.
JKP_EXCLUDE = frozenset({
    "id", "permno", "permco", "gvkey", "iid", "excntry", "exch_main",
    "common", "primary_sec", "bidask", "crsp_shrcd", "crsp_exchcd",
    "comp_tpci", "comp_exchg", "curcd", "fx", "date", "eom", "adjfct",
    "source_crsp", "obs_main", "gics", "sic", "naics", "ff49", "size_grp",
    "ret", "ret_local", "ret_exc", "ret_lag_dif", "ret_exc_lead1m",
    "prc_local",
})

#: Ordered first-match rules mapping JKP characteristic names to declared
#: families. Order matters (accruals before growth: `cowc_gr1a` is an
#: accrual, not "growth"). A column no rule claims lands in UNMAPPED and
#: the build prints it — the map's gaps are visible, never pooled quietly.
FAMILY_RULES: tuple[tuple[str, str], ...] = (
    ("EARNINGS_MOMENTUM", r"^(saleq_su|niq_su|ni_inc8q|niq_at_chg1|"
                          r"niq_be_chg1|ocf_at_chg1)$"),
    ("ACCRUALS", r"^(oaccruals_|taccruals_|cowc_gr1a|nncoa_gr1a|"
                 r"noa_gr1a|noa_at|oa_gr1a|ol_gr1a|coa_gr1a|col_gr1a|"
                 r"ncoa_gr1a|ncol_gr1a)"),
    ("ISSUANCE_PAYOUT", r"^(eqnpo|eqnetis|eqbb|eqis|eqpo|chcsho|netis|"
                        r"dltnetis|dstnetis|dbnetis|fincf|div_ni|div_at$|"
                        r"divspc)"),
    ("PRICE_MOMENTUM", r"^(ret_\d|seas_|resff3_|prc_highprc)"),
    ("RISK_PRICE", r"^(beta|ivol|iskew|coskew|rvol|rskew|rmax|corr_1260d|"
                   r"betadown|betabab|mispricing_)"),
    ("LIQUIDITY", r"^(dolvol|tvol$|turnover|zero_trades|ami_126d|"
                  r"bidaskhl)"),
    ("SIZE_SCALE", r"^(me$|me_company$|me_lag1$|market_equity$|prc$|"
                   r"prc_high$|prc_low$|shares$|assets$|sales$|"
                   r"book_equity$|net_income$|enterprise_value$)"),
    ("VALUE", r"(_me$|_mev$)|^(eq_dur|intrinsic_value|ival_me|debt_me|"
              r"netdebt_me|at_be$)"),
    ("GROWTH_INVESTMENT", r"(_gr1$|_gr2$|_gr3$|_gr1a$|_gr3a$)|"
                          r"^(capx_|capex_abn|emp_gr1|sale_emp_gr1|"
                          r"saleq_gr1|ppeinv_gr1a|lnoa_gr1a|sti_gr1a|"
                          r"inv_gr1$|rd5_at$)"),
    ("QUALITY_PROFITABILITY", r"^(gp_|ebit|ope_|ni_|nix_|ocf|fcf_|cop_|"
                              r"op_at|op_atl1|pi_|niq_at$|niq_be$|f_score|"
                              r"o_score|z_score|kz_index|qmj|tangibility|"
                              r"aliq_|age$|earnings_variability|roe|roeq|"
                              r"gpoa_ch5|roa_ch5|cfoa_ch5|gmar_ch5|"
                              r"at_turnover|inv_turnover|rec_turnover|"
                              r"ap_turnover|inv_days|rec_days|ap_days|"
                              r"cash_conversion|sale_|dgp_dsale|dsale_d|"
                              r"niq_saleq_std|fi_at$|fi_bev$)"),
    ("BALANCE_SHEET", r"^(debt_|cash_|pstk_|debtlt_|debtst_|int_|cl_lt|"
                      r"lt_ppen|caliq_cl|ca_cl|inv_act|rec_act|"
                      r"profit_cl|nwc_at|opex_at|spi_at|xido_at|nri_at|"
                      r"adv_sale|staff_sale|rd_|be_bev|tax_)"),
)


class PanelRefused(RuntimeError):
    """A required input is missing or malformed. Refused, not defaulted."""


def family_map(columns: list[str]) -> dict[str, str]:
    """First-match family per column; unmatched -> 'UNMAPPED'."""
    out = {}
    for c in columns:
        for fam, pat in FAMILY_RULES:
            if re.search(pat, c):
                out[c] = fam
                break
        else:
            out[c] = "UNMAPPED"
    return out


def _floor_frame(panel: Panel) -> pd.DataFrame:
    """Month-end rows with the 7 floor features + daily-derived reported
    labels. Drops rows only on MISSING FEATURES (past data) — never on the
    forward columns, so delisting months keep their spine label."""
    px, ret = panel.px, panel.ret
    month_ends = px.groupby(px.index.to_period("M")).tail(1).index
    feats = {}
    for w in (21, 63, 126):
        feats[f"mom_{w}"] = px / px.shift(w) - 1.0
    feats["mom_252_21"] = px.shift(21) / px.shift(252) - 1.0
    for w in (21, 63):
        feats[f"vol_{w}"] = ret.rolling(w).std(ddof=1)
    feats["dd_252"] = px / px.rolling(252).max() - 1.0
    fwd_ret = px.shift(-21) / px - 1.0
    fwd_vol = ret[::-1].rolling(21).std(ddof=1)[::-1].shift(-1)

    rows = []
    for d in month_ends:
        elig = panel.elig_by_month.get(d.to_period("M"), set())
        frame = pd.DataFrame({k: v.loc[d] for k, v in feats.items()})
        frame = frame.dropna(subset=list(FLOOR_FEATURES))
        frame = frame[frame.index.isin(elig)]
        frame["fwd_ret_21d_px"] = fwd_ret.loc[d].reindex(frame.index)
        frame["fwd_vol_21d"] = fwd_vol.loc[d].reindex(frame.index)
        frame["date"] = d
        frame["permno"] = frame.index.astype(int)
        rows.append(frame.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def _spine_labels(spine_path: Path | None = None) -> pd.DataFrame:
    """(permno, month) -> next calendar month's ret_incl_delist. A month
    gap yields NaN — the lead must be month+1, never 'next observed'.
    `spine_path` overrides for the early-era spine; default is v1."""
    p = Path(spine_path) if spine_path is not None else PIT_PATH
    if not p.exists():
        raise PanelRefused(f"{p} missing")
    u = pd.read_parquet(p,
                        columns=["permno", "date", "ret_incl_delist"])
    u["month"] = pd.to_datetime(u["date"]).dt.to_period("M")
    u = u.sort_values(["permno", "month"])
    g = u.groupby("permno")
    lead_ret = g["ret_incl_delist"].shift(-1)
    lead_month = g["month"].shift(-1)
    contiguous = (lead_month == u["month"] + 1)
    u["ret_1m_fwd"] = lead_ret.where(contiguous)
    return u[["permno", "month", "ret_1m_fwd"]]


def _jkp_features() -> tuple[pd.DataFrame, dict[str, str]]:
    if not JKP_PATH.exists():
        raise PanelRefused(f"{JKP_PATH} missing")
    j = pd.read_parquet(JKP_PATH)
    j = j[j["obs_main"] == 1] if "obs_main" in j.columns else j
    feat_cols = [c for c in j.columns if c not in JKP_EXCLUDE]
    fam = family_map(feat_cols)
    j["month"] = pd.to_datetime(j["eom"]).dt.to_period("M")
    j["permno"] = j["permno"].astype("Int64")
    keep = ["permno", "month"] + feat_cols
    j = j.dropna(subset=["permno"])[keep]
    j["permno"] = j["permno"].astype(int)
    # one row per permno-month or the join multiplies rows: refuse, loudly
    dup = j.duplicated(["permno", "month"]).sum()
    if dup:
        raise PanelRefused(f"JKP has {dup} duplicate permno-months — the "
                           f"join would multiply rows; resolve first")
    return j, fam


@dataclass
class BuildResult:
    df: pd.DataFrame
    families: dict[str, str]
    coverage: dict


def build(years: tuple[int, int] = (2013, 2024)) -> BuildResult:
    panel = load_panel(years=years)
    base = _floor_frame(panel)
    base["month"] = base["date"].dt.to_period("M")

    labels = _spine_labels()
    base = base.merge(labels, on=["permno", "month"], how="left")

    jkp, fam = _jkp_features()
    collide = (set(jkp.columns) - {"permno", "month"}) & set(base.columns)
    if collide:
        raise PanelRefused(f"JKP/base column collision: {sorted(collide)}")
    df = base.merge(jkp, on=["permno", "month"], how="left")

    jkp_cols = [c for c in jkp.columns if c not in ("permno", "month")]
    # a broken join (dtype drift, month-convention drift) yields all-NaN
    # characteristics that would RUN as "no signal" — refuse instead
    match_rate = (float(df[jkp_cols[0]].notna().mean()) if jkp_cols
                  else 0.0)
    if match_rate < 0.90:
        raise PanelRefused(
            f"JKP join matched only {match_rate:.1%} of rows (≥90% "
            f"expected — measured 100% at v1). A quiet all-NaN join would "
            f"run the tournament against nothing.")
    fam_full = dict(fam)
    fam_full.update({c: "PRICE_FLOOR" for c in FLOOR_FEATURES})

    years_ix = df["date"].dt.year
    by_family: dict[str, list[str]] = {}
    for c, f in fam_full.items():
        by_family.setdefault(f, []).append(c)
    cov_matrix = {}
    for f, cols in sorted(by_family.items()):
        cov_matrix[f] = {
            int(y): round(float(df.loc[years_ix == y, cols]
                                .notna().mean().mean()), 4)
            for y in sorted(years_ix.unique())}

    n_jkp_matched = int(df[jkp_cols[0]].notna().sum()) if jkp_cols else 0
    coverage = {
        "panel": PANEL,
        "n_rows": int(len(df)),
        "n_months": int(df["month"].nunique()),
        "n_permnos": int(df["permno"].nunique()),
        "window": [str(df['date'].min().date()),
                   str(df['date'].max().date())],
        "n_feature_columns": len(fam_full),
        "n_rows_with_primary_label": int(df["ret_1m_fwd"].notna().sum()),
        "n_rows_jkp_matched": n_jkp_matched,
        "jkp_match_rate": round(n_jkp_matched / max(len(df), 1), 4),
        "unmapped_columns": sorted(c for c, f in fam_full.items()
                                   if f == "UNMAPPED"),
        "families": {f: len(cols) for f, cols in sorted(by_family.items())},
        "coverage_by_year_family": cov_matrix,
        "declared_absent_families": {
            "TEXT": "no PIT text corpus joined in v1 — declared, not missing",
            "OWNERSHIP": "13F/insider joins are a v2 named-consumer item",
            "OPTIONS": "optionm surface joins are a v2 named-consumer item",
        },
    }
    return BuildResult(df=df, families=fam_full, coverage=coverage)


def write(res: BuildResult) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "panel": OUT_DIR / "aegis_panel_v1.parquet",
        "coverage": OUT_DIR / "aegis_panel_v1_coverage.json",
        "meta": OUT_DIR / "aegis_panel_v1.meta.json",
    }
    df = res.df.copy()
    df["month"] = df["month"].astype(str)
    df.to_parquet(paths["panel"], index=False)
    paths["coverage"].write_text(
        json.dumps(res.coverage, indent=2), encoding="utf-8")
    meta = {
        "dataset": PANEL,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "spine": str(PIT_PATH.name),
            "characteristics": str(JKP_PATH.name),
            "daily": "crsp_dsf_YYYY.parquet (floor features + reported "
                     "daily-derived labels)",
        },
        "primary_label": "ret_1m_fwd (next calendar month ret_incl_delist "
                         "from the PIT spine; month gaps -> NaN)",
        "reported_labels": ["fwd_ret_21d_px", "fwd_vol_21d"],
        "family_map": res.families,
        "row_key": "(permno, date) — formation month-end",
        "pit_note": "JKP characteristics are eom formation-stamped per JKP "
                    "construction; spot-audit receipt required before first "
                    "trial use (aegis_panel_jkp_pit_audit)",
    }
    paths["meta"].write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return paths
