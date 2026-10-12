# UCI Dataset 697 Attribution and Preparation

The public test data in `northstar_uci_697_prepared.csv` is derived from **Predict Students' Dropout and Academic Success**, UCI Machine Learning Repository dataset 697.

- Authors: Valentim Realinho, Mónica Vieira Martins, Jorge Machado, and Luís Baptista
- DOI: https://doi.org/10.24432/C5MC89
- License: Creative Commons Attribution 4.0 International
- Official page: https://archive.ics.uci.edu/dataset/697/predict%2Bstudents%2Bdropout%2Band%2Bacademic%2Bsuccess

Preparation decisions:

- Rows whose target is `Enrolled` are excluded because they are not confirmed graduates or dropouts and would be a censored outcome in a binary model.
- `Dropout` becomes 1 and `Graduate` becomes 0.
- Student identifiers are generated and contain no source identity.
- Semester grades on the source 0-20 scale are converted to percentages.
- Credit approval and evaluation-participation ratios are derived from first-semester curricular-unit counts.
- Evaluation attempts can exceed enrolled modules, so the canonical module-participation count is capped at enrolled modules rather than weakening the application's submitted-count validation.
- Gender and age bands are excluded from prediction and retained only for subgroup auditing.

The data remains a development benchmark. It does not establish performance at another institution.

