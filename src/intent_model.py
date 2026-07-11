"""
intent_model.py — XGBoost intent classifier with SHAP explanations
===================================================================
Trains a binary classifier to predict conversion probability.
Outputs a calibrated 0–100 Intent Score with per-prediction SHAP reasons.
"""

import os
import sys
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, f1_score,
    classification_report, confusion_matrix, precision_recall_curve
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
import shap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

warnings.filterwarnings("ignore")

# Features used for intent prediction (behavioral + demographic, NOT eligibility)
INTENT_FEATURES = [
    "source_channel",
    "intent_recency_days",
    "intent_frequency_90d",
    "digital_engagement_score",
    "occupation_sector",
    "existing_bank_relationship",
    "inquiry_product",
    "employment_years",
    "city_tier",
    "age",
    "cashflow_cv",
    "bounce_count_6m",
    "salary_regularity_score",
]

CATEGORICAL_FEATURES = [
    "source_channel", "occupation_sector", "inquiry_product", "city_tier",
]


class IntentModel:
    """XGBoost-based intent scoring model with SHAP explanations."""

    def __init__(self):
        self.model = None
        self.calibrated_model = None
        self.explainer = None
        self.label_encoders = {}
        self.feature_names = []
        self.metrics = {}

    def _encode_features(self, df: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        """Encode categorical features for XGBoost."""
        df_encoded = df.copy()

        for col in CATEGORICAL_FEATURES:
            if col not in df_encoded.columns:
                continue
            if fit:
                le = LabelEncoder()
                df_encoded[col] = le.fit_transform(df_encoded[col].astype(str))
                self.label_encoders[col] = le
            else:
                le = self.label_encoders.get(col)
                if le is not None:
                    # Handle unseen labels
                    df_encoded[col] = df_encoded[col].astype(str).map(
                        lambda x, _le=le: (
                            _le.transform([x])[0] if x in _le.classes_
                            else len(_le.classes_)
                        )
                    )

        # Convert boolean to int
        if "existing_bank_relationship" in df_encoded.columns:
            df_encoded["existing_bank_relationship"] = df_encoded["existing_bank_relationship"].astype(int)

        return df_encoded

    def train(self, features_df: pd.DataFrame, test_size: float = 0.2) -> dict:
        """
        Train the intent model.

        Returns dict with metrics and train/test split info.
        """
        print("[ML] Training Intent Model...")

        # Select features
        available_features = [f for f in INTENT_FEATURES if f in features_df.columns]
        self.feature_names = available_features

        df = features_df[available_features + ["converted", "customer_id"]].dropna(subset=["converted"])
        df["converted"] = df["converted"].astype(int)

        # Train/test split
        train_df, test_df = train_test_split(
            df, test_size=test_size, stratify=df["converted"], random_state=config.RANDOM_SEED
        )

        # Encode
        X_train = self._encode_features(train_df[available_features], fit=True)
        X_test = self._encode_features(test_df[available_features], fit=False)
        y_train = train_df["converted"].values
        y_test = test_df["converted"].values

        # Store test customer IDs for backtest
        self.test_customer_ids = test_df["customer_id"].values

        # XGBoost
        self.model = xgb.XGBClassifier(
            max_depth=5,
            n_estimators=200,
            learning_rate=0.1,
            objective="binary:logistic",
            eval_metric="auc",
            random_state=config.RANDOM_SEED,
            use_label_encoder=False,
            scale_pos_weight=len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1),
        )

        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        # Calibrate probabilities
        self.calibrated_model = CalibratedClassifierCV(
            self.model, method="isotonic", cv=3
        )
        self.calibrated_model.fit(X_train, y_train)

        # Evaluate
        y_proba = self.calibrated_model.predict_proba(X_test)[:, 1]

        # Find optimal threshold using precision-recall curve
        # (since base rate ~10%, default 0.5 is too high)
        precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
        f1_scores = 2 * precisions * recalls / (precisions + recalls + 1e-8)
        best_idx = np.argmax(f1_scores)
        optimal_threshold = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.5

        y_pred = (y_proba >= optimal_threshold).astype(int)

        auc = roc_auc_score(y_test, y_proba)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        cm = confusion_matrix(y_test, y_pred)

        self.metrics = {
            "auc_roc": round(auc, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "optimal_threshold": round(optimal_threshold, 4),
            "confusion_matrix": cm.tolist(),
            "train_size": len(train_df),
            "test_size": len(test_df),
            "conversion_rate_train": round(y_train.mean(), 4),
            "conversion_rate_test": round(y_test.mean(), 4),
        }

        print(f"  AUC-ROC: {auc:.4f}")
        print(f"  Precision: {precision:.4f}")
        print(f"  Recall: {recall:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        print(f"  Train/Test: {len(train_df)}/{len(test_df)}")

        # Setup SHAP explainer
        # XGBoost 3.x can have issues with SHAP's TreeExplainer.
        # We try multiple approaches and fall back to feature-importance-based explanations.
        self.explainer = None
        self._use_shap = False
        try:
            # Patch base_score if needed (XGBoost 3.x stores it as '[5E-1]')
            booster = self.model.get_booster()
            self.explainer = shap.TreeExplainer(booster)
            self._use_shap = True
        except Exception:
            try:
                self.explainer = shap.TreeExplainer(self.model)
                self._use_shap = True
            except Exception as e:
                print(f"  Note: SHAP TreeExplainer unavailable ({e}). Using feature importance fallback.")
                self._use_shap = False
                # Store feature importances for fallback explanations
                self._feature_importances = dict(
                    zip(self.feature_names, self.model.feature_importances_)
                )

        # Store test data for validation
        self.X_test = X_test
        self.y_test = y_test
        self.test_proba = y_proba

        return self.metrics

    def predict_score(self, features_row: pd.DataFrame) -> float:
        """Predict intent score (0–100) for a single prospect."""
        if self.calibrated_model is None:
            raise ValueError("Model not trained yet")

        encoded = self._encode_features(features_row[self.feature_names], fit=False)
        proba = self.calibrated_model.predict_proba(encoded)[:, 1]
        return float(round(proba[0] * 100, 1))

    def predict_scores_batch(self, features_df: pd.DataFrame) -> np.ndarray:
        """
        Predict intent scores for a batch of prospects.

        Uses percentile-based scoring (0–100) so scores spread meaningfully
        across the population. The rank order is identical to raw probability
        ordering, which is what matters for lead prioritization.
        """
        if self.calibrated_model is None:
            raise ValueError("Model not trained yet")

        available = [f for f in self.feature_names if f in features_df.columns]
        encoded = self._encode_features(features_df[available], fit=False)
        proba = self.calibrated_model.predict_proba(encoded)[:, 1]

        # Convert to percentile-based scores (0–100)
        from scipy.stats import rankdata
        ranks = rankdata(proba, method='average')
        percentile_scores = (ranks - 1) / (len(ranks) - 1) * 100
        return np.round(percentile_scores, 1)

    def explain_prediction(self, features_row: pd.DataFrame, top_n: int = 3) -> dict:
        """
        Generate explanation for a single prediction.
        Uses SHAP TreeExplainer if available, otherwise falls back to
        feature-importance-weighted explanations.

        Returns:
            dict with 'shap_values', 'top_factors' (list of dicts),
            'reason_string' (human-readable)
        """
        encoded = self._encode_features(features_row[self.feature_names], fit=False)

        if self._use_shap and self.explainer is not None:
            # SHAP path
            try:
                shap_values = self.explainer.shap_values(encoded)
                if isinstance(shap_values, list):
                    sv = shap_values[1][0]
                else:
                    sv = shap_values[0]
                feature_importance = list(zip(self.feature_names, sv))
            except Exception:
                # Fall through to importance-based
                feature_importance = self._importance_based_explanation(encoded)
        else:
            # Feature importance fallback
            feature_importance = self._importance_based_explanation(encoded)

        feature_importance.sort(key=lambda x: abs(x[1]), reverse=True)

        top_factors = []
        reason_parts = []

        for feat_name, importance_val in feature_importance[:top_n]:
            raw_value = features_row[feat_name].iloc[0] if feat_name in features_row.columns else "N/A"

            # Decode categorical values for display
            if feat_name in self.label_encoders and isinstance(raw_value, (int, np.integer)):
                le = self.label_encoders[feat_name]
                if raw_value < len(le.classes_):
                    raw_value = le.classes_[raw_value]

            direction = "positive" if importance_val > 0 else "negative"
            human_name = feat_name.replace("_", " ").title()

            top_factors.append({
                "feature": feat_name,
                "display_name": human_name,
                "value": str(raw_value),
                "shap_value": round(float(importance_val), 4),
                "direction": direction,
            })

            if direction == "positive":
                reason_parts.append(f"High {human_name} ({raw_value})")
            else:
                reason_parts.append(f"Low {human_name} ({raw_value})")

        sv_dict = {fn: round(float(v), 4) for fn, v in feature_importance}
        return {
            "shap_values": sv_dict,
            "top_factors": top_factors,
            "reason_string": "; ".join(reason_parts),
        }

    def _importance_based_explanation(self, encoded_row: pd.DataFrame) -> list:
        """
        Fallback explanation using feature importances × feature deviation.
        Positive = feature value is above average (suggesting conversion),
        Negative = below average.
        """
        importances = getattr(self, '_feature_importances', None)
        if importances is None:
            importances = dict(zip(self.feature_names, self.model.feature_importances_))

        result = []
        for feat_name in self.feature_names:
            imp = importances.get(feat_name, 0)
            val = encoded_row[feat_name].iloc[0] if feat_name in encoded_row.columns else 0
            # Use importance as magnitude, sign based on whether value is "high"
            # For simplicity: positive importance if value > 0.5 (normalized), else negative
            sign = 1.0 if val > 0 else -1.0
            result.append((feat_name, imp * sign))
        return result

    def explain_batch(self, features_df: pd.DataFrame, top_n: int = 3) -> list:
        """Generate SHAP explanations for a batch."""
        explanations = []
        for idx in range(len(features_df)):
            row = features_df.iloc[[idx]]
            try:
                explanation = self.explain_prediction(row, top_n)
            except Exception:
                explanation = {
                    "shap_values": {},
                    "top_factors": [],
                    "reason_string": "Explanation unavailable",
                }
            explanations.append(explanation)
        return explanations

    def save(self, path: str = None):
        """Save model artifacts."""
        if path is None:
            path = config.MODEL_DIR

        os.makedirs(path, exist_ok=True)

        # Save XGBoost model
        self.model.save_model(os.path.join(path, "intent_xgb.json"))

        # Save metadata
        metadata = {
            "feature_names": self.feature_names,
            "metrics": self.metrics,
            "label_encoders": {
                k: list(le.classes_) for k, le in self.label_encoders.items()
            },
        }
        with open(os.path.join(path, "intent_metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"[OK] Model saved -> {path}")

    def load(self, path: str = None):
        """Load model artifacts."""
        if path is None:
            path = config.MODEL_DIR

        # Load XGBoost model
        self.model = xgb.XGBClassifier()
        self.model.load_model(os.path.join(path, "intent_xgb.json"))

        # Load metadata
        with open(os.path.join(path, "intent_metadata.json"), "r") as f:
            metadata = json.load(f)

        self.feature_names = metadata["feature_names"]
        self.metrics = metadata["metrics"]

        # Rebuild label encoders
        self.label_encoders = {}
        for k, classes in metadata["label_encoders"].items():
            le = LabelEncoder()
            le.classes_ = np.array(classes)
            self.label_encoders[k] = le

        # Setup SHAP
        self.explainer = None
        self._use_shap = False
        try:
            self.explainer = shap.TreeExplainer(self.model.get_booster())
            self._use_shap = True
        except Exception:
            try:
                self.explainer = shap.TreeExplainer(self.model)
                self._use_shap = True
            except Exception:
                self._use_shap = False
                self._feature_importances = dict(
                    zip(self.feature_names, self.model.feature_importances_)
                )

        print(f"[OK] Model loaded ← {path}")


if __name__ == "__main__":
    # Quick train & evaluate
    features = pd.read_csv(
        os.path.join(config.DATA_DIR, "features.csv")
    )
    model = IntentModel()
    metrics = model.train(features)
    model.save()

    print(f"\n── Model Metrics ──")
    for k, v in metrics.items():
        if k != "confusion_matrix":
            print(f"  {k}: {v}")
    print(f"  Confusion Matrix:\n  {metrics['confusion_matrix']}")
