"""
feature_engineering.py — Derive features from transaction ledger + profile
==========================================================================
Key features:
  - est_monthly_income (salary detection → fallback regression)
  - existing_monthly_obligations (declared + detected from ledger)
  - cash_flow_stability metrics
  - digital_engagement_score
  - intent signals
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

warnings.filterwarnings("ignore", category=UserWarning)


# ──────────────────────────────────────────────────────────────────────────────
# Income estimation
# ──────────────────────────────────────────────────────────────────────────────

def detect_salary_pattern(txns_customer: pd.DataFrame) -> dict:
    """
    Detect a recurring salary-like credit pattern.

    Criteria: regular amount (CV < 0.10), appearing most months,
    on a consistent day (std < 5 days).

    Returns dict with:
      - detected: bool
      - est_salary: float or None
      - regularity_score: float 0–1
    """
    # Filter salary credits
    salary_txns = txns_customer[txns_customer["category"] == "salary_credit"].copy()

    if len(salary_txns) < 3:
        # Try to detect salary-like credits: large recurring credits
        credits = txns_customer[txns_customer["direction"] == "credit"].copy()
        if len(credits) < 3:
            return {"detected": False, "est_salary": None, "regularity_score": 0.0}

        # Group by month and find the largest credit per month
        credits["month"] = credits["txn_date"].dt.to_period("M")
        monthly_max = credits.groupby("month")["amount"].max()

        if len(monthly_max) < 3:
            return {"detected": False, "est_salary": None, "regularity_score": 0.0}

        cv = monthly_max.std() / monthly_max.mean() if monthly_max.mean() > 0 else 1.0
        if cv < 0.15:  # relatively consistent
            return {
                "detected": True,
                "est_salary": float(monthly_max.median()),
                "regularity_score": float(max(0, 1.0 - cv * 5)),
            }
        return {"detected": False, "est_salary": None, "regularity_score": 0.0}

    # Analyse salary credits
    amounts = salary_txns["amount"].values
    days = salary_txns["txn_date"].dt.day.values

    amount_cv = np.std(amounts) / np.mean(amounts) if np.mean(amounts) > 0 else 1.0
    day_std = np.std(days)

    # Count months covered
    months_covered = salary_txns["txn_date"].dt.to_period("M").nunique()
    total_months = txns_customer["txn_date"].dt.to_period("M").nunique()
    coverage = months_covered / max(total_months, 1)

    regularity = max(0, 1.0 - amount_cv * 3) * 0.5 + max(0, 1.0 - day_std / 10) * 0.3 + coverage * 0.2

    if amount_cv < 0.10 and coverage > 0.6:
        return {
            "detected": True,
            "est_salary": float(np.median(amounts)),
            "regularity_score": float(np.clip(regularity, 0, 1)),
        }

    return {"detected": False, "est_salary": None, "regularity_score": float(np.clip(regularity, 0, 1))}


def estimate_income_fallback(prospect_row: pd.Series, avg_monthly_spend: float) -> float:
    """
    Fallback income estimation for non-salaried prospects.
    Uses occupation, city tier, education, and spend as proxies.
    """
    # Base by occupation
    occupation = prospect_row.get("occupation_sector", "other")
    lo, hi = config.INCOME_RANGES.get(occupation, (10_000, 50_000))
    base = (lo + hi) / 2

    # Adjust by city tier
    city_tier = prospect_row.get("city_tier", "tier2")
    tier_mult = {"tier1": 1.2, "tier2": 1.0, "tier3": 0.8}.get(city_tier, 1.0)

    # Adjust by education
    education = prospect_row.get("education_level", "graduate")
    edu_mult = {
        "below_10th": 0.6, "10th_pass": 0.7, "12th_pass": 0.8,
        "diploma": 0.9, "graduate": 1.0, "post_graduate": 1.15,
        "professional_degree": 1.3,
    }.get(education, 1.0)

    # Spend-based adjustment: if spending a lot, income is likely higher
    if avg_monthly_spend > 0:
        # Assume people spend 40–70% of income
        spend_implied = avg_monthly_spend / 0.55
        # Weight: 40% from profile, 60% from spend
        estimated = 0.4 * (base * tier_mult * edu_mult) + 0.6 * spend_implied
    else:
        estimated = base * tier_mult * edu_mult

    return float(max(estimated, 8_000))  # floor at ₹8K


# ──────────────────────────────────────────────────────────────────────────────
# Obligation detection
# ──────────────────────────────────────────────────────────────────────────────

def detect_recurring_debits(txns_customer: pd.DataFrame) -> float:
    """
    Detect recurring debit patterns (EMIs, rent) from the ledger
    that aren't already captured as 'existing_emi_debit'.
    """
    # Look at rent + any untagged recurring debits
    debits = txns_customer[
        (txns_customer["direction"] == "debit") &
        (txns_customer["category"].isin(["rent_debit", "other"]))
    ].copy()

    if len(debits) < 3:
        return 0.0

    debits["month"] = debits["txn_date"].dt.to_period("M")

    # Group by approximate amount (within 10%)
    recurring_total = 0.0
    amounts = debits["amount"].values

    # Simple approach: find amounts that appear in most months
    months = debits["month"].nunique()
    if months < 3:
        return 0.0

    # Cluster amounts (within 10% tolerance)
    sorted_amounts = np.sort(amounts)
    clusters = []
    current_cluster = [sorted_amounts[0]]

    for amt in sorted_amounts[1:]:
        if amt <= current_cluster[0] * 1.10:
            current_cluster.append(amt)
        else:
            clusters.append(current_cluster)
            current_cluster = [amt]
    clusters.append(current_cluster)

    for cluster in clusters:
        if len(cluster) >= months * 0.5:  # appears in at least half the months
            recurring_total += np.median(cluster)

    return float(recurring_total)


# ──────────────────────────────────────────────────────────────────────────────
# Cash flow features
# ──────────────────────────────────────────────────────────────────────────────

def compute_cashflow_features(txns_customer: pd.DataFrame) -> dict:
    """Compute monthly cash flow metrics."""
    txns = txns_customer.copy()
    txns["month"] = txns["txn_date"].dt.to_period("M")
    txns["signed_amount"] = np.where(
        txns["direction"] == "credit", txns["amount"], -txns["amount"]
    )

    monthly = txns.groupby("month").agg(
        total_credit=("signed_amount", lambda x: x[x > 0].sum()),
        total_debit=("signed_amount", lambda x: abs(x[x < 0].sum())),
        net_cashflow=("signed_amount", "sum"),
        min_balance=("balance_after", "min"),
    )

    avg_net = monthly["net_cashflow"].mean()
    std_net = monthly["net_cashflow"].std()
    if pd.isna(std_net):
        std_net = 0.0
    cv = std_net / abs(avg_net) if abs(avg_net) > 0 else 2.0

    # Bounce events
    bounce_count = len(txns_customer[txns_customer["category"] == "bounce_charge"])

    # Negative balance days
    neg_balance = (txns_customer["balance_after"] < 0).sum()

    return {
        "avg_monthly_net_cashflow": float(avg_net),
        "avg_monthly_spend": float(monthly["total_debit"].mean()),
        "avg_monthly_credit": float(monthly["total_credit"].mean()),
        "cashflow_cv": float(np.clip(cv, 0, 5)),
        "bounce_count_6m": int(bounce_count),
        "negative_balance_days": int(neg_balance),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Digital engagement
# ──────────────────────────────────────────────────────────────────────────────

def compute_engagement_score(prospect_row: pd.Series) -> float:
    """Compute normalised 0–100 digital engagement score."""
    score = 0.0
    for field, weight in config.ENGAGEMENT_WEIGHTS.items():
        raw = prospect_row.get(field, 0)
        max_val = config.ENGAGEMENT_MAX.get(field, 10)
        normalised = min(raw / max_val, 1.0) if max_val > 0 else 0.0
        score += weight * normalised

    return float(round(score * 100, 1))


# ──────────────────────────────────────────────────────────────────────────────
# Intent signals
# ──────────────────────────────────────────────────────────────────────────────

def compute_intent_signals(prospect_row: pd.Series, reference_date=None) -> dict:
    """Compute intent recency and frequency features."""
    from datetime import datetime

    if reference_date is None:
        reference_date = datetime.now()

    inquiry_date = pd.to_datetime(prospect_row.get("inquiry_date"))
    days_since = (reference_date - inquiry_date).days if pd.notna(inquiry_date) else 90

    return {
        "intent_recency_days": max(0, int(days_since)),
        "intent_frequency_90d": int(prospect_row.get("inquiry_count_90d", 0)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def engineer_features(
    transactions_df: pd.DataFrame,
    prospects_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Full feature engineering pipeline.

    Returns a DataFrame with one row per prospect, all derived features.
    """
    print("[FE] Engineering features...")

    features_list = []
    grouped = transactions_df.groupby("customer_id")

    for i, (customer_id, txns) in enumerate(grouped):
        prospect_row = prospects_df[prospects_df["customer_id"] == customer_id]
        if prospect_row.empty:
            continue
        prospect_row = prospect_row.iloc[0]

        # 1. Salary / income detection
        salary_result = detect_salary_pattern(txns)

        # 2. Cash flow features
        cf = compute_cashflow_features(txns)

        # 3. Income estimation
        if salary_result["detected"] and salary_result["est_salary"] is not None:
            est_income = salary_result["est_salary"]
            income_method = "salary_detection"
        else:
            est_income = estimate_income_fallback(prospect_row, cf["avg_monthly_spend"])
            income_method = "proxy_model"

        # 4. Obligation detection
        declared_emis = float(prospect_row.get("declared_existing_emis", 0))
        detected_recurring = detect_recurring_debits(txns)
        # Don't double-count: if declared EMIs are already in ledger as existing_emi_debit
        emi_in_ledger = txns[txns["category"] == "existing_emi_debit"]["amount"].median()
        if pd.notna(emi_in_ledger) and abs(emi_in_ledger - declared_emis) < declared_emis * 0.2:
            # Declared matches ledger — use the larger of declared or (declared + extra detected)
            existing_obligations = max(declared_emis, declared_emis + detected_recurring * 0.5)
        else:
            existing_obligations = declared_emis + detected_recurring

        # 5. Digital engagement
        engagement = compute_engagement_score(prospect_row)

        # 6. Intent signals
        intent = compute_intent_signals(prospect_row)

        # Assemble feature row
        feature_row = {
            "customer_id": customer_id,
            "customer_name": prospect_row.get("customer_name"),
            # Income
            "est_monthly_income": round(est_income, 2),
            "income_method": income_method,
            "salary_regularity_score": salary_result["regularity_score"],
            # Obligations
            "declared_existing_emis": declared_emis,
            "detected_recurring_debits": round(detected_recurring, 2),
            "existing_monthly_obligations": round(existing_obligations, 2),
            # Cash flow
            "avg_monthly_net_cashflow": round(cf["avg_monthly_net_cashflow"], 2),
            "avg_monthly_spend": round(cf["avg_monthly_spend"], 2),
            "avg_monthly_credit": round(cf["avg_monthly_credit"], 2),
            "cashflow_cv": round(cf["cashflow_cv"], 4),
            "bounce_count_6m": cf["bounce_count_6m"],
            "negative_balance_days": cf["negative_balance_days"],
            # Engagement & intent
            "digital_engagement_score": engagement,
            "intent_recency_days": intent["intent_recency_days"],
            "intent_frequency_90d": intent["intent_frequency_90d"],
            # Pass-through from profile (needed for intent model)
            "age": prospect_row["age"],
            "occupation_sector": prospect_row["occupation_sector"],
            "employment_years": prospect_row["employment_years"],
            "education_level": prospect_row["education_level"],
            "city_tier": prospect_row["city_tier"],
            "existing_bank_relationship": prospect_row["existing_bank_relationship"],
            "source_channel": prospect_row["source_channel"],
            "inquiry_product": prospect_row["inquiry_product"],
            "credit_bureau_score": prospect_row.get("credit_bureau_score"),
            "gender": prospect_row["gender"],
            "inquiry_date": prospect_row["inquiry_date"],
            "existing_products": prospect_row.get("existing_products", ""),
            # Label (training only)
            "converted": prospect_row.get("converted"),
        }
        features_list.append(feature_row)

        if (i + 1) % 500 == 0:
            print(f"  Processed {i+1} prospects...")

    features_df = pd.DataFrame(features_list)
    print(f"[OK] Feature engineering complete: {len(features_df)} prospects, {len(features_df.columns)} features")
    return features_df


def save_features(features_df: pd.DataFrame):
    """Save engineered features to CSV."""
    path = os.path.join(config.DATA_DIR, "features.csv")
    features_df.to_csv(path, index=False)
    print(f"[OK] Saved features -> {path}")


if __name__ == "__main__":
    txns = pd.read_csv(os.path.join(config.DATA_DIR, "transactions.csv"), parse_dates=["txn_date"])
    prospects = pd.read_csv(os.path.join(config.DATA_DIR, "prospects.csv"))
    features = engineer_features(txns, prospects)
    save_features(features)
