# Stabilization audit — 2 November 2026

## Follow-up verification
The latest run passed all 58 Python tests and all 10 interface tests (68 total).
Further fixes: target saves tolerate page changes and suppress duplicate submissions; ordinary target edits stay on the settings page; invalid percentage/day bounds are caught before sending; structured server validation errors display readable field messages.
The running server was checked to serve the updated interface assets (20261102-2).

## Verification result
- Full Python regression run: **57 passed**.
- Additional demonstration-loading failure regression: **1 passed**.
- JavaScript interface behavior suite: **7 passed**; syntax check passed.
- Total: **65 passing automated checks** across those runs.
- Tests use temporary databases and isolated institutions, not existing user accounts.
- Library deprecation warnings remain for FastAPI startup hooks and the installed Starlette/httpx testing adapter. They did not fail the checks.
- The application was restarted and its health, home page and versioned interface assets were checked over HTTP.
- Live demonstration sign-in, dashboard, prediction list and sign-out passed after restart: 3,630 records (High 1,014; Medium 308; Low 2,156; Insufficient data 152), with the trained benchmark model loaded.

## Corrected defects

| Area | Defect and correction |
| --- | --- |
| Account creation | The backend signed in a new administrator but the interface returned to login. Signup now enters the CSV/targets setup journey. |
| Setup sequence | New administrators now follow account → CSV → local targets → results. |
| Dataset ownership | Uploads previously belonged to an email/session. They now belong to the institution and are shared with its authorised staff. |
| Restart persistence | CSV source, results and the active configuration now persist in SQLite across logout and process reload. |
| Target changes | Saving targets validates and recalculates the current CSV before committing configuration and results together. No re-upload is required. |
| Re-upload regression | A new CSV retains institution targets and derives fresh units; stale percentage settings and model-profile markers are not carried into a new upload. |
| Unsafe model selection | A new institution no longer inherits a public model solely because some column names match. |
| Misleading probability | Rule-based results have a screening index rather than an asserted dropout probability. Arbitrary uncertainty ranges were removed. |
| Explanation mismatch | Local-screen observations use the saved institution target. Training comparisons and policy comparisons are identified separately. |
| Missing input handling | Insufficient information stays separate from Low risk; at least three independent recognised learning signals are required. |
| CSV identifiers | Leading zeroes are preserved; blanks, whitespace-normalised duplicates and ambiguous duplicate mappings are rejected. |
| CSV parsing | Semicolon files and conventional percentage cells work; empty or malformed files and invalid ranges are rejected. |
| Invalid numeric values | Nonfinite input and invalid target settings produce validation errors rather than saving corrupt results. |
| Upload rollback | Failed uploads leave the last valid dataset available. The 5,000-student limit is enforced at 5,001. |
| Permissions | Only administrators upload CSVs or edit targets/create staff. Viewers cannot save cases or screening, and their edit controls are disabled/hidden. |
| Session authority | User roles are reloaded from storage, with a generated persistent local secret rather than a fixed development cookie secret. |
| Institution isolation | Another institution cannot retrieve or alter a student's uploaded record or support case. |
| Screening completion | The exact checklist is required. High/Medium progress uses the same eligible students for numerator and denominator; Low records cannot inflate it. |
| Missing student records | Unknown IDs return not-found responses and cannot receive new screening/case writes. |
| Student tables | Search, risk filtering and 50-row pagination replace truncated or oversized tables; review links remain functional after filtering. |
| Stale responses | Earlier student, case and CSV-inspection responses cannot overwrite later selections or pages after navigation. |
| Staff creation form | The form is captured before the asynchronous request so successful creation can reset it safely. |
| Charts | Zero values display as zero. Inactivity uses the maximum-target direction and zero targets do not produce invalid values. |
| Case list | Removed the silent 500-case cap that could disagree with summary totals. Historical cases remain retained. |
| Small-screen sign-out | Sign-out is visible in the compact layout. |
| Demonstration failure | A failed model load produces a clear error, rather than an endless preparation screen or automatic retry loop. |
| Starting the app | START_PROJECT.cmd and RUN_PROJECT.ps1 start from the project folder, avoiding the System32 path error. |

## Dataset coverage
Successful uploads and student-detail retrieval:
- 60 simulated college records.
- 500 public UCI university records with the natural historical balance.
- 500 UCI records selected for a balanced comparison.
- 300 public OULAD holdout records.
- 5,000 generated records, followed by safe rejection of 5,001.

Negative cases include empty files, header-only files, duplicate/ambiguous IDs, broken CSV quoting, missing row-level inputs, invalid ranges, infinite activity values and malformed institution settings.
Tests also verify target changes, re-upload, logout/login, module reload, teacher sharing, viewer restrictions, other-institution isolation and checklist progress.

## Limits of this verification
Browser automation was disabled in the host settings. The interface was tested with a simulated document and HTTP asset checks; a fresh real-browser visual check remains outstanding.
The checks verify software behavior, not new institutional predictive accuracy. Local-target screening is a rule-based fallback; public-model metrics do not establish that it works accurately for every school or university.
The project remains a local capstone application. Public deployment, retention/backups policy, operational security and local model validation are separate release gates.
No claim is made that all possible bugs have been eliminated.

## Files
- Walkthrough and calculation details: STABLE_RELEASE.md
- Backend regressions: tests/test_stability.py and existing tests/
- Interface behavior checks: tests/frontend.test.cjs
- Database backup made before the restart: data/backups/
