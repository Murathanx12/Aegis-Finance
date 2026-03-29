"""
Aegis Finance — Retirement/Savings Projection Calculator
==========================================================

Simple compound interest projections with monthly contributions.
Pure math — no Monte Carlo, instant response.

Usage:
    from backend.services.savings_calculator import project_savings
"""


def project_savings(
    monthly_contribution: float,
    current_savings: float,
    current_age: int,
    target_age: int,
    risk_level: str = "moderate",
    inflation_rate: float = 0.025,
    target_amount: float = 1_000_000,
) -> dict:
    """Project savings growth year-by-year.

    Args:
        monthly_contribution: Monthly investment amount ($)
        current_savings: Current portfolio value ($)
        current_age: Current age in years
        target_age: Target retirement age
        risk_level: "conservative" (5%), "moderate" (7%), "aggressive" (9%)
        inflation_rate: Annual inflation rate (default 2.5%)
        target_amount: Goal amount (default $1M)

    Returns:
        Dict with year-by-year projections and milestones
    """
    expected_returns = {
        "conservative": 0.05,
        "moderate": 0.07,
        "aggressive": 0.09,
    }
    nominal_rate = expected_returns.get(risk_level, 0.07)
    monthly_rate = nominal_rate / 12
    monthly_inflation = inflation_rate / 12

    years = max(target_age - current_age, 1)
    total_months = years * 12

    projections = []
    nominal_balance = current_savings
    real_balance = current_savings
    total_contributed = current_savings
    target_met = False
    target_met_age = None
    years_to_target = None

    for year in range(1, years + 1):
        age = current_age + year

        for _ in range(12):
            nominal_balance = nominal_balance * (1 + monthly_rate) + monthly_contribution
            real_balance = real_balance * (1 + monthly_rate - monthly_inflation) + monthly_contribution
            total_contributed += monthly_contribution

        projections.append({
            "year": year,
            "age": age,
            "nominal_balance": round(nominal_balance, 2),
            "real_balance": round(real_balance, 2),
            "total_contributed": round(total_contributed, 2),
            "growth": round(nominal_balance - total_contributed, 2),
        })

        if not target_met and nominal_balance >= target_amount:
            target_met = True
            target_met_age = age
            years_to_target = year

    # Compute required monthly for target if not met
    required_monthly = None
    if not target_met:
        required_monthly = _required_monthly_for_target(
            current_savings, target_amount, total_months, monthly_rate
        )

    # Milestones
    milestones = []
    thresholds = [100_000, 250_000, 500_000, 1_000_000, 2_000_000, 5_000_000]
    for t in thresholds:
        if t <= current_savings:
            continue
        for p in projections:
            if p["nominal_balance"] >= t:
                milestones.append({
                    "amount": t,
                    "age": p["age"],
                    "year": p["year"],
                })
                break

    return {
        "projections": projections,
        "summary": {
            "final_nominal": round(nominal_balance, 2),
            "final_real": round(real_balance, 2),
            "total_contributed": round(total_contributed, 2),
            "total_growth": round(nominal_balance - total_contributed, 2),
            "nominal_rate": nominal_rate,
            "inflation_rate": inflation_rate,
            "real_rate": round(nominal_rate - inflation_rate, 4),
        },
        "target": {
            "amount": target_amount,
            "met": target_met,
            "met_at_age": target_met_age,
            "years_to_target": years_to_target,
            "required_monthly": round(required_monthly, 2) if required_monthly else None,
        },
        "milestones": milestones,
    }


def _required_monthly_for_target(
    current: float, target: float, months: int, monthly_rate: float
) -> float:
    """Calculate required monthly contribution to reach target."""
    if monthly_rate == 0:
        return (target - current) / max(months, 1)

    # Future value of current savings
    fv_current = current * (1 + monthly_rate) ** months

    # Remaining needed from contributions
    remaining = target - fv_current
    if remaining <= 0:
        return 0.0

    # PMT formula: FV = PMT * ((1+r)^n - 1) / r
    factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
    return remaining / factor if factor > 0 else remaining / max(months, 1)
