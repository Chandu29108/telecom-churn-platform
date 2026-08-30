"""
Per-customer and global explainability using SHAP.

Why this exists: the platform's feature_importance list (model.feature_
importances_) is GLOBAL — it tells you what matters across the whole
dataset, but not why any single customer scored the way they did. That gap
is the #1 thing every serious competitor (DataRobot, H2O.ai, Kumo.ai) has
that this platform didn't. SHAP (TreeExplainer, exact for tree ensembles
like GradientBoostingClassifier) gives a signed, per-feature contribution
for a single prediction: "this customer's risk is high mainly BECAUSE
incoming-call minutes dropped and recharge amount dropped."

Performance note: SHAP on a full 100k-row dataset is too slow to run
synchronously in a request. We deliberately only explain the subset the
product actually needs explanations for — the top-N highest-risk customers
shown in the dashboard table, or a single customer on the Prediction page —
never the full uploaded dataset.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap


def build_explainer(model) -> shap.TreeExplainer:
    """GradientBoostingClassifier is a tree ensemble, so TreeExplainer gives
    exact (not sampled/approximated) SHAP values and is fast for the small
    batches this module is used on."""
    return shap.TreeExplainer(model)


def _normalize_shap_output(raw_values) -> np.ndarray:
    """shap.TreeExplainer.shap_values() return shape differs across sklearn/
    shap versions for binary classifiers — sometimes a single 2D array of
    contributions to the positive class, sometimes a list of two arrays
    (one per class), sometimes a 3D array (n_samples, n_features, n_classes).
    Normalize all of these down to a single (n_samples, n_features) array of
    contributions to the POSITIVE (churn) class."""
    arr = np.array(raw_values, dtype=object) if isinstance(raw_values, list) else raw_values

    if isinstance(raw_values, list):
        # list of per-class arrays -> take the positive class (index 1) if
        # present, otherwise the only array available
        return np.asarray(raw_values[1] if len(raw_values) > 1 else raw_values[0])

    arr = np.asarray(raw_values)
    if arr.ndim == 3:
        # (n_samples, n_features, n_classes) -> positive class slice
        return arr[:, :, -1]
    return arr  # already (n_samples, n_features)


def explain_batch(model, X: pd.DataFrame, top_n: int = 3) -> list[list[dict]]:
    """Returns, for each row in X, the top_n features that pushed that
    customer's prediction most, with signed impact and a human-readable
    direction. Row order in the output matches X's row order exactly."""
    if len(X) == 0:
        return []

    explainer = build_explainer(model)
    raw = explainer.shap_values(X)
    values = _normalize_shap_output(raw)

    feature_names = list(X.columns)
    out = []
    for row in values:
        idx = np.argsort(-np.abs(row))[:top_n]
        out.append([
            {
                "feature": feature_names[i],
                "impact": round(float(row[i]), 4),
                "direction": "increases_risk" if row[i] > 0 else "decreases_risk",
            }
            for i in idx
        ])
    return out


def explain_single(model, x_row: pd.DataFrame, top_n: int = 5) -> list[dict]:
    """Convenience wrapper for the single-customer Prediction page — same
    logic as explain_batch but for exactly one row."""
    return explain_batch(model, x_row, top_n=top_n)[0]
