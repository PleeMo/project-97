"""
CSV data exports — for auditors, spreadsheets and offline reporting.

Every endpoint returns a plain text/csv attachment. Any logged-in role can
download (the data is already visible to them in the UI); nothing here
mutates state.
"""
import csv
import io
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/export", tags=["export"])

# Keep in sync with routers/cold_chain.py
SAFE_MIN_C = 0.0
SAFE_MAX_C = 8.0


def _iso(dt) -> str:
    return dt.isoformat(sep=" ", timespec="seconds") if isinstance(dt, datetime) else ""


def _enum(v):
    return getattr(v, "value", v)


def _csv_response(header: List[str], rows: List[list], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require_user(user: models.User = Depends(auth.get_current_user)) -> models.User:
    return user


@router.get("/batches.csv")
def export_batches(db: Session = Depends(get_db), user=Depends(_require_user)):
    """One row per batch: identity, shelf life, lineage and latest QC risk."""
    tests_by_batch = {}
    for t in db.query(models.QualityTest).all():
        tests_by_batch.setdefault(t.batch_id, []).append(t)

    rows = []
    for b in db.query(models.Batch).order_by(models.Batch.created_at.desc()).all():
        material = b.raw_material
        supplier = material.supplier if material else None
        tests = sorted(tests_by_batch.get(b.id, []), key=lambda t: t.tested_at)
        latest = tests[-1] if tests else None
        rows.append([
            b.batch_code,
            b.product_name,
            _enum(b.status),
            _iso(b.production_date),
            _iso(b.expiry_date),
            b.volume_liters if b.volume_liters is not None else "",
            supplier.name if supplier else "",
            material.material_type if material else "",
            round(latest.risk_score, 1) if latest and latest.risk_score is not None else "",
            _enum(latest.result) if latest and latest.result else "",
            len(tests),
            _iso(b.created_at),
        ])

    today = models.utcnow().date().isoformat()
    return _csv_response(
        ["batch_code", "product_name", "status", "production_date", "expiry_date",
         "volume_liters", "supplier", "material_type", "latest_risk_score",
         "latest_result", "qc_tests", "created_at"],
        rows, f"trace-batches-{today}.csv",
    )


@router.get("/quality-tests.csv")
def export_quality_tests(db: Session = Depends(get_db), user=Depends(_require_user)):
    """One row per QC test (the full lab history, certificate filenames included)."""
    code_of = {b.id: b.batch_code for b in db.query(models.Batch).all()}
    rows = []
    for t in db.query(models.QualityTest).order_by(models.QualityTest.tested_at.desc()).all():
        rows.append([
            code_of.get(t.batch_id, ""),
            _iso(t.tested_at),
            t.ph if t.ph is not None else "",
            t.brix if t.brix is not None else "",
            t.microbial_cfu if t.microbial_cfu is not None else "",
            t.temperature_c if t.temperature_c is not None else "",
            _enum(t.result) or "",
            round(t.risk_score, 1) if t.risk_score is not None else "",
            t.certificate_filename or "",
            (t.notes or "").replace("\n", " "),
        ])
    today = models.utcnow().date().isoformat()
    return _csv_response(
        ["batch_code", "tested_at", "ph", "brix", "microbial_cfu", "temperature_c",
         "result", "risk_score", "certificate_filename", "notes"],
        rows, f"trace-quality-tests-{today}.csv",
    )


@router.get("/scans.csv")
def export_scans(db: Session = Depends(get_db), user=Depends(_require_user)):
    """Every public QR verification attempt (raw IP is never stored — only a hash)."""
    code_of = {b.id: b.batch_code for b in db.query(models.Batch).all()}
    rows = []
    for s in db.query(models.QRScan).order_by(models.QRScan.scanned_at.desc()).all():
        rows.append([
            code_of.get(s.batch_id, ""),
            _iso(s.scanned_at),
            s.location or "",
            (s.user_agent or "")[:80],
            (s.ip_hash or "")[:12],
        ])
    today = models.utcnow().date().isoformat()
    return _csv_response(
        ["batch_code", "scanned_at", "location", "user_agent", "ip_hash_prefix"],
        rows, f"trace-scans-{today}.csv",
    )


@router.get("/temperatures.csv")
def export_temperatures(db: Session = Depends(get_db), user=Depends(_require_user)):
    """Cold-chain telemetry with an in_safe_range flag per reading."""
    code_of = {b.id: b.batch_code for b in db.query(models.Batch).all()}
    rows = []
    for r in db.query(models.TemperatureReading).order_by(models.TemperatureReading.recorded_at.desc()).all():
        in_range = SAFE_MIN_C <= r.temperature_c <= SAFE_MAX_C
        rows.append([
            code_of.get(r.batch_id, ""),
            _iso(r.recorded_at),
            round(r.temperature_c, 2),
            "yes" if in_range else "no",
            r.location or "",
            r.device_id or "",
        ])
    today = models.utcnow().date().isoformat()
    return _csv_response(
        ["batch_code", "recorded_at", "temperature_c", "in_safe_range", "location", "device_id"],
        rows, f"trace-temperatures-{today}.csv",
    )


@router.get("/recalls.csv")
def export_recalls(db: Session = Depends(get_db), user=Depends(_require_user)):
    """Recall register: what was pulled back, why, and where it had reached."""
    code_of = {b.id: b.batch_code for b in db.query(models.Batch).all()}
    rows = []
    for r in db.query(models.RecallLog).order_by(models.RecallLog.date.desc()).all():
        rows.append([
            code_of.get(r.batch_id, ""),
            _iso(r.date),
            (r.reason or "").replace("\n", " "),
            (r.affected_locations or "").replace("\n", " "),
        ])
    today = models.utcnow().date().isoformat()
    return _csv_response(
        ["batch_code", "date", "reason", "affected_locations"],
        rows, f"trace-recalls-{today}.csv",
    )
