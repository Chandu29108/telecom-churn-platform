"""
This module is a direct port of Sections 3 (Feature Engineering), 4 (Model
Building) and 6 (Scoring) from the source notebook `main.ipynb`, refactored
into reusable functions so the exact same logic can run against ANY uploaded
CSV that follows the same schema (month-suffixed columns _6/_7/_8/_9, e.g.
`arpu_6`, `total_ic_mou_7`, `total_rech_amt_8`...).

Why re-derive instead of just loading a single pickled model:
Retention behaviour, plan pricing, and customer mix genuinely differ between
telecom operators and time periods. Re-fitting Gradient Boosting on the
uploaded data (rather than always scoring with one frozen model trained on
one historical dataset) keeps the tool honest — it produces insights that
reflect the data you actually gave it, the same way the original notebook
was built to analyse one operator's snapshot.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, roc_curve, precision_recall_curve, confusion_matrix,
)

from .config import CHURN_THRESHOLD, RISK_TIER_BOUNDS

RANDOM_STATE = 42
MONTHS = [6, 7, 8]  # "good phase" months used as predictive features
TARGET_MONTH = 9    # churn is defined from this month's activity


# --------------------------------------------------------------------------- #
# 1. Feature engineering  (mirrors notebook Section 3)
# --------------------------------------------------------------------------- #
def engineer_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series | None]:
    """
    Returns (X, y). y is None if the uploaded data has no way to derive churn
    (i.e. no `churn` column AND no month-9 usage columns to derive it from) —
    callers should treat that as a "score only, can't train/evaluate" case.
    """
    df = df.copy()

    # --- Derive / read the churn label -----------------------------------
    y = None
    if "churn" in df.columns:
        y = df["churn"].astype(int)
    else:
        usage_9 = [c for c in df.columns if c.endswith("_9") and (
            c.startswith("total_ic_mou") or c.startswith("total_og_mou")
            or c.startswith("vol_2g_mb") or c.startswith("vol_3g_mb")
        )]
        if usage_9:
            # Standard definition for this dataset family: a customer has
            # churned if ALL month-9 usage/data columns are zero (no
            # outgoing, no incoming, no data — the line has gone dark).
            y = (df[usage_9].fillna(0).sum(axis=1) == 0).astype(int)

    # --- Drop columns that would leak the target or aren't predictive ----
    leak_cols = [c for c in df.columns if c.endswith(f"_{TARGET_MONTH}")]
    drop_cols = leak_cols + [c for c in ["mobile_number", "circle_id", "churn"] if c in df.columns]
    date_cols = [c for c in df.columns if "date" in c.lower()]
    df_fe = df.drop(columns=[c for c in drop_cols + date_cols if c in df.columns], errors="ignore")

    numeric_df = df_fe.select_dtypes(include=[np.number]).copy()

    # --- Derived trend / ratio features, same construction as notebook ---
    def base_metrics():
        # metric_prefixes we know how to build trend features for, if present
        return ["arpu", "total_og_mou", "total_ic_mou", "total_rech_amt"]

    for metric in base_metrics():
        cols = {m: f"{metric}_{m}" for m in MONTHS}
        if all(c in numeric_df.columns for c in cols.values()):
            numeric_df[f"{metric}_trend_7_to_8"] = (
                numeric_df[cols[8]] - numeric_df[cols[7]]
            ) / (numeric_df[cols[7]].abs() + 1)
            numeric_df[f"{metric}_trend_6_to_7"] = (
                numeric_df[cols[7]] - numeric_df[cols[6]]
            ) / (numeric_df[cols[6]].abs() + 1)
            numeric_df[f"{metric}_overall_trend"] = (
                numeric_df[cols[8]] - numeric_df[cols[6]]
            ) / (numeric_df[cols[6]].abs() + 1)
            numeric_df[f"{metric}_avg_678"] = numeric_df[[cols[6], cols[7]]].mean(axis=1)
            numeric_df[f"{metric}_std_678"] = numeric_df[[cols[6], cols[7], cols[8]]].std(axis=1)
            good_phase = numeric_df[[cols[6], cols[7]]].mean(axis=1)
            numeric_df[f"aug_vs_good_{metric.replace('total_', '').replace('_mou', '').replace('_amt','')}"] = (
                numeric_df[cols[8]] - good_phase
            ) / (good_phase.abs() + 1)

    # roaming behavioural flag, same idea as notebook
    roam_cols = [c for c in numeric_df.columns if c.startswith("roam_")]
    if roam_cols:
        numeric_df["roaming_user_flag"] = (numeric_df[roam_cols].fillna(0).sum(axis=1) > 0).astype(int)

    # --- Missing values: drop columns >40% missing, then median-impute ----
    missing_pct = numeric_df.isna().mean()
    numeric_df = numeric_df.drop(columns=missing_pct[missing_pct > 0.40].index.tolist())
    numeric_df = numeric_df.fillna(numeric_df.median(numeric_only=True))
    numeric_df = numeric_df.fillna(0)

    return numeric_df, y


# --------------------------------------------------------------------------- #
# 2. Train + evaluate  (mirrors notebook Section 4/5)
# --------------------------------------------------------------------------- #
def train_and_evaluate(X: pd.DataFrame, y: pd.Series):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_STATE, stratify=y
    )

    model = GradientBoostingClassifier(random_state=RANDOM_STATE)
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)

    fpr, tpr, _ = roc_curve(y_test, proba)
    prec_curve, rec_curve, _ = precision_recall_curve(y_test, proba)
    cm = confusion_matrix(y_test, preds).tolist()

    metrics = {
        "accuracy": round(accuracy_score(y_test, preds), 4),
        "precision": round(precision_score(y_test, preds, zero_division=0), 4),
        "recall": round(recall_score(y_test, preds, zero_division=0), 4),
        "f1_score": round(f1_score(y_test, preds, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_test, proba), 4),
        "confusion_matrix": cm,  # [[TN, FP], [FN, TP]]
        "roc_curve": {"fpr": fpr[::max(1, len(fpr)//60)].tolist(),
                      "tpr": tpr[::max(1, len(tpr)//60)].tolist()},
        "pr_curve": {"precision": prec_curve[::max(1, len(prec_curve)//60)].tolist(),
                     "recall": rec_curve[::max(1, len(rec_curve)//60)].tolist()},
    }

    importances = (
        pd.Series(model.feature_importances_, index=X.columns)
        .sort_values(ascending=False)
        .head(20)
    )
    feature_importance = [
        {"feature": k, "importance": round(float(v), 4)} for k, v in importances.items()
    ]

    return model, metrics, feature_importance


# --------------------------------------------------------------------------- #
# 3. Score full dataset + risk tiers  (mirrors notebook Section 6)
# --------------------------------------------------------------------------- #
def score_customers(model, X: pd.DataFrame, id_series: pd.Series | None) -> pd.DataFrame:
    proba = model.predict_proba(X)[:, 1]

    def tier(p: float) -> str:
        for name, bound in RISK_TIER_BOUNDS.items():
            if p >= bound:
                return name
        return "Low"

    result = pd.DataFrame({
        "customer_id": id_series.values if id_series is not None else np.arange(len(X)),
        "churn_probability": np.round(proba, 4),
        "churn_flag": (proba >= CHURN_THRESHOLD).astype(int),
        "risk_tier": [tier(p) for p in proba],
    })
    return result


# --------------------------------------------------------------------------- #
# 4. EDA summaries used by the dashboard + insight engine
# --------------------------------------------------------------------------- #
def eda_summary(df: pd.DataFrame, y: pd.Series | None) -> dict:
    out: dict = {}
    if y is not None:
        out["churn_rate"] = round(float(y.mean()), 4)
        out["total_customers"] = int(len(df))
        out["churned_customers"] = int(y.sum())
        out["active_customers"] = int(len(df) - y.sum())

    if y is not None and "aon" in df.columns:
        tenure_years = (df["aon"] / 365).clip(lower=0)
        bins = [0, 1, 2, 3, 5, 100]
        labels = ["<1yr", "1-2yr", "2-3yr", "3-5yr", "5+yr"]
        tenure_bucket = pd.cut(tenure_years, bins=bins, labels=labels, right=False)
        out["churn_by_tenure"] = (
            pd.DataFrame({"bucket": tenure_bucket, "churn": y})
            .groupby("bucket", observed=True)["churn"].mean().round(4).to_dict()
        )

    rech_col = "total_rech_amt_6" if "total_rech_amt_6" in df.columns else None
    if y is not None and rech_col:
        bins = [-1, 100, 300, 600, 1000, 1e9]
        labels = ["<100", "100-300", "300-600", "600-1000", "1000+"]
        bucket = pd.cut(df[rech_col].fillna(0), bins=bins, labels=labels)
        out["churn_by_recharge"] = (
            pd.DataFrame({"bucket": bucket, "churn": y})
            .groupby("bucket", observed=True)["churn"].mean().round(4).to_dict()
        )

    if "arpu_6" in df.columns:
        out["avg_monthly_charges"] = round(float(df[[c for c in
            ["arpu_6", "arpu_7", "arpu_8"] if c in df.columns]].mean().mean()), 2)
    if "aon" in df.columns:
        out["avg_tenure_days"] = round(float(df["aon"].mean()), 1)

    return out
