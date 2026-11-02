# Real Data Upload Guide

## Official source used

This project now includes samples derived from UCI Machine Learning Repository dataset 697, **Predict Students' Dropout and Academic Success**. It contains 4,424 higher-education student records and a three-class final outcome: dropout, enrolled, or graduate.

Official page: https://archive.ics.uci.edu/dataset/697/predict%2Bstudents%2Bdropout%2Band%2Bacademic%2Bsuccess

Citation: Realinho, V., Vieira Martins, M., Machado, J., & Baptista, L. (2021). *Predict Students' Dropout and Academic Success* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5MC89.

License: CC BY 4.0.

## Files included

| File | Rows | Known dropout label | Purpose |
|---|---:|---:|---|
| `uci_697_real_500_natural_upload.csv` | 500 | 199 dropout, 301 non-dropout | Use this first. It keeps the natural source balance. |
| `uci_697_real_500_balanced_comparison.csv` | 500 | 250 dropout, 250 non-dropout | Use only to explain how balancing changes an evaluation set. |

The original source also contains an `Enrolled` final status. It is excluded from these binary samples because it is not a confirmed dropout or confirmed completion outcome.

## How to upload the natural sample

1. Open the development demonstration.
2. Select **Try a test CSV**.
3. Download and upload `uci_697_real_500_natural_upload.csv`.
4. Use the following mapping:

| CSV header | Meaning in the app |
|---|---|
| `learner_id` | Student identifier |
| `modules_enrolled` | Assignments due |
| `modules_evaluated` | Assignments submitted / evaluated |
| `first_semester_average` | Assessment average |
| `semester_score_change` | Assessment change |
| `credits_completed_percent` | Credits completed ratio |
| `academic_engagement` | Engagement score |
| `gender_audit` | Do not map |
| `age_band_audit` | Do not map |
| `confirmed_dropout` | Do not map while predicting |

## What to explain about balance

The natural sample has about 40% known dropouts. A model that predicts “not dropout” for everyone would look about 60% accurate while finding no students who actually dropped out. This is why the project should discuss dropout recall, precision, and the confusion matrix rather than accuracy alone.

The balanced sample is useful for classroom comparison. It should not be presented as the real prevalence of dropout at a university.

## Important limitation

`confirmed_dropout` is a known historical outcome. It is included so you can discuss later evaluation, not as an input for current prediction. Mapping it during prediction would leak the answer and invalidate the demonstration.
