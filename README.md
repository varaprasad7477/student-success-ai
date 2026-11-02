# Student Success AI

A local capstone application for student dropout-risk screening and optional teacher support follow-up.

## Start
Double-click **START_PROJECT.cmd** in this folder, then open http://127.0.0.1:8000.
The launcher uses the project folder automatically. Keep its window open while using the app.
Do not start a second server if port 8000 already has this project running.

For a manual start:
```powershell
Set-Location -LiteralPath 'C:\Users\vara prasad\Desktop\Student-Success-AI-Capstone'
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

## Main workflow
**Create institution account → upload CSV → review recognised fields → set local targets → automatic risk groups → optional teacher review.**

- Administrator: institution targets, replacement CSVs, staff accounts and all review features.
- Teacher: shared institution results, screening checklist and support cases.
- Viewer: read-only institution results and records.
- Data and settings persist in SQLite across logout and server restarts.
- High, Medium, Low and Need more information appear in the overview and filterable student list.
- Teachers see plain-language observations and bars comparing recorded values with local targets.
- Saving targets recalculates the current CSV without another upload.
- Unknown headers are ignored; unsafe mappings and invalid records return validation messages.

See [the walkthrough and limitations](STABLE_RELEASE.md) and [the completed audit](QUALITY_AUDIT.md).

## Screening versus trained prediction
New institution workspaces use a configurable **rule-based screening index**, not a calibrated dropout probability. Local targets affect that index immediately.
The development demonstration uses separate trained public-benchmark models. Matching column names alone is insufficient evidence that a public model works for another institution.
A risk group is not a confirmed dropout outcome. Explanations describe recorded learning signals, not a student's ability or the personal cause of leaving.
Missing required inputs produce Need more information rather than an assumed Low result. The app does not invent confidence intervals.

## CSV examples
Use the files under DEMO_DATASETS:
- simple_college_demo_60.csv — simulated records, including missing information.
- uci_697_real_500_natural_upload.csv — public university sample with its natural historical balance.
- uci_697_real_500_balanced_comparison.csv — deliberately balanced comparison; unsuitable for estimating real prevalence.
- oulad_clean_labeled_300.csv — public benchmark holdout slice.
- oulad_missing_features_300.csv and oulad_missing_id_20.csv — negative validation examples.

CSV rules: one unique student ID, at least three independent recognised learning signals, at most 5,000 records.
Use 0–1 for rate columns, or percentage headers / percent cells for 0–100. Assessment average is 0–100.
Work due plus work submitted counts as one derived submission-rate signal. Other grading scales require explicit conversion.
Historical outcomes and demographic fields are not used as live prediction inputs.

These uploads test application behavior. They do not prove accuracy on a new institution, and the existing holdout samples are not new independent evaluation sets.
See data/OULAD_ATTRIBUTION.md, REAL_DATA_UPLOAD_GUIDE.md, MODEL_CARD.md and EVALUATION_REPORT.md for existing public-data provenance and benchmark evaluation context.

## Development checks
```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/frontend.test.cjs
```

Backend tests use temporary databases and test accounts. Frontend tests simulate document behavior and cover navigation, permissions, filtering, search and stale responses. They do not substitute for a real-browser visual check.

## Data and deployment
Keep data/student_success.db and data/.session_secret private. Back up the database before moving the installation. Demo records are separate from institution records.
Do not commit account data or secrets to a repository.
This release is intended for a local capstone demonstration. Public deployment and institution-specific model validation are separate work.

Training utilities remain under scripts/ for reproducible benchmark work. Do not retrain during ordinary app startup.
