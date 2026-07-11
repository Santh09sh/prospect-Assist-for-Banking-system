"""
config.py — Central configuration for Prospect Assist AI
=========================================================
All values are DEMO ASSUMPTIONS for the hackathon prototype.
They do NOT represent actual IDBI Bank policy.
"""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Synthetic data parameters
# ---------------------------------------------------------------------------
NUM_PROSPECTS = 2000
MONTHS_MIN = 6
MONTHS_MAX = 12
RANDOM_SEED = 42

# Occupation sector distribution (weights)
OCCUPATION_DISTRIBUTION = {
    "salaried_govt": 0.10,
    "salaried_pvt_it": 0.18,
    "salaried_pvt_other": 0.22,
    "self_employed_professional": 0.12,
    "self_employed_business": 0.15,
    "gig_worker": 0.10,
    "retired": 0.08,
    "other": 0.05,
}

# Income ranges by occupation (monthly, INR)
INCOME_RANGES = {
    "salaried_govt": (25_000, 1_50_000),
    "salaried_pvt_it": (30_000, 2_50_000),
    "salaried_pvt_other": (18_000, 1_20_000),
    "self_employed_professional": (20_000, 3_00_000),
    "self_employed_business": (15_000, 2_00_000),
    "gig_worker": (8_000, 60_000),
    "retired": (15_000, 80_000),
    "other": (10_000, 50_000),
}

# City tier distribution
CITY_TIER_DISTRIBUTION = {"tier1": 0.40, "tier2": 0.35, "tier3": 0.25}

# Source channel distribution
SOURCE_CHANNEL_DISTRIBUTION = {
    "branch_walkin": 0.20,
    "website_organic": 0.25,
    "campaign_click": 0.25,
    "referral": 0.15,
    "partner": 0.15,
}

# Education levels
EDUCATION_LEVELS = [
    "below_10th", "10th_pass", "12th_pass",
    "diploma", "graduate", "post_graduate", "professional_degree",
]

# Inquiry product distribution
INQUIRY_PRODUCT_DISTRIBUTION = {
    "personal_loan": 0.35,
    "home_loan": 0.25,
    "mortgage_loan_lap": 0.15,
    "auto_loan": 0.25,
}

# Transaction channels
TXN_CHANNELS = [
    "UPI", "NEFT", "RTGS", "IMPS", "cash", "cheque", "card", "standing_instruction",
]

# Transaction categories
TXN_CATEGORIES = [
    "salary_credit", "rent_debit", "existing_emi_debit", "utility_bill",
    "grocery_retail", "discretionary_spend", "investment_debit",
    "cash_withdrawal", "transfer_in", "transfer_out", "refund",
    "bounce_charge", "other",
]

# ---------------------------------------------------------------------------
# FOIR caps (Fixed Obligation to Income Ratio)
# DEMO ASSUMPTIONS — NOT real IDBI policy
# ---------------------------------------------------------------------------
FOIR_CAPS = [
    (25_000, 0.40),   # income < ₹25,000 → 40%
    (75_000, 0.50),   # ₹25,000–₹75,000 → 50%
    (float("inf"), 0.55),  # > ₹75,000 → 55%
]

def get_foir_cap(monthly_income: float) -> float:
    """Return the FOIR cap for a given monthly income."""
    for threshold, cap in FOIR_CAPS:
        if monthly_income < threshold:
            return cap
    return FOIR_CAPS[-1][1]

# ---------------------------------------------------------------------------
# Product parameters
# DEMO ASSUMPTIONS — NOT real IDBI policy
# ---------------------------------------------------------------------------
PRODUCT_PARAMS = {
    "personal_loan": {
        "display_name": "Personal Loan",
        "type": "unsecured",
        "annual_rate": 0.1175,       # 11.75% p.a.
        "max_tenure_years": 5,
        "default_tenure_years": 3,
        "min_ticket": 50_000,
        "max_ticket": 25_00_000,
        "income_multiple_cap": 15,   # principal ≤ 15× monthly income
        "ltv_cap": None,             # unsecured — no LTV
        "assumed_asset_value": None,
        "description": "Unsecured; principal ≤ ~15× monthly income; tenure ≤ 5 yrs",
    },
    "auto_loan": {
        "display_name": "Auto Loan",
        "type": "secured",
        "annual_rate": 0.0890,       # 8.90% p.a.
        "max_tenure_years": 7,
        "default_tenure_years": 5,
        "min_ticket": 1_00_000,
        "max_ticket": 50_00_000,
        "income_multiple_cap": None,
        "ltv_cap": 0.85,            # ≤ 85% of on-road price
        "assumed_asset_value": 8_00_000,  # mid-range vehicle (demo)
        "description": "≤ ~85% of on-road price; tenure ≤ 7 yrs",
    },
    "home_loan": {
        "display_name": "Home Loan",
        "type": "secured",
        "annual_rate": 0.0865,       # 8.65% p.a.
        "max_tenure_years": 30,
        "default_tenure_years": 20,
        "min_ticket": 5_00_000,
        "max_ticket": 5_00_00_000,
        "income_multiple_cap": None,
        "ltv_cap": 0.80,            # LTV ≤ 80% of property being PURCHASED
        "assumed_asset_value": 50_00_000,  # demo property value
        "description": "LTV ≤ ~80% of property value (purchase); tenure ≤ 20–30 yrs",
    },
    "mortgage_loan_lap": {
        "display_name": "Mortgage Loan (LAP)",
        "type": "secured",
        "annual_rate": 0.0950,       # 9.50% p.a.
        "max_tenure_years": 15,
        "default_tenure_years": 10,
        "min_ticket": 5_00_000,
        "max_ticket": 3_00_00_000,
        "income_multiple_cap": None,
        "ltv_cap": 0.60,            # LTV ≤ 60% of property being PLEDGED
        "assumed_asset_value": 40_00_000,  # demo pledged property value
        "description": "LTV ≤ ~60% of pledged property value; tenure ≤ 15 yrs",
    },
}

# ---------------------------------------------------------------------------
# Intent Score tiering
# ---------------------------------------------------------------------------
TIER_HOT = 70       # Intent Score ≥ 70
TIER_WARM = 40      # Intent Score 40–69
# < 40 = Cold (only among eligible prospects)
# Not Eligible = separate flag

# ---------------------------------------------------------------------------
# Digital engagement weights (for normalised 0–100 score)
# ---------------------------------------------------------------------------
ENGAGEMENT_WEIGHTS = {
    "app_logins_30d": 0.30,
    "emi_calculator_uses_30d": 0.40,
    "product_page_visits_30d": 0.30,
}

# Max expected values for normalisation
ENGAGEMENT_MAX = {
    "app_logins_30d": 30,
    "emi_calculator_uses_30d": 15,
    "product_page_visits_30d": 20,
}

# ---------------------------------------------------------------------------
# Conversion label generation (for honest backtest)
# ---------------------------------------------------------------------------
CONVERSION_SIGNAL_WEIGHT = 0.65   # 65% signal from eligibility + intent
CONVERSION_NOISE_WEIGHT = 0.35    # 35% random noise
BASE_CONVERSION_RATE = 0.12       # ~12% overall conversion rate (realistic)
