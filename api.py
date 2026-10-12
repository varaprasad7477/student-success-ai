from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from student_success.prediction import PredictionService
from student_success.schema import load_config
from student_success.storage import AuditStore


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.getenv("INSTITUTION_CONFIG", ROOT / "config/institutions/northstar_metropolitan.json"))
EXPLICIT_MODEL_PATH = os.getenv("MODEL_PATH")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data/student_success.db"))
API_KEY = os.getenv("STUDENT_SUCCESS_API_KEY", "development-only-key")

config = load_config(CONFIG_PATH)
default_model = ROOT / "models/northstar/model_bundle.joblib" if config.get("institution_id") == "northstar-metropolitan-university" else None
service = PredictionService(config, Path(EXPLICIT_MODEL_PATH) if EXPLICIT_MODEL_PATH else default_model, allow_demo_score=False)
store = AuditStore(DATABASE_PATH)
app = FastAPI(title="Student Success AI API", version="1.0.0")


class StudentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    student_id: str = Field(min_length=1, max_length=100)


class BatchRequest(BaseModel):
    students: list[dict] = Field(min_length=1, max_length=5000)


def authorize(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "institution_id": config.get("institution_id"),
        "model_loaded": service.bundle is not None,
    }


@app.post("/v1/predict", dependencies=[Depends(authorize)])
def predict(request: BatchRequest):
    try:
        results, warnings = service.predict(pd.DataFrame(request.students))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    records = json.loads(results.to_json(orient="records"))
    for record in records:
        record["audit_id"] = store.record(config.get("institution_id", "unknown"), record)
    return {"predictions": records, "warnings": warnings}


@app.get("/v1/audit/recent", dependencies=[Depends(authorize)])
def recent_audit(limit: int = 100):
    return {"items": store.recent(min(max(limit, 1), 1000))}

