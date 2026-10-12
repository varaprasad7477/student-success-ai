# Student Success AI Implementation Plan

## Product decision

Build one stable prediction core with institution adapters around it. Schools, colleges, and universities do not share identical column names, policies, schedules, or outcome definitions; therefore a universal model cannot safely accept arbitrary tables. Each institution receives a versioned configuration that maps its fields to a canonical schema, declares units, sets outreach thresholds, and defines local rules. A model is trained and approved for a defined data population. Cross-institution transfer must be measured, not assumed.

## Gaps found in the supplied work

| Gap | Why it fails | Resolution in this rebuild |
|---|---|---|
| Three-record test set | A 66.7% result is not credible, and one class had zero recall | Minimum-data gate and stratified out-of-fold evaluation |
| Accuracy used as headline | It hides failures on the smaller dropout class | Recall, precision, F1, PR-AUC, ROC-AUC, and Brier score |
| Batch-relative features | Mean/max features change when unrelated students are added | Row-stable rates and institution-defined measures |
| Wrong-row explanation | API scored a submitted row but explained training row zero | Explanations are calculated from the scored row |
| Generic explanation text | Absolute feature importance does not show whether a factor raises risk | Local counterfactual effect against the training reference |
| Demographics as predictors | Creates fairness and governance risk without demonstrated benefit | Excluded from the default model; audit-only by policy |
| Hard-coded source schema | Breaks when institutions use different field names or units | JSON column mapping, unit conversion, and range checks |
| Policy mixed with ML | A school rule is not the same as a learned probability | Separate, traceable rule flags alongside model evidence |
| Silent synthetic fallback | Can make a demo look like a validated real model | Explicit “transparent demo score” status and training gate |
| No insufficient-data state | A precise score can be shown from weak evidence | Completeness score and blocked explanation state |
| Unattractive single screen | Weak navigation and decision flow | Four-page sidebar dashboard with restrained blue/teal system |
| Deployment planned too early | Infrastructure cannot rescue an invalid model | Deployment deliberately deferred until shadow-mode acceptance |

## Finish sequence

### Phase 1 Core concept complete

- Canonical schema and per-institution adapter
- Strict validation, unit handling, missingness reporting
- Stable feature definitions with no batch dependency
- Editable institution rules kept separate from model output
- Training pipeline with model comparison and data sufficiency gate
- Prediction service with local explanations and insufficient-data handling
- Portfolio, student review, onboarding, and governance dashboard
- Unit tests for invariants that caused the original errors

Exit criterion: the same student produces the same result regardless of other uploaded rows; invalid units are rejected; explanations refer to the same scored row; and staff can distinguish model evidence from policy rules.

### Phase 2 Real data readiness

- Agree on one operational outcome, such as non-enrollment in the next term, with a fixed observation and prediction window
- Obtain at least two historical cohorts per institution
- Create the institution mapping and data dictionary
- Remove leakage fields that occur after the prediction date
- Establish legal basis, retention, access, and pseudonymization controls

Exit criterion: data owner and academic owner sign off on the outcome, fields, and time boundary.

### Phase 3 Institution validation

- Train on earlier cohorts and test on a later cohort
- For shared models, hold out an entire institution as a transfer test
- Review calibration and choose an outreach threshold based on staff capacity and missed-student cost
- Audit performance and error rates across approved subgroups
- Run counterfactual and domain sanity checks on explanations

Exit criterion: agreed minimum recall and precision are met, calibration is acceptable, and no unexplained subgroup harm is present.

### Phase 4 Shadow pilot

- Show results to a small authorized advising team
- Do not automate messages, holds, grading, or enrollment action
- Record whether the flag was useful, which intervention was chosen, and the later outcome
- Monitor missingness, drift, overrides, and alert volume for one academic period

Exit criterion: users find the evidence actionable, false-alert workload is acceptable, and a rollback owner exists.

### Phase 5 Product hardening

- Add authentication, role-based access, audit logging, encrypted storage, and database-backed prediction history
- Add intervention workflow and outcome feedback without exposing protected student data
- Version datasets, mappings, rules, thresholds, and model artifacts together
- Add automated drift and calibration reports

Exit criterion: security and governance review passes and all model decisions are reproducible.

### Phase 6 Deployment later

Deployment begins only after the earlier exit criteria. Then choose hosting, managed database, secrets, backups, monitoring, CI/CD, and disaster recovery based on the institution's privacy and procurement requirements.

## Reviewer demonstration flow

1. Upload the same conceptual data with a new institution's column names.
2. Show the adapter mapping and unit validation.
3. Open the portfolio and select a high-priority student.
4. Explain the probability, the top local factors, data completeness, and separate policy flags.
5. Add an unrelated student and demonstrate that the first student's result does not change.
6. Open model governance and explain why recall, PR-AUC, calibration, and temporal validation matter more than a single accuracy value.
7. State clearly that the tool recommends outreach and does not decide a student's status.

