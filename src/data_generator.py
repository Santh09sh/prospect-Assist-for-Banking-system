"""
data_generator.py — Synthetic data layer for Prospect Assist AI
================================================================
Generates:
  1. Transaction ledger (6–12 months per customer)
  2. Prospect profile with behavioral + demographic fields

All values are DEMO / SYNTHETIC. Generation assumptions are documented inline.
"""

import os
import random
import sys
from datetime import datetime, timedelta
from typing import List, Tuple

import numpy as np
import pandas as pd
from faker import Faker

# Add parent dir to path so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

fake = Faker("en_IN")
Faker.seed(config.RANDOM_SEED)
np.random.seed(config.RANDOM_SEED)
random.seed(config.RANDOM_SEED)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _weighted_choice(d: dict):
    """Pick a key from dict with values as weights."""
    keys = list(d.keys())
    weights = list(d.values())
    return random.choices(keys, weights=weights, k=1)[0]


def _random_income(occupation: str) -> float:
    """Draw a monthly income from a log-normal distribution within occupation range."""
    lo, hi = config.INCOME_RANGES[occupation]
    mu = np.log((lo + hi) / 2)
    sigma = 0.4
    income = np.exp(np.random.normal(mu, sigma))
    return float(np.clip(income, lo, hi))


def _is_salaried(occupation: str) -> bool:
    return occupation.startswith("salaried") or occupation == "retired"


def _generate_salary_day() -> int:
    """Typical salary credit day (1st, 5th, last working day)."""
    return random.choice([1, 1, 1, 5, 5, 25, 28, 30])


# ──────────────────────────────────────────────────────────────────────────────
# Transaction generation
# ──────────────────────────────────────────────────────────────────────────────

def _generate_transactions_for_prospect(
    customer_id: str,
    occupation: str,
    monthly_income: float,
    declared_emis: float,
    months: int,
    start_date: datetime,
) -> List[dict]:
    """Generate a realistic transaction ledger for one prospect."""

    txns = []
    balance = float(np.random.uniform(5_000, 50_000))  # opening balance
    is_salaried = _is_salaried(occupation)
    salary_day = _generate_salary_day()
    has_bounce_risk = random.random() < 0.08  # 8% of prospects have bounce risk

    # Recurring debit amounts
    rent_amount = monthly_income * random.uniform(0.15, 0.35) if random.random() < 0.6 else 0
    utility_amount = random.uniform(800, 4_000)
    emi_amount = declared_emis  # may be 0
    grocery_base = monthly_income * random.uniform(0.05, 0.12)

    for month_offset in range(months):
        month_date = start_date + timedelta(days=30 * month_offset)
        year = month_date.year
        month = month_date.month

        # ── Income credits ──
        if is_salaried:
            # Salary: near-monthly, similar amount ±5%, similar day ±2
            salary = monthly_income * random.uniform(0.95, 1.05)
            day = max(1, min(28, salary_day + random.randint(-2, 2)))
            txn_date = datetime(year, month, day)
            balance += salary
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(salary, 2),
                "direction": "credit",
                "channel": random.choice(["NEFT", "RTGS", "IMPS"]),
                "category": "salary_credit",
                "counterparty_tag": "employer_X",
                "balance_after": round(balance, 2),
            })
        else:
            # Self-employed / gig: irregular clustered credits
            n_credits = np.random.poisson(lam=4 if occupation == "gig_worker" else 3)
            n_credits = max(1, n_credits)
            for _ in range(n_credits):
                amount = monthly_income / n_credits * random.uniform(0.5, 1.8)
                day = random.randint(1, 28)
                txn_date = datetime(year, month, day)
                balance += amount
                txns.append({
                    "customer_id": customer_id,
                    "txn_date": txn_date.strftime("%Y-%m-%d"),
                    "amount": round(amount, 2),
                    "direction": "credit",
                    "channel": random.choice(["UPI", "NEFT", "IMPS", "cash"]),
                    "category": random.choice(["transfer_in", "other"]),
                    "counterparty_tag": random.choice(["client_A", "client_B", "platform_pay", None]),
                    "balance_after": round(balance, 2),
                })

        # ── Recurring debits ──
        # Rent
        if rent_amount > 0:
            day = random.choice([1, 2, 3, 5])
            txn_date = datetime(year, month, min(day, 28))
            balance -= rent_amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(rent_amount, 2),
                "direction": "debit",
                "channel": random.choice(["UPI", "NEFT", "standing_instruction"]),
                "category": "rent_debit",
                "counterparty_tag": "landlord",
                "balance_after": round(balance, 2),
            })

        # Existing EMI
        if emi_amount > 0:
            day = random.choice([5, 10, 15])
            txn_date = datetime(year, month, day)
            balance -= emi_amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(emi_amount, 2),
                "direction": "debit",
                "channel": "standing_instruction",
                "category": "existing_emi_debit",
                "counterparty_tag": "bank_emi",
                "balance_after": round(balance, 2),
            })

        # Utility bills
        for _ in range(random.randint(1, 3)):
            amount = utility_amount * random.uniform(0.7, 1.4)
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance -= amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "direction": "debit",
                "channel": random.choice(["UPI", "card", "NEFT"]),
                "category": "utility_bill",
                "counterparty_tag": random.choice(["electricity", "water", "internet", "gas"]),
                "balance_after": round(balance, 2),
            })

        # Groceries / retail
        for _ in range(random.randint(3, 8)):
            amount = grocery_base * random.uniform(0.3, 0.6)
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance -= amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "direction": "debit",
                "channel": random.choice(["UPI", "card"]),
                "category": "grocery_retail",
                "counterparty_tag": None,
                "balance_after": round(balance, 2),
            })

        # Discretionary spending (2–5 txns/month)
        for _ in range(random.randint(2, 5)):
            amount = monthly_income * random.uniform(0.01, 0.08)
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance -= amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "direction": "debit",
                "channel": random.choice(["UPI", "card", "cash"]),
                "category": "discretionary_spend",
                "counterparty_tag": None,
                "balance_after": round(balance, 2),
            })

        # Investment debits (30% of prospects)
        if random.random() < 0.30:
            amount = monthly_income * random.uniform(0.05, 0.15)
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance -= amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "direction": "debit",
                "channel": random.choice(["NEFT", "UPI"]),
                "category": "investment_debit",
                "counterparty_tag": "mutual_fund_sip",
                "balance_after": round(balance, 2),
            })

        # Cash withdrawals (1–3/month)
        for _ in range(random.randint(0, 3)):
            amount = random.choice([500, 1000, 2000, 5000, 10000])
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance -= amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": float(amount),
                "direction": "debit",
                "channel": "cash",
                "category": "cash_withdrawal",
                "counterparty_tag": "ATM",
                "balance_after": round(balance, 2),
            })

        # Bounce charges (risk signal — only for risky prospects, not every month)
        if has_bounce_risk and random.random() < 0.3:
            amount = random.choice([350, 500, 750])
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance -= amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": float(amount),
                "direction": "debit",
                "channel": "NEFT",
                "category": "bounce_charge",
                "counterparty_tag": "bank_penalty",
                "balance_after": round(balance, 2),
            })

        # Occasional refund (5% chance)
        if random.random() < 0.05:
            amount = random.uniform(200, 3000)
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            balance += amount
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "direction": "credit",
                "channel": random.choice(["UPI", "NEFT"]),
                "category": "refund",
                "counterparty_tag": "merchant_refund",
                "balance_after": round(balance, 2),
            })

        # Transfer in/out (random peer transfers)
        if random.random() < 0.25:
            amount = random.uniform(1000, 20_000)
            direction = random.choice(["credit", "debit"])
            day = random.randint(1, 28)
            txn_date = datetime(year, month, day)
            if direction == "credit":
                balance += amount
                cat = "transfer_in"
            else:
                balance -= amount
                cat = "transfer_out"
            txns.append({
                "customer_id": customer_id,
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "direction": direction,
                "channel": random.choice(["UPI", "IMPS"]),
                "category": cat,
                "counterparty_tag": "peer",
                "balance_after": round(balance, 2),
            })

        # Ensure balance doesn't go unrealistically negative for long
        if balance < -5000:
            # Inject a credit to partially recover (e.g. overdraft or emergency)
            recovery = abs(balance) * random.uniform(0.5, 1.0)
            balance += recovery

    return txns


# ──────────────────────────────────────────────────────────────────────────────
# Prospect profile generation
# ──────────────────────────────────────────────────────────────────────────────

def _generate_prospect_profile(customer_id: str, occupation: str, monthly_income: float) -> dict:
    """Generate a single prospect profile."""

    is_salaried = _is_salaried(occupation)

    # Age: occupation-dependent
    if occupation == "retired":
        age = random.randint(55, 70)
    elif occupation == "gig_worker":
        age = random.randint(20, 35)
    else:
        age = random.randint(22, 60)

    gender = random.choice(["M", "F", "M", "M"])  # ~75% M for bank loan applicants (realistic)

    # Employment years
    if occupation == "retired":
        employment_years = random.uniform(20, 40)
    else:
        max_exp = age - 20
        employment_years = max(0.5, random.uniform(0.5, max(1, max_exp)))

    # Education: correlated with occupation
    if occupation in ("salaried_pvt_it", "self_employed_professional"):
        education = random.choice(["graduate", "post_graduate", "professional_degree",
                                    "post_graduate", "professional_degree"])
    elif occupation in ("salaried_govt", "salaried_pvt_other"):
        education = random.choice(["graduate", "post_graduate", "diploma", "graduate"])
    else:
        education = random.choice(config.EDUCATION_LEVELS)

    city_tier = _weighted_choice(config.CITY_TIER_DISTRIBUTION)
    source_channel = _weighted_choice(config.SOURCE_CHANNEL_DISTRIBUTION)
    inquiry_product = _weighted_choice(config.INQUIRY_PRODUCT_DISTRIBUTION)

    existing_bank = random.random() < 0.35  # 35% are existing IDBI customers

    # Existing products for existing customers
    existing_products = []
    if existing_bank:
        possible = ["savings_account", "fd", "credit_card", "insurance"]
        existing_products = random.sample(possible, k=random.randint(1, 3))

    # Declared existing EMIs
    if random.random() < 0.4:
        declared_emis = round(monthly_income * random.uniform(0.05, 0.25), 0)
    else:
        declared_emis = 0.0

    # Bureau score: correlated with income stability and occupation
    base_score = 650 if is_salaried else 620
    bureau_score = int(np.clip(
        np.random.normal(base_score, 80), 300, 900
    ))
    # Make some not available
    if random.random() < 0.10:
        bureau_score = None

    # Digital engagement: higher for digital channels
    digital_multiplier = 1.5 if source_channel in ("website_organic", "campaign_click") else 0.8
    app_logins = max(0, int(np.random.poisson(5 * digital_multiplier)))
    emi_calc_uses = max(0, int(np.random.poisson(2 * digital_multiplier)))
    page_visits = max(0, int(np.random.poisson(4 * digital_multiplier)))

    # Inquiry timing
    inquiry_date = datetime.now() - timedelta(days=random.randint(0, 90))
    inquiry_count_90d = max(1, int(np.random.poisson(2)))

    return {
        "customer_id": customer_id,
        "customer_name": fake.name(),
        "age": age,
        "gender": gender,
        "occupation_sector": occupation,
        "employment_years": round(employment_years, 1),
        "education_level": education,
        "city_tier": city_tier,
        "existing_bank_relationship": existing_bank,
        "existing_products": ",".join(existing_products) if existing_products else "",
        "declared_existing_emis": declared_emis,
        "source_channel": source_channel,
        "inquiry_product": inquiry_product,
        "inquiry_date": inquiry_date.strftime("%Y-%m-%d"),
        "inquiry_count_90d": inquiry_count_90d,
        "app_logins_30d": app_logins,
        "emi_calculator_uses_30d": emi_calc_uses,
        "product_page_visits_30d": page_visits,
        "credit_bureau_score": bureau_score,
        "monthly_income_actual": round(monthly_income, 2),  # ground truth for validation only
    }


# ──────────────────────────────────────────────────────────────────────────────
# Conversion label generation
# ──────────────────────────────────────────────────────────────────────────────

def _generate_conversion_label(profile: dict, monthly_income: float) -> bool:
    """
    Generate a realistic `converted` label driven by:
    - Eligibility signals (income, low obligations, good bureau score)
    - Intent signals (digital engagement, recency, existing customer)
    - Random noise

    ~65% signal, ~35% noise. Overall conversion ~12%.
    """
    score = 0.0

    # --- Eligibility signals ---
    # Higher income → higher conversion probability
    income_norm = min(monthly_income / 1_50_000, 1.0)
    score += 0.15 * income_norm

    # Low obligation ratio
    if monthly_income > 0:
        obligation_ratio = profile["declared_existing_emis"] / monthly_income
        score += 0.10 * max(0, 1.0 - obligation_ratio * 3)

    # Good bureau score
    if profile["credit_bureau_score"] is not None:
        bureau_norm = (profile["credit_bureau_score"] - 300) / 600
        score += 0.10 * bureau_norm

    # --- Intent signals ---
    # Digital engagement
    engagement = (
        0.3 * min(profile["app_logins_30d"] / 10, 1.0) +
        0.4 * min(profile["emi_calculator_uses_30d"] / 5, 1.0) +
        0.3 * min(profile["product_page_visits_30d"] / 8, 1.0)
    )
    score += 0.20 * engagement

    # Inquiry recency (more recent = higher)
    days_since = (datetime.now() - datetime.strptime(profile["inquiry_date"], "%Y-%m-%d")).days
    recency_score = max(0, 1.0 - days_since / 90)
    score += 0.10 * recency_score

    # Inquiry frequency
    freq_score = min(profile["inquiry_count_90d"] / 4, 1.0)
    score += 0.05 * freq_score

    # Existing customer boost
    if profile["existing_bank_relationship"]:
        score += 0.08

    # Source channel (referral/partner higher)
    if profile["source_channel"] in ("referral", "partner"):
        score += 0.05
    elif profile["source_channel"] == "campaign_click":
        score += 0.03

    # Employment stability
    emp_score = min(profile["employment_years"] / 10, 1.0)
    score += 0.05 * emp_score

    # Occupation (salaried more likely to convert due to doc ease)
    if profile["occupation_sector"].startswith("salaried"):
        score += 0.04

    # --- Noise ---
    noise = np.random.normal(0, 0.08)
    final_score = score + noise

    # Use a sigmoid-based probability, calibrated so overall conversion ~ 12%
    # The raw score components sum to max ~0.92, typical values ~0.3-0.55
    # We want only ~12% to convert, so set midpoint high
    import math
    k = 15.0  # steepness
    midpoint = 0.72  # high threshold: only strong signals convert
    probability = 1.0 / (1.0 + math.exp(-k * (final_score - midpoint)))
    return random.random() < probability


# ──────────────────────────────────────────────────────────────────────────────
# Main generation
# ──────────────────────────────────────────────────────────────────────────────

def generate_all(
    num_prospects: int = config.NUM_PROSPECTS,
    seed: int = config.RANDOM_SEED,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate the full synthetic dataset.

    Returns:
        (transactions_df, prospects_df)
    """
    np.random.seed(seed)
    random.seed(seed)
    Faker.seed(seed)

    all_transactions = []
    all_prospects = []

    occupations = list(config.OCCUPATION_DISTRIBUTION.keys())
    occ_weights = list(config.OCCUPATION_DISTRIBUTION.values())

    for i in range(num_prospects):
        customer_id = f"CUST_{i+1:05d}"
        occupation = random.choices(occupations, weights=occ_weights, k=1)[0]
        monthly_income = _random_income(occupation)

        # Determine declared EMIs (generated in profile, needed for transactions)
        if random.random() < 0.4:
            declared_emis = round(monthly_income * random.uniform(0.05, 0.25), 0)
        else:
            declared_emis = 0.0

        # Transaction history length
        months = random.randint(config.MONTHS_MIN, config.MONTHS_MAX)
        start_date = datetime.now() - timedelta(days=30 * months)

        # Generate transactions
        txns = _generate_transactions_for_prospect(
            customer_id, occupation, monthly_income, declared_emis, months, start_date
        )
        all_transactions.extend(txns)

        # Generate profile
        profile = _generate_prospect_profile(customer_id, occupation, monthly_income)
        profile["declared_existing_emis"] = declared_emis  # sync with txn gen

        # Generate conversion label
        profile["converted"] = _generate_conversion_label(profile, monthly_income)

        all_prospects.append(profile)

        if (i + 1) % 500 == 0:
            print(f"  Generated {i+1}/{num_prospects} prospects...")

    transactions_df = pd.DataFrame(all_transactions)
    prospects_df = pd.DataFrame(all_prospects)

    # Sort transactions by customer and date
    transactions_df["txn_date"] = pd.to_datetime(transactions_df["txn_date"])
    transactions_df = transactions_df.sort_values(["customer_id", "txn_date"]).reset_index(drop=True)

    return transactions_df, prospects_df


def save_data(transactions_df: pd.DataFrame, prospects_df: pd.DataFrame):
    """Save generated data to CSV."""
    txn_path = os.path.join(config.DATA_DIR, "transactions.csv")
    prospect_path = os.path.join(config.DATA_DIR, "prospects.csv")

    transactions_df.to_csv(txn_path, index=False)
    prospects_df.to_csv(prospect_path, index=False)

    print(f"\n[OK] Saved {len(transactions_df):,} transactions -> {txn_path}")
    print(f"[OK] Saved {len(prospects_df):,} prospects -> {prospect_path}")

    # Summary stats
    print(f"\n-- Summary --")
    print(f"Prospects: {len(prospects_df)}")
    print(f"Transactions: {len(transactions_df):,}")
    print(f"Avg txns/prospect: {len(transactions_df)/len(prospects_df):.0f}")
    print(f"Conversion rate: {prospects_df['converted'].mean():.1%}")
    print(f"\nOccupation distribution:")
    print(prospects_df["occupation_sector"].value_counts().to_string())
    print(f"\nInquiry product distribution:")
    print(prospects_df["inquiry_product"].value_counts().to_string())


if __name__ == "__main__":
    print("[GEN] Generating synthetic data...")
    txns, prospects = generate_all()
    save_data(txns, prospects)
