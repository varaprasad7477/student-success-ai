# Student Success AI Implementation Plan

## Product decision

Build one stable prediction core with institution adapters around it. Schools, colleges, and universities do not share identical column names, policies, schedules, or outcome definitions; therefore a universal model cannot safely accept arbitrary tables. Each institution receives a versioned configuration that maps its fields to a canonical schema, declares units, sets outreach thresholds, and defines local rules. A model is trained and approved for a defined data population. Cross-institution transfer must be measured, not assumed.

## Recommended capstone scope

### One user, one decision, one prediction window

For the review, present this as a **university semester-one early-support screening prototype**. Its job is to help an authorized advisor decide who may benefit from a conversation; it does not diagnose a cause, decide student status, or automatically intervene. Keep the existing institution mapping as a demonstration of adaptability, but do not claim that one model already works for schools, colleges, and universities.

Before any real-institution claim, agree with the data owner on:

1. **Population:** which enrolled students are eligible for screening.
2. **Prediction point:** the latest date/time at which every input is known.
3. **Outcome and window:** exactly what counts as dropout/non-completion and by when.
4. **Action:** what supportive follow-up staff can offer and how many cases they can handle.

The UCI 697 benchmark currently contrasts confirmed Dropout with Graduate and excludes 794 still-Enrolled records. It is useful for a reproducible demonstration, but it does not establish a local or next-term outcome. OULAD supplies a separate day-28 withdrawal benchmark; its 2014J temporal holdout is materially weaker than the UCI shuffled-fold result. Keep those datasets and claims separate.

### Model choice

Use the existing model comparison rather than announcing one universally best algorithm:

| Role | Recommendation | Why |
|---|---|---|
| Explainable baseline | Regularized logistic regression | Simple reference point; makes it easier to tell whether added complexity earns its place. |
| Candidate champion | Histogram gradient boosting | It leads the current UCI benchmark by PR-AUC and Brier score, but its advantage over random forest is small and it is not proven to transfer. |
| Challenger | Random forest | Its UCI recall/F1 are slightly higher at its own tuned threshold; compare it under the same untouched test design and workload constraints. |
| Not now | Deep learning, LLM-based prediction, or a complex ensemble | The available inputs are small structured tables; these add complexity without evidence of better out-of-time decisions. |

For the capstone, keep the current scikit-learn pipeline and report all candidates. Do not select solely on accuracy or a single F1-maximizing threshold. Select an operating threshold on validation data using the cost of missed cases, false alerts, and advisor capacity; report the resulting precision, recall, PR-AUC, calibration/Brier score, and alert volume on a separate untouched test set. The general training path currently reports out-of-fold metrics used to rank models and tune a threshold on the same OOF predictions, so describe those numbers as development estimates, not an independent final test. Prefer a cohort/time holdout for the final claim.

An LLM is not needed to predict risk. If a later version adds a staff-facing assistant, limit it to retrieving approved institutional support resources and summarizing reviewed case notes; do not let it invent student facts, set risk scores, or make decisions.

### Data entities and editing boundaries

Keep the domain model small and explicit:

- **Institution** — configuration, source-column mapping, units, rules, and thresholds.
- **Student record** — institution-scoped stable ID and validated, time-stamped source facts.
- **Model release** — model artifact/version, feature list, label/window, dataset reference, and evaluation report.
- **Screening** — score, threshold, model release, input snapshot, missing-data state, and timestamp.
- **Support case / intervention** — owner, status, follow-up, action, and outcome; separate from the model score.

The app already supports editing mappings, rules, screening notes, and support cases. For the demo, show these as the user-configurable entities. Do not let staff silently edit historical model inputs in place: correct source facts through a validated import/correction flow, retain who changed what and when, then create a new screening. Use pseudonymous IDs in demo/reviewer data.

### Keep versus defer

**Keep:** CSV validation and mapping, insufficient-data handling, transparent model comparison, local evidence, policy flags separate from predictions, advisor review, and case follow-up. These directly support the project goal and can be demonstrated end to end.

**Defer or remove from the capstone claim:** support for every education level, live production deployment, automated interventions/messages, complex AI assistant features, extra dashboards that do not change an advisor's action, and claims that benchmark performance is production accuracy. Authentication and the local database may remain as prototype infrastructure, but institutional identity integration, privacy approval, and operational security are production gates—not evidence that the model is accurate.

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

Exit criterion: the data owner approves the outcome window; agreed minimum recall and precision are met on an untouched time-based test, calibration and alert workload are acceptable, and no unexplained subgroup harm is present. If these conditions are not met, keep the system in data-quality review or non-predictive demo mode.

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
