"""
lead_scorer.py — Combine eligibility + intent into ranked, tiered leads
========================================================================
Logic:
  1. Eligibility gate: eligible_loan_amount > min_ticket for each product
  2. Within eligible pool, rank by Intent Score
  3. Tier: Hot (≥70), Warm (40–69), Cold (<40)
  4. Not Eligible = separate flag (not "Cold")
  5. Recommend best product by headroom × intent
"""

import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.eligibility import calculate_all_products, get_best_product


def assign_tier(intent_score: float, is_eligible: bool) -> str:
    """Assign a lead tier based on intent score and eligibility."""
    if not is_eligible:
        return "not_eligible"
    if intent_score >= config.TIER_HOT:
        return "hot"
    elif intent_score >= config.TIER_WARM:
        return "warm"
    else:
        return "cold"


def tier_badge(tier: str) -> str:
    """Return display badge for tier."""
    return {
        "hot": "🔥 Hot",
        "warm": "🟡 Warm",
        "cold": "🔵 Cold",
        "not_eligible": "⛔ Not Eligible",
    }.get(tier, tier)


def score_single_prospect(
    features_row: pd.Series,
    intent_score: float,
    shap_explanation: dict,
) -> dict:
    """
    Score a single prospect: eligibility for all products + intent + tier.

    Returns a complete lead record.
    """
    income = features_row.get("est_monthly_income", 0)
    obligations = features_row.get("existing_monthly_obligations", 0)
    bureau_score = features_row.get("credit_bureau_score")
    inquiry_product = features_row.get("inquiry_product", "personal_loan")

    # Calculate eligibility for all products
    eligibility = calculate_all_products(income, obligations, bureau_score)

    # Determine overall eligibility (eligible for at least one product)
    eligible_products = {k: v for k, v in eligibility.items() if v.get("eligible")}
    is_eligible = len(eligible_products) > 0

    # Assign tier
    tier = assign_tier(intent_score, is_eligible)

    # Find best product
    recommended_product = None
    recommended_amount = 0
    recommended_emi = 0

    if eligible_products:
        # Score each product: headroom × intent
        product_scores = {}
        for pk, ev in eligible_products.items():
            max_ticket = config.PRODUCT_PARAMS[pk]["max_ticket"]
            headroom = ev["eligible_amount"] / max_ticket if max_ticket > 0 else 0
            # Boost if it's the inquiry product
            boost = 1.5 if pk == inquiry_product else 1.0
            product_scores[pk] = headroom * intent_score * boost

        recommended_product = max(product_scores, key=product_scores.get)
        recommended_amount = eligible_products[recommended_product]["eligible_amount"]
        recommended_emi = eligible_products[recommended_product]["eligible_emi"]

    # Build lead record
    lead = {
        "customer_id": features_row.get("customer_id"),
        "customer_name": features_row.get("customer_name"),
        "intent_score": intent_score,
        "tier": tier,
        "tier_badge": tier_badge(tier),
        "is_eligible": is_eligible,
        "recommended_product": recommended_product,
        "recommended_product_name": (
            config.PRODUCT_PARAMS[recommended_product]["display_name"]
            if recommended_product else "—"
        ),
        "recommended_amount": recommended_amount,
        "recommended_emi": recommended_emi,
        "inquiry_product": inquiry_product,
        "inquiry_product_name": (
            config.PRODUCT_PARAMS.get(inquiry_product, {}).get("display_name", inquiry_product)
        ),
        "eligible_product_count": len(eligible_products),
        "est_monthly_income": income,
        "existing_obligations": obligations,
        "source_channel": features_row.get("source_channel", ""),
        "occupation_sector": features_row.get("occupation_sector", ""),
        "city_tier": features_row.get("city_tier", ""),
        "age": features_row.get("age"),
        "gender": features_row.get("gender", ""),
        "employment_years": features_row.get("employment_years"),
        "education_level": features_row.get("education_level", ""),
        "existing_bank_relationship": features_row.get("existing_bank_relationship"),
        "credit_bureau_score": bureau_score,
        "digital_engagement_score": features_row.get("digital_engagement_score", 0),
        "inquiry_date": features_row.get("inquiry_date", ""),
        "top_reason": shap_explanation.get("reason_string", ""),
        "shap_factors": shap_explanation.get("top_factors", []),
        "eligibility_details": eligibility,
        "converted": features_row.get("converted"),  # for backtest only
    }

    return lead


def score_all_prospects(
    features_df: pd.DataFrame,
    intent_scores: np.ndarray,
    shap_explanations: list,
) -> pd.DataFrame:
    """
    Score all prospects and return a ranked lead list.

    Returns DataFrame sorted by: eligible first, then by intent score descending.
    """
    print("[SCORE] Scoring all prospects...")

    leads = []
    for i in range(len(features_df)):
        row = features_df.iloc[i]
        lead = score_single_prospect(
            row,
            float(intent_scores[i]),
            shap_explanations[i] if i < len(shap_explanations) else {},
        )
        leads.append(lead)

    leads_df = pd.DataFrame(leads)

    # Rank: eligible first, then by intent score
    leads_df["_sort_eligible"] = leads_df["is_eligible"].astype(int) * -1  # eligible first
    leads_df["_sort_intent"] = -leads_df["intent_score"]
    leads_df = leads_df.sort_values(
        ["_sort_eligible", "_sort_intent"]
    ).reset_index(drop=True)
    leads_df["rank"] = range(1, len(leads_df) + 1)
    leads_df = leads_df.drop(columns=["_sort_eligible", "_sort_intent"])

    # Stats
    total = len(leads_df)
    eligible = leads_df["is_eligible"].sum()
    hot = (leads_df["tier"] == "hot").sum()
    warm = (leads_df["tier"] == "warm").sum()
    cold = (leads_df["tier"] == "cold").sum()
    not_elig = (leads_df["tier"] == "not_eligible").sum()

    print(f"[OK] Lead scoring complete:")
    print(f"  Total: {total}")
    print(f"  Eligible: {eligible} ({eligible/total:.1%})")
    print(f"  Hot: {hot}  Warm: {warm}  Cold: {cold}  Not Eligible: {not_elig}")

    return leads_df


def get_funnel_stats(leads_df: pd.DataFrame) -> dict:
    """Compute funnel statistics for the analytics dashboard."""
    total = len(leads_df)
    eligible = int(leads_df["is_eligible"].sum())
    hot = int((leads_df["tier"] == "hot").sum())
    warm = int((leads_df["tier"] == "warm").sum())
    cold = int((leads_df["tier"] == "cold").sum())
    not_eligible = int((leads_df["tier"] == "not_eligible").sum())

    return {
        "total": total,
        "eligible": eligible,
        "not_eligible": not_eligible,
        "hot": hot,
        "warm": warm,
        "cold": cold,
        "eligible_pct": round(eligible / total * 100, 1) if total > 0 else 0,
        "hot_pct": round(hot / total * 100, 1) if total > 0 else 0,
    }


if __name__ == "__main__":
    print("Lead scorer module loaded. Use score_all_prospects() to score.")
