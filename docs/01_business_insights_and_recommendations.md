# Telecom Churn Prediction — Business Insights & Recommendations

*Grounded entirely in the outputs of `main.ipynb` (99,999 customers, June–September usage data). No generic filler — every number below traces back to a specific cell output or chart in the notebook.*

---

## 1. Business Insights

### 1.1 What actually drives churn (feature importance + correlation)

The top correlated feature with churn is **`aug_vs_good_og`** (Aug outgoing usage vs. the customer's own "good phase" baseline, r = 0.320), followed by `aug_vs_good_arpu` (0.306) and `aug_vs_good_rech` (0.293). The Gradient Boosting feature importance chart confirms this: **`total_ic_mou_8`** (August incoming minutes) alone accounts for over 55% of the model's decision weight, dwarfing every other feature.

**What this means in plain terms:** churn is not predicted well by *who the customer is* (demographics, plan type) — it's predicted by **the shape of their own usage curve**. The single strongest signal is a customer's August behavior collapsing relative to their own June/July baseline. This is a "dying SIM" pattern, not a snap decision: the EDA usage-trend chart shows churners' median ARPU, outgoing minutes, and incoming minutes all decline steadily from June → July → August, hitting ~0 by August, a full month *before* the September churn label is even assigned.

**Business takeaway:** churn is detectable and interceptable roughly 30 days before it's officially recorded. A model built on August behavior isn't predicting the future so much as reading a decision the customer has effectively already made — which makes proactive intervention viable if triggered early in the August billing cycle rather than at month-end.

### 1.2 Customer segments most likely to churn

| Segment | Churn rate | vs. average (9.0%) |
|---|---|---|
| Tenure < 1 year | 14.6% | +5.6 pts |
| Tenure 1–2 years | 11.9% | +2.9 pts |
| Tenure 2–3 years | 10.0% | +1.0 pt |
| Tenure 3–5 years | 5.9% | −3.1 pts |
| Tenure 5+ years | 2.7% | −6.3 pts |
| Recharge < ₹100 | 6.8% | −2.2 pts |
| Recharge ₹600–1000 | 9.4% | +0.4 pt |
| Recharge ₹1000+ | 10.5% | +1.5 pts |

Two findings worth calling out because they're *not* the obvious story:

- **Tenure is the single cleanest churn predictor in the raw EDA** — churn risk drops almost monotonically the longer a customer stays, from 14.6% to 2.7%. New customers need the most retention attention, not existing high-value ones.
- **High-recharge customers churn *more*, not less** (10.5% at ₹1000+ vs. 6.8% at <₹100). This contradicts the usual "protect your big spenders less, they're loyal" assumption. It suggests your heaviest rechargers behave more like semi-postpaid power users who are also the most price-sensitive to competitor offers — they have the means and the motive to switch. This segment deserves proactive retention despite (or because of) their spend level.

### 1.3 Revenue / business impact

At the operating threshold (probability ≥ 0.45), the model flags **17,362 of 99,999 customers (17.4%)** as churn-risk, split into tiers:

- **Critical: 11,013 customers (11.0%)**
- **High: 6,349 customers (6.3%)**
- **Medium: 7,220 customers (7.2%)**
- **Low: 75,417 customers (75.4%)**

Using the June ARPU distribution (median ≈ ₹197 for the not-churned base) as a proxy for monthly value per customer, the **Critical + High tiers alone (17,362 customers) represent roughly ₹34–41 lakh/month of revenue actively at risk** (17,362 × ~₹197–235 median ARPU range across the three months). This is the pool retention spend should be targeted at first — not the full 91% base, and not spread evenly.

### 1.4 EDA patterns worth acting on

- **The August cliff**: churners' median total recharge amount falls from ₹230 (June, indistinguishable from non-churners) to ₹110 (July) to ₹0 (August). Non-churners hold steady at ₹230–250 throughout. This is a near-perfect leading indicator, not a lagging one.
- **ARPU distributions are heavily right-skewed with a churn-heavy spike near ₹0** in every month, most pronounced in August — visually confirming the same collapse pattern from a different angle.
- **Recharge amount and ARPU are almost perfectly self-correlated month-to-month** (r = 0.95–0.96 between consecutive months for the same customer) — meaning ARPU is largely just a restatement of recharge behavior, not an independent signal. This matters for the dashboard/feature design: don't double-count these as if they were two separate business levers.

### 1.5 Interpreting model performance

The team correctly optimized for **ROC-AUC and Recall over raw Accuracy** — the right call on a 9%-positive imbalanced problem, where a model that predicts "no churn" for everyone would already score 91% accuracy while being useless.

- **ROC-AUC 0.946** (Gradient Boosting) means the model ranks a random churner above a random non-churner 94.6% of the time — strong separability.
- **Recall 0.849** means the model catches ~85% of customers who will actually churn. In a retention context this is the number that matters most: missing a churner (false negative) costs a lost customer; flagging a loyal customer unnecessarily (false positive) just costs a discount coupon.
- **Precision 0.496** means roughly half of flagged customers won't actually churn. This is the expected and *acceptable* trade-off given the recall priority — see the threshold analysis below, which shows precision can be dialed up to 0.61 (at threshold 0.70) if a business team decides false-positive cost (e.g. an expensive retention offer) outweighs the value of catching every churner.
- **Cross-validation (0.9428 ± 0.0046 AUC across 5 folds)** confirms the model is stable and not overfit to one split — a genuinely production-defensible result, not just a lucky train/test split.
- The **confusion matrix for Gradient Boosting** (16,640 TN / 1,556 FP / 272 FN / 1,532 TP on the 20,000-row test set) shows the model misses only 272 of 1,804 actual churners (15.1% miss rate) — consistent with the 84.9% recall figure.

### 1.6 How this helps business teams make decisions

Instead of a retention team treating all 91,000 active customers identically, the model output (`churn_flag_customer_scores.csv`) gives them a ranked, actionable list: 11,013 customers who need intervention *this week*, 6,349 who need a nudge, and 75,417 who don't need spend at all right now. This converts churn management from a blanket, low-ROI campaign into a targeted, measurable one — and because the top driver is a customer's own August usage collapse, retention teams can build a real-time trigger (e.g. "usage down >60% vs. 3-month average") instead of waiting for a monthly batch score.

---

## 2. Actionable Recommendations

### 2.1 Real-time "usage cliff" early-warning trigger
**Recommendation:** Don't wait for the monthly batch churn score. Since `aug_vs_good_og` and `aug_vs_good_rech` (a customer's current usage vs. their own historical baseline) are the strongest predictors, build a lightweight rule/streaming trigger that fires the moment a customer's weekly usage or recharge drops more than ~50–60% below their trailing 3-month average.
**Why it works:** The EDA shows the collapse is gradual and visible weeks before the churn event — the model is effectively confirming something that's already observable mid-cycle.
**Expected impact:** Shifts intervention from "after the fact" (September batch score) to "mid-decline" (August, week 1–2), which is when a retention offer still has a chance of reversing behavior.

### 2.2 Tiered retention campaigns by risk score, not a single blanket offer
**Recommendation:** Use the four risk tiers directly — Critical gets a personal outreach + strongest offer (e.g. bill credit, data top-up), High gets an automated SMS/app offer, Medium gets a soft-touch loyalty nudge, Low gets nothing.
**Why it works:** 75.4% of customers are Low-risk; spending retention budget on them is pure waste. Concentrating spend on the 17.4% flagged pool (with Critical getting the most) maximizes ROI per rupee spent.
**Expected impact:** With Critical + High representing an estimated ₹34–41 lakh/month at risk, even a modest 15–20% save rate on that tier is worth pursuing aggressively, while Medium/Low tiers get proportionally cheaper interventions.

### 2.3 New-customer onboarding program (first 12 months)
**Recommendation:** Tenure <1yr customers churn at 14.6% vs. 2.7% for 5+yr customers — build a structured 90/180/365-day onboarding journey (welcome offers, proactive check-ins, milestone rewards) specifically for this cohort.
**Why it works:** This is the single cleanest churn signal in the whole EDA and it's fully within the company's control — unlike usage patterns, tenure milestones can be actively managed with a defined playbook.
**Expected impact:** Even a modest reduction from 14.6% → 12% churn in the <1yr cohort meaningfully improves blended churn rate, since new customers are typically overrepresented in acquisition-heavy periods.

### 2.4 Dedicated retention track for high-recharge customers
**Recommendation:** Don't assume ₹1000+ rechargers are "safe" — they churn at 10.5%, the highest of any recharge bucket. Give this segment a named account manager or premium support tier and proactively check in rather than waiting for a risk flag.
**Why it works:** This segment has the means to switch easily and is likely being actively targeted by competitor offers; standard automated retention flows (built for average customers) probably under-serve them.
**Expected impact:** This is your highest-ARPU segment — losing one customer here costs several times what losing a low-recharge customer costs, so even small percentage-point improvements have outsized revenue impact.

### 2.5 Contract/plan optimization using the pricing feedback loop
**Recommendation:** Pair the churn model with a review of plan/pricing tiers for customers who show a recharge trend decline (`rech_trend_7_to_8`, `og_trend_7_to_8` — both in the top-30 correlated features) but haven't yet hit the "critical" cliff — offer a plan downgrade or right-sizing option before they leave entirely.
**Why it works:** A customer scaling down usage may not want to leave the network entirely, just spend less — losing them to a cheaper plan is far better than losing them to a competitor.
**Expected impact:** Converts some fraction of "would-have-churned" customers into lower-ARPU but retained customers, protecting base size and future upsell potential even if near-term revenue per customer dips slightly.

### 2.6 Support/experience audit for the Critical tier before contacting them
**Recommendation:** Before sending offers to the 11,013 Critical-tier customers, do a light audit of recent support tickets/network complaints (if available) for that cohort — because a large recharge/usage collapse can also mean poor network experience, not just competitor pull.
**Why it works:** A discount offer to a customer leaving because of network quality issues doesn't fix the underlying cause and wastes the retention spend.
**Expected impact:** Improves the effectiveness of retention spend by routing customers to the right remedy (service fix vs. price fix) instead of a one-size-fits-all discount.

### 2.7 Operationalize the model as a monthly + trigger-based scoring pipeline
**Recommendation:** Move `churn_flag_customer_scores.csv` generation from an ad hoc notebook run to a scheduled pipeline (monthly batch + the real-time trigger from 2.1), feeding a CRM/dashboard the retention team can actually act on daily.
**Why it works:** A model sitting in a notebook produces academic insight; a model wired into the CRM produces retained revenue. Recall of 84.9% means the model is good enough to build a real operational process around.
**Expected impact:** Converts this from a portfolio/analysis project into an actual revenue-protecting system — this is also the strongest "product thinking" signal for a resume/interview narrative.

### 2.8 Precision/recall threshold tuning by campaign cost
**Recommendation:** Use the threshold analysis already in the notebook (0.30 → 4,307 flagged / 0.5318 F1 vs. 0.70 → 2,269 flagged / 0.6806 F1) to pick different thresholds for different offer costs — a cheap SMS nudge can use a low threshold (catch more people, tolerate lower precision), while an expensive retention call/gift should use a high threshold (fewer, more confident targets).
**Why it works:** There's no single "correct" threshold — it's an economic decision, not a modeling one, and the notebook already contains the data needed to make it.
**Expected impact:** Prevents overspending on expensive interventions for false positives while still casting a wide net for cheap ones.
