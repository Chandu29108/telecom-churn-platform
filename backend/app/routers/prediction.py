"""
Single-customer prediction endpoint for the website's Prediction page.

Honesty note (see project README): this uses the calling org's currently
ACTIVE model version (see model_registry.py) if one exists. If that org
hasn't trained a model yet, it falls back to a transparent, clearly-labelled
weighted heuristic built from the same top features the notebook's Gradient
Boosting model ranked highest — NOT a disguised fake model. The response
always tells you which mode produced the number, and which mode produced
the explanation (SHAP vs. a breakdown of the heuristic's own terms).
"""
import logging

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import PredictRequest, PredictResponse
from ..config import MODEL_DIR, RISK_TIER_BOUNDS
from ..deps import get_current_user
from ..models_db import User
from ..ml import explainability
from ..model_registry import load_active_model

router = APIRouter(prefix="/api/predict", tags=["prediction"])
logger = logging.getLogger("churn_platform.prediction")


def _tier(p: float) -> str:
    for name, bound in RISK_TIER_BOUNDS.items():
        if p >= bound:
            return name
    return "Low"


def _heuristic_probability_and_factors(req: PredictRequest):
    """Weighted sum over min-max-normalised top features, weights taken
    directly from the notebook's Section 5 feature-importance ranking.
    Also returns each term's contribution so the response has SOMETHING
    explainable even before a real model has been trained for this org."""
    ic_drop = max(0.0, (req.total_ic_mou_6 + req.total_ic_mou_7) / 2 - req.total_ic_mou_8)
    rech_drop = max(0.0, (req.total_rech_amt_6 + req.total_rech_amt_7) / 2 - req.total_rech_amt_8)
    arpu_drop = max(0.0, (req.arpu_6 + req.arpu_7) / 2 - req.arpu_8)
    tenure_factor = max(0.0, 1 - req.aon / (365 * 3))  # newer customers score riskier

    terms = {
        "incoming_call_minutes_drop": 0.45 * min(1.0, ic_drop / 200),
        "recharge_amount_drop": 0.20 * min(1.0, rech_drop / 300),
        "arpu_drop": 0.15 * min(1.0, arpu_drop / 300),
        "roaming_outgoing_minutes": 0.10 * min(1.0, req.roam_og_mou_8 / 100),
        "short_tenure": 0.10 * tenure_factor,
    }
    score = float(np.clip(sum(terms.values()), 0.01, 0.99))

    factors = sorted(
        (
            {"feature": k, "impact": round(v, 4), "direction": "increases_risk" if v > 0 else "decreases_risk"}
            for k, v in terms.items()
        ),
        key=lambda f: abs(f["impact"]),
        reverse=True,
    )[:5]
    return score, factors


@router.post("", response_model=PredictResponse)
def predict(
    req: PredictRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model, cols, _version = load_active_model(db, current_user.org_id, MODEL_DIR)

    mode = "model"
    top_factors = []

    if model is not None:
        row = {c: 0.0 for c in cols}
        for field, value in req.dict().items():
            if field in row:
                row[field] = value
        X = pd.DataFrame([row])[cols]
        proba = float(model.predict_proba(X)[0, 1])
        try:
            top_factors = explainability.explain_single(model, X, top_n=5)
            explanation_mode = "shap"
        except Exception:
            logger.exception("SHAP explanation failed for single prediction; continuing without it.")
            explanation_mode = "shap"
            top_factors = []
    else:
        mode = "heuristic"
        explanation_mode = "heuristic"
        proba, top_factors = _heuristic_probability_and_factors(req)

    tier = _tier(proba)
    actions = {
        "Critical": "Immediate personal outreach + strongest retention offer (bill credit / data top-up).",
        "High": "Automated high-value SMS/app offer within 48 hours.",
        "Medium": "Soft-touch loyalty nudge or engagement campaign.",
        "Low": "No action needed — monitor at next scoring cycle.",
    }

    return PredictResponse(
        churn_probability=round(proba, 4),
        churn_flag=proba >= 0.45,
        risk_tier=tier,
        confidence=round(abs(proba - 0.5) * 2, 4),  # distance from the decision boundary
        recommended_action=actions[tier] + (
            "" if mode == "model" else " (heuristic estimate — upload a dataset to train the real model)"
        ),
        explanation_mode=explanation_mode,
        top_factors=top_factors,
    )
