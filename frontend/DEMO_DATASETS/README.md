# Demo datasets

Start with **simple_college_demo_60.csv** in a new institution workspace.

| File | Records | Purpose |
| --- | ---: | --- |
| simple_college_demo_60.csv | 60 | Simulated students with differing learning signals and missing information. Best first walkthrough. |
| simple_college_demo_15.csv | 15 | Small simulated example for inspecting individual records. |
| uci_697_real_500_natural_upload.csv | 500 | Public university sample with its original sample outcome balance. |
| uci_697_real_500_balanced_comparison.csv | 500 | Deliberately balanced public-data comparison; not representative dropout prevalence. |
| oulad_clean_labeled_300.csv | 300 | Public benchmark holdout sample. |
| oulad_missing_features_300.csv | 300 | Negative test: incomplete learning inputs. Expect rejection or insufficient-data results depending on the selected workflow. |
| oulad_missing_id_20.csv | 20 | Negative test: missing student ID. Upload should be rejected. |

Create an institution → upload CSV → check recognised fields → save institution targets → view results.
Missing data is not evidence of low risk. Historical outcome columns are not prediction inputs.
New institutions use local-target screening; public benchmark machine-learning models are separate demonstrations.

Provenance: see ../data/UCI_697_ATTRIBUTION.md and ../data/OULAD_ATTRIBUTION.md.
Full training/preparation data remain in ../data because model preparation and demonstration loading require them.
