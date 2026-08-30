import numpy as np
import pandas as pd

from app import pipeline


def _make_df(n=100, seed=1):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"mobile_number": 7000000000 + np.arange(n)})
    for m in [6, 7, 8, 9]:
        df[f"total_ic_mou_{m}"] = rng.exponential(80, n)
        df[f"total_og_mou_{m}"] = rng.exponential(90, n)
        df[f"arpu_{m}"] = rng.exponential(150, n)
        df[f"total_rech_amt_{m}"] = rng.exponential(180, n)
        if m == 9:
            df[f"vol_2g_mb_{m}"] = rng.exponential(50, n)
            df[f"vol_3g_mb_{m}"] = rng.exponential(50, n)
    df["aon"] = rng.integers(30, 2000, n)
    df["roam_og_mou_8"] = rng.exponential(5, n)
    return df


def test_engineer_features_derives_churn_label_when_absent():
    df = _make_df()
    churn_idx = [0, 1, 2, 3, 4]
    for c in ["total_ic_mou_9", "total_og_mou_9", "vol_2g_mb_9", "vol_3g_mb_9"]:
        df.loc[churn_idx, c] = 0

    X, y = pipeline.engineer_features(df)
    assert y is not None
    assert y.iloc[churn_idx].sum() == len(churn_idx)  # all flagged as churned
    # month-9 columns must be dropped (they define the label -> would leak)
    assert not any(c.endswith("_9") for c in X.columns)


def test_engineer_features_reads_explicit_churn_column():
    df = _make_df()
    df["churn"] = [1, 0] * (len(df) // 2)
    X, y = pipeline.engineer_features(df)
    assert y.tolist() == df["churn"].tolist()
    assert "churn" not in X.columns


def test_train_and_evaluate_returns_sane_metrics():
    df = _make_df(n=200, seed=2)
    churn_idx = np.random.default_rng(2).choice(len(df), 40, replace=False)
    for c in ["total_ic_mou_9", "total_og_mou_9", "vol_2g_mb_9", "vol_3g_mb_9"]:
        df.loc[churn_idx, c] = 0

    X, y = pipeline.engineer_features(df)
    model, metrics, feature_importance = pipeline.train_and_evaluate(X, y)

    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert len(feature_importance) > 0
    assert len(metrics["confusion_matrix"]) == 2


def test_score_customers_assigns_risk_tiers():
    df = _make_df(n=150, seed=3)
    churn_idx = np.random.default_rng(3).choice(len(df), 30, replace=False)
    for c in ["total_ic_mou_9", "total_og_mou_9", "vol_2g_mb_9", "vol_3g_mb_9"]:
        df.loc[churn_idx, c] = 0

    X, y = pipeline.engineer_features(df)
    model, _, _ = pipeline.train_and_evaluate(X, y)
    scored = pipeline.score_customers(model, X, df["mobile_number"])

    assert set(scored["risk_tier"]) <= {"Critical", "High", "Medium", "Low"}
    assert scored["churn_probability"].between(0, 1).all()
    assert len(scored) == len(df)
