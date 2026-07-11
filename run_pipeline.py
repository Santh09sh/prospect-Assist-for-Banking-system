"""
run_pipeline.py — End-to-end pipeline: generate → engineer → train → score → validate
========================================================================================
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src.data_generator import generate_all, save_data
from src.feature_engineering import engineer_features, save_features
from src.eligibility import calculate_all_products
from src.intent_model import IntentModel
from src.lead_scorer import score_all_prospects, get_funnel_stats
from src.validation import compute_backtest, save_validation_results


def run_pipeline():
    """Run the full pipeline."""
    start = time.time()

    print("=" * 70)
    print("  PROSPECT ASSIST AI — Full Pipeline")
    print("=" * 70)

    # ── Step 1: Generate synthetic data ──
    print("\n[DATA] Step 1/5: Generating synthetic data...")
    transactions_df, prospects_df = generate_all()
    save_data(transactions_df, prospects_df)

    # ── Step 2: Feature engineering ──
    print("\n[FE] Step 2/5: Engineering features...")
    features_df = engineer_features(transactions_df, prospects_df)
    save_features(features_df)

    # ── Step 3: Train intent model ──
    print("\n[ML] Step 3/5: Training intent model...")
    intent_model = IntentModel()
    metrics = intent_model.train(features_df)
    intent_model.save()

    # ── Step 4: Score all prospects ──
    print("\n[SCORE] Step 4/5: Scoring all prospects...")
    intent_scores = intent_model.predict_scores_batch(features_df)
    shap_explanations = intent_model.explain_batch(features_df)
    leads_df = score_all_prospects(features_df, intent_scores, shap_explanations)

    # Save leads
    # Need to handle complex columns for CSV
    leads_save = leads_df.copy()
    leads_save["shap_factors"] = leads_save["shap_factors"].apply(json.dumps)
    leads_save["eligibility_details"] = leads_save["eligibility_details"].apply(json.dumps)
    leads_save.to_csv(os.path.join(config.DATA_DIR, "leads.csv"), index=False)
    print(f"[OK] Saved leads -> {os.path.join(config.DATA_DIR, 'leads.csv')}")

    # ── Step 5: Validation ──
    print("\n[TEST] Step 5/5: Running backtest validation...")
    validation_results = compute_backtest(leads_df)
    save_validation_results(validation_results)

    # Save funnel stats
    funnel = get_funnel_stats(leads_df)
    with open(os.path.join(config.DATA_DIR, "funnel_stats.json"), "w") as f:
        json.dump(funnel, f, indent=2)

    # Save model metrics separately for the dashboard
    with open(os.path.join(config.DATA_DIR, "model_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    elapsed = time.time() - start
    print(f"\n{'=' * 70}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    print(f"{'=' * 70}")

    return {
        "leads_df": leads_df,
        "validation_results": validation_results,
        "model_metrics": metrics,
        "funnel_stats": funnel,
    }


if __name__ == "__main__":
    run_pipeline()
