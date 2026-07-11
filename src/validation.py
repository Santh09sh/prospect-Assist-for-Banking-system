"""
validation.py — Backtest & lift chart to prove >30% conversion target
======================================================================
The single most important artifact in the entire build.

Computes:
  1. Baseline conversion rate (random sample)
  2. AI-prioritized conversion rate (top-ranked by combined score)
  3. Cumulative gains / lift chart
  4. Quintile comparison bar chart
"""

import os
import sys
from typing import Dict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def compute_backtest(leads_df: pd.DataFrame) -> dict:
    """
    Run the backtest on scored leads.

    Uses the 'converted' label (historical, never used as a feature).

    Returns dict with all validation metrics and chart data.
    """
    print("[TEST] Running backtest validation...")

    # Work only with eligible leads for the conversion analysis
    # (since non-eligible prospects would never be contacted)
    all_leads = leads_df.copy()
    eligible_leads = all_leads[all_leads["is_eligible"] == True].copy()

    if len(eligible_leads) == 0 or "converted" not in eligible_leads.columns:
        return {"error": "No eligible leads or no converted label"}

    eligible_leads = eligible_leads.sort_values("intent_score", ascending=False).reset_index(drop=True)

    # Overall baseline
    total_conversion = all_leads["converted"].mean()
    eligible_conversion = eligible_leads["converted"].mean()

    # ── Cumulative gains chart ──
    n = len(eligible_leads)
    gains_x = []  # % of prospects contacted
    gains_y = []  # % of total conversions captured
    total_conversions = eligible_leads["converted"].sum()

    cumulative_conversions = 0
    for i in range(n):
        if eligible_leads.iloc[i]["converted"]:
            cumulative_conversions += 1
        pct_contacted = (i + 1) / n * 100
        pct_captured = cumulative_conversions / total_conversions * 100 if total_conversions > 0 else 0
        # Sample every 1%
        if (i + 1) % max(1, n // 100) == 0 or i == n - 1:
            gains_x.append(round(pct_contacted, 1))
            gains_y.append(round(pct_captured, 1))

    # ── Quintile analysis ──
    quintile_size = n // 5
    quintile_results = []
    for q in range(5):
        start = q * quintile_size
        end = start + quintile_size if q < 4 else n
        quintile = eligible_leads.iloc[start:end]
        conv_rate = quintile["converted"].mean() * 100
        quintile_results.append({
            "quintile": q + 1,
            "label": f"Q{q+1} ({'Top' if q == 0 else 'Bottom' if q == 4 else f'{q+1}'})",
            "size": len(quintile),
            "conversions": int(quintile["converted"].sum()),
            "conversion_rate": round(conv_rate, 1),
        })

    # ── Decile analysis ──
    decile_size = n // 10
    decile_results = []
    for d in range(10):
        start = d * decile_size
        end = start + decile_size if d < 9 else n
        decile = eligible_leads.iloc[start:end]
        conv_rate = decile["converted"].mean() * 100
        decile_results.append({
            "decile": d + 1,
            "label": f"D{d+1}",
            "size": len(decile),
            "conversions": int(decile["converted"].sum()),
            "conversion_rate": round(conv_rate, 1),
        })

    # ── Top-N% analysis ──
    top_percentages = [5, 10, 15, 20, 25, 30, 50]
    top_n_results = []
    for pct in top_percentages:
        k = max(1, int(n * pct / 100))
        top_k = eligible_leads.iloc[:k]
        conv_rate = top_k["converted"].mean() * 100
        top_n_results.append({
            "pct": pct,
            "label": f"Top {pct}%",
            "size": len(top_k),
            "conversions": int(top_k["converted"].sum()),
            "conversion_rate": round(conv_rate, 1),
        })

    # ── Tier-level analysis ──
    tier_results = {}
    for tier in ["hot", "warm", "cold"]:
        tier_leads = eligible_leads[eligible_leads["tier"] == tier]
        if len(tier_leads) > 0:
            tier_results[tier] = {
                "count": len(tier_leads),
                "conversions": int(tier_leads["converted"].sum()),
                "conversion_rate": round(tier_leads["converted"].mean() * 100, 1),
            }

    # ── Lift calculation ──
    baseline_rate = total_conversion * 100
    top_quintile_rate = quintile_results[0]["conversion_rate"]
    top_20_rate = next((r["conversion_rate"] for r in top_n_results if r["pct"] == 20), 0)
    lift = top_quintile_rate / baseline_rate if baseline_rate > 0 else 0

    results = {
        "baseline_conversion_rate": round(baseline_rate, 1),
        "eligible_conversion_rate": round(eligible_conversion * 100, 1),
        "top_quintile_conversion_rate": top_quintile_rate,
        "top_20_conversion_rate": top_20_rate,
        "lift_over_baseline": round(lift, 2),
        "clears_30_pct": top_quintile_rate > 30,
        "total_prospects": len(all_leads),
        "eligible_prospects": len(eligible_leads),
        "total_conversions": int(total_conversions),
        "gains_chart": {"x": gains_x, "y": gains_y},
        "quintile_results": quintile_results,
        "decile_results": decile_results,
        "top_n_results": top_n_results,
        "tier_results": tier_results,
    }

    # Print summary
    print(f"\n{'='*60}")
    print(f"  BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"  Total prospects:              {len(all_leads)}")
    print(f"  Eligible prospects:           {len(eligible_leads)} ({len(eligible_leads)/len(all_leads):.1%})")
    print(f"  Baseline conversion:          {baseline_rate:.1f}%")
    print(f"  Eligible pool conversion:     {eligible_conversion*100:.1f}%")
    print(f"  Top-20% AI-prioritized:       {top_20_rate:.1f}%")
    print(f"  Top quintile conversion:      {top_quintile_rate:.1f}%")
    print(f"  Lift over baseline:           {lift:.2f}×")
    print(f"  Clears 30% target:            {'[OK] YES' if top_quintile_rate > 30 else '[FAIL] NO'}")
    print(f"{'='*60}")

    if tier_results:
        print(f"\n  Tier breakdown:")
        for tier, tr in tier_results.items():
            print(f"    {tier.upper():15s} — {tr['count']:4d} leads, {tr['conversion_rate']:.1f}% conversion")

    return results


def save_validation_results(results: dict, path: str = None):
    """Save validation results to JSON."""
    import json

    if path is None:
        path = os.path.join(config.DATA_DIR, "validation_results.json")

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    with open(path, "w") as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)

    print(f"\n[OK] Validation results saved -> {path}")


if __name__ == "__main__":
    leads = pd.read_csv(os.path.join(config.DATA_DIR, "leads.csv"))
    results = compute_backtest(leads)
    save_validation_results(results)
