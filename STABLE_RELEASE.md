# Stabilized local release — 2 November 2026

## Saved project layout
- DEMO_DATASETS/: all seven upload examples and a dataset guide.
- frontend/, student_success/, api.py: application code.
- config/, models/, data/: required configuration, trained benchmark models, training inputs and saved institution records.
- tests/, scripts/: verification and reproducible data/model preparation.
- START_PROJECT.cmd: double-click to run.

The empty manual_signup_students.csv placeholder was removed during final organisation. Generated caches remain because automatic approval review blocked their removal. Existing account databases, model assets, attribution files and backups were preserved. Do not delete the .venv folder; the start launcher uses it.

Project folder: C:\Users\vara prasad\Desktop\Student-Success-AI-Capstone

## Start the project
Double-click START_PROJECT.cmd in this folder and open http://127.0.0.1:8000.
Keep its window open. If the app is already running on port 8000, use that instance rather than starting a second one.
The launcher chooses the project directory automatically, preventing the previous System32 / missing requirements error.
The existing environment contains the required libraries; a fresh environment is installed only when absent.

## New institution walkthrough
1. Choose **Create an institution workspace** on the sign-in page.
2. Enter the institution name, review period, term, data owner, administrator name, email and password. Select the learning signals you expect to have.
3. You are signed in automatically. Upload the student CSV. For a first test use DEMO_DATASETS/simple_college_demo_60.csv.
4. Check the recognised column summary and choose **Screen for dropout risk**.
5. The setup wizard opens **Institution settings**. Enter your attendance, assessment, work submission, credit, engagement and inactivity targets. Unavailable signals are not invented.
6. Save targets. The existing CSV is recalculated immediately, with no re-upload required.
7. Open **Dropout predictions**. Filter High, Medium, Low or Need more information, search student IDs, and use Previous / Next.
8. Open a student's record to compare recorded values with the institution targets and read plain-language observations.
9. Optional teacher screening and support cases record human follow-up. Automatic scoring never marks the teacher checklist complete.
10. Create teacher or read-only viewer accounts in Institution settings. Only administrators can upload replacement CSVs or edit institution targets.

Uploads, targets, screening and cases persist in data/student_success.db. Staff share their institution's dataset; institutions remain separate.
Replacing a CSV does not erase saved cases or screening history. Historical cases may therefore include students absent from the latest CSV.
A pre-update upload that existed only in the old server's memory cannot be recovered after restart: upload that CSV once. Subsequent uploads persist.

## CSV meaning and validation
- One current record per student; unique, nonblank IDs. Leading zeroes such as 001 are preserved.
- At least three independent recognised learning signals. Work due and work submitted together produce ONE submission-rate signal.
- Rates use 0–1 with names such as attendance_rate. Percentage headers such as Attendance % accept 0–100 or cells such as 65%.
- Assessment average is a percentage on a 0–100 scale. Convert other grading scales explicitly before upload.
- Missing required learning values produce **Need more information**, never Low by default.
- Familiar headers map automatically. Ambiguous duplicate mappings, unknown identifiers, invalid ranges, impossible assignment counts and more than 5,000 records are rejected without replacing the previous valid dataset.
- Unfamiliar columns are ignored. Rename them to documented headers only when their meaning and units match. The app cannot infer any institution's arbitrary CSV correctly.
- Historical dropout labels are not used as live prediction inputs.

## What the results mean
High / Medium / Low describe stronger or weaker risk signals, not confirmed dropout or student ability.
New institution workspaces use a transparent, configurable RULE-BASED SCREENING INDEX. It is not a measured dropout probability or a newly trained machine-learning model.
The rule screen combines weighted shortfalls from the institution targets: attendance 0.25, work submission 0.20, assessment 0.20, inactivity 0.10, credits 0.10 and engagement 0.15. Available weights are normalised; shortfalls are scaled by 3.2 and capped at 1. Default group cutoffs are 0.35 and 0.65. These are design choices, not empirically validated universal cutoffs.
Public demonstration workspaces use their separate trained benchmark models. Changing a local target does not retrain a benchmark model.
Plain-language observations and target bars show recorded differences; they do not establish why a student may leave.
Do not claim accuracy on a new institution until independently testing historical outcomes with a suitable time split and checking false alerts, missed dropouts and calibration.

## Verification and limits
See QUALITY_AUDIT.md for the regression checks and corrected defects.
Browser automation was unavailable in the current app settings. Interface behavior was tested using Node with a simulated document; a fresh visual, real-browser verification is still outstanding.
This release is for a local capstone demonstration. Public deployment, HTTPS, backup/retention policy and operational institution validation remain separate work.
