# Prospect Assist AI

> **IDBI Innovate 2026 · Problem Statement PS2**
> AI-powered lead scoring for retail lending — identifying eligible, genuinely interested loan prospects

---

## Overview

Prospect Assist AI uses **transaction-level banking data** and **behavioral signals** to identify high-quality loan prospects for IDBI Bank. It produces two separately-explainable scores:

1. **Eligibility Score** — A transparent, rule-based calculation of quantifiable repayment capacity (eligible EMI and loan amount per product)
2. **Intent Score** — An ML-driven probability (XGBoost) of genuine purchase interest, with per-prediction explanations

The system achieves **>30% conversion rate** in the AI-prioritized cohort (vs ~10% baseline), demonstrated through a rigorous backtest on held-out data.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Prospect Assist AI                          │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Synthetic│ Feature  │Eligibility│ Intent  │  Lead    │Validation│
│   Data   │Engineering│Calculator│  Model  │ Scorer   │ Backtest │
│Generator │ Pipeline │(Rule-based)│(XGBoost)│(Combine) │(Lift/30%)│
├──────────┴──────────┴──────────┴──────────┴──────────┴─────────┤
│                     FastAPI Backend                            │
├────────────────────────────────────────────────────────────────┤
│              Dashboard (HTML/CSS/JS + Plotly)                  │
└────────────────────────────────────────────────────────────────┘
```

## Key Features

### Data Layer
- **Transaction ledger**: 6–12 months of synthetic transactions per prospect with realistic patterns:
  - Salaried: near-monthly salary credits (±5% amount, ±2 days)
  - Self-employed: irregular clustered credits, higher variance
  - Risk signals: bounce charges, negative balance events
  - Recurring debits: EMIs, rent, utilities

### Scoring
- **Eligibility**: FOIR-based calculation with full arithmetic trace
  - Per-product caps (Personal Loan, Auto Loan, Home Loan, Mortgage/LAP)
  - Home Loan ≠ Mortgage Loan — distinct LTV caps (80% vs 60%) and tenures
- **Intent**: XGBoost classifier trained on behavioral features
  - Percentile-based 0–100 scoring for meaningful tier distribution
  - Feature importance-based explanations (SHAP fallback)

### Validation
- **Backtest**: Cumulative gains/lift chart proving >30% conversion in top quintile
- **Model metrics**: AUC-ROC, Precision, Recall, F1

### Dashboard
- Lead list with sorting, filtering, pagination
- Lead detail with transaction charts, eligibility trace, intent factors
- Analytics with lift chart, conversion bars, funnel
- Batch CSV upload → scored CSV download
- Real-time single-prospect scoring form

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run the full pipeline (generates data, trains model, runs backtest)
python run_pipeline.py

# Start the server
python -m api.main
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

### API Documentation
FastAPI auto-generates Swagger docs at [http://localhost:8000/docs](http://localhost:8000/docs)

## Project Structure

```
IDBI hackathon/
├── config.py                  # All demo assumptions (FOIR caps, product params)
├── run_pipeline.py            # End-to-end pipeline runner
├── requirements.txt
├── data/                      # Generated CSVs (not committed)
│   ├── transactions.csv       # ~290K transaction records
│   ├── prospects.csv          # 2,000 prospect profiles
│   ├── features.csv           # Engineered features
│   ├── leads.csv              # Scored and ranked leads
│   └── validation_results.json
├── src/
│   ├── data_generator.py      # Synthetic data generation
│   ├── feature_engineering.py # Feature derivation from ledger
│   ├── eligibility.py         # FOIR-based eligibility calculator
│   ├── intent_model.py        # XGBoost + explanations
│   ├── lead_scorer.py         # Score combination + tiering
│   └── validation.py          # Backtest & lift chart
├── api/
│   └── main.py                # FastAPI backend
├── frontend/
│   ├── index.html             # Dashboard SPA
│   ├── style.css              # Dark-theme premium CSS
│   └── app.js                 # Dashboard logic + Plotly charts
├── models/
│   ├── intent_xgb.json        # Saved XGBoost model
│   └── intent_metadata.json   # Model metadata
└── README.md
```

## Demo Assumptions

> **IMPORTANT**: All financial parameters are demo assumptions for the hackathon prototype. They do NOT represent actual IDBI Bank policy.

| Parameter | Value | Notes |
|-----------|-------|-------|
| FOIR cap (income < ₹25K) | 40% | Fixed obligation to income ratio |
| FOIR cap (₹25K–₹75K) | 50% | |
| FOIR cap (> ₹75K) | 55% | |
| Personal Loan rate | 11.75% p.a. | Unsecured, ≤5yr tenure |
| Auto Loan rate | 8.90% p.a. | 85% LTV, ≤7yr |
| Home Loan rate | 8.65% p.a. | 80% LTV on purchase, ≤30yr |
| Mortgage/LAP rate | 9.50% p.a. | 60% LTV on pledged property, ≤15yr |
| Demo vehicle price | ₹8,00,000 | For Auto Loan cap calculation |
| Demo property price (Home) | ₹50,00,000 | For Home Loan cap |
| Demo property price (LAP) | ₹40,00,000 | For Mortgage cap |

## Swapping in IDBI's Real Sandbox Data

If shortlisted, replace the synthetic data with IDBI's real sandbox datasets:

1. **Transaction data**: Map IDBI's transaction/UPI columns to our schema (see `data/transactions.csv` header). Key fields: `customer_id`, `txn_date`, `amount`, `direction`, `channel`, `category`.

2. **Prospect profiles**: Map to `data/prospects.csv` schema. The `converted` field becomes your historical conversion labels.

3. **Re-run the pipeline**:
   ```bash
   # Place your mapped CSVs in data/
   # Skip data generation, run from feature engineering:
   python -c "
   from src.feature_engineering import engineer_features, save_features
   from src.intent_model import IntentModel
   from src.lead_scorer import score_all_prospects
   from src.validation import compute_backtest, save_validation_results
   import pandas as pd
   txns = pd.read_csv('data/transactions.csv', parse_dates=['txn_date'])
   prospects = pd.read_csv('data/prospects.csv')
   features = engineer_features(txns, prospects)
   save_features(features)
   # ... then train, score, validate
   "
   ```

4. **Adjust config.py**: Update FOIR caps, product rates, and asset values to match IDBI's actual parameters.

## Future Work (Out of Scope for This Build)

- What-If simulator (interactive parameter adjustment)
- Lead-decay / follow-up-timing alerts
- A/B test simulator
- Public-facing REST API beyond FastAPI auto-docs

## Tech Stack

- **Python 3.11**: pandas, numpy, scikit-learn, xgboost, shap, Faker
- **FastAPI**: Backend with auto-generated Swagger docs
- **HTML/CSS/JS**: Dashboard with Plotly.js charts
- **Design**: Dark theme, glassmorphism, IDBI Bank blue (#00539F)
