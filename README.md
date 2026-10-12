# Student Success AI

An institution-adaptable early-warning prototype for supportive student outreach. It combines public-benchmark machine-learning models with editable local policy rules. The application does not establish a student's ability or the personal reason for leaving; staff must ask the student and verify the record. It never makes disciplinary or enrollment decisions automatically.

## What was fixed from the prototype

- No batch-dependent features. A student's result no longer changes because a different group was uploaded.
- Explanations are generated for the submitted student, not an unrelated training row.
- Unknown institution columns are mapped through a configurable semantic layer.
- Institution policies are editable JSON rules and are shown separately from model evidence.
- Model selection uses repeated stratified cross-validation, out-of-fold probabilities, threshold tuning, calibration metrics, and an explicit minimum-data gate.
- Demographic fields are excluded from prediction by default and reserved for fairness auditing.
- Every result includes data-quality warnings and a "not enough evidence" state.
- The dashboard has a coherent sidebar, accessible risk colors, portfolio filters, student drill-down, schema mapping, and policy editing.
- Sign-in and institution account creation are built in with PBKDF2 password hashing.
- Registration captures institution type, source-to-canonical schema mapping, risk thresholds, and editable policy rules before the administrator account is created.
- Teachers receive a persistent seven-step screening checklist, support-plan notes, suggested next actions, and aggregate screening workload metrics.
- The deployed model has an explicit prediction horizon and config-enforced feature allowlist to prevent late-data leakage.
- Critical missing fields block scoring; every result discloses missing inputs and a data-quality caution range.
- Case ownership, follow-up dates, intervention acceptance, outcomes, and student feedback are tracked separately from model scores.
- Public-benchmark demo notes and cases are held only in the current browser session; real institution workspaces use the local database. Never enter real student information in a public demo.
- Capacity-aware threshold planning and evidence-backed production release gates are included.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/train_model.py --data data/northstar_uci_697_prepared.csv --config config/institutions/northstar_metropolitan.json --output models/northstar
streamlit run streamlit_app.py
```

The app does **not** score an institution upload unless a validated model is attached. A public benchmark model is never automatically attached to a newly created institution or an uploaded CSV. Local data and institution-specific validation are needed before predictive use. Empty learner IDs are rejected, malformed numeric values are reported, and duplicate IDs are checked after trimming whitespace.

## Try the three CSV test files

In the app, choose **Continue with development demonstration**, select **Open University · day 28**, then open **Test with CSV**. Download the included files from that page or use the paths below:

- [Clean labeled holdout](data/test_uploads/oulad_clean_labeled_300.csv): 300 learners from the presentation held out of training; the outcome column permits an honest self-test of this public benchmark.
- [Missing learning features](data/test_uploads/oulad_missing_features_300.csv): IDs exist, but critical activity fields are absent; all rows should say **Insufficient data**.
- [Missing student ID](data/test_uploads/oulad_missing_id_20.csv): deliberately invalid schema; upload should be rejected with a missing `student_id` message.

The clean test is a slice of the same 2014J holdout used in the published evaluation, not a new independent validation. Use it to check that the app and model run, **not** to make a fresh accuracy claim. A dashboard CSV upload does not attach the public model; use the dedicated **Test with CSV** page for this benchmark self-test.

## Second public benchmark: OULAD day 28

The development demonstration now offers two separate datasets in the sidebar. The Open University Learning Analytics Dataset (OULAD, UCI ID 349) is converted to a day-28 snapshot with a subsequent-withdrawal label; it is **not** pooled with the semester-one UCI 697 data. Download the official ZIP from [UCI](https://archive.ics.uci.edu/dataset/349/open+university+learning+analytics+dataset), then reproduce the snapshot and temporal evaluation:

```powershell
python scripts/prepare_oulad.py --archive path/to/oulad.zip --output data/oulad_day28_prepared.csv
python scripts/train_oulad.py --data data/oulad_day28_prepared.csv --output models/oulad_day28
```

The included public-data holdout is the latest `2014J` presentation. Training rows with recurring learner IDs are excluded from the holdout population. The holdout achieved PR-AUC 0.249, ROC-AUC 0.633, recall 0.379, precision 0.301 and Brier 0.153 at the validation-selected threshold. Calibration varies materially by risk decile. This is evidence of remaining model weakness, not a deployment claim. See [data/OULAD_ATTRIBUTION.md](data/OULAD_ATTRIBUTION.md) and the in-app governance page for details.

Start the authenticated API in a second terminal:

```powershell
$env:STUDENT_SUCCESS_API_KEY="replace-with-a-long-random-secret"
uvicorn api:app --host 127.0.0.1 --port 8000
```

Interactive API documentation is then available at `http://127.0.0.1:8000/docs`. For a containerized local environment, set `STUDENT_SUCCESS_API_KEY` and run `docker compose up --build`.

## Institution onboarding

1. Copy `config/institutions/example.json`.
2. Map the institution's source columns to the canonical fields.
3. Adjust risk thresholds and rule values with academic leadership.
4. Upload historical outcomes and run `python scripts/train_model.py --data <file> --config <config>`.
5. Review recall, precision, PR-AUC, Brier score, subgroup metrics, and threshold trade-offs before approval.
6. Start in shadow mode. Staff see predictions, but no workflow action is automated.

## Canonical input fields

Required for training: `student_id`, `outcome`. Candidate predictors include `attendance_rate`, `assignments_due`, `assignments_submitted`, `assessment_average`, `assessment_change`, `days_since_login`, `support_contacts`, and `credits_completed_ratio`. The actual training inputs are restricted to the institution configuration's `model_fields` allowlist and must be available before its approved prediction horizon.

Rates use 0–1. Scores use 0–100. `outcome` is 1 for historical dropout/non-completion and 0 otherwise. The mapper rejects ambiguous or out-of-range values instead of silently guessing.

## Evaluation standard

Accuracy is not a release criterion. The report emphasizes dropout recall, precision, F1, PR-AUC, ROC-AUC, Brier score, and calibration. Thresholds are tuned only on out-of-fold predictions. A model is blocked when there are fewer than 100 labeled rows, fewer than 20 examples of either class, or fewer than four examples per cross-validation fold.

For longitudinal data, split by cohort or time before production approval. For multi-institution data, hold out whole institutions to measure transfer performance.

## Safety and governance

- The score is an outreach signal, not a fact about a student.
- Staff must record the intervention and outcome.
- Protected attributes must not be used as predictors without a documented legal and ethical basis.
- Monitor missingness, drift, calibration, recall, false positives, and subgroup gaps.
- Retrain only after data approval, version every model/config, and keep an audit trail.

## Project map

```text
config/institutions/   institution mappings, thresholds, and rules
data/                  demonstration data only
models/                generated model bundle and metrics
scripts/               training entry points
student_success/       mapping, rules, modeling, prediction, explanations
streamlit_app.py       polished multipage dashboard
api.py                 authenticated prediction and audit API
MODEL_CARD.md           intended use, evaluation, limitations, release gate
tests/                 unit tests for core invariants
```

## Account and onboarding flow

Open the application and choose **Create institution account**. Complete the institution profile, review the proposed schema mapping, edit risk thresholds and policy flags, and then create the administrator account. Passwords are salted and hashed locally; plaintext passwords are never stored. After sign-in, upload a CSV that matches the saved source-column mapping. The demonstration button opens the supplied development dataset without creating an account.

The current implementation is suitable for a capstone and controlled local pilot. A public deployment should replace local authentication with the institution's identity provider, enforce HTTPS and secure secrets, add password recovery and email verification, and complete an institutional security review.

## Current verification

- Semester-one benchmark model trained on 3,630 confirmed UCI outcomes after out-of-fold model comparison.
- Eight automated tests pass, covering stable predictions, unit validation, duplicate rejection, missing/critical fields, horizon/range disclosure, policy traceability, authentication, cases, API prediction, and audit persistence.
- Dashboard portfolio and student explanation views were visually inspected in a live local run.
- Docker Compose and GitHub Actions configuration are included. External hosting is intentionally not performed without a selected institution-approved platform and credentials.

## Public benchmark demonstration

The default demonstration now uses the official UCI **Predict Students' Dropout and Academic Success** dataset through the fictional **Northstar Metropolitan University** workspace. The reproducible preparation script, institution adapter, trained model, attribution, and detailed findings are included. Read [EVALUATION_REPORT.md](EVALUATION_REPORT.md) before presenting the metrics.

For a control-by-control account of the remaining risks and release blockers, read [RED_FLAG_REMEDIATION.md](RED_FLAG_REMEDIATION.md). Benchmark results never unlock institution-owned production gates.

