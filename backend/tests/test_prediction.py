SAMPLE_PREDICT_PAYLOAD = {
    "total_ic_mou_8": 5, "total_ic_mou_7": 120, "total_ic_mou_6": 130,
    "total_rech_amt_8": 20, "total_rech_amt_7": 200, "total_rech_amt_6": 220,
    "arpu_8": 15, "arpu_7": 190, "arpu_6": 200,
    "last_day_rch_amt_8": 0, "roam_og_mou_8": 0, "aon": 90,
}


def test_predict_requires_auth(client):
    res = client.post("/api/predict", json=SAMPLE_PREDICT_PAYLOAD)
    assert res.status_code == 401


def test_predict_falls_back_to_heuristic_with_no_trained_model(client, auth_headers):
    headers = auth_headers()
    res = client.post("/api/predict", headers=headers, json=SAMPLE_PREDICT_PAYLOAD)
    assert res.status_code == 200
    body = res.json()
    assert body["explanation_mode"] == "heuristic"
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert body["risk_tier"] in ("Critical", "High", "Medium", "Low")
    assert len(body["top_factors"]) > 0
    assert "heuristic estimate" in body["recommended_action"]


def test_predict_uses_trained_model_and_shap_after_upload(client, auth_headers, synthetic_churn_csv):
    headers = auth_headers()
    client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn.csv", synthetic_churn_csv, "text/csv")},
    )

    res = client.post("/api/predict", headers=headers, json=SAMPLE_PREDICT_PAYLOAD)
    assert res.status_code == 200
    body = res.json()
    assert body["explanation_mode"] == "shap"
    assert "heuristic estimate" not in body["recommended_action"]
    assert len(body["top_factors"]) > 0


def test_predict_models_are_isolated_between_organizations(client, auth_headers, synthetic_churn_csv):
    """Org A trains a model; Org B (who hasn't uploaded anything) must still
    get the heuristic fallback, never Org A's model."""
    org_a = auth_headers(email="a@orga.com", org="Org A")
    org_b = auth_headers(email="b@orgb.com", org="Org B")

    client.post(
        "/api/analysis/upload", headers=org_a,
        files={"file": ("churn.csv", synthetic_churn_csv, "text/csv")},
    )

    res_b = client.post("/api/predict", headers=org_b, json=SAMPLE_PREDICT_PAYLOAD)
    assert res_b.json()["explanation_mode"] == "heuristic"
