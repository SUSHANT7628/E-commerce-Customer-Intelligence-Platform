# Model Validation Protocol

## Why time-aware validation?
Random train/test splitting can leak future behavior into training when customer activity changes over time. For a churn use case, an expanding-window split is more realistic.

## Models
1. Logistic Regression — interpretable baseline
2. Random Forest — nonlinear ensemble
3. Gradient Boosting — stronger nonlinear baseline

## Metrics
- Precision
- Recall
- F1
- ROC-AUC
- PR-AUC

## Selection principle
Choose the model using business objectives, not simply the highest accuracy. If retention capacity is limited, precision among high-risk customers may matter more; if missing churners is costly, recall becomes more important.

## Before resume claims
Run the validation on the final feature set and record mean and standard deviation across folds.
