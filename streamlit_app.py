from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics import accuracy_score, precision_score, recall_score

from student_success.prediction import PredictionService, plain_language_evidence
from student_success.schema import canonicalize, load_config
from student_success.demo_storage import DemoSupportStore
from student_success.storage import AuditStore


ROOT = Path(__file__).resolve().parent
DEMO_CONFIG = ROOT / "config" / "institutions" / "northstar_metropolitan.json"
MODEL_PATH = ROOT / "models" / "northstar" / "model_bundle.joblib"
DEMO_METRICS_PATH = ROOT / "models" / "northstar" / "metrics.json"
DEMO_PATH = ROOT / "data" / "northstar_uci_697_prepared.csv"
OULAD_CONFIG = ROOT / "config" / "institutions" / "open_university_day28.json"
OULAD_MODEL = ROOT / "models" / "oulad_day28" / "model_bundle.joblib"
OULAD_METRICS = ROOT / "models" / "oulad_day28" / "metrics.json"
OULAD_PATH = ROOT / "data" / "oulad_day28_prepared.csv"
STORE = AuditStore(ROOT / "data" / "student_success.db")

st.set_page_config(page_title="Student Success AI", page_icon="🎓", layout="wide")
st.markdown("""
<style>
:root { --ink:#17223b; --muted:#59677d; --blue:#334e8b; --teal:#087f73; }
.stApp { background:#f6f8fc; color:var(--ink); }
[data-testid="stSidebar"] { background:#182641; }
[data-testid="stSidebar"] * { color:#f7fbff !important; }
.hero { padding:1.55rem 1.7rem; border-radius:18px; color:white; background:linear-gradient(115deg,#243b70,#087f73); margin-bottom:1rem; }
.hero h1 { margin:0 0 .35rem; font-size:2rem; }.hero p { margin:0;color:#dceff0; }
.card { background:white;border:1px solid #dbe2ed;border-radius:14px;padding:1rem 1.1rem;box-shadow:0 5px 18px rgba(25,55,80,.06); }
.pill { display:inline-block;padding:.25rem .6rem;border-radius:999px;background:#e0f3ee;color:#075d55;font-weight:700; }
.value-compare { display:flex;gap:.7rem;flex-wrap:wrap;margin-top:.8rem; }
.value-chip { flex:1;min-width:130px;padding:.6rem .75rem;border-radius:10px;background:#f2f5fa;border:1px solid #dce4ee; }
.value-chip.student { background:#e1f4ef;border-color:#79c4b4; }
.value-chip small { display:block;color:#4e6075;font-weight:600;letter-spacing:.01em; }
.value-chip strong { display:block;color:#142943;font-size:1.25rem;line-height:1.35; }
.fine { color:#637083;font-size:.9rem; }
[data-testid="stMetric"] { background:white;border:1px solid #dce4ec;border-radius:14px;padding:.85rem 1rem;box-shadow:0 4px 14px rgba(25,55,80,.05); }
[data-testid="stMetricLabel"],[data-testid="stMetricValue"] { color:var(--ink)!important; }
</style>
""", unsafe_allow_html=True)


SCHEMA_TEMPLATES = {
    "School": {
        "student_number": "student_id", "attendance_percent": "attendance_rate",
        "tasks_due": "assignments_due", "tasks_submitted": "assignments_submitted",
        "average_mark": "assessment_average", "mark_change": "assessment_change",
        "days_absent_from_portal": "days_since_login", "support_contacts": "support_contacts",
    },
    "College": {
        "student_id": "student_id", "attendance_rate": "attendance_rate",
        "assignment_submissions": "assignments_submitted", "assessment_score": "assessment_average",
        "engagement_score": "engagement_score", "dropout_risk": "outcome",
    },
    "University": {
        "learner_id": "student_id", "attendance_pct": "attendance_rate",
        "modules_enrolled": "assignments_due", "modules_evaluated": "assignments_submitted",
        "first_semester_average": "assessment_average", "semester_score_change": "assessment_change",
        "credits_completed_percent": "credits_completed_ratio", "academic_engagement": "engagement_score",
        "confirmed_dropout": "outcome",
    },
}

DEFAULT_POLICIES = [
    {"id":"attendance-critical","field":"attendance_rate","operator":"lt","value":0.65,"severity":"high","message":"Attendance is below the institution outreach threshold."},
    {"id":"submission-gap","field":"submission_rate","operator":"lt","value":0.60,"severity":"medium","message":"The assignment submission rate needs review."},
    {"id":"inactive","field":"days_since_login","operator":"gt","value":14.0,"severity":"medium","message":"No learning-platform activity for more than 14 days."},
    {"id":"low-credit-progress","field":"credits_completed_ratio","operator":"lt","value":0.50,"severity":"high","message":"Fewer than half of enrolled credits were completed in the observed semester."},
]

CHECKLIST = {
    "identity_verified": "Confirm the student record and current enrollment",
    "attendance_reviewed": "Review recent attendance evidence",
    "academic_reviewed": "Review assignments and assessment trajectory",
    "student_contacted": "Contact the student using a supportive message",
    "barriers_discussed": "Discuss academic, financial, wellbeing, or access barriers",
    "support_agreed": "Agree and record an appropriate support action",
    "follow_up_scheduled": "Schedule a follow-up date",
}


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "institution"


def onboarding_config(name: str, institution_type: str, mapping: pd.DataFrame, policies: pd.DataFrame,
                      medium: float, high: float, prediction_horizon: str) -> dict:
    column_map = {
        str(row["source_column"]).strip(): str(row["canonical_field"]).strip()
        for _, row in mapping.dropna().iterrows() if str(row["source_column"]).strip()
    }
    rules = []
    for row in policies.to_dict(orient="records"):
        if row.get("id") and row.get("field") and row.get("operator"):
            row["value"] = float(row["value"])
            rules.append(row)
    model_fields = sorted(set(column_map.values()) & {
        "attendance_rate", "assignments_due", "assignments_submitted", "submission_rate",
        "assessment_average", "assessment_change", "days_since_login", "support_contacts",
        "credits_completed_ratio", "engagement_score",
    })
    if institution_type == "University":
        model_fields = [field for field in model_fields if field != "assessment_change"]
    critical = [field for field in ["attendance_rate", "assignments_due", "assignments_submitted", "assessment_average", "credits_completed_ratio"] if field in model_fields]
    return {
        "institution_id": slug(name), "display_name": name, "institution_type": institution_type,
        "column_map": column_map,
        "units": {key: "percent" for key in ["attendance_rate", "credits_completed_ratio"] if key in model_fields},
        "model_fields": model_fields, "critical_fields": critical,
        "minimum_data_completeness": .75, "prediction_horizon": prediction_horizon,
        "data_dictionary": [{"field": field, "definition": "Institution approval required", "available_by": prediction_horizon, "owner": "Unassigned", "zero_is_valid": False} for field in model_fields],
        "risk_thresholds": {"medium": medium, "high": high}, "rules": rules,
    }


def render_authentication() -> dict | None:
    st.markdown('<div class="hero"><h1>Student Success AI</h1><p>Create an institution-aware early-support workspace or sign in to an existing one.</p></div>', unsafe_allow_html=True)
    signin, signup = st.tabs(["Sign in", "Create institution account"])
    with signin:
        with st.form("signin"):
            email = st.text_input("Work email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            user = STORE.authenticate(email, password)
            if user:
                st.session_state.auth_user = user
                st.rerun()
            st.error("Email or password is incorrect.")
        if st.button("Continue with development demonstration", width="stretch"):
            st.session_state.demo_store = DemoSupportStore()
            st.session_state.auth_user = {
                "institution_id":"northstar-metropolitan", "institution_name":"Northstar Metropolitan University",
                "institution_type":"College", "display_name":"Demonstration Teacher", "email":"demo@local",
                "role":"teacher", "config":load_config(DEMO_CONFIG), "demo":True,
            }
            st.rerun()
    with signup:
        st.subheader("1 Institution profile")
        left, right = st.columns(2)
        institution_name = left.text_input("Institution name")
        institution_type = right.selectbox("Institution type", list(SCHEMA_TEMPLATES))
        st.subheader("2 Data schema plan")
        st.caption("Map the columns your institution exports to the stable fields understood by the model. You can revise this after registration.")
        mapping_default = pd.DataFrame([
            {"source_column": source, "canonical_field": canonical}
            for source, canonical in SCHEMA_TEMPLATES[institution_type].items()
        ])
        mapping = st.data_editor(mapping_default, num_rows="dynamic", width="stretch", key=f"mapping-{institution_type}")
        prediction_horizon = st.text_input("Prediction horizon", value="End of the current reporting period — support planning for the next period", help="Every model input must exist before this point.")
        st.subheader("3 Risk bands and institution policy flags")
        c1, c2 = st.columns(2)
        medium = c1.slider("Medium-risk threshold", 0.10, 0.70, 0.35, 0.05)
        high = c2.slider("High-risk threshold", 0.40, 0.95, 0.65, 0.05)
        available_fields = set(SCHEMA_TEMPLATES[institution_type].values()) | {"submission_rate"}
        policy_defaults = [rule for rule in DEFAULT_POLICIES if rule["field"] in available_fields]
        policies = st.data_editor(pd.DataFrame(policy_defaults), num_rows="dynamic", width="stretch", key=f"signup-policies-{institution_type}")
        st.caption("Policy flags are deterministic local rules. They remain separate from machine-learning explanations.")
        st.subheader("4 Administrator account")
        with st.form("signup"):
            display_name = st.text_input("Administrator name")
            email = st.text_input("Administrator work email")
            password = st.text_input("Create password", type="password", help="At least 10 characters")
            confirm = st.text_input("Confirm password", type="password")
            consent = st.checkbox("I understand this system supports human outreach and must not automate adverse decisions.")
            create = st.form_submit_button("Create institution workspace", type="primary", width="stretch")
        if create:
            if not institution_name or not display_name or "@" not in email:
                st.error("Complete the institution, administrator, and email fields.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif high <= medium:
                st.error("The high-risk threshold must be greater than the medium-risk threshold.")
            elif not consent:
                st.error("Confirm the responsible-use statement before creating the workspace.")
            else:
                config = onboarding_config(institution_name, institution_type, mapping, policies, medium, high, prediction_horizon)
                institution_id = f"{slug(institution_name)}-{abs(hash(email.lower())) % 100000:05d}"
                config["institution_id"] = institution_id
                try:
                    STORE.create_institution_with_admin(institution_id, institution_name, institution_type, config, display_name, email, password)
                except (ValueError, sqlite3.IntegrityError) as exc:
                    st.error(f"The workspace could not be created: {exc}")
                else:
                    st.success("Workspace created. Sign in with the administrator account.")
    return None


@st.cache_resource
def prediction_service(config_text: str, model_path: str, model_stamp: float):
    return PredictionService(json.loads(config_text), model_path or None, allow_demo_score=False)


def suggested_actions(reason_codes: list[dict], flags: list[dict]) -> list[str]:
    fields = {item.get("feature") for item in reason_codes} | {item.get("field") for item in flags}
    suggestions = []
    if "attendance_rate" in fields:
        suggestions.append("Check the attendance timeline and ask about transport, timetable, health, or access barriers.")
    if fields & {"submission_rate", "assignments_submitted"}:
        suggestions.append("Review missing work, clarify the smallest recoverable task, and agree a realistic submission plan.")
    if fields & {"assessment_average", "assessment_change"}:
        suggestions.append("Offer an academic review, tutoring, office hours, or a study-plan referral.")
    if fields & {"days_since_login", "engagement_score"}:
        suggestions.append("Verify platform access and invite the student to reconnect with one low-friction learning activity.")
    if fields & {"support_contacts", "credits_completed_ratio"}:
        suggestions.append("Coordinate with the adviser or student-support team and avoid duplicating outreach.")
    suggestions.append("Ask the student what support would be useful; do not infer a cause from the model score.")
    return list(dict.fromkeys(suggestions))


user = st.session_state.get("auth_user")
if not user:
    render_authentication()
    st.stop()

config = user["config"]
with st.sidebar:
    st.markdown("## Student Success AI")
    st.caption("Public benchmark workspace" if user.get("demo") else user["institution_name"])
    st.write(f"Signed in as **{user['display_name']}**")
    st.caption(user["role"].title())
    benchmark = st.selectbox("Demonstration dataset", ["Northstar · semester 1", "Open University · day 28"],
                             help="Each public benchmark has its own schema, model and evaluation.") if user.get("demo") else None
    if benchmark:
        st.caption(benchmark)
    page = st.radio("Navigate", ["Teacher dashboard", "Student screening", "Cases and outcomes", "Data and schema", "Institution policies", "Model governance", "Test with CSV"], label_visibility="collapsed")
    st.divider()
    uploaded = st.file_uploader("Upload institution CSV", type="csv")
    if st.button("Sign out", width="stretch"):
        st.session_state.pop("auth_user", None)
        st.session_state.pop("demo_store", None)
        st.rerun()

active_institution_id = user["institution_id"]
active_institution_name = user["institution_name"]
active_model = Path()
active_metrics = None
active_demo_path = DEMO_PATH
if user.get("demo") and "demo_store" not in st.session_state:
    st.session_state.demo_store = DemoSupportStore()
support_store = st.session_state.demo_store if user.get("demo") else STORE
if user.get("demo"):
    if benchmark == "Open University · day 28":
        config = load_config(OULAD_CONFIG)
        active_model, active_metrics, active_demo_path = OULAD_MODEL, OULAD_METRICS, OULAD_PATH
    else:
        config = load_config(DEMO_CONFIG)
        active_model, active_metrics = MODEL_PATH, DEMO_METRICS_PATH
    active_institution_id = config["institution_id"]
    active_institution_name = config["display_name"]

if uploaded is not None and page != "Test with CSV":
    source = pd.read_csv(uploaded)
elif user.get("demo") and active_demo_path.exists():
    source = pd.read_csv(active_demo_path).drop(columns=["dropout_risk"], errors="ignore")
    if benchmark == "Open University · day 28":
        source = source.loc[source.code_presentation.eq("2014J")].drop(
            columns=["withdrawn_after_28", "id_student", "gender_audit", "age_band_audit"])
else:
    source = pd.DataFrame()

if source.empty:
    st.markdown('<div class="hero"><h1>Institution workspace ready</h1><p>Upload the first institution CSV to validate its schema and create the teacher screening dashboard.</p></div>', unsafe_allow_html=True)
    st.caption("Public benchmarks are available through the development demonstration on the sign-in screen; an institution workspace requires its own mapped data.")
    st.subheader("Expected source columns")
    st.dataframe(pd.DataFrame(config["column_map"].items(), columns=["Source column","Meaning"]), hide_index=True, width="stretch")
    st.info("The upload is validated against your saved mapping, units, and allowed ranges before any score is produced.")
    st.stop()

model_for_source = active_model if user.get("demo") and uploaded is None and active_model.is_file() else None
service = prediction_service(json.dumps(config, sort_keys=True), str(model_for_source) if model_for_source else "",
                             model_for_source.stat().st_mtime if model_for_source else 0)
try:
    predictions, warnings = service.predict(source, include_explanations=False)
except Exception as exc:
    st.error(f"The uploaded data could not be scored: {exc}")
    st.stop()

summary = support_store.screening_summary(active_institution_id)
if not service.bundle:
    st.warning("No institution-validated model is attached to this upload. The app will check data and local rules, but will not invent a dropout probability or support priority.")
else:
    st.caption(f"Public benchmark: {active_institution_name}. These results do not transfer to another institution without local validation.")

if page == "Teacher dashboard":
    st.markdown('<div class="hero"><h1>Teacher support dashboard</h1><p>See the workload, prioritize supportive review, and track screening completion.</p></div>', unsafe_allow_html=True)
    high = int((predictions.risk_band == "High").sum())
    medium_count = int((predictions.risk_band == "Medium").sum())
    missing_count = int((predictions.risk_band == "Insufficient data").sum())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Students", len(predictions)); c2.metric("High priority", high); c3.metric("Medium priority", medium_count)
    c4.metric("Need more information", missing_count); c5.metric("Screenings complete", summary["complete"])
    st.caption(f"Prediction horizon: {config.get('prediction_horizon', 'Not approved')} · Minimum completeness: {config.get('minimum_data_completeness', .70):.0%}")
    st.subheader("Priority workload")
    w1, w2, w3 = st.columns(3)
    w1.markdown(f"<div class='card'><span class='pill'>Act first</span><h3>{high}</h3><p>High-priority records need human screening, not automatic action.</p></div>", unsafe_allow_html=True)
    w2.markdown(f"<div class='card'><span class='pill'>Monitor</span><h3>{medium_count}</h3><p>Medium-priority records should be reviewed for worsening signals.</p></div>", unsafe_allow_html=True)
    w3.markdown(f"<div class='card'><span class='pill'>Follow through</span><h3>{summary['open']}</h3><p>Started screenings still have checklist items outstanding.</p></div>", unsafe_allow_html=True)
    st.subheader("Students by support priority")
    counts = predictions.risk_band.value_counts().rename_axis("Risk band").reset_index(name="Students")
    fig = px.bar(counts, x="Risk band", y="Students", color="Risk band", color_discrete_map={"High":"#b84a53","Medium":"#bd812d","Low":"#087f73","Insufficient data":"#7b8794","Not scored":"#7b8794"})
    fig.update_layout(height=420, showlegend=False, margin=dict(l=20,r=20,t=20,b=20), plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    st.subheader("Student review list")
    ordered = predictions.assign(priority_order=predictions.risk_band.map({
        "High": 0, "Medium": 1, "Low": 2, "Insufficient data": 3, "Not scored": 4,
    }).fillna(5))
    view = ordered.sort_values(["priority_order", "risk_probability"], ascending=[True, False])[["student_id","risk_band","data_completeness","missing_fields"]].copy()
    view.columns = ["Student", "Support priority", "Data available", "Missing information"]
    view["Data available"] = view["Data available"].map(lambda value: f"{value:.0%}")
    view["Missing information"] = view["Missing information"].map(lambda fields: ", ".join(fields) if fields else "None")
    st.dataframe(view, hide_index=True, width="stretch", height=430)

elif page == "Student screening":
    st.markdown('<div class="hero"><h1>Student screening and support plan</h1><p>Review model evidence, local policy flags, and teacher observations together.</p></div>', unsafe_allow_html=True)
    student_id = st.selectbox("Student", predictions.student_id.tolist())
    raw_frame = source[source.iloc[:, 0].astype(str) == student_id]
    detailed, _ = service.predict(raw_frame, include_explanations=True)
    result = detailed.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Support priority", result.risk_band)
    c2.metric("Information available", f"{result.data_completeness:.0%}")
    c3.metric("Local policy alerts", len(result.policy_flags))
    if result.missing_fields:
        st.warning("Missing inputs: " + ", ".join(result.missing_fields))
    evidence, plan = st.columns([1, 1])
    with evidence:
        st.subheader("What the records suggest reviewing")
        human_evidence = plain_language_evidence(result.reason_codes)
        if human_evidence:
            for item in human_evidence:
                st.markdown(f"<div class='card'><span class='pill'>Observed pattern</span><p>{item['observation']}</p><p class='fine'>{item['next_step']}</p></div><br>", unsafe_allow_html=True)
        else:
            st.info("The available records do not show a clear, plain-language pattern. Review the student's situation directly; the model cannot identify a personal cause.")
        st.caption("These are clues in recorded data, not a judgement about ability or an explanation of why someone may leave.")
        st.subheader("Institution policy flags")
        if result.policy_flags:
            for flag in result.policy_flags:
                st.warning(flag["message"])
        else:
            st.success("No configured institution policy rule is triggered.")
        st.subheader("Suggested supportive next steps")
        for suggestion in suggested_actions(result.reason_codes, result.policy_flags):
            st.write(f"• {suggestion}")
    with plan:
        st.subheader("Teacher screening checklist")
        saved = support_store.get_screening(active_institution_id, student_id)
        with st.form(f"screening-{student_id}"):
            checklist = {key: st.checkbox(label, value=bool(saved["checklist"].get(key, False))) for key, label in CHECKLIST.items()}
            notes = st.text_area("Teacher observations and agreed support", value=saved["notes"], height=150, placeholder="Record verified facts, the student's perspective, agreed action, owner, and follow-up date.")
            save = st.form_submit_button("Save screening record", type="primary", width="stretch")
        if save:
            support_store.save_screening(active_institution_id, student_id, checklist, notes, user["email"])
            st.success("Screening record saved with an audit timestamp.")
        completed = sum(checklist.values())
        st.progress(completed / len(checklist), text=f"{completed} of {len(checklist)} screening steps complete")
        if saved["updated_at"]:
            st.caption(f"Last saved by {saved['updated_by']} at {saved['updated_at']}.")
    st.caption("Only the student and a supportive conversation can clarify personal circumstances. This screen must not trigger an adverse decision.")

elif page == "Cases and outcomes":
    st.markdown('<div class="hero"><h1>Support cases and outcomes</h1><p>Record who is helping, what was agreed, and what happened next.</p></div>', unsafe_allow_html=True)
    if user.get("demo"):
        st.info("Demo case notes stay in this browser session only and disappear when you sign out. Do not enter real student information in a public demonstration.")
    else:
        st.info("Records are stored in this project's local SQLite database. Signed-in institution users can work in their own institution workspace. This is a development access model, not a production privacy approval.")
    case_summary = support_store.case_summary(active_institution_id)
    cols = st.columns(4)
    for col, label, key in zip(cols, ["Cases", "Open", "Unassigned", "Resolved"], ["total", "open", "unassigned", "resolved"]):
        col.metric(label, case_summary[key])
    existing_cases = support_store.list_cases(active_institution_id)
    if existing_cases:
        st.subheader("Saved cases")
        st.dataframe(pd.DataFrame(existing_cases), hide_index=True, width="stretch")
    student_id = st.selectbox("Student case", predictions.student_id.tolist())
    saved_case = support_store.get_case(active_institution_id, student_id)
    with st.form(f"case-{student_id}"):
        owner = st.text_input("Case owner email", value=saved_case["owner_email"], placeholder="teacher@institution.edu")
        status = st.selectbox("Case status", ["Needs review", "Contact planned", "Student contacted", "Support active", "Resolved", "Closed"], index=max(0, ["Needs review", "Contact planned", "Student contacted", "Support active", "Resolved", "Closed"].index(saved_case["status"]) if saved_case["status"] in ["Needs review", "Contact planned", "Student contacted", "Support active", "Resolved", "Closed"] else 0))
        priority = st.selectbox("Human-reviewed priority", ["Normal", "Elevated", "Urgent"], index=["Normal", "Elevated", "Urgent"].index(saved_case["priority"]) if saved_case["priority"] in ["Normal", "Elevated", "Urgent"] else 0)
        due_date = st.text_input("Follow-up due date (YYYY-MM-DD)", value=saved_case["due_date"])
        intervention_options = ["", "Academic advising", "Tutoring", "Financial support referral", "Wellbeing referral", "Accessibility support", "Technology/access support", "Other"]
        intervention = st.selectbox("Intervention offered", intervention_options, index=intervention_options.index(saved_case["intervention_type"]) if saved_case["intervention_type"] in intervention_options else 0)
        response_options = ["Not recorded", "Accepted", "Declined", "Unable to contact"]
        accepted = st.selectbox("Student response", response_options, index=response_options.index(saved_case["intervention_accepted"]) if saved_case["intervention_accepted"] in response_options else 0)
        outcome = st.text_area("Follow-up outcome", value=saved_case["follow_up_outcome"], placeholder="Record observable outcome; do not infer motivation or diagnosis.")
        feedback = st.text_area("Student feedback", value=saved_case["student_feedback"], placeholder="Record the student's words or an accurate summary with consent.")
        save_case = st.form_submit_button("Save case record", type="primary", width="stretch")
    if save_case:
        support_store.save_case(active_institution_id, student_id, {"owner_email": owner, "status": status, "priority": priority, "due_date": due_date, "intervention_type": intervention, "intervention_accepted": accepted, "follow_up_outcome": outcome, "student_feedback": feedback}, user["email"])
        st.success("Case ownership and outcome saved.")
        st.rerun()
    st.subheader("Who last updated this case")
    if saved_case["updated_at"]:
        st.write(f"**{saved_case['updated_by']}** · {saved_case['updated_at']}")
    else:
        st.caption("No case has been saved for this student yet.")
    history = support_store.case_history(active_institution_id, student_id)
    if history:
        st.dataframe(pd.DataFrame(history), hide_index=True, width="stretch")

elif page == "Data and schema":
    st.markdown('<div class="hero"><h1>Data and column guide</h1><p>See which spreadsheet columns the app uses and what needs fixing.</p></div>', unsafe_allow_html=True)
    st.write("Each institution can name its columns differently. This table shows how this workspace translates the uploaded CSV into the common fields used for screening. A missing student ID stops the upload; missing learning information may prevent a review priority.")
    definitions = {item["field"]: item["definition"] for item in config.get("data_dictionary", [])}
    mapping_rows = [{"CSV column": source_name, "Meaning in the app": target_name,
                     "What it represents": definitions.get(target_name, "Student identifier or outcome label")}
                    for source_name, target_name in config["column_map"].items()]
    st.dataframe(pd.DataFrame(mapping_rows), hide_index=True, width="stretch")
    if user["role"] == "admin" and not user.get("demo"):
        st.subheader("Change CSV column names")
        st.caption("If your institution exports a different header, edit only its CSV column name. The meaning on the right must stay the same.")
        editable_mapping = st.data_editor(pd.DataFrame(config["column_map"].items(), columns=["CSV column", "Meaning in the app"]),
                                          disabled=["Meaning in the app"], hide_index=True, width="stretch", key="edit-column-map")
        if st.button("Save column names"):
            names = [str(value).strip() for value in editable_mapping["CSV column"]]
            if not all(names) or len(names) != len(set(names)):
                st.error("Every CSV column name must be non-empty and unique.")
            else:
                updated_config = {**config, "column_map": dict(zip(names, editable_mapping["Meaning in the app"]))}
                try:
                    STORE.update_institution_config(active_institution_id, updated_config, user["email"])
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.auth_user = {**user, "config": updated_config}
                    st.success("Column names saved for this institution.")
                    st.rerun()
    st.subheader("Uploaded source preview")
    st.dataframe(source.head(20), hide_index=True, width="stretch")
    for warning in warnings:
        st.warning(warning)
    issues = getattr(service, "last_dataset_issues", [])
    if issues:
        st.subheader("Data quality issues")
        st.dataframe(pd.DataFrame(issues), hide_index=True, width="stretch")
    st.write(f"Rows loaded: **{len(source)}** · Columns received: **{len(source.columns)}** · Mean completeness: **{predictions.data_completeness.mean():.0%}**")

elif page == "Institution policies":
    st.markdown('<div class="hero"><h1>Local support rules</h1><p>Simple rules your institution can review separately from the model.</p></div>', unsafe_allow_html=True)
    st.write("Example: if fewer than half of expected tasks were submitted, show an alert for a teacher to verify. A rule does not diagnose a student and does not change the model score.")
    st.dataframe(pd.DataFrame(config.get("rules", [])).rename(columns={"field":"Information checked", "operator":"Comparison", "value":"Trigger point", "severity":"Attention level", "message":"Teacher-facing alert"}), hide_index=True, width="stretch")
    if user["role"] == "admin" and not user.get("demo"):
        st.subheader("Edit your institution's alerts")
        st.caption("Use lt (below), lte (at or below), gt (above), gte (at or above), or eq (equal). Rate fields use decimals such as 0.60 for 60%.")
        edited_rules = st.data_editor(pd.DataFrame(config.get("rules", [])), num_rows="dynamic", width="stretch", key="edit-rules")
        if st.button("Save policy alerts", type="primary"):
            try:
                allowed_fields = set(config.get("model_fields", [])) | {"submission_rate"}
                cleaned = []
                for raw_rule in edited_rules.to_dict("records"):
                    if not any(pd.notna(value) and str(value).strip() for value in raw_rule.values()):
                        continue
                    rule = {key: raw_rule.get(key) for key in ("id", "field", "operator", "value", "severity", "message")}
                    if not rule["id"] or rule["field"] not in allowed_fields or rule["operator"] not in {"lt", "lte", "gt", "gte", "eq"}:
                        raise ValueError("Each alert needs an ID, a mapped information field, and a supported comparison.")
                    rule["value"] = float(rule["value"])
                    if rule["severity"] not in {"low", "medium", "high"} or not str(rule["message"]).strip():
                        raise ValueError("Choose low, medium, or high attention and write a teacher-facing message.")
                    cleaned.append(rule)
                if len({rule["id"] for rule in cleaned}) != len(cleaned):
                    raise ValueError("Alert IDs must be unique.")
                updated_config = {**config, "rules": cleaned}
                STORE.update_institution_config(active_institution_id, updated_config, user["email"])
                st.session_state.auth_user = {**user, "config": updated_config}
                st.success("Policy alerts saved for this institution.")
                st.rerun()
            except (TypeError, ValueError) as exc:
                st.error(f"Could not save alerts: {exc}")
    st.subheader("How flags are used")
    st.write("A flag highlights a value that crossed a threshold approved during onboarding. It does not change the model probability and it is never a diagnosis. Teachers verify the source record, discuss context with the student, and document the support decision.")
    st.subheader("How support priority is grouped")
    st.write("The medium and high boundaries decide how the dashboard groups predictions. They are settings for review workload, not medical or academic diagnoses.")
    st.json(config.get("risk_thresholds", {}))
    st.subheader("Capacity-aware threshold preview")
    weekly_capacity = st.number_input("Students the support team can review each week", min_value=1, max_value=max(1, len(predictions)), value=min(50, len(predictions)))
    ranked = predictions.dropna(subset=["risk_probability"]).sort_values("risk_probability", ascending=False)
    capacity_threshold = float(ranked.iloc[min(weekly_capacity, len(ranked)) - 1].risk_probability) if len(ranked) else 1.0
    st.write(f"At current scores, reviewing the top **{min(weekly_capacity, len(ranked))}** students corresponds to a probability boundary near **{capacity_threshold:.0%}**.")
    st.caption("This is planning support only. An approved threshold must also consider false negatives, false positives, equity, and intervention benefit.")

elif page == "Model governance":
    st.markdown('<div class="hero"><h1>Can this model be trusted here?</h1><p>What has been tested, what remains uncertain, and why deployment is still blocked.</p></div>', unsafe_allow_html=True)
    st.write("A model learns patterns from past students. Before a school uses it for real outreach, we must check that it works on later students, gives meaningful priorities across groups, protects private data, and helps rather than harms.")
    metrics_path = active_metrics if user.get("demo") else None
    if metrics_path and metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")); winner = metrics["winner"]
        cols = st.columns(5)
        cols[0].metric("PR-AUC", f"{winner['pr_auc']:.3f}"); cols[1].metric("Recall", f"{winner['recall']:.3f}")
        cols[2].metric("Precision", f"{winner['precision']:.3f}"); cols[3].metric("Brier", f"{winner['brier']:.3f}"); cols[4].metric("Threshold", f"{winner['threshold']:.2f}")
        st.dataframe(pd.DataFrame(metrics["leaderboard"]), hide_index=True, width="stretch")
        st.warning("These are public-benchmark development results, not a production accuracy claim for a new institution.")
        with st.expander("What do these measurements mean?"):
            st.write("**Recall:** of students who later withdrew, the share marked for review. **Precision:** of students marked for review, the share who later withdrew. **PR-AUC:** how well the model ranks withdrawals when they are relatively uncommon. **Brier score:** how close estimated probabilities are to observed outcomes; lower is better. No single number proves that a model is safe or useful.")
        if metrics.get("holdout_presentation"):
            st.caption(f"Forward holdout: {metrics['holdout_presentation']} · Validation: {metrics['validation_presentation']} · Evaluation rows: {winner['rows']:,}")
            st.info("The day-28 OULAD holdout has modest discrimination and imperfect calibration. Treat these scores as a research demonstration, not a reliable local decision tool.")
            if metrics.get("calibration_deciles"):
                chart = pd.DataFrame(metrics["calibration_deciles"])
                st.subheader("Holdout calibration by score decile")
                st.line_chart(chart.set_index("decile")[["observed", "predicted"]])
        subgroup_rows = [{"field": field, **group} for field, groups in metrics.get("subgroup_audit", {}).items() for group in groups]
        if subgroup_rows:
            st.subheader("Development subgroup audit")
            st.dataframe(pd.DataFrame(subgroup_rows), hide_index=True, width="stretch")
    st.subheader("What must happen before real use")
    gates = [
        ("Outcome and prediction horizon approved", bool(config.get("prediction_horizon"))),
        ("Data dictionary approved", bool(config.get("data_dictionary"))),
        ("Temporal holdout passed", False),
        ("Calibration reviewed on local data", False),
        ("Subgroup audit passed on local data", False),
        ("Shadow pilot completed", False),
        ("Privacy and security review passed", False),
        ("Enterprise SSO and role review completed", False),
        ("Rollback owner assigned", False),
    ]
    st.dataframe(pd.DataFrame([{"Release gate": name, "Status": "Evidence recorded" if passed else "Blocked — institution evidence required"} for name, passed in gates]), hide_index=True, width="stretch")
    st.error("Production release is blocked until every institution-owned gate has evidence. The application does not allow benchmark results to satisfy local validation gates.")

else:
    st.markdown('<div class="hero"><h1>Test the model with a CSV</h1><p>Try a clean labeled file, then try missing information and see the safeguards respond.</p></div>', unsafe_allow_html=True)
    if not user.get("demo") or benchmark != "Open University · day 28" or not OULAD_MODEL.exists():
        st.info("Choose the development demonstration and select “Open University · day 28” in the sidebar to use these test files. A public model must not be used to judge another institution's data.")
        st.stop()
    samples = [
        ("Clean labeled holdout (300 learners)", "oulad_clean_labeled_300.csv"),
        ("Missing learning features (300 learners)", "oulad_missing_features_300.csv"),
        ("Missing student ID (20 learners)", "oulad_missing_id_20.csv"),
    ]
    for label, filename in samples:
        sample_path = ROOT / "data" / "test_uploads" / filename
        st.download_button(label, sample_path.read_bytes(), file_name=filename, mime="text/csv", key=filename)
    st.write("The clean file comes from the **2014J presentation held out of training** and includes the known later-withdrawal outcome. Upload it here to compare predictions with those outcomes. The other files deliberately test missing-data handling; they cannot measure accuracy.")
    test_upload = st.file_uploader("Choose a test CSV", type="csv", key="evaluation-upload")
    if test_upload is not None:
        try:
            test_source = pd.read_csv(test_upload)
            checked = canonicalize(test_source, config, training=False)
            evaluated = PredictionService(config, OULAD_MODEL)
            outcomes, _ = evaluated.predict(test_source, include_explanations=False)
            st.write(f"**{len(test_source):,} rows checked.** {int(outcomes.risk_band.eq('Insufficient data').sum()):,} need more information before scoring.")
            st.dataframe(outcomes[["student_id", "risk_band", "data_completeness", "missing_fields"]].head(25), hide_index=True, width="stretch")
            label_column = next((name for name, target in config["column_map"].items() if target == "outcome"), None)
            if label_column not in test_source:
                st.info("No known outcome column was provided. This file can test data validation, but not prediction accuracy.")
            else:
                labeled = canonicalize(test_source, config, training=True).frame["outcome"]
                valid = outcomes.risk_band.ne("Insufficient data")
                if not valid.any():
                    st.warning("Accuracy cannot be calculated: every row needs more information.")
                else:
                    actual = labeled.loc[valid].to_numpy()
                    predicted = outcomes.loc[valid, "risk_probability"].to_numpy() >= float(json.loads(OULAD_METRICS.read_text())["winner"]["threshold"])
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Correct classifications", f"{accuracy_score(actual, predicted):.1%}")
                    c2.metric("Withdrawals found", f"{recall_score(actual, predicted, zero_division=0):.1%}")
                    c3.metric("Alerts that were withdrawals", f"{precision_score(actual, predicted, zero_division=0):.1%}")
                    baseline_accuracy = max(float(actual.mean()), 1.0 - float(actual.mean()))
                    st.caption(f"For comparison, guessing the more common outcome for every learner would be {baseline_accuracy:.1%} correct on this file. Accuracy alone can hide missed withdrawals.")
                    st.dataframe(pd.DataFrame([{
                        "Later withdrew and alerted": int(((actual == 1) & predicted).sum()),
                        "Later withdrew but missed": int(((actual == 1) & ~predicted).sum()),
                        "Did not withdraw but alerted": int(((actual == 0) & predicted).sum()),
                        "Did not withdraw and not alerted": int(((actual == 0) & ~predicted).sum()),
                    }]), hide_index=True, width="stretch")
                    st.caption(f"Evaluated {len(actual)} labeled rows. This is a benchmark self-test, not evidence that the model works at your institution.")
        except Exception as exc:
            st.error(f"The file could not be evaluated: {exc}")
            st.write("Check that it has a learner_id and the mapped learning columns shown on the Data and column guide page.")
