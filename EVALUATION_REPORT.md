# External Dataset Evaluation Report

## Test institution

**Northstar Metropolitan University** is a fictional institution created for the end-to-end demonstration. No real institution or student identity is represented.

## Public dataset

The test uses UCI Machine Learning Repository dataset 697, **Predict Students' Dropout and Academic Success**, licensed CC BY 4.0. The official dataset contains 4,424 higher-education records and 36 features. See `data/UCI_697_ATTRIBUTION.md` for citation and transformation details.

## Outcome preparation

The source has three outcomes: Dropout, Enrolled, and Graduate. The application currently performs binary screening. Treating Enrolled as a successful/non-dropout record would create label error because those students have not reached a final outcome. Therefore:

- Dropout maps to 1.
- Graduate maps to 0.
- 794 Enrolled records are excluded.
- 3,630 confirmed-outcome records remain.
- The positive dropout rate is 39.15%.

## Features used

- First-semester enrolled modules
- First-semester modules with evaluation participation
- Evaluation participation rate
- First-semester assessment average
- Change from first- to second-semester assessment average
- First-semester credit approval ratio
- Derived academic engagement ratio

Gender and age band are not model inputs. They are used only for subgroup auditing.

## Results

The model comparison uses shuffled stratified out-of-fold predictions. The selected model is histogram gradient boosting. Training is restricted to the approved semester-one feature allowlist; the semester-to-semester change feature is excluded to match the prediction horizon.

| Metric | Result |
|---|---:|
| PR-AUC | 0.8974 |
| ROC-AUC | 0.9066 |
| Brier score | 0.1057 |
| Recall | 0.8037 |
| Precision | 0.8134 |
| F1 | 0.8085 |
| Selected threshold | 0.370 |

These are benchmark results for this public dataset, not a promise of performance at another institution.

## Mistakes found and resolved

### Unfinished outcomes could be mislabeled

**Problem:** The source `Enrolled` outcome is censored and cannot safely be treated as non-dropout.

**Resolution:** Exclude Enrolled rows from binary model training and report the exclusion count.

### Evaluation attempts are not submitted modules

**Problem:** Source evaluation counts can exceed enrolled modules because students may make repeated attempts. The first adapter violated the application's `submitted <= due` validation.

**Resolution:** Convert evaluation attempts to a module-participation proxy capped at enrolled modules. Preserve the global validation rule.

### Generic institution schemas are insufficient

**Problem:** A generic university template did not match the public dataset's semantic field names.

**Resolution:** Add a reviewed Northstar configuration and update the university onboarding template with the tested mappings.

### First-run testing depended on a browser file picker

**Problem:** The new institution workspace required a CSV upload before any dashboard could be evaluated, making a reviewer demo fragile.

**Resolution:** Add an explicitly attributed “Load the UCI benchmark demonstration” action. Normal institution CSV upload remains available and is still validated against the saved schema.

### Signup policies could reference unavailable fields

**Problem:** A university schema without platform-login data inherited an inactivity rule using `days_since_login`, so that rule could never fire.

**Resolution:** Filter onboarding policy defaults to fields supported by the selected schema and use a credit-progress rule for the tested university schema.

### Synthetic results were unrealistically strong

**Problem:** The original 600-row synthetic data produced near-perfect scores and could create false confidence.

**Resolution:** Make the UCI benchmark the default demonstration and label all results by dataset and validation design.

### Risk thresholds and model operating threshold can diverge

**Problem:** The benchmark's F1-selected operating threshold is 0.370 while the display's medium/high boundaries are 0.35 and 0.65.

**Resolution:** Treat 0.35 as the screening-entry boundary and 0.65 as the high-priority workload boundary. The values remain institution-editable and must be selected from real capacity and error costs.

### Subgroup performance differs

**Problem:** Recall and precision vary across gender and age audit groups. For example, recall is lower for the `20 or younger` group than for older groups.

**Resolution:** Display subgroup results in model governance, exclude these fields from prediction, and require a real-data fairness review before production approval. This benchmark alone cannot establish fairness.

### Explainability is not causality

**Problem:** Strong semester-performance features can dominate predictions, but they do not prove why a student may leave.

**Resolution:** Label reason codes as model evidence, keep policy flags separate, add supportive suggestions, and require teacher verification and student conversation through the screening checklist.

## Remaining limitations

- The dataset does not contain institution timestamps suitable for a true temporal holdout.
- Second-semester features may be too late for some intervention programs.
- The public data comes from one higher-education context and does not prove transfer to schools or other universities.
- The binary version excludes currently enrolled students rather than modeling time-to-event or three classes.
- The application still needs institution-specific identity integration, access control review, retention policy, and a shadow pilot before operational deployment.

