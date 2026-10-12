# Red-Flag Remediation Register

This register distinguishes implemented safeguards from evidence that only a participating institution can provide. A prototype must not represent an external approval as complete.

| Risk | Implemented control | Remaining production evidence |
|---|---|---|
| Prediction occurs too late | Explicit semester-one prediction horizon; training feature allowlist; semester-two change removed from the deployed model | Institution approves the intervention date and source-system cut-off |
| Benchmark does not transfer | Benchmark warning and blocked local-validation gates | Temporal validation on each institution's historical cohorts |
| Random evaluation is optimistic | Limitation displayed and temporal-holdout release gate blocked | Dated cohorts and untouched future-cohort test |
| Outcome is oversimplified | Confirmed outcomes only; unfinished `Enrolled` records excluded | Institution outcome dictionary covering transfer, stop-out, withdrawal, and return |
| Explanation mistaken for cause or ability | Teacher-facing observations now describe recorded attendance, work, and activity in plain language, with supportive next steps; no statement that a student is "incapable" | Student interviews, user training, and periodic explanation review |
| Missing data hidden | Per-student missing-field list, dataset issue table, critical-field block, minimum-completeness gate; blocked rows no longer show a probability | Source owners and service-level agreements |
| Same column means different things | Data dictionary with definition, availability, owner, and zero semantics | Field-by-field institutional approval |
| Temporal leakage | Feature allowlist tied to horizon; training now obeys config allowlist | Automated checks against institution event timestamps |
| Threshold ignores capacity | Weekly-capacity preview and workload boundary | Approved staffing, error costs, and intervention benefit |
| Calibration decays | Brier score shown and local-calibration gate blocked | Recurring calibration and drift monitoring on local outcomes |
| Fairness audit incomplete | Protected fields excluded from prediction; subgroup results shown | Legally reviewed groups, intersections, and local benefit audit |
| Prototype authentication | PBKDF2 password hashing, authenticated local workspace, and admin-only policy/schema-header edits | Enterprise OIDC/SAML, MFA, session policy, lockout, and formal RBAC review |
| Student privacy | Demo casework is session-only; institution records remain locally scoped; minimal displayed identifiers | Existing legacy demo notes still need owner-approved cleanup; encryption/key management, retention/deletion policy, DPIA/legal review, row-level access |
| Duplicate or ownerless outreach | Case owner, status, priority, due date, unassigned-case count, and saved-change history | Team routing and notification integration; read-access audit remains absent |
| Support effectiveness unknown | Intervention, acceptance, outcome, and student-feedback fields | Approved evaluation design measuring educational benefit |
| Stigma and automation bias | Support-priority language, no adverse-action use, human confirmation checklist | Staff training, student review/correction process, adverse-impact monitoring |
| Training/production separation | Versioned config/model artifacts, explicit release gates, Docker and CI | Model registry, artifact signing, staged promotion, rollback exercise |
| Monitoring incomplete | Data quality, workload, case progress, performance and subgroup views | Scheduled alerts, drift baselines, incident response ownership |
| Test coverage small | Expanded validation, missingness, duplicate, horizon, range, auth, case, API, and rule tests | Load, accessibility, concurrency, migration, and penetration testing |
| Accessibility unverified | Semantic Streamlit controls and textual chart/table alternatives | WCAG audit with keyboard and screen-reader users |
| Self-test confused with new validation | Clean and deliberately damaged CSVs plus a labeled holdout self-test page; missing data abstains or rejects | Independent external and local cohort validation |
| Misleading accuracy and dashboard ordering | Self-test now compares accuracy with a majority-class baseline and displays missed withdrawals and false alerts; dashboard uses explicit support-priority order | Staff review of workload costs and intervention benefit |

## Release rule

The application remains a development/shadow-mode system until all institution-owned production gates have documented evidence. Benchmark performance can never unlock a local production gate.
