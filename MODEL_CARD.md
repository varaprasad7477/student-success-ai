# Model Card — Northstar Semester-One Support Model

## Intended use

This model prioritizes human review for supportive outreach after semester one. It must not determine admission, discipline, financial aid, grading, or enrollment status.

## Data and outcome

The development benchmark is UCI dataset 697, *Predict Students' Dropout and Academic Success* (CC BY 4.0). `Dropout` is mapped to 1, `Graduate` to 0, and 794 unfinished `Enrolled` outcomes are excluded. The evaluated set contains 3,630 confirmed outcomes.

## Prediction horizon and leakage control

The prediction point is the end of semester one, for support planning in the following term. The deployed feature allowlist contains only semester-one information. The previously used semester-to-semester assessment-change feature is retained only as a source/audit field and is excluded from model training and scoring.

## Inputs

- Semester-one enrolled units
- Semester-one evaluation participation
- Submission/participation ratio
- Semester-one assessment average
- Semester-one credit completion ratio
- Derived semester-one academic engagement

Gender and age are excluded from prediction and used only for development subgroup auditing.

## Validation results

The selected histogram gradient boosting model was evaluated with shuffled stratified out-of-fold predictions because the public dataset has no cohort timestamp suitable for a temporal split.

| Metric | Result |
|---|---:|
| PR-AUC | 0.8974 |
| ROC-AUC | 0.9066 |
| Brier score | 0.1057 |
| Recall | 0.8037 |
| Precision | 0.8134 |
| F1 | 0.8085 |
| Development threshold | 0.370 |

These results are not a production claim for another institution.

## Safeguards

- Configured feature allowlist and explicit prediction horizon
- Critical-field and minimum-completeness gates
- Missing-field disclosure and data-quality review range
- Model evidence separated from institution policy flags
- Human screening, case ownership, intervention, and outcome records
- Local-data release gates for temporal validation, calibration, fairness, privacy, SSO, shadow piloting, and rollback

## Known limitations

- No temporal cohort field is available in the benchmark.
- Transfer performance is unknown for other institutions.
- The review range is a data-quality caution band, not a statistical confidence interval.
- Explanations describe model sensitivity, not the cause of a student's circumstances.
- Real educational benefit must be established through an approved, monitored institutional pilot.
