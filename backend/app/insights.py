"""
Turns the numeric output of pipeline.py into plain-English insights and
recommendations. Deliberately template-based rather than calling an LLM:
this needs to run instantly, deterministically, and for free on every
upload, and the source notebook's own analysis showed that clear rules
over the model's own numbers (feature importance, tier counts, segment
churn rates) already tell an honest, specific story — no generation needed.
"""


def build_insights(eda: dict, metrics: dict, feature_importance: list[dict],
                    risk_counts: dict) -> list[dict]:
    insights = []

    if "churn_rate" in eda:
        insights.append({
            "title": "Overall churn rate",
            "body": (
                f"{eda['churn_rate']*100:.1f}% of {eda['total_customers']:,} customers "
                f"in this dataset churned ({eda['churned_customers']:,} customers). "
                f"{'This is a highly imbalanced problem — accuracy alone is not a useful metric here.' if eda['churn_rate'] < 0.20 else ''}"
            ),
        })

    if feature_importance:
        top = feature_importance[0]
        insights.append({
            "title": "Strongest churn driver",
            "body": (
                f"'{top['feature']}' is the single strongest predictor the model found, "
                f"carrying {top['importance']*100:.1f}% of total decision weight — "
                f"far more influential than any customer attribute like plan type or demographics. "
                f"This suggests churn is best explained by a change in behaviour, not who the customer is."
            ),
        })

    if "churn_by_tenure" in eda and eda["churn_by_tenure"]:
        sorted_t = sorted(eda["churn_by_tenure"].items(), key=lambda x: x[1], reverse=True)
        worst, worst_rate = sorted_t[0]
        best, best_rate = sorted_t[-1]
        insights.append({
            "title": "Tenure is protective",
            "body": (
                f"Customers with tenure '{worst}' churn at {worst_rate*100:.1f}%, "
                f"vs. {best_rate*100:.1f}% for '{best}' — "
                f"{'a clear sign that new customers need the most retention attention.' if worst == '<1yr' else ''}"
            ),
        })

    if "churn_by_recharge" in eda and eda["churn_by_recharge"]:
        items = sorted(eda["churn_by_recharge"].items())
        insights.append({
            "title": "Recharge behaviour vs. churn",
            "body": (
                "Churn by recharge bucket: " +
                ", ".join(f"{k} → {v*100:.1f}%" for k, v in items) +
                ". If high-recharge customers don't show the lowest churn rate, "
                "that's a signal your highest-value segment needs proactive retention, not just automated flows."
            ),
        })

    if metrics:
        insights.append({
            "title": "Model performance",
            "body": (
                f"ROC-AUC {metrics['roc_auc']:.3f}, Recall {metrics['recall']*100:.1f}%, "
                f"Precision {metrics['precision']*100:.1f}%. "
                f"The model catches {metrics['recall']*100:.0f}% of customers who actually churn "
                f"({'strong' if metrics['recall'] > 0.75 else 'moderate'} recall), while roughly "
                f"{(1-metrics['precision'])*100:.0f}% of flagged customers turn out to be false positives — "
                f"an acceptable trade-off if the intervention cost per flagged customer is low."
            ),
        })

    if risk_counts:
        total = sum(risk_counts.values()) or 1
        critical = risk_counts.get("Critical", 0)
        insights.append({
            "title": "Revenue at risk",
            "body": (
                f"{critical:,} customers ({critical/total*100:.1f}%) fall into the Critical risk tier "
                f"and warrant intervention this cycle, out of {total:,} scored."
            ),
        })

    return insights


def build_recommendations(eda: dict, feature_importance: list[dict],
                           risk_counts: dict) -> list[dict]:
    recs = []

    recs.append({
        "recommendation": "Tier retention spend by risk score, not a blanket campaign",
        "why_it_works": (
            "Most customers are Low risk; spending budget there is waste. Concentrating "
            "spend on Critical/High tiers maximizes retention ROI per rupee/dollar spent."
        ),
        "expected_impact": f"Targets the {risk_counts.get('Critical', 0) + risk_counts.get('High', 0):,} "
                            f"highest-risk customers instead of the full base.",
        "priority": "High",
    })

    if feature_importance:
        top_feat = feature_importance[0]["feature"]
        recs.append({
            "recommendation": f"Build a real-time trigger on '{top_feat}'",
            "why_it_works": (
                "Since this is the model's strongest signal, monitoring it directly (rather than "
                "waiting for a monthly batch score) catches at-risk customers earlier, while an "
                "offer still has a chance to change behaviour."
            ),
            "expected_impact": "Shifts intervention timing from after-the-fact to mid-decline.",
            "priority": "High",
        })

    if "churn_by_tenure" in eda and eda["churn_by_tenure"]:
        sorted_t = sorted(eda["churn_by_tenure"].items(), key=lambda x: x[1], reverse=True)
        if sorted_t and sorted_t[0][0] == "<1yr":
            recs.append({
                "recommendation": "Structured onboarding journey for customers in year one",
                "why_it_works": "New customers show the highest churn risk and are the segment most "
                                 "responsive to a defined 90/180/365-day engagement plan.",
                "expected_impact": "Directly targets the cohort driving the highest segment churn rate.",
                "priority": "Medium",
            })

    recs.append({
        "recommendation": "Tune the decision threshold to the cost of the offer",
        "why_it_works": "A cheap SMS nudge can tolerate more false positives (lower threshold); "
                         "an expensive retention call should only go to high-confidence flags "
                         "(higher threshold).",
        "expected_impact": "Prevents overspending on expensive offers sent to unlikely churners.",
        "priority": "Medium",
    })

    recs.append({
        "recommendation": "Move scoring from a one-off run to a scheduled pipeline",
        "why_it_works": "A model that only runs in a notebook produces analysis; a model wired "
                         "into a CRM on a schedule produces retained revenue.",
        "expected_impact": "Turns this into an operational system rather than a one-time report.",
        "priority": "Low",
    })

    return recs
