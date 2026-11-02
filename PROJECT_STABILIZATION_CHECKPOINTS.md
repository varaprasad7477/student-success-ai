# Project Stabilization Checkpoints

Use this checklist before a demonstration, a pilot, and any real institutional use. A failed checkpoint has a stated fallback; it must not be bypassed.

## 1. Access and workspace

- [ ] Administrator signs in with the correct work email and password.
- [ ] Sign out removes access and returns to the sign-in page.
- [ ] Institution name, current term, data owner, and review horizon are recorded.

Fallback: do not upload student records. Recreate or recover the local administrator account and verify the correct workspace.

## 2. Data mapping

- [ ] Exactly one CSV column is mapped to **Student identifier**.
- [ ] Each learner ID is non-empty and unique.
- [ ] Every mapped field has been confirmed by someone who understands the source system.
- [ ] Values use the expected unit: rates are 0–1 and assessment scores are 0–100.

Fallback: use **Data check** to inspect headers and samples, correct the source file or mapping, then upload again. Do not manually guess a mapping from an unclear column name.

## 3. Student-review readiness

- [ ] The CSV is accepted with no duplicate ID or range error.
- [ ] Critical fields meet the configured completeness requirement.
- [ ] Policy flags are reviewed as local reminders, separate from model evidence.
- [ ] Every priority is reviewed by a teacher or student-support staff member.

Fallback: mark the record as **Insufficient data** or use only a human-led support conversation. Never infer a personal cause from missing information.

## 4. Model-use checkpoint

- [ ] A model was trained and validated on the institution's own historical data.
- [ ] The prediction horizon and outcome definition have been approved.
- [ ] Precision, recall, calibration, subgroup results, and intervention capacity are documented.
- [ ] A shadow pilot and privacy/security review are complete.

Fallback: use the workspace only for data quality checks, transparent policy flags, and case management. It must show **No institution-validated model** rather than a dropout probability.

## 5. Follow-through and recovery

- [ ] Every active support case has an owner and follow-up date.
- [ ] The student conversation, offered intervention, and outcome are recorded.
- [ ] The local database is backed up before significant demonstrations or data entry.

Fallback: if the browser is closed or the local service restarts, upload the CSV again. Case records for non-demo work remain in `data/student_success.db`; development-demo notes are intentionally cleared on sign out.

## Presentation-safe demonstration route

1. Sign in using the development demonstration.
2. Open **Data check** and upload `DEMO_DATASETS/oulad_clean_labeled_300.csv`.
3. Open **Overview**, then **Review a student**.
4. Explain that a priority begins a human conversation; it is not a dropout verdict.
5. Show **About this workspace** and explain the required checkpoints and fallback state.
