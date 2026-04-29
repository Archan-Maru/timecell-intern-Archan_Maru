"""
Task 01 — Portfolio Risk Calculator

Computes key risk metrics for a given portfolio under two crash scenarios.
No external libraries required.
"""

# ─ Core computation

def compute_risk_metrics(portfolio: dict, crash_severity: float = 1.0) -> dict:
    """
    Compute risk metrics for a portfolio under a crash scenario.

    Args:
        portfolio:       Portfolio dict with total_value_inr, monthly_expenses_inr, assets.
        crash_severity:  1.0 = full crash, 0.5 = moderate crash (50% of expected loss).

    Returns:
        Dictionary with: post_crash_value, runway_months, ruin_test,
                         largest_risk_asset, concentration_warning.
    """
    total_value      = portfolio["total_value_inr"]
    monthly_expenses = portfolio["monthly_expenses_inr"]
    assets           = portfolio["assets"]

    if not assets or total_value <= 0:
        return {
            "post_crash_value":    0.0,
            "runway_months":       0.0,
            "ruin_test":           "FAIL",
            "largest_risk_asset":  None,
            "concentration_warning": False,
        }

    post_crash_value = total_value
    for asset in assets:
        allocation_fraction = asset["allocation_pct"] / 100
        crash_loss_fraction = asset["expected_crash_pct"] / 100 
        asset_value         = total_value * allocation_fraction
        post_crash_value   += asset_value * crash_loss_fraction * crash_severity

    if monthly_expenses <= 0:
        runway_months = float("inf")
    else:
        runway_months = post_crash_value / monthly_expenses

    ruin_test = "PASS" if runway_months > 12 else "FAIL"

    def risk_score(asset: dict) -> float:
        return asset["allocation_pct"] * abs(asset["expected_crash_pct"])

    largest_risk_asset = max(assets, key=risk_score)["name"]

    concentration_warning = any(asset["allocation_pct"] > 40 for asset in assets)

    return {
        "post_crash_value":      round(post_crash_value, 2),
        "runway_months":         round(runway_months, 1),
        "ruin_test":             ruin_test,
        "largest_risk_asset":    largest_risk_asset,
        "concentration_warning": concentration_warning,
    }

def print_allocation_chart(portfolio: dict) -> None:
    """Print a simple horizontal bar chart of asset allocations to the terminal."""
    assets    = portfolio["assets"]
    bar_width = 40 

    print("\nPortfolio Allocation")
    print("-" * (bar_width + 20))

    for asset in assets:
        pct  = asset["allocation_pct"]
        bar  = "=" * int(pct / 100 * bar_width)
        print(f"  {asset['name']:<10} {bar:<{bar_width}} {pct}%")

    print("-" * (bar_width + 20))


def print_metrics(label: str, metrics: dict) -> None:
    """Pretty-print a metrics dict with a scenario label."""
    print(f"\n{'-' * 45}")
    print(f"  Scenario: {label}")
    print(f"{'-' * 45}")
    print(f"  Post-crash value     : INR {metrics['post_crash_value']:>15,.2f}")

    runway = metrics["runway_months"]
    runway_display = f"{runway:.1f} months" if runway != float("inf") else "infinity"
    print(f"  Runway               : {runway_display}")
    print(f"  Ruin test (>12 mo)   : {metrics['ruin_test']}")
    print(f"  Largest risk asset   : {metrics['largest_risk_asset']}")
    print(f"  Concentration warning: {metrics['concentration_warning']}")


def main() -> None:
    """Run the risk calculator on a sample portfolio and print the results."""
    portfolio = {
        "total_value_inr":    10_000_000,  # 1 Crore INR
        "monthly_expenses_inr": 80_000,
        "assets": [
            {"name": "BTC",     "allocation_pct": 30, "expected_crash_pct": -80},
            {"name": "NIFTY50", "allocation_pct": 40, "expected_crash_pct": -40},
            {"name": "GOLD",    "allocation_pct": 20, "expected_crash_pct": -15},
            {"name": "CASH",    "allocation_pct": 10, "expected_crash_pct":   0},
        ],
    }

    # Allocation bar chart
    print_allocation_chart(portfolio)

    # Severe crash (full magnitude)
    severe_metrics = compute_risk_metrics(portfolio, crash_severity=1.0)
    print_metrics("Severe crash (full magnitude)", severe_metrics)

    # Moderate crash (50% of expected loss)
    moderate_metrics = compute_risk_metrics(portfolio, crash_severity=0.5)
    print_metrics("Moderate crash (50% of magnitude)", moderate_metrics)

    print()


def run_edge_case_tests() -> None:
    """Quick sanity checks for edge cases."""

    # 100% cash — should never lose value
    cash_portfolio = {
        "total_value_inr": 1_000_000,
        "monthly_expenses_inr": 50_000,
        "assets": [{"name": "CASH", "allocation_pct": 100, "expected_crash_pct": 0}],
    }
    result = compute_risk_metrics(cash_portfolio)
    assert result["post_crash_value"] == 1_000_000.0, "100% cash should not lose value"
    assert result["ruin_test"] == "PASS"

    # Zero allocation asset — should not affect crash value
    zero_alloc_portfolio = {
        "total_value_inr": 1_000_000,
        "monthly_expenses_inr": 50_000,
        "assets": [
            {"name": "BTC",  "allocation_pct":   0, "expected_crash_pct": -80},
            {"name": "CASH", "allocation_pct": 100, "expected_crash_pct":   0},
        ],
    }
    result = compute_risk_metrics(zero_alloc_portfolio)
    assert result["post_crash_value"] == 1_000_000.0, "Zero-allocation asset should not affect value"

    # Empty portfolio
    empty_portfolio = {"total_value_inr": 0, "monthly_expenses_inr": 50_000, "assets": []}
    result = compute_risk_metrics(empty_portfolio)
    assert result["ruin_test"] == "FAIL"

    # Zero monthly expenses — runway should be infinite
    free_living_portfolio = {
        "total_value_inr": 1_000_000,
        "monthly_expenses_inr": 0,
        "assets": [{"name": "CASH", "allocation_pct": 100, "expected_crash_pct": 0}],
    }
    result = compute_risk_metrics(free_living_portfolio)
    assert result["runway_months"] == float("inf"), "Zero expenses should give infinite runway"
    assert result["ruin_test"] == "PASS"

    print("All edge case tests passed [OK]")


if __name__ == "__main__":
    run_edge_case_tests()
    main()