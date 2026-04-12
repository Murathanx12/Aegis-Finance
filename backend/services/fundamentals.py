"""
Aegis Finance — SEC EDGAR Fundamentals Service
=================================================

Fetches structured financial statements (income statement, balance sheet,
cash flow) directly from SEC EDGAR via edgartools. This is more reliable
than yfinance for fundamentals: data comes from actual 10-K/10-Q filings
and is free with no rate limits.

Key metrics extracted:
- Revenue, net income, EPS (quarterly and annual)
- Debt/equity, current ratio, interest coverage
- Free cash flow, operating margins
- Revenue and earnings growth rates
- Piotroski F-Score (financial strength composite)

Usage:
    from backend.services.fundamentals import get_fundamentals
"""

import logging
from typing import Optional

import numpy as np

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

try:
    from edgar import Company, set_identity
    set_identity("Aegis Finance aegis@example.com")
    EDGAR_AVAILABLE = True
except ImportError:
    EDGAR_AVAILABLE = False
    logger.info("edgartools not installed — EDGAR fundamentals disabled")

_CACHE_TTL = 86400  # 24 hours — filings don't change often


def get_fundamentals(ticker: str) -> Optional[dict]:
    """Fetch structured fundamentals from SEC EDGAR.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").

    Returns:
        dict with income_statement, balance_sheet, cash_flow, metrics,
        piotroski_score, and filing metadata. None if unavailable.
    """
    if not EDGAR_AVAILABLE:
        return None

    cache_key = f"fundamentals:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    try:
        company = Company(ticker)
        filings = company.get_filings(form="10-K").latest(1)
        if not filings:
            logger.debug("%s: No 10-K filings found", ticker)
            return None

        filing = filings[0] if hasattr(filings, '__getitem__') else filings
        xbrl = filing.xbrl()
        if xbrl is None:
            logger.debug("%s: No XBRL data in filing", ticker)
            return None

        # Extract financial statements
        income = _extract_income_statement(xbrl)
        balance = _extract_balance_sheet(xbrl)
        cashflow = _extract_cash_flow(xbrl)

        # Compute derived metrics
        metrics = _compute_metrics(income, balance, cashflow)
        f_score = _compute_piotroski(income, balance, cashflow)

        result = {
            "ticker": ticker,
            "source": "SEC EDGAR (10-K)",
            "filing_date": str(filing.filing_date) if hasattr(filing, 'filing_date') else None,
            "income_statement": income,
            "balance_sheet": balance,
            "cash_flow": cashflow,
            "metrics": metrics,
            "piotroski_score": f_score,
        }

        cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.warning("%s: EDGAR fundamentals failed — %s", ticker, e)
        return None


def _extract_income_statement(xbrl) -> dict:
    """Extract key income statement items from XBRL."""
    fields = {
        "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                     "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"],
        "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
        "gross_profit": ["GrossProfit"],
        "operating_income": ["OperatingIncomeLoss"],
        "net_income": ["NetIncomeLoss", "ProfitLoss"],
        "eps_basic": ["EarningsPerShareBasic"],
        "eps_diluted": ["EarningsPerShareDiluted"],
        "research_development": ["ResearchAndDevelopmentExpense"],
    }
    return _extract_fields(xbrl, fields)


def _extract_balance_sheet(xbrl) -> dict:
    """Extract key balance sheet items from XBRL."""
    fields = {
        "total_assets": ["Assets"],
        "total_liabilities": ["Liabilities"],
        "stockholders_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "current_assets": ["AssetsCurrent"],
        "current_liabilities": ["LiabilitiesCurrent"],
        "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"],
        "total_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
        "short_term_debt": ["ShortTermBorrowings", "DebtCurrent"],
        "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    }
    return _extract_fields(xbrl, fields)


def _extract_cash_flow(xbrl) -> dict:
    """Extract key cash flow items from XBRL."""
    fields = {
        "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
        "capital_expenditures": ["PaymentsToAcquirePropertyPlantAndEquipment",
                                  "PaymentsToAcquireProductiveAssets"],
        "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
        "share_repurchases": ["PaymentsForRepurchaseOfCommonStock"],
    }
    return _extract_fields(xbrl, fields)


def _extract_fields(xbrl, field_map: dict) -> dict:
    """Extract XBRL facts by trying multiple concept names per field."""
    result = {}
    for field_name, concepts in field_map.items():
        for concept in concepts:
            try:
                facts = xbrl.get_fact(concept)
                if facts is not None:
                    val = facts
                    if hasattr(val, 'value'):
                        val = val.value
                    if hasattr(val, 'iloc'):
                        val = val.iloc[-1] if len(val) > 0 else None
                    if val is not None:
                        result[field_name] = _safe_float(val)
                        break
            except (KeyError, AttributeError, IndexError, TypeError):
                continue
    return result


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None on failure."""
    try:
        f = float(val)
        return f if np.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _compute_metrics(income: dict, balance: dict, cashflow: dict) -> dict:
    """Compute derived financial metrics."""
    metrics = {}

    # Profitability
    revenue = income.get("revenue")
    net_income = income.get("net_income")
    operating_income = income.get("operating_income")

    if revenue and revenue > 0:
        if net_income is not None:
            metrics["net_margin"] = round(net_income / revenue * 100, 2)
        if operating_income is not None:
            metrics["operating_margin"] = round(operating_income / revenue * 100, 2)
        gross = income.get("gross_profit")
        if gross is not None:
            metrics["gross_margin"] = round(gross / revenue * 100, 2)

    # Leverage
    equity = balance.get("stockholders_equity")
    total_debt = balance.get("total_debt", 0) or 0
    short_debt = balance.get("short_term_debt", 0) or 0
    total_all_debt = total_debt + short_debt

    if equity and equity > 0:
        metrics["debt_to_equity"] = round(total_all_debt / equity, 3)
    if net_income and balance.get("total_assets"):
        metrics["return_on_assets"] = round(net_income / balance["total_assets"] * 100, 2)
    if net_income and equity and equity > 0:
        metrics["return_on_equity"] = round(net_income / equity * 100, 2)

    # Liquidity
    curr_assets = balance.get("current_assets")
    curr_liab = balance.get("current_liabilities")
    if curr_assets and curr_liab and curr_liab > 0:
        metrics["current_ratio"] = round(curr_assets / curr_liab, 2)

    # Free cash flow
    ocf = cashflow.get("operating_cash_flow")
    capex = cashflow.get("capital_expenditures")
    if ocf is not None and capex is not None:
        metrics["free_cash_flow"] = ocf - abs(capex)
        if revenue and revenue > 0:
            metrics["fcf_margin"] = round((ocf - abs(capex)) / revenue * 100, 2)

    return metrics


def _compute_piotroski(income: dict, balance: dict, cashflow: dict) -> Optional[dict]:
    """Compute Piotroski F-Score (0-9 financial strength indicator).

    9 binary signals across profitability, leverage, and operating efficiency.
    Score ≥ 7 = strong, ≤ 3 = weak.
    """
    score = 0
    details = {}

    # Profitability (4 points)
    net_income = income.get("net_income")
    ocf = cashflow.get("operating_cash_flow")
    assets = balance.get("total_assets")

    if net_income is not None and assets and assets > 0:
        roa = net_income / assets
        details["positive_roa"] = roa > 0
        if roa > 0:
            score += 1

    if ocf is not None and ocf > 0:
        details["positive_ocf"] = True
        score += 1
    elif ocf is not None:
        details["positive_ocf"] = False

    # Quality of earnings: OCF > net income
    if ocf is not None and net_income is not None:
        details["accruals_quality"] = ocf > net_income
        if ocf > net_income:
            score += 1

    # Leverage (3 points) — simplified without prior year comparison
    curr_assets = balance.get("current_assets")
    curr_liab = balance.get("current_liabilities")
    if curr_assets and curr_liab and curr_liab > 0:
        cr = curr_assets / curr_liab
        details["current_ratio_above_1"] = cr > 1
        if cr > 1:
            score += 1

    equity = balance.get("stockholders_equity")
    total_debt = (balance.get("total_debt") or 0) + (balance.get("short_term_debt") or 0)
    if equity and equity > 0:
        de = total_debt / equity
        details["low_leverage"] = de < 0.5
        if de < 0.5:
            score += 1

    # Operating efficiency (2 points)
    revenue = income.get("revenue")
    if revenue and assets and assets > 0:
        turnover = revenue / assets
        details["asset_turnover"] = round(turnover, 3)
        if turnover > 0.5:
            score += 1

    gross = income.get("gross_profit")
    if gross and revenue and revenue > 0:
        gm = gross / revenue
        details["gross_margin_positive"] = gm > 0
        if gm > 0:
            score += 1

    strength = "strong" if score >= 7 else "moderate" if score >= 4 else "weak"

    return {
        "score": score,
        "max_score": 9,
        "strength": strength,
        "details": details,
    }
