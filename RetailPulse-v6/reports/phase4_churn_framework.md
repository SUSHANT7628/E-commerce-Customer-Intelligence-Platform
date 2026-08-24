# RetailPulse — Phase 4: Churn Prediction

## Target definition
For this portfolio project, churn is defined as no purchase for at least 120 days.
This threshold should be tested for sensitivity and adjusted to the business's normal purchase cycle.

## Models
- Logistic Regression: interpretable baseline
- Random Forest: nonlinear tree ensemble

Optional next step:
- XGBoost

## Evaluation
Report:
- Precision
- Recall
- F1
- ROC-AUC
- PR-AUC

Accuracy should not be the primary metric if churn is imbalanced.

## Business layer
Combine churn probability with predicted 12-month CLV to prioritize retention:
High CLV + high churn probability = highest-value intervention cohort.
