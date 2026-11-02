from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import threading
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.sessions import SessionMiddleware

from student_success.demo_storage import DemoSupportStore
from student_success.onboarding import ALLOWED_FIELDS, build_institution_config, readiness_check, slug
from student_success.prediction import PredictionService, plain_language_evidence, student_signal_checks
from student_success.schema import MODEL_FIELDS, canonicalize, load_config
from student_success.storage import AuditStore
from student_success.workflow import (
    FIELD_LABELS,
    automatic_column_mapping,
    student_source_row,
    suggest_column_mappings,
    validate_column_mapping,
)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "frontend"
CONFIG_PATH = Path(os.getenv("INSTITUTION_CONFIG", ROOT / "config/institutions/northstar_metropolitan.json"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data/student_success.db"))
API_KEY = os.getenv("STUDENT_SUCCESS_API_KEY", "")
_secret_path = ROOT / "data" / ".session_secret"
SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    _secret_path.parent.mkdir(parents=True, exist_ok=True)
    if not _secret_path.exists():
        _secret_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    SESSION_SECRET = _secret_path.read_text(encoding="utf-8").strip()
store = AuditStore(DATABASE_PATH)
app = FastAPI(title="Student Success AI", version="2.1.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=False)
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

DEMO_CONFIGS = {
    "northstar": (ROOT / "config/institutions/northstar_metropolitan.json", ROOT / "models/northstar/model_bundle.joblib", ROOT / "data/northstar_uci_697_prepared.csv"),
    "ou": (ROOT / "config/institutions/open_university_day28.json", ROOT / "models/oulad_day28/model_bundle.joblib", ROOT / "data/oulad_day28_prepared.csv"),
}
CHECKLIST = {
    "identity_verified": "Confirm the student record and current enrollment",
    "attendance_reviewed": "Review recent attendance evidence",
    "academic_reviewed": "Review assignments and assessment trajectory",
    "student_contacted": "Contact the student using a supportive message",
    "barriers_discussed": "Discuss academic, financial, wellbeing, or access barriers",
    "support_agreed": "Agree and record an appropriate support action",
    "follow_up_scheduled": "Schedule a follow-up date",
}
INTERVENTIONS = ["", "Academic advising", "Tutoring", "Financial support referral", "Wellbeing referral", "Accessibility support", "Technology/access support", "Other"]
STATUSES = ["Needs review", "Contact planned", "Student contacted", "Support active", "Resolved", "Closed"]
DEFAULT_REVIEW_TARGETS = {
    "attendance_rate": .75, "submission_rate": .60, "assessment_average": 50,
    "credits_completed_ratio": .50, "engagement_score": .60, "days_since_login": 14,
}


def with_review_targets(config: dict) -> dict:
    """Keep older institution workspaces compatible with editable local targets."""
    return {**config, "review_targets": {**DEFAULT_REVIEW_TARGETS, **config.get("review_targets", {})}}


def synchronize_review_rules(config: dict) -> dict:
    """Keep visible policy reminders consistent with editable local targets."""
    targets = config.get("review_targets", {})
    rules = []
    for rule in config.get("rules", []):
        field = rule.get("field")
        if field in targets:
            value = float(targets[field])
            message = f"{field.replace('_', ' ').capitalize()} is outside this institution's local review target."
            rules.append({**rule, "value": value, "message": message})
        else:
            rules.append(rule)
    return {**config, "rules": rules}

class Login(BaseModel):
    email: str
    password: str

class Signup(BaseModel):
    institution_name: str
    institution_type: str = "University"
    display_name: str
    email: str
    password: str
    prediction_horizon: str = "End of the current term — support planning for the next review period"
    term_label: str = "Current term"
    data_owner: str = "Institution data team"
    selected_fields: list[str] = []
    responsible_use_confirmed: bool = False

class StudentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    student_id: str = Field(min_length=1, max_length=100)

class BatchRequest(BaseModel):
    students: list[dict] = Field(min_length=1, max_length=5000)


class StaffAccount(BaseModel):
    display_name: str = Field(min_length=2, max_length=100)
    email: str
    password: str = Field(min_length=10)
    role: str = "teacher"

def current_user(request: Request) -> dict:
    session_user = request.session.get("user")
    if not session_user:
        raise HTTPException(401, "Please sign in to continue")
    if session_user.get("demo"):
        benchmark = session_user.get("benchmark", "northstar")
        if benchmark not in DEMO_CONFIGS:
            raise HTTPException(401, "Demonstration workspace is unavailable")
        config = load_config(DEMO_CONFIGS[benchmark][0])
        return {**session_user, "config": config}
    stored_user = store.get_user(session_user.get("email", ""))
    if not stored_user:
        raise HTTPException(401, "Institution workspace is unavailable")
    return stored_user

def compact_user(user: dict) -> dict:
    keys = ("institution_id", "institution_name", "institution_type", "display_name",
            "email", "role", "demo", "benchmark", "session_key")
    return {key: user[key] for key in keys if key in user}


def workspace_key(user: dict) -> str:
    """Share normal uploads within an institution; keep demo uploads private."""
    return user.get("session_key", "") if user.get("demo") else user["institution_id"]

def authorize(x_api_key: str = Header(default="")):
    if not API_KEY:
        raise HTTPException(503, "This optional API is disabled until STUDENT_SUCCESS_API_KEY is configured.")
    if x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key")

def support_store(request: Request, user: dict):
    if user.get("demo"):
        key = user.get("session_key", "")
        stores = request.app.state.demo_stores
        return stores.setdefault(key, DemoSupportStore())
    return store

def service_for(user: dict, config_override: dict | None = None) -> tuple[PredictionService, dict, str | None]:
    profile = (config_override or {}).get("_model_profile")
    if user.get("demo") and profile in DEMO_CONFIGS:
        config_path, model_path, _ = DEMO_CONFIGS[profile]
        return PredictionService(config_override or load_config(config_path), model_path if model_path.is_file() else None, allow_demo_score=True), config_override or load_config(config_path), str(model_path) if model_path.is_file() else None
    if user.get("demo") and (config_override or {}).get("_local_screen"):
        return PredictionService(config_override, None, allow_demo_score=True), config_override, None
    if user.get("demo"):
        benchmark = user.get("benchmark", "northstar")
        config_path, model_path, _ = DEMO_CONFIGS[benchmark]
        standard_config = load_config(config_path)
        if config_override is None or config_override == standard_config:
            service, config = cached_demo_service(benchmark)
        else:
            config = config_override
            service = PredictionService(config, model_path if model_path.is_file() else None, allow_demo_score=False)
        return service, config, str(model_path) if model_path.is_file() else None
    config = config_override or user["config"]
    # A new institution does not silently receive another institution's model.
    # It still gets a transparent, lightweight risk screen when 3+ meaningful
    # signals are mapped; local validation is required before calling it a model.
    return PredictionService(config, None, allow_demo_score=True), config, None


def prepare_upload_config(user: dict, base_config: dict, mapping: dict[str, str], units: dict) -> dict:
    """Choose a compatible public model only when the CSV supports all its inputs."""
    available = set(mapping.values())
    if {"assignments_due", "assignments_submitted"} <= available:
        available.add("submission_rate")
    best_profile = None
    best_features: list[str] = []
    if user.get("demo"):
        for profile, (config_path, model_path, _) in DEMO_CONFIGS.items():
            if not model_path.is_file():
                continue
            service, _ = cached_demo_service(profile)
            needed = service.bundle["feature_names"] if service.bundle else []
            if needed and set(needed).issubset(available) and len(needed) > len(best_features):
                best_profile, best_features = profile, list(needed)
    config = {**base_config, "column_map": mapping, "units": units}
    config.pop("_model_profile", None)
    config.pop("_local_screen", None)
    if best_profile:
        config["_model_profile"] = best_profile
        benchmark_config = load_config(DEMO_CONFIGS[best_profile][0])
        config["institution_id"] = benchmark_config["institution_id"]
        config["risk_thresholds"] = benchmark_config["risk_thresholds"]
        config["prediction_horizon"] = benchmark_config["prediction_horizon"]
        config["model_fields"] = best_features
        config["critical_fields"] = [field for field in best_features if field != "submission_rate"]
        config["rules"] = [rule for rule in config.get("rules", []) if rule.get("field") in set(best_features)]
    else:
        usable = [field for field in (
            "attendance_rate", "assignments_due", "assignments_submitted", "submission_rate",
            "assessment_average", "assessment_change", "days_since_login",
            "support_contacts", "credits_completed_ratio", "engagement_score",
        ) if field in available]
        signals = set(usable) & set(DEFAULT_REVIEW_TARGETS)
        if len(signals) < 3:
            raise ValueError("This CSV does not contain enough recognised learning information for dropout screening. Include a student ID and at least three of: attendance, work expected/submitted, assessment result, activity, credit progress, or engagement.")
        config["_local_screen"] = True
        config["model_fields"] = sorted(signals)
        config["critical_fields"] = sorted(signals)
        config["rules"] = [rule for rule in config.get("rules", []) if rule.get("field") in set(usable)]
    return synchronize_review_rules(with_review_targets(config))

app.state.demo_stores = {}
app.state.upload_configs = {}
app.state.demo_cache_ready = set()
app.state.demo_cache_warming = set()
app.state.demo_cache_errors = {}
app.state.demo_cache_lock = threading.Lock()


@lru_cache(maxsize=2)
def cached_demo_service(benchmark: str) -> tuple[PredictionService, dict]:
    """Load a public benchmark model once per server process."""
    config_path, model_path, _ = DEMO_CONFIGS[benchmark]
    config = load_config(config_path)
    return PredictionService(config, model_path if model_path.is_file() else None, allow_demo_score=False), config


@lru_cache(maxsize=2)
def cached_demo_frames(benchmark: str) -> tuple[str, str]:
    """Score unchanged benchmark data once and share immutable results across demo sessions."""
    _, _, data_path = DEMO_CONFIGS[benchmark]
    frame = pd.read_csv(data_path).drop(columns=["dropout_risk"], errors="ignore")
    if benchmark == "ou":
        frame = frame.loc[frame.code_presentation.eq("2014J")].drop(
            columns=["withdrawn_after_28", "id_student", "gender_audit", "age_band_audit"], errors="ignore"
        )
    service, _ = cached_demo_service(benchmark)
    results, _ = service.predict(frame, include_explanations=False)
    return frame.to_json(orient="records"), results.to_json(orient="records")


def prepare_demo_cache(benchmark: str) -> None:
    try:
        cached_demo_frames(benchmark)
        app.state.demo_cache_ready.add(benchmark)
        app.state.demo_cache_errors.pop(benchmark, None)
    except Exception as exc:
        app.state.demo_cache_errors[benchmark] = str(exc)
        logging.getLogger("uvicorn.error").exception("Demonstration model preparation failed: %s", benchmark)
    finally:
        app.state.demo_cache_warming.discard(benchmark)


def start_demo_warmup(benchmark: str) -> None:
    with app.state.demo_cache_lock:
        if benchmark in app.state.demo_cache_ready or benchmark in app.state.demo_cache_warming or benchmark in app.state.demo_cache_errors:
            return
        app.state.demo_cache_warming.add(benchmark)
        threading.Thread(target=lambda: prepare_demo_cache(benchmark), daemon=True).start()


@app.on_event("startup")
def warm_default_demo() -> None:
    # The sign-in page stays responsive while the default public benchmark prepares in the background.
    if "pytest" in sys.modules:
        return
    start_demo_warmup("northstar")

def active_config(request: Request, user: dict) -> dict:
    if not user.get("demo"):
        saved = store.get_dataset(user["institution_id"])
        if saved:
            return with_review_targets(json.loads(saved["config_json"]))
    return with_review_targets(request.app.state.upload_configs.get(workspace_key(user), user["config"]))


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

@app.get("/health")
def health():
    return {"status": "ok", "interface": "web", "version": "2.1.0", "model_loaded": bool(cached_demo_service.cache_info().currsize)}

@app.post("/v1/auth/login")
def login(payload: Login, request: Request):
    user = store.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(401, "Email or password is incorrect")
    request.session.clear()
    request.session["user"] = compact_user(user)
    return {"user": public_user(user)}

def public_user(user: dict) -> dict:
    return {"display_name": user["display_name"], "email": user["email"], "institution_name": user["institution_name"], "institution_type": user["institution_type"], "role": user["role"], "demo": bool(user.get("demo"))}

@app.post("/v1/auth/demo")
def demo(request: Request, benchmark: str = "northstar"):
    if benchmark not in DEMO_CONFIGS:
        raise HTTPException(422, "Unknown demonstration dataset")
    request.session.clear()
    config = load_config(DEMO_CONFIGS[benchmark][0])
    user = {"institution_id": config["institution_id"], "institution_name": config["display_name"], "institution_type": "University", "display_name": "Demonstration Teacher", "email": "demo@local", "role": "teacher", "config": config, "demo": True, "benchmark": benchmark, "session_key": secrets.token_urlsafe(18)}
    request.session["user"] = compact_user(user)
    return {"user": public_user(user)}

@app.post("/v1/auth/signup")
def signup(payload: Signup, request: Request):
    name = payload.institution_name.strip()
    display_name = payload.display_name.strip()
    email = payload.email.strip().lower()
    if len(name) < 2 or len(display_name) < 2 or "@" not in email:
        raise HTTPException(422, "Enter an institution name, administrator name, and work email.")
    if len(payload.password) < 10:
        raise HTTPException(422, "Password must contain at least 10 characters")
    if not payload.responsible_use_confirmed:
        raise HTTPException(422, "Confirm that this workspace supports human outreach and will not make automatic adverse decisions.")
    if len(payload.prediction_horizon.strip()) < 12:
        raise HTTPException(422, "Describe when the review happens and what future period it is intended to support.")
    institution_id = f"{slug(name) or 'institution'}-{secrets.token_hex(3)}"
    try:
        config = build_institution_config(
            institution_id, name, payload.institution_type, payload.prediction_horizon,
            payload.term_label, payload.data_owner, payload.selected_fields,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        store.create_institution_with_admin(institution_id, name, payload.institution_type, config, display_name, email, payload.password)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    user = store.authenticate(email, payload.password)
    request.session.clear()
    request.session["user"] = compact_user(user)
    return {"created": True, "message": "Workspace created. Continue with CSV upload.", "user": public_user(user)}

@app.post("/v1/auth/logout")
def logout(request: Request):
    user = request.session.get("user", {})
    if user.get("demo"):
        key = workspace_key(user)
        request.app.state.demo_stores.pop(key, None)
        request.app.state.uploads.pop(key, None)
        request.app.state.results.pop(key, None)
        request.app.state.upload_configs.pop(key, None)
    request.session.clear()
    return {"ok": True}


@app.post("/v1/users")
def create_staff_account(payload: StaffAccount, user: dict = Depends(current_user)):
    if user.get("demo") or user.get("role") != "admin":
        raise HTTPException(403, "Only an institution administrator can create staff accounts.")
    if "@" not in payload.email:
        raise HTTPException(422, "Enter a valid work email address.")
    try:
        return store.create_staff_user(user["institution_id"], payload.display_name, payload.email, payload.password, payload.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.get("/v1/me")
def me(user: dict = Depends(current_user)):
    return {"user": public_user(user), "checklist": CHECKLIST, "config": user["config"]}

@app.post("/v1/benchmark")
def set_benchmark(request: Request, user: dict = Depends(current_user), benchmark: str = "northstar"):
    if not user.get("demo") or benchmark not in DEMO_CONFIGS:
        raise HTTPException(422, "Dataset selection is available in the demonstration workspace")
    user["benchmark"] = benchmark
    user["config"] = load_config(DEMO_CONFIGS[benchmark][0])
    request.session["user"] = compact_user(user)
    key = user.get("session_key", user["email"])
    request.app.state.uploads.pop(key, None)
    request.app.state.results.pop(key, None)
    request.app.state.upload_configs.pop(key, None)
    return {"ok": True}

@app.post("/v1/data/inspect")
async def inspect_data(
    file: UploadFile = File(...),
    request: Request = None,
    user: dict = Depends(current_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(415, "Choose a CSV file")
    try:
        frame = pd.read_csv(file.file, nrows=5, dtype=str, sep=None, engine="python")
        config = active_config(request, user)
        suggestions = suggest_column_mappings(
            list(frame.columns),
            {column: frame[column].tolist() for column in frame.columns},
            config.get("column_map", {}),
        )
    except Exception as exc:
        raise HTTPException(422, f"Could not inspect this CSV: {exc}") from exc
    return {
        "columns": suggestions,
        "fields": FIELD_LABELS,
        "required_fields": ["student_id"],
        "message": "Recognised columns will be mapped automatically. Unknown columns are ignored.",
    }

@app.post("/v1/data/upload")
async def upload_data(
    file: UploadFile = File(...),
    column_map: str | None = Form(None),
    save_mapping: bool = Form(False),
    request: Request = None,
    user: dict = Depends(current_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(415, "Choose a CSV file")
    if not user.get("demo") and user.get("role") != "admin":
        raise HTTPException(403, "Only an institution administrator can upload or replace the institution CSV.")
    try:
        frame = pd.read_csv(file.file, dtype=str, sep=None, engine="python", nrows=5001)
        if frame.empty:
            raise ValueError("The CSV has no student records. Add at least one data row.")
        if len(frame) > 5000:
            raise ValueError("This local workspace accepts up to 5,000 student records per upload.")
        requested_map = json.loads(column_map) if column_map else automatic_column_mapping(list(frame.columns), active_config(request, user).get("column_map", {}))
        if not requested_map:
            requested_map = automatic_column_mapping(list(frame.columns), active_config(request, user).get("column_map", {}))
        mapping = validate_column_mapping(list(frame.columns), requested_map)
        units: dict[str, str] = {}
        for source_name, field in mapping.items():
            normalized_header = source_name.lower().replace("_", " ")
            if field in {"attendance_rate", "credits_completed_ratio", "engagement_score"} and (
                "%" in source_name or "percent" in normalized_header or "percentage" in normalized_header
            ):
                units[field] = "percent"
            elif field == "assessment_average":
                units[field] = "percentage_text"
        for source_name, field in mapping.items():
            if field in {"attendance_rate", "credits_completed_ratio", "engagement_score"} and frame[source_name].astype(str).str.endswith("%").any():
                units[field] = "percent"
        config = prepare_upload_config(user, active_config(request, user), mapping, units)
        service, config, _ = service_for(user, config)
        predictions, warnings = service.predict(frame, include_explanations=False)
        if save_mapping:
            if user.get("demo") or user.get("role") != "admin":
                raise HTTPException(403, "Only an institution administrator can save the mapping for the workspace.")
            store.update_institution_config(user["institution_id"], config, user["email"])
            user["config"] = config
            request.session["user"] = compact_user(user)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(422, f"The data needs attention: {exc}") from exc
    key = workspace_key(user)
    request.app.state.uploads[key] = frame.copy()
    request.app.state.results[key] = predictions.copy()
    request.app.state.upload_configs[key] = config
    if not user.get("demo"):
        store.save_dataset(user["institution_id"], frame.to_json(orient="records"), predictions.to_json(orient="records"), config)
    return {"rows": len(frame), "columns": list(frame.columns), "predictions": json.loads(predictions.to_json(orient="records")), "warnings": warnings, "has_model": service.bundle is not None, "model_profile": config.get("_model_profile"), "mapping": mapping, "issues": getattr(service, "last_dataset_issues", []), "mapping_saved": save_mapping}

app.state.uploads = {}
app.state.results = {}

def load_frames(request: Request, user: dict):
    if not user.get("demo"):
        saved = store.get_dataset(user["institution_id"])
        if not saved:
            return pd.DataFrame(), pd.DataFrame()
        return pd.DataFrame(json.loads(saved["source_json"])), pd.DataFrame(json.loads(saved["results_json"]))
    key = workspace_key(user)
    if user.get("demo") and key not in request.app.state.uploads:
        benchmark = user.get("benchmark", "northstar")
        if benchmark not in request.app.state.demo_cache_ready:
            start_demo_warmup(benchmark)
            return pd.DataFrame(), pd.DataFrame()
        source_json, results_json = cached_demo_frames(benchmark)
        request.app.state.uploads[key] = source_json
        request.app.state.results[key] = results_json
    if key not in request.app.state.uploads:
        return pd.DataFrame(), pd.DataFrame()
    source = request.app.state.uploads[key]
    results = request.app.state.results[key]
    if isinstance(source, pd.DataFrame):
        return source.copy(), results.copy()
    return pd.DataFrame(json.loads(source)), pd.DataFrame(json.loads(results))

@app.get("/v1/dashboard")
def dashboard(request: Request, user: dict = Depends(current_user)):
    benchmark = user.get("benchmark", "northstar")
    if user.get("demo") and benchmark in request.app.state.demo_cache_errors:
        raise HTTPException(503, "The demonstration model could not be loaded. Check the server log and installed requirements, then restart. You can still create an institution workspace and upload a CSV.")
    source, predictions = load_frames(request, user)
    config = active_config(request, user)
    ws = support_store(request, user)
    if predictions.empty:
        benchmark = user.get("benchmark", "northstar")
        warming = bool(user.get("demo") and benchmark not in request.app.state.demo_cache_ready)
        has_model = bool(user.get("demo") and DEMO_CONFIGS[benchmark][1].is_file()) if warming else service_for(user, config)[0].bundle is not None
        return {"ready": False, "warming": warming, "user": public_user(user), "readiness": readiness_check(config, False, has_model)}
    has_model = service_for(user, config)[0].bundle is not None
    counts = predictions.risk_band.value_counts().to_dict()
    eligible_for_screening = int(counts.get("High", 0) + counts.get("Medium", 0))
    eligible_ids = predictions.loc[predictions.risk_band.isin(["High", "Medium"]), "student_id"].astype(str).tolist()
    summary = ws.screening_summary(user["institution_id"], eligible_ids)
    summary["eligible"] = eligible_for_screening
    summary["not_started"] = max(0, eligible_for_screening - summary["started"])
    students = []
    for row in json.loads(predictions.to_json(orient="records")):
        students.append({"student_id": row["student_id"], "risk_band": row["risk_band"], "data_completeness": row["data_completeness"], "missing_fields": row.get("missing_fields") or []})
    return {"ready": True, "institution": user["institution_name"], "prediction_horizon": config.get("prediction_horizon", "Not approved"), "minimum_data_completeness": config.get("minimum_data_completeness", .7), "students": students, "counts": counts, "screening": summary, "has_model": has_model, "columns": list(source.columns), "readiness": readiness_check(config, True, has_model)}


@app.get("/v1/dropout-predictions")
def dropout_predictions(request: Request, user: dict = Depends(current_user)):
    """Return automatic risk results and plain-language review reasons.

    Teacher screening is intentionally not part of this calculation. It is an
    optional follow-up record after the prediction is available.
    """
    source, _ = load_frames(request, user)
    if source.empty:
        raise HTTPException(404, "Upload a CSV before viewing dropout predictions")
    service, _, _ = service_for(user, active_config(request, user))
    predicted, warnings = service.predict(source, include_explanations=True)
    records = []
    for row in json.loads(predicted.to_json(orient="records")):
        records.append({
            "student_id": row["student_id"],
            "risk_band": row["risk_band"],
            "data_completeness": row["data_completeness"],
            "missing_fields": row.get("missing_fields") or [],
            "reasons": plain_language_evidence(row.get("reason_codes") or []),
        })
    return {
        "records": records,
        "counts": predicted.risk_band.value_counts().to_dict(),
        "warnings": warnings,
        "model_status": "trained model" if service.bundle else "transparent dropout-risk screen",
    }

@app.get("/v1/students/{student_id}")
def student_detail(student_id: str, request: Request, user: dict = Depends(current_user)):
    source, _ = load_frames(request, user)
    if source.empty:
        raise HTTPException(404, "Upload a CSV to review students")
    service, config, _ = service_for(user, active_config(request, user))
    try:
        raw = student_source_row(source, config["column_map"], student_id)
    except ValueError as exc:
        raise HTTPException(404, "Student record is not part of the current uploaded CSV.") from exc
    detailed, _ = service.predict(raw, include_explanations=True)
    result = json.loads(detailed.to_json(orient="records"))[0]
    result["evidence"] = plain_language_evidence(result.get("reason_codes", []))
    canonical = canonicalize(raw, config).frame.iloc[0]
    result["signal_checks"] = student_signal_checks(canonical, config.get("model_fields", []), config.get("review_targets"))
    ws = support_store(request, user)
    result["screening"] = ws.get_screening(user["institution_id"], student_id)
    result["case"] = ws.get_case(user["institution_id"], student_id)
    result["checklist_labels"] = CHECKLIST
    result["rules"] = config.get("rules", [])
    return result

@app.put("/v1/students/{student_id}/screening")
async def save_screening(student_id: str, payload: dict, request: Request, user: dict = Depends(current_user)):
    if user.get("role") == "viewer":
        raise HTTPException(403, "Read-only viewers cannot save screening records.")
    checklist = payload.get("checklist", {})
    if not isinstance(payload.get("notes", ""), str):
        raise HTTPException(422, "Screening notes must be text.")
    if not isinstance(checklist, dict) or set(checklist) != set(CHECKLIST) or not all(isinstance(value, bool) for value in checklist.values()):
        raise HTTPException(422, "Submit the complete teacher screening checklist using valid true/false values.")
    source, _ = load_frames(request, user)
    try:
        student_source_row(source, active_config(request, user)["column_map"], student_id)
    except ValueError as exc:
        raise HTTPException(404, "Student record is not part of the current uploaded CSV.") from exc
    support_store(request, user).save_screening(user["institution_id"], student_id, checklist, payload.get("notes", ""), user["email"])
    return {"ok": True}

@app.get("/v1/cases")
def cases(request: Request, user: dict = Depends(current_user)):
    ws = support_store(request, user)
    return {"summary": ws.case_summary(user["institution_id"]), "items": ws.list_cases(user["institution_id"]), "students": load_frames(request, user)[1].student_id.tolist() if not load_frames(request, user)[1].empty else [], "statuses": STATUSES, "interventions": INTERVENTIONS}

@app.put("/v1/cases/{student_id}")
async def save_case(student_id: str, payload: dict, request: Request, user: dict = Depends(current_user)):
    if user.get("role") == "viewer":
        raise HTTPException(403, "Read-only viewers cannot change support cases.")
    text_fields = ("owner_email", "status", "priority", "due_date", "intervention_type",
                   "intervention_accepted", "follow_up_outcome", "student_feedback")
    if any(field in payload and not isinstance(payload[field], str) for field in text_fields):
        raise HTTPException(422, "Case fields must contain text values.")
    if payload.get("intervention_accepted", "Not recorded") not in {"Not recorded", "Accepted", "Declined", "Unable to contact"}:
        raise HTTPException(422, "Choose a valid student response.")
    source, _ = load_frames(request, user)
    try:
        student_source_row(source, active_config(request, user)["column_map"], student_id)
    except ValueError as exc:
        raise HTTPException(404, "Student record is not part of the current uploaded CSV.") from exc
    if payload.get("status", "Needs review") not in STATUSES:
        raise HTTPException(422, "Choose a valid case status.")
    if payload.get("priority", "Normal") not in {"Normal", "Elevated", "Urgent"}:
        raise HTTPException(422, "Choose a valid case priority.")
    if payload.get("intervention_type", "") not in INTERVENTIONS:
        raise HTTPException(422, "Choose a valid support intervention.")
    if payload.get("due_date"):
        try: date.fromisoformat(payload["due_date"])
        except ValueError as exc: raise HTTPException(422, "Enter a follow-up date as YYYY-MM-DD") from exc
    if payload.get("status") not in {"Resolved", "Closed"} and not payload.get("owner_email", "").strip():
        raise HTTPException(422, "Assign an owner before saving an active case")
    support_store(request, user).save_case(user["institution_id"], student_id, payload, user["email"])
    return {"ok": True}

@app.get("/v1/setup")
def setup(request: Request, user: dict = Depends(current_user)):
    return {"config": active_config(request, user), "role": user["role"], "demo": user.get("demo", False)}

@app.put("/v1/setup")
async def update_setup(payload: dict, request: Request, user: dict = Depends(current_user)):
    if user.get("demo") or user.get("role") != "admin": raise HTTPException(403, "Only an institution administrator can edit workspace setup")
    config = payload.get("config", {})
    if not isinstance(config, dict):
        raise HTTPException(422, "Institution settings must be an object.")
    fields = config.get("model_fields", [])
    if not isinstance(fields, list) or any(field not in MODEL_FIELDS for field in fields):
        raise HTTPException(422, "Unknown model fields in institution settings.")
    if config.get("institution_id") != user["institution_id"]:
        raise HTTPException(422, "The institution identifier cannot be changed.")
    if not isinstance(config.get("column_map"), dict) or "student_id" not in config["column_map"].values():
        raise HTTPException(422, "Map one CSV column as the student identifier.")
    thresholds = config.get("risk_thresholds", {})
    if not isinstance(thresholds, dict):
        raise HTTPException(422, "Risk thresholds must be an object.")
    try:
        medium_threshold = float(thresholds.get("medium", .35))
        high_threshold = float(thresholds.get("high", .65))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Risk thresholds must be valid numbers.") from exc
    if not 0 <= medium_threshold <= 1 or not 0 <= high_threshold <= 1 or high_threshold <= medium_threshold:
        raise HTTPException(422, "Risk thresholds must be between 0 and 1, and high must be greater than medium.")
    targets = config.get("review_targets", {})
    allowed_targets = {"attendance_rate", "submission_rate", "credits_completed_ratio", "engagement_score", "assessment_average", "days_since_login"}
    if not isinstance(targets, dict) or not set(targets).issubset(allowed_targets):
        raise HTTPException(422, "Unsupported institution review target.")
    for field, raw_value in targets.items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"{field.replace('_', ' ')} review target must be a valid number.") from exc
        if field == "assessment_average" and not 0 <= value <= 100:
            raise HTTPException(422, "Assessment review target must be between 0 and 100.")
        if field == "days_since_login" and not 0 <= value <= 365:
            raise HTTPException(422, "Activity review target must be between 0 and 365 days.")
        if field not in {"assessment_average", "days_since_login"} and not 0 <= value <= 1:
            raise HTTPException(422, "Percentage review targets must be between 0% and 100%.")
        targets[field] = value
    # Preserve the verified schema and model selection. Only the exposed policy
    # fields are editable here; validate and score BEFORE committing either.
    active = active_config(request, user)
    config = {**active, "review_targets": {**DEFAULT_REVIEW_TARGETS, **targets},
              "risk_thresholds": {"medium": medium_threshold, "high": high_threshold}}
    config["onboarding"] = {**config.get("onboarding", {}), "targets_confirmed": True}
    config = synchronize_review_rules(config)
    source, _ = load_frames(request, user)
    recalculated = not source.empty
    try:
        if recalculated:
            service, config, _ = service_for(user, config)
            predictions, _ = service.predict(source, include_explanations=False)
            store.save_dataset(user["institution_id"], source.to_json(orient="records"),
                               predictions.to_json(orient="records"), config, update_institution=True)
        else:
            store.update_institution_config(user["institution_id"], config, user["email"])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, f"Settings could not be applied: {exc}") from exc
    request.session["user"] = compact_user(user)
    return {"ok": True, "recalculated": recalculated}

@app.get("/v1/test-files")
def test_files():
    return {"files": ["simple_college_demo_60.csv", "uci_697_real_500_natural_upload.csv", "uci_697_real_500_balanced_comparison.csv", "simple_college_demo_15.csv", "oulad_clean_labeled_300.csv", "oulad_missing_features_300.csv", "oulad_missing_id_20.csv"]}

@app.get("/v1/test-files/{filename}")
def download_test_file(filename: str):
    allowed = {"simple_college_demo_60.csv", "uci_697_real_500_natural_upload.csv", "uci_697_real_500_balanced_comparison.csv", "simple_college_demo_15.csv", "oulad_clean_labeled_300.csv", "oulad_missing_features_300.csv", "oulad_missing_id_20.csv"}
    if filename not in allowed:
        raise HTTPException(404, "Test file not found")
    path = ROOT / "DEMO_DATASETS" / filename
    if not path.is_file():
        raise HTTPException(404, "Test file not found")
    return FileResponse(path, media_type="text/csv", filename=filename)

@app.get("/v1/audit/recent", dependencies=[Depends(authorize)])
def recent_audit(limit: int = 100):
    return {"items": store.recent(min(max(limit, 1), 1000))}

@app.post("/v1/predict", dependencies=[Depends(authorize)])
def predict(request: BatchRequest):
    config = load_config(CONFIG_PATH)
    model = ROOT / "models/northstar/model_bundle.joblib" if config.get("institution_id") == "northstar-metropolitan-university" else None
    service = PredictionService(config, model, allow_demo_score=False)
    try: results, warnings = service.predict(pd.DataFrame(request.students))
    except ValueError as exc: raise HTTPException(422, detail=str(exc)) from exc
    records = json.loads(results.to_json(orient="records"))
    for record in records: record["audit_id"] = store.record(config.get("institution_id", "unknown"), record)
    return {"predictions": records, "warnings": warnings}
