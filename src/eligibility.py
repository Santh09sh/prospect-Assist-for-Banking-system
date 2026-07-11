"""
eligibility.py — Transparent eligibility scoring with full calculation trace
=============================================================================
Implements FOIR-based repayment capacity calculation per product.

All caps and rates are DEMO ASSUMPTIONS — NOT real IDBI Bank policy.
"""

import os
import sys
from typing import Dict, List, Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def emi_to_principal(emi: float, annual_rate: float, tenure_years: int) -> float:
    """
    Convert a monthly EMI to the maximum principal using the standard formula:
    P = EMI × [(1+r)^n − 1] / [r × (1+r)^n]
    where r = monthly rate, n = total months.
    """
    if emi <= 0 or annual_rate <= 0 or tenure_years <= 0:
        return 0.0

    r = annual_rate / 12
    n = tenure_years * 12
    factor = ((1 + r) ** n - 1) / (r * (1 + r) ** n)
    return emi * factor


def principal_to_emi(principal: float, annual_rate: float, tenure_years: int) -> float:
    """
    Convert a principal to monthly EMI using the standard formula:
    EMI = P × r × (1+r)^n / [(1+r)^n − 1]
    """
    if principal <= 0 or annual_rate <= 0 or tenure_years <= 0:
        return 0.0

    r = annual_rate / 12
    n = tenure_years * 12
    emi = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    return emi


def calculate_eligibility(
    est_monthly_income: float,
    existing_monthly_obligations: float,
    product_key: str,
    credit_bureau_score: Optional[int] = None,
) -> dict:
    """
    Calculate eligibility for a specific loan product.

    Returns a dict with:
      - eligible: bool
      - eligible_emi: float
      - eligible_amount: float
      - foir_cap: float
      - available_capacity: float
      - product_cap_applied: bool
      - product_cap_reason: str
      - calculation_trace: list of step strings
      - tenure_years: int
      - annual_rate: float
    """
    product = config.PRODUCT_PARAMS.get(product_key)
    if product is None:
        return {"eligible": False, "error": f"Unknown product: {product_key}"}

    trace = []
    income = est_monthly_income
    obligations = existing_monthly_obligations

    # Step 1: FOIR cap
    foir_cap = config.get_foir_cap(income)
    trace.append(
        f"Step 1: Monthly income = ₹{income:,.0f} → FOIR cap = {foir_cap:.0%} "
        f"(income {'<' if income < 25000 else '≤' if income <= 75000 else '>'} "
        f"{'₹25K' if income < 25000 else '₹75K' if income <= 75000 else '₹75K'})"
    )

    # Step 2: Available capacity
    max_emi_allowed = income * foir_cap
    available_capacity = max_emi_allowed - obligations
    trace.append(
        f"Step 2: Max EMI allowed = ₹{income:,.0f} × {foir_cap:.0%} = ₹{max_emi_allowed:,.0f}"
    )
    trace.append(
        f"Step 3: Available capacity = ₹{max_emi_allowed:,.0f} − ₹{obligations:,.0f} "
        f"(existing obligations) = ₹{available_capacity:,.0f}"
    )

    # Step 3: Eligible EMI
    eligible_emi = max(0.0, available_capacity)
    if eligible_emi == 0:
        trace.append("Step 4: Eligible EMI = ₹0 (obligations exceed capacity)")
        return {
            "eligible": False,
            "eligible_emi": 0.0,
            "eligible_amount": 0.0,
            "foir_cap": foir_cap,
            "available_capacity": 0.0,
            "product_cap_applied": False,
            "product_cap_reason": "Obligations exceed FOIR-based capacity",
            "calculation_trace": trace,
            "tenure_years": product["default_tenure_years"],
            "annual_rate": product["annual_rate"],
            "product_key": product_key,
            "product_name": product["display_name"],
        }

    trace.append(f"Step 4: Eligible EMI = ₹{eligible_emi:,.0f}")

    # Step 4: EMI → Principal
    tenure = product["default_tenure_years"]
    rate = product["annual_rate"]
    eligible_amount = emi_to_principal(eligible_emi, rate, tenure)
    trace.append(
        f"Step 5: EMI → Principal (rate={rate:.2%} p.a., tenure={tenure}yr) = ₹{eligible_amount:,.0f}"
    )

    # Step 5: Apply product-specific caps
    product_cap_applied = False
    product_cap_reason = "No cap applied"

    # 5a: Income multiple cap (Personal Loan)
    if product.get("income_multiple_cap"):
        max_by_income = income * product["income_multiple_cap"]
        if eligible_amount > max_by_income:
            eligible_amount = max_by_income
            product_cap_applied = True
            product_cap_reason = f"Capped at {product['income_multiple_cap']}× monthly income"
            trace.append(
                f"Step 6: Product cap — Personal Loan ≤ {product['income_multiple_cap']}× "
                f"income = ₹{max_by_income:,.0f} → capped to ₹{eligible_amount:,.0f}"
            )

    # 5b: LTV cap (secured loans)
    if product.get("ltv_cap") and product.get("assumed_asset_value"):
        max_by_ltv = product["assumed_asset_value"] * product["ltv_cap"]
        if eligible_amount > max_by_ltv:
            eligible_amount = max_by_ltv
            product_cap_applied = True
            asset_type = "property" if "home" in product_key or "mortgage" in product_key else "vehicle"
            product_cap_reason = (
                f"LTV cap: {product['ltv_cap']:.0%} of {asset_type} value "
                f"₹{product['assumed_asset_value']:,.0f}"
            )
            trace.append(
                f"Step 6: LTV cap — {product['display_name']} ≤ {product['ltv_cap']:.0%} × "
                f"₹{product['assumed_asset_value']:,.0f} = ₹{max_by_ltv:,.0f} → "
                f"capped to ₹{eligible_amount:,.0f}"
            )

    # 5c: Min/max ticket
    if eligible_amount < product["min_ticket"]:
        trace.append(
            f"Step 7: Below minimum ticket ₹{product['min_ticket']:,.0f} → Not eligible"
        )
        return {
            "eligible": False,
            "eligible_emi": eligible_emi,
            "eligible_amount": 0.0,
            "foir_cap": foir_cap,
            "available_capacity": available_capacity,
            "product_cap_applied": True,
            "product_cap_reason": f"Below minimum ticket size ₹{product['min_ticket']:,.0f}",
            "calculation_trace": trace,
            "tenure_years": tenure,
            "annual_rate": rate,
            "product_key": product_key,
            "product_name": product["display_name"],
        }

    if eligible_amount > product["max_ticket"]:
        eligible_amount = product["max_ticket"]
        product_cap_applied = True
        product_cap_reason = f"Capped at max ticket ₹{product['max_ticket']:,.0f}"
        trace.append(
            f"Step 6: Max ticket cap = ₹{product['max_ticket']:,.0f} → "
            f"capped to ₹{eligible_amount:,.0f}"
        )

    if not product_cap_applied:
        trace.append("Step 6: No product cap applied")

    # Recalculate EMI for the capped amount
    final_emi = principal_to_emi(eligible_amount, rate, tenure)
    trace.append(
        f"Final: Eligible amount = ₹{eligible_amount:,.0f}, "
        f"EMI = ₹{final_emi:,.0f}/month for {tenure} years"
    )

    return {
        "eligible": True,
        "eligible_emi": round(final_emi, 2),
        "eligible_amount": round(eligible_amount, 2),
        "foir_cap": foir_cap,
        "available_capacity": round(available_capacity, 2),
        "product_cap_applied": product_cap_applied,
        "product_cap_reason": product_cap_reason,
        "calculation_trace": trace,
        "tenure_years": tenure,
        "annual_rate": rate,
        "product_key": product_key,
        "product_name": product["display_name"],
    }


def calculate_all_products(
    est_monthly_income: float,
    existing_monthly_obligations: float,
    credit_bureau_score: Optional[int] = None,
) -> Dict[str, dict]:
    """Calculate eligibility for all products."""
    results = {}
    for product_key in config.PRODUCT_PARAMS:
        results[product_key] = calculate_eligibility(
            est_monthly_income, existing_monthly_obligations,
            product_key, credit_bureau_score,
        )
    return results


def get_best_product(eligibility_results: Dict[str, dict], inquiry_product: str = None) -> Optional[str]:
    """
    Select the best product based on eligibility headroom.

    Priority:
    1. The inquiry product if eligible
    2. Product with highest eligible_amount / max_ticket ratio
    """
    eligible = {k: v for k, v in eligibility_results.items() if v.get("eligible")}

    if not eligible:
        return None

    # If the inquired product is eligible, prefer it
    if inquiry_product and inquiry_product in eligible:
        return inquiry_product

    # Otherwise, pick by highest headroom
    best = max(
        eligible.items(),
        key=lambda kv: kv[1]["eligible_amount"] / config.PRODUCT_PARAMS[kv[0]]["max_ticket"]
    )
    return best[0]


if __name__ == "__main__":
    # Quick demo
    print("── Eligibility Calculator Demo ──\n")

    # Salaried prospect with ₹75K income, ₹12K existing EMIs
    results = calculate_all_products(75_000, 12_000)
    for product, result in results.items():
        status = "[OK] Eligible" if result["eligible"] else "[FAIL] Not Eligible"
        amt = f"₹{result['eligible_amount']:,.0f}" if result["eligible"] else "—"
        print(f"{result['product_name']:30s} {status}  Amount: {amt}")
        for step in result["calculation_trace"]:
            print(f"    {step}")
        print()
