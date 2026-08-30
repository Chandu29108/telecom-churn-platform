# Power BI Dashboard Specification

Data source: connect Power BI Desktop to the same PostgreSQL database the backend writes to
(`analysis_runs`, `customer_scores` tables) — Get Data → PostgreSQL database → point at your
Render/local connection string. This means the Power BI report and the web app dashboard are
always showing the same numbers, not two versions that drift apart.

## KPI Cards (page 1, top row)

| KPI | DAX measure sketch | Source |
|---|---|---|
| Total Customers | `COUNTROWS(customer_scores)` | customer_scores |
| Active Customers | `CALCULATE(COUNTROWS(customer_scores), churn_flag = 0)` | customer_scores |
| Churned Customers | `CALCULATE(COUNTROWS(customer_scores), churn_flag = 1)` | customer_scores |
| Churn Rate % | `DIVIDE([Churned Customers],[Total Customers])` | derived |
| Predicted High-Risk | `CALCULATE(COUNTROWS(customer_scores), risk_tier IN {"Critical","High"})` | customer_scores |
| Avg Monthly Charges | from `analysis_runs.eda_summary[avg_monthly_charges]` (JSON field, flatten on import) | analysis_runs |
| Avg Customer Tenure | from `analysis_runs.eda_summary[avg_tenure_days]` | analysis_runs |
| Estimated Revenue at Risk | `[Predicted High-Risk] * [Avg Monthly Charges]` | derived |

## Charts

| Visual | Type | Fields | Filter | Purpose | Takeaway |
|---|---|---|---|---|---|
| Churn by Tenure Group | Clustered bar | `eda_summary.churn_by_tenure` (bucket, rate) | run_id (latest) | Show which tenure cohort needs the most retention attention | New customers churn 5x more than 5+yr customers |
| Churn by Recharge Bucket | Clustered bar | `eda_summary.churn_by_recharge` | run_id | Test the "high spenders are safe" assumption | High-recharge customers are not automatically low-risk |
| Feature Importance | Horizontal bar | `feature_importance` (feature, importance) | top 15 | Explain *why* the model flags customers | Usage-drop features dominate over static attributes |
| Customer Risk Distribution | Donut | `risk_tier` count | run_id | At-a-glance base health | Most customers are Low risk — spend accordingly |
| ROC Curve | Line | `metrics.roc_curve` (fpr, tpr) | run_id | Model quality for technical stakeholders | AUC ~0.95 = strong separability |
| Confusion Matrix | Matrix/heatmap | `metrics.confusion_matrix` | run_id | Show real trade-off between false positives/negatives | Recall prioritized over precision, by design |
| Precision vs Recall (threshold) | Line, dual-axis | precision/recall by threshold | run_id | Let ops pick a threshold matching offer cost | Higher threshold = fewer, more confident flags |
| High-Risk Customer Table | Table | customer_id, churn_probability, risk_tier | risk_tier ∈ {Critical, High} | Actionable list for the retention team | Direct campaign export source |
| Customer Segmentation | Scatter (ARPU vs tenure, colored by risk) | arpu, aon, risk_tier | run_id | Spot segment patterns visually | High spend + low tenure = highest-risk quadrant |
| Geographic Distribution | Map (if circle_id/region present) | region, churn_rate | run_id | Only include if the dataset has a region field | Regional hotspots for targeted campaigns |

## Layout (wireframe)

```
┌─────────────────────────────────────────────────────────────┐
│ [Total] [Active] [Churned] [Churn %] [High-Risk] [Rev@Risk]  │  ← KPI row
├───────────────────────────────┬───────────────────────────────┤
│  Churn by Tenure (bar)         │  Churn by Recharge (bar)      │
├───────────────────────────────┼───────────────────────────────┤
│  Feature Importance (bar)      │  Risk Distribution (donut)    │
├───────────────────────────────┴───────────────────────────────┤
│  High-Risk Customer Table (drill-through → Customer Detail)   │
└─────────────────────────────────────────────────────────────┘
Page 2 — Model Performance: ROC curve | PR curve | Confusion matrix | threshold slider
Page 3 — Customer Detail (drill-through target): single-customer usage trend + score history
```

## Color palette

Matches the web app so both tools feel like one product:
`#0F1530` (ink/navy — headers, text), `#12B8A6` (signal teal — primary accent), risk tiers
`#E5484D` Critical, `#F2994A` High, `#F2C94C` Medium, `#27AE60` Low.

## Interactions

- **Slicers**: risk tier, tenure bucket, recharge bucket, run/upload date.
- **Drill-through**: click a row in the High-Risk table → Customer Detail page (usage trend
  line for that customer across months 6–8, score history if scored multiple times).
- **Cross-filtering**: clicking a bar in "Churn by Tenure" filters the High-Risk table to that
  cohort.
- **Bookmarks**: "Executive view" (KPIs + risk distribution only) vs. "Analyst view" (full page
  with model performance).
