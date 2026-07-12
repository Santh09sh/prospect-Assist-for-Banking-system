"""
statement_parser.py — Parse raw bank statement CSVs into internal transaction format
=====================================================================================
Handles:
  - Auto-detection of common column names (Date, Narration, Debit, Credit, Balance, etc.)
  - Keyword-based transaction classification (salary, EMI, rent, utility, etc.)
  - Channel inference from narration text
  - Validation: minimum 3 months of transaction data
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Column name mappings — covers most Indian bank statement exports
# ──────────────────────────────────────────────────────────────────────────────

DATE_ALIASES = [
    "date", "txn_date", "txn date", "transaction date", "trans date",
    "value date", "value_date", "posting date", "posting_date", "dt",
]

NARRATION_ALIASES = [
    "narration", "description", "particulars", "remarks", "details",
    "transaction details", "transaction_details", "txn description",
    "txn_description", "narrative", "payment details",
]

DEBIT_ALIASES = [
    "debit", "withdrawal", "withdrawals", "debit amount", "debit_amount",
    "dr", "dr.", "withdrawal amount", "withdrawal_amount", "debit(dr)",
]

CREDIT_ALIASES = [
    "credit", "deposit", "deposits", "credit amount", "credit_amount",
    "cr", "cr.", "deposit amount", "deposit_amount", "credit(cr)",
]

BALANCE_ALIASES = [
    "balance", "closing balance", "closing_balance", "running balance",
    "running_balance", "available balance", "bal", "balance_after",
]

AMOUNT_ALIASES = [
    "amount", "transaction amount", "txn amount", "txn_amount",
    "transaction_amount",
]


# ──────────────────────────────────────────────────────────────────────────────
# Transaction classification keywords
# ──────────────────────────────────────────────────────────────────────────────

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "salary_credit": [
        "salary", "sal cr", "sal/", "payroll", "stipend", "wages",
        "monthly pay", "emolument",
    ],
    "existing_emi_debit": [
        "emi", "loan repay", "loan emi", "auto debit loan",
        "home loan", "car loan", "personal loan", "vehicle loan",
        "housing loan", "education loan", "loan instalment",
    ],
    "rent_debit": [
        "rent", "house rent", "monthly rent", "rental",
    ],
    "utility_bill": [
        "electricity", "electric", "power bill", "bescom", "tata power",
        "adani elect", "water bill", "water charge", "gas bill",
        "piped gas", "internet", "broadband", "wifi", "jio fiber",
        "airtel xstream", "act fibernet", "telephone", "mobile recharge",
        "prepaid", "postpaid", "dth", "tata sky", "dish tv",
    ],
    "grocery_retail": [
        "grocery", "grocer", "supermarket", "bigbasket", "blinkit",
        "zepto", "dunzo", "swiggy instamart", "dmart", "reliance fresh",
        "more retail", "spencer", "star bazaar",
    ],
    "discretionary_spend": [
        "amazon", "flipkart", "myntra", "ajio", "meesho",
        "zomato", "swiggy", "food delivery", "restaurant",
        "hotel", "movie", "bookmyshow", "pvr", "inox",
        "shopping", "mall", "fashion", "apparel",
    ],
    "investment_debit": [
        "mutual fund", "mf purchase", "sip", "zerodha", "groww",
        "kuvera", "coin", "stock", "share", "demat", "nps",
        "ppf", "fixed deposit", "fd", "recurring deposit", "rd",
        "insurance", "lic", "premium",
    ],
    "transfer_in": [
        "received from", "cr by transfer", "inward", "imps cr",
        "neft cr", "rtgs cr", "upi cr", "fund transfer cr",
    ],
    "transfer_out": [
        "transfer to", "fund transfer", "outward", "imps dr",
        "neft dr", "rtgs dr", "paid to",
    ],
    "bounce_charge": [
        "bounce", "dishonour", "return charge", "ecs return",
        "nach return", "insufficient fund",
    ],
    "cash_withdrawal": [
        "atm", "cash withdrawal", "atm wdl", "cash wdl",
    ],
    "refund": [
        "refund", "reversal", "cashback", "returned",
    ],
}

CHANNEL_KEYWORDS: Dict[str, List[str]] = {
    "UPI": ["upi", "upi/", "upi-"],
    "NEFT": ["neft"],
    "RTGS": ["rtgs"],
    "IMPS": ["imps"],
    "card": ["card", "visa", "mastercard", "rupay", "pos", "ecom"],
    "cheque": ["cheque", "chq", "clg"],
    "cash": ["cash", "atm"],
    "standing_instruction": ["standing instruction", "si/", "nach", "ecs", "auto debit", "mandate"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Column detection
# ──────────────────────────────────────────────────────────────────────────────

def _find_column(columns: List[str], aliases: List[str]) -> Optional[str]:
    """Find a column name from a list of aliases (case-insensitive, strip whitespace)."""
    norm_cols = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in norm_cols:
            return norm_cols[alias]
    # Partial match fallback
    for alias in aliases:
        for norm, orig in norm_cols.items():
            if alias in norm:
                return orig
    return None


def _detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Auto-detect relevant columns in the uploaded CSV."""
    cols = list(df.columns)
    return {
        "date": _find_column(cols, DATE_ALIASES),
        "narration": _find_column(cols, NARRATION_ALIASES),
        "debit": _find_column(cols, DEBIT_ALIASES),
        "credit": _find_column(cols, CREDIT_ALIASES),
        "balance": _find_column(cols, BALANCE_ALIASES),
        "amount": _find_column(cols, AMOUNT_ALIASES),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Classification
# ──────────────────────────────────────────────────────────────────────────────

def _classify_transaction(narration: str, direction: str) -> str:
    """Classify a transaction by scanning narration for keywords."""
    if not narration or not isinstance(narration, str):
        return "other"
    text = narration.lower().strip()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return category

    return "other"


def _detect_channel(narration: str) -> str:
    """Detect payment channel from narration text."""
    if not narration or not isinstance(narration, str):
        return "other"
    text = narration.lower().strip()

    for channel, keywords in CHANNEL_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return channel

    return "other"


# ──────────────────────────────────────────────────────────────────────────────
# Date parsing
# ──────────────────────────────────────────────────────────────────────────────

DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y",
    "%d %B %Y", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
]


def _parse_dates(series: pd.Series) -> pd.Series:
    """Try multiple date formats to parse a date column."""
    # First try pandas auto-detection
    try:
        parsed = pd.to_datetime(series, dayfirst=True, format="mixed")
        if parsed.notna().sum() > len(series) * 0.8:
            return parsed
    except Exception:
        pass

    # Try explicit formats
    for fmt in DATE_FORMATS:
        try:
            parsed = pd.to_datetime(series, format=fmt)
            if parsed.notna().sum() > len(series) * 0.8:
                return parsed
        except Exception:
            continue

    # Final fallback
    return pd.to_datetime(series, errors="coerce", dayfirst=True)


# ──────────────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_bank_statement(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """
    Parse a raw bank statement DataFrame into the internal transaction format.

    Returns:
        (transactions_df, metadata)
        - transactions_df: DataFrame with columns matching internal format
          (customer_id, txn_date, amount, direction, channel, category,
           counterparty_tag, balance_after)
        - metadata: dict with parsing info (months_covered, total_txns,
          columns_detected, etc.)
    """
    if df.empty:
        raise ValueError("The uploaded file is empty.")

    # Step 1: Detect columns
    detected = _detect_columns(df)
    metadata = {"columns_detected": {k: v for k, v in detected.items() if v is not None}}

    if detected["date"] is None:
        raise ValueError(
            "Could not detect a date column. "
            "Please ensure your CSV has a column named 'Date', 'Txn Date', or 'Transaction Date'."
        )

    # Step 2: Parse dates
    df["_parsed_date"] = _parse_dates(df[detected["date"]])
    df = df.dropna(subset=["_parsed_date"]).copy()
    df = df.sort_values("_parsed_date").reset_index(drop=True)

    if len(df) < 5:
        raise ValueError("Too few valid transactions found after parsing dates.")

    # Step 3: Determine amounts and direction
    has_separate_cols = detected["debit"] is not None and detected["credit"] is not None
    has_single_amount = detected["amount"] is not None

    txns = []

    for _, row in df.iterrows():
        txn_date = row["_parsed_date"]
        narration = str(row.get(detected["narration"], "")) if detected["narration"] else ""

        debit_amt = 0.0
        credit_amt = 0.0

        if has_separate_cols:
            raw_debit = row.get(detected["debit"], 0)
            raw_credit = row.get(detected["credit"], 0)
            debit_amt = _parse_amount(raw_debit)
            credit_amt = _parse_amount(raw_credit)
        elif has_single_amount:
            raw_amt = row.get(detected["amount"], 0)
            amt = _parse_amount(raw_amt)
            # Try to infer direction from narration or sign
            if amt < 0:
                debit_amt = abs(amt)
            elif amt > 0:
                credit_amt = amt
            else:
                continue  # skip zero-amount rows

        if debit_amt == 0 and credit_amt == 0:
            continue

        direction = "credit" if credit_amt > debit_amt else "debit"
        amount = max(debit_amt, credit_amt)

        # Balance
        balance_after = 0.0
        if detected["balance"]:
            balance_after = _parse_amount(row.get(detected["balance"], 0))

        # Classify
        category = _classify_transaction(narration, direction)
        channel = _detect_channel(narration)

        txns.append({
            "customer_id": "STATEMENT_USER",
            "txn_date": txn_date,
            "amount": round(amount, 2),
            "direction": direction,
            "channel": channel,
            "category": category,
            "counterparty_tag": _extract_counterparty(narration),
            "balance_after": round(balance_after, 2),
        })

    if len(txns) < 5:
        raise ValueError("Too few valid transactions could be parsed from the statement.")

    txns_df = pd.DataFrame(txns)
    txns_df["txn_date"] = pd.to_datetime(txns_df["txn_date"])

    # Validate: minimum 2 months
    months_covered = txns_df["txn_date"].dt.to_period("M").nunique()
    if months_covered < 2:
        raise ValueError(
            f"Statement covers only {months_covered} month(s). "
            f"Minimum 2 months of data is required for accurate scoring."
        )

    metadata.update({
        "total_transactions": len(txns_df),
        "months_covered": int(months_covered),
        "date_range_start": txns_df["txn_date"].min().strftime("%Y-%m-%d"),
        "date_range_end": txns_df["txn_date"].max().strftime("%Y-%m-%d"),
        "credits_count": int((txns_df["direction"] == "credit").sum()),
        "debits_count": int((txns_df["direction"] == "debit").sum()),
        "categories_found": {k: int(v) for k, v in txns_df["category"].value_counts().to_dict().items()},
    })

    return txns_df, metadata


def _parse_amount(val) -> float:
    """Parse an amount value, handling commas, currency symbols, parentheses, blanks."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in ("-", "--", "—", ""):
        return 0.0
    # Remove currency symbols and commas
    s = re.sub(r"[₹$,\s]", "", s)
    # Handle parentheses as negative: (1234.56) → -1234.56
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_counterparty(narration: str) -> Optional[str]:
    """Extract a rough counterparty tag from narration."""
    if not narration or not isinstance(narration, str):
        return None
    text = narration.strip()
    # For UPI: extract the UPI ID or name after common patterns
    upi_match = re.search(r"(?:upi[/-])([^/\s]+)", text, re.IGNORECASE)
    if upi_match:
        return upi_match.group(1)[:30]
    # For NEFT/RTGS: extract name after common patterns
    neft_match = re.search(r"(?:neft|rtgs|imps)[/-]?\s*[^-/]*[-/]\s*(.+)", text, re.IGNORECASE)
    if neft_match:
        return neft_match.group(1).strip()[:30]
    # Fallback: first 30 chars
    return text[:30] if len(text) > 0 else None
