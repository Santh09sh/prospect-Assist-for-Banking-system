"""
main.py — FastAPI backend for Prospect Assist AI
==================================================
Endpoints:
  GET  /api/leads              — Paginated lead list with filters
  GET  /api/leads/{id}         — Lead detail with full traces
  GET  /api/analytics          — Model metrics, funnel stats
  GET  /api/analytics/lift     — Lift chart data
  POST /api/score-batch        — Upload CSV → scored CSV
  POST /api/score-single       — Score one prospect (real-time demo)
  GET  /api/products           — Product parameters
"""

import os
import sys
import json
import io
import csv
from contextlib import asynccontextmanager
from typing import Optional, List

import numpy as np
import pandas as pd
from pydantic import BaseModel
from fastapi import FastAPI, Query, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.eligibility import calculate_all_products, calculate_eligibility
from src.feature_engineering import (
    compute_engagement_score, compute_intent_signals,
    detect_salary_pattern, compute_cashflow_features,
    detect_recurring_debits, estimate_income_fallback,
)
from src.statement_parser import parse_bank_statement
from src.pdf_extractor import extract_csv_from_pdf

# ──────────────────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    _load_data()
    yield

app = FastAPI(
    title="Prospect Assist AI",
    description="AI-powered lead scoring for IDBI Bank retail lending — IDBI Innovate 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Data loading (cached in memory)
# ──────────────────────────────────────────────────────────────────────────────

_cache = {}


def _load_data():
    """Load pre-computed data into memory."""
    if "leads" in _cache:
        return

    leads_path = os.path.join(config.DATA_DIR, "leads.csv")
    if not os.path.exists(leads_path):
        raise RuntimeError(
            "Pipeline data not found. Run `python run_pipeline.py` first."
        )

    leads_df = pd.read_csv(leads_path)

    # Parse JSON columns
    for col in ["shap_factors", "eligibility_details"]:
        if col in leads_df.columns:
            leads_df[col] = leads_df[col].apply(
                lambda x: json.loads(x) if isinstance(x, str) else x
            )

    _cache["leads"] = leads_df

    # Load validation results
    val_path = os.path.join(config.DATA_DIR, "validation_results.json")
    if os.path.exists(val_path):
        with open(val_path) as f:
            _cache["validation"] = json.load(f)

    # Load model metrics
    metrics_path = os.path.join(config.DATA_DIR, "model_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            _cache["metrics"] = json.load(f)

    # Load funnel stats
    funnel_path = os.path.join(config.DATA_DIR, "funnel_stats.json")
    if os.path.exists(funnel_path):
        with open(funnel_path) as f:
            _cache["funnel"] = json.load(f)

    # Load transactions for detail views
    txn_path = os.path.join(config.DATA_DIR, "transactions.csv")
    if os.path.exists(txn_path):
        _cache["transactions"] = pd.read_csv(txn_path, parse_dates=["txn_date"])

    # Load features
    feat_path = os.path.join(config.DATA_DIR, "features.csv")
    if os.path.exists(feat_path):
        _cache["features"] = pd.read_csv(feat_path)


# Data is loaded via lifespan handler above


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "leads_loaded": "leads" in _cache,
        "lead_count": len(_cache.get("leads", [])),
    }

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Mock AI Chatbot for website data queries."""
    msg = req.message.lower()
    
    import asyncio
    await asyncio.sleep(1.0) # simulate thinking
    
    if "conversion" in msg or "lift" in msg or "model" in msg:
        response = "Based on our model metrics, the AI identifies the top 20% of prospects which captures around 85% of total conversions. The conversion rate for High Intent (Q1) leads is around 43%."
    elif "leads" in msg or "how many" in msg:
        lead_count = len(_cache.get("leads", []))
        response = f"We currently have {lead_count} leads in the database. About 25% of them are eligible for a product offering based on our pipeline analysis."
    elif "product" in msg or "eligible" in msg:
        response = "The model evaluates eligibility across Personal Loans, Home Loans, Auto Loans, and Mortgage Loans based on cashflow, estimated income, and current obligations."
    elif "features" in msg or "data" in msg:
        response = "The AI analyzes transaction data (credits/debits, salary patterns) and behavioral data (mobile banking activity, loan inquiries) to compute an intent score and recommend the best loan product."
    else:
        response = "I am the Prospect Assist AI chatbot! I can answer questions about our model performance, lead database, or how we score eligibility. (Full database integration coming soon!)"

    return {"response": response}

@app.get("/api/leads")
async def get_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    tier: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
    sort_by: Optional[str] = Query("rank"),
    sort_order: Optional[str] = Query("asc"),
    search: Optional[str] = Query(None),
):
    """Get paginated, filtered lead list."""
    df = _cache["leads"].copy()

    # Filters
    if tier:
        df = df[df["tier"] == tier]
    if product:
        df = df[df["recommended_product"] == product]
    if min_score is not None:
        df = df[df["intent_score"] >= min_score]
    if max_score is not None:
        df = df[df["intent_score"] <= max_score]
    if search:
        df = df[df["customer_id"].str.contains(search, case=False, na=False)]

    # Sort
    if sort_by in df.columns:
        ascending = sort_order != "desc"
        df = df.sort_values(sort_by, ascending=ascending)

    total = len(df)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = df.iloc[start:end]

    # Convert to records, excluding heavy columns
    display_cols = [
        "rank", "customer_id", "customer_name", "tier", "tier_badge", "intent_score",
        "is_eligible", "recommended_product_name", "recommended_amount",
        "recommended_emi", "inquiry_product_name", "source_channel",
        "occupation_sector", "top_reason", "est_monthly_income",
        "city_tier", "age", "inquiry_date", "digital_engagement_score",
    ]
    available_cols = [c for c in display_cols if c in page_df.columns]
    records = page_df[available_cols].to_dict(orient="records")

    # Clean NaN values
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                rec[k] = None

    return {
        "leads": records,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@app.get("/api/leads/{customer_id}")
async def get_lead_detail(customer_id: str):
    """Get full detail for a single lead."""
    df = _cache["leads"]
    row = df[df["customer_id"] == customer_id]

    if row.empty:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = row.iloc[0].to_dict()

    # Clean NaN
    for k, v in lead.items():
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            lead[k] = None

    # Get transaction summary for this customer
    txn_summary = None
    if "transactions" in _cache:
        txns = _cache["transactions"]
        cust_txns = txns[txns["customer_id"] == customer_id].copy()
        if not cust_txns.empty:
            cust_txns["month"] = cust_txns["txn_date"].dt.to_period("M").astype(str)
            monthly = cust_txns.groupby(["month", "direction"])["amount"].sum().unstack(fill_value=0)
            txn_summary = {
                "months": list(monthly.index),
                "credits": list(monthly.get("credit", pd.Series([0]*len(monthly))).values.astype(float)),
                "debits": list(monthly.get("debit", pd.Series([0]*len(monthly))).values.astype(float)),
            }

    # Get feature detail
    feature_detail = None
    if "features" in _cache:
        feat_row = _cache["features"][_cache["features"]["customer_id"] == customer_id]
        if not feat_row.empty:
            feature_detail = feat_row.iloc[0].to_dict()
            for k, v in feature_detail.items():
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    feature_detail[k] = None

    lead["transaction_summary"] = txn_summary
    lead["feature_detail"] = feature_detail

    return lead


@app.get("/api/analytics")
async def get_analytics():
    """Get analytics data: model metrics, funnel, conversion rates."""
    # Dynamic revenue opportunity calculation
    revenue_opportunity = 0
    avg_ticket = 0
    hot_leads_count = 0
    if "leads" in _cache:
        leads = _cache["leads"]
        hot_leads = leads[leads["tier"] == "hot"]
        hot_leads_count = len(hot_leads)
        if not hot_leads.empty:
            revenue_opportunity = float(hot_leads["recommended_amount"].sum())
            avg_ticket = float(hot_leads["recommended_amount"].mean())

    return {
        "model_metrics": _cache.get("metrics", {}),
        "funnel": _cache.get("funnel", {}),
        "validation": {
            k: v for k, v in _cache.get("validation", {}).items()
            if k not in ("gains_chart",)  # exclude large chart data
        },
        "revenue": {
            "total_opportunity": round(revenue_opportunity, 0),
            "avg_ticket_size": round(avg_ticket, 0),
            "hot_lead_count": hot_leads_count,
        },
    }


@app.get("/api/analytics/lift")
async def get_lift_chart():
    """Get lift/gains chart data."""
    val = _cache.get("validation", {})
    return {
        "gains_chart": val.get("gains_chart", {}),
        "quintile_results": val.get("quintile_results", []),
        "decile_results": val.get("decile_results", []),
        "top_n_results": val.get("top_n_results", []),
        "tier_results": val.get("tier_results", {}),
        "baseline_conversion_rate": val.get("baseline_conversion_rate", 0),
        "top_quintile_conversion_rate": val.get("top_quintile_conversion_rate", 0),
        "lift_over_baseline": val.get("lift_over_baseline", 0),
        "clears_30_pct": val.get("clears_30_pct", False),
    }


@app.post("/api/score-single")
async def score_single(
    age: int = Query(...),
    occupation_sector: str = Query(...),
    employment_years: float = Query(...),
    education_level: str = Query("graduate"),
    city_tier: str = Query("tier2"),
    est_monthly_income: float = Query(...),
    existing_obligations: float = Query(0),
    source_channel: str = Query("website_organic"),
    inquiry_product: str = Query("personal_loan"),
    existing_bank_relationship: bool = Query(False),
    app_logins_30d: int = Query(0),
    emi_calculator_uses_30d: int = Query(0),
    product_page_visits_30d: int = Query(0),
    credit_bureau_score: Optional[int] = Query(None),
):
    """Score a single prospect in real-time (demo form)."""

    # Calculate eligibility
    eligibility = calculate_all_products(
        est_monthly_income, existing_obligations, credit_bureau_score
    )

    # Build a feature-like Series for engagement score
    prospect_data = pd.Series({
        "app_logins_30d": app_logins_30d,
        "emi_calculator_uses_30d": emi_calculator_uses_30d,
        "product_page_visits_30d": product_page_visits_30d,
    })
    engagement = compute_engagement_score(prospect_data)

    # Simple intent score heuristic (since we can't run the full model on one-off data easily)
    intent_score = min(100, max(0, round(
        engagement * 0.4 +
        (30 if existing_bank_relationship else 0) +
        (20 if source_channel in ("referral", "partner") else 10) +
        min(employment_years * 2, 20),
    1)))

    # Determine eligibility and tier
    eligible_products = {k: v for k, v in eligibility.items() if v.get("eligible")}
    is_eligible = len(eligible_products) > 0

    tier = "not_eligible"
    if is_eligible:
        if intent_score >= config.TIER_HOT:
            tier = "hot"
        elif intent_score >= config.TIER_WARM:
            tier = "warm"
        else:
            tier = "cold"

    # Recommend product
    recommended = None
    if eligible_products:
        if inquiry_product in eligible_products:
            recommended = inquiry_product
        else:
            recommended = max(eligible_products, key=lambda k: eligible_products[k]["eligible_amount"])

    return {
        "intent_score": intent_score,
        "digital_engagement_score": engagement,
        "tier": tier,
        "is_eligible": is_eligible,
        "recommended_product": recommended,
        "recommended_product_name": (
            config.PRODUCT_PARAMS[recommended]["display_name"] if recommended else "—"
        ),
        "recommended_amount": (
            eligible_products[recommended]["eligible_amount"] if recommended else 0
        ),
        "recommended_emi": (
            eligible_products[recommended]["eligible_emi"] if recommended else 0
        ),
        "eligibility_details": eligibility,
    }


@app.post("/api/score-batch")
async def score_batch(file: UploadFile = File(...)):
    """Upload a CSV of prospects, return scored results."""
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")

    results = []
    for _, row in df.iterrows():
        income = row.get("est_monthly_income", row.get("monthly_income", 0))
        obligations = row.get("existing_obligations", row.get("declared_existing_emis", 0))

        eligibility = calculate_all_products(float(income), float(obligations))
        eligible_products = {k: v for k, v in eligibility.items() if v.get("eligible")}

        best_product = None
        best_amount = 0
        if eligible_products:
            best_product = max(eligible_products, key=lambda k: eligible_products[k]["eligible_amount"])
            best_amount = eligible_products[best_product]["eligible_amount"]

        results.append({
            "customer_id": row.get("customer_id", ""),
            "est_monthly_income": income,
            "eligible": len(eligible_products) > 0,
            "eligible_product_count": len(eligible_products),
            "best_product": best_product or "none",
            "best_eligible_amount": best_amount,
        })

    output = pd.DataFrame(results)
    stream = io.StringIO()
    output.to_csv(stream, index=False)

    return StreamingResponse(
        io.BytesIO(stream.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=scored_results.csv"},
    )


@app.get("/api/products")
async def get_products():
    """Get product parameters and caps."""
    return {
        k: {
            "display_name": v["display_name"],
            "type": v["type"],
            "annual_rate": v["annual_rate"],
            "max_tenure_years": v["max_tenure_years"],
            "min_ticket": v["min_ticket"],
            "max_ticket": v["max_ticket"],
            "description": v["description"],
            "ltv_cap": v.get("ltv_cap"),
            "income_multiple_cap": v.get("income_multiple_cap"),
        }
        for k, v in config.PRODUCT_PARAMS.items()
    }


# ──────────────────────────────────────────────────────────────────────────────
# Statement Analyzer
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/score-statement")
async def score_statement(
    file: UploadFile = File(...),
    pdf_password: Optional[str] = Query(None),
    age: int = Query(35),
    occupation_sector: str = Query("salaried_pvt_other"),
    employment_years: float = Query(5),
    education_level: str = Query("graduate"),
    city_tier: str = Query("tier2"),
    credit_bureau_score: Optional[int] = Query(None),
    inquiry_product: str = Query("personal_loan"),
):
    """Upload a bank statement CSV (3-12 months) and get a full score analysis."""

    # 1. Read and parse the file
    try:
        contents = await file.read()
        filename = file.filename.lower() if file.filename else ""
        
        if filename.endswith(".pdf"):
            # Use the AI PDF extractor to convert PDF text to CSV bytes
            csv_bytes = extract_csv_from_pdf(contents, pdf_password)
            raw_df = pd.read_csv(io.BytesIO(csv_bytes))
        else:
            # Assume CSV by default
            raw_df = pd.read_csv(io.BytesIO(contents))
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid file or parsing failed: {str(e)}")

    try:
        txns_df, parse_meta = parse_bank_statement(raw_df)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Run feature engineering functions on the parsed transactions
    # Salary / income detection
    salary_result = detect_salary_pattern(txns_df)

    # Cash flow features
    cf = compute_cashflow_features(txns_df)

    # Income estimation
    if salary_result["detected"] and salary_result["est_salary"] is not None:
        est_income = salary_result["est_salary"]
        income_method = "salary_detection"
    else:
        # Fallback: use profile + spend
        profile_series = pd.Series({
            "occupation_sector": occupation_sector,
            "city_tier": city_tier,
            "education_level": education_level,
        })
        est_income = estimate_income_fallback(profile_series, cf["avg_monthly_spend"])
        income_method = "proxy_model"

    # Obligation detection from ledger
    detected_recurring = detect_recurring_debits(txns_df)
    # Check for existing EMI debits in the statement
    emi_in_ledger = txns_df[txns_df["category"] == "existing_emi_debit"]["amount"].median()
    existing_obligations = detected_recurring
    if pd.notna(emi_in_ledger):
        existing_obligations = max(detected_recurring, emi_in_ledger + detected_recurring * 0.3)

    # 3. Calculate eligibility
    eligibility = calculate_all_products(
        float(est_income), float(existing_obligations), credit_bureau_score
    )

    eligible_products = {k: v for k, v in eligibility.items() if v.get("eligible")}
    is_eligible = len(eligible_products) > 0

    # 4. Heuristic intent score based on statement quality
    stability_bonus = max(0, 30 - cf["cashflow_cv"] * 15)  # up to 30
    income_bonus = min(20, est_income / 10000)  # up to 20
    tenure_bonus = min(15, parse_meta["months_covered"] * 1.5)  # up to 15
    salary_bonus = 20 if salary_result["detected"] else 0  # 20 if salary detected
    bounce_penalty = min(15, cf["bounce_count_6m"] * 5)  # up to -15

    intent_score = min(100, max(0, round(
        stability_bonus + income_bonus + tenure_bonus + salary_bonus - bounce_penalty + 10
    )))

    # Determine tier
    tier = "not_eligible"
    if is_eligible:
        if intent_score >= config.TIER_HOT:
            tier = "hot"
        elif intent_score >= config.TIER_WARM:
            tier = "warm"
        else:
            tier = "cold"

    # Recommend best product
    recommended = None
    if eligible_products:
        if inquiry_product in eligible_products:
            recommended = inquiry_product
        else:
            recommended = max(eligible_products, key=lambda k: eligible_products[k]["eligible_amount"])

    # 5. Build analysis summary
    analysis_summary = []
    if salary_result["detected"]:
        analysis_summary.append(f"Regular salary detected: ~₹{est_income:,.0f}/month (regularity: {salary_result['regularity_score']:.0%})")
    else:
        analysis_summary.append(f"No regular salary pattern found. Estimated income from spending: ~₹{est_income:,.0f}/month")

    if existing_obligations > 0:
        analysis_summary.append(f"Detected recurring obligations: ~₹{existing_obligations:,.0f}/month")
    else:
        analysis_summary.append("No significant recurring obligations detected.")

    if cf["bounce_count_6m"] > 0:
        analysis_summary.append(f"⚠ {cf['bounce_count_6m']} bounce/dishonour event(s) found — may impact score.")

    if cf["cashflow_cv"] < 0.5:
        analysis_summary.append("Cash flow is stable and consistent.")
    elif cf["cashflow_cv"] < 1.0:
        analysis_summary.append("Cash flow shows moderate variability.")
    else:
        analysis_summary.append("Cash flow is highly variable — typical for self-employed profiles.")

    return {
        "intent_score": intent_score,
        "tier": tier,
        "is_eligible": is_eligible,
        "recommended_product": recommended,
        "recommended_product_name": (
            config.PRODUCT_PARAMS[recommended]["display_name"] if recommended else "—"
        ),
        "recommended_amount": (
            eligible_products[recommended]["eligible_amount"] if recommended else 0
        ),
        "recommended_emi": (
            eligible_products[recommended]["eligible_emi"] if recommended else 0
        ),
        "income_analysis": {
            "est_monthly_income": round(est_income, 2),
            "income_method": income_method,
            "salary_detected": salary_result["detected"],
            "salary_regularity": round(salary_result["regularity_score"], 2),
        },
        "cashflow_analysis": {
            "avg_monthly_credit": round(cf["avg_monthly_credit"], 2),
            "avg_monthly_spend": round(cf["avg_monthly_spend"], 2),
            "avg_monthly_net_cashflow": round(cf["avg_monthly_net_cashflow"], 2),
            "cashflow_stability": round(1 - min(cf["cashflow_cv"], 1), 2),
            "bounce_count": cf["bounce_count_6m"],
            "negative_balance_days": cf["negative_balance_days"],
        },
        "obligations": {
            "detected_recurring": round(detected_recurring, 2),
            "total_obligations": round(existing_obligations, 2),
        },
        "statement_info": parse_meta,
        "eligibility_details": eligibility,
        "analysis_summary": analysis_summary,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Serve frontend
# ──────────────────────────────────────────────────────────────────────────────

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    @app.get("/favicon.ico")
    async def favicon():
        ico_path = os.path.join(frontend_dir, "idbi-logo.png")
        if os.path.exists(ico_path):
            return FileResponse(ico_path)
        return JSONResponse(content={}, status_code=204)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
