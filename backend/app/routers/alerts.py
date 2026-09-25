"""
Consolidated alert feed: everything that needs a human's attention, in one
list — counterfeit flags, QC failures, cold-chain breaches, expiring stock
and active recalls. Sorted critical-first.
"""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/alerts", tags=["alerts"])

EXPIRY_WARNING_DAYS = 7
SCAN_VELOCITY_24H = 5      # keep in sync with routers/scans.py
SCAN_SPREAD_24H = 3        # keep in sync with routers/scans.py


@router.get("", response_model=List[schemas.AlertOut])
def list_alerts(db: Session = Depends(get_db),
                user: models.User = Depends(auth.get_current_user)):
    now = models.utcnow()
    since_24h = now - timedelta(hours=24)
    alerts: List[schemas.AlertOut] = []

    def batch_map(ids):
        if not ids:
            return {}
        rows = db.query(models.Batch).filter(models.Batch.id.in_(list(ids))).all()
        return {b.id: b for b in rows}

    # ---- 1. Anti-counterfeit: QR codes lighting up ----
    velocity = {
        bid: c for bid, c in (
            db.query(models.QRScan.batch_id, func.count(models.QRScan.id))
            .filter(models.QRScan.scanned_at >= since_24h)
            .group_by(models.QRScan.batch_id).all()
        ) if c >= SCAN_VELOCITY_24H
    }
    spread = {
        bid: c for bid, c in (
            db.query(models.QRScan.batch_id, func.count(func.distinct(models.QRScan.location)))
            .filter(models.QRScan.scanned_at >= since_24h, models.QRScan.location.isnot(None))
            .group_by(models.QRScan.batch_id).all()
        ) if c >= SCAN_SPREAD_24H
    }
    for bid, batch in batch_map(set(velocity) | set(spread)).items():
        parts = []
        if bid in velocity:
            parts.append(f"{velocity[bid]} scans in 24h")
        if bid in spread:
            parts.append(f"{spread[bid]} different locations in 24h")
        last = (db.query(func.max(models.QRScan.scanned_at))
                .filter(models.QRScan.batch_id == bid).scalar())
        alerts.append(schemas.AlertOut(
            id=f"counterfeit:{bid}", type="counterfeit", severity="critical",
            batch_id=bid, batch_code=batch.batch_code, product_name=batch.product_name,
            message="Possible cloned QR code — " + ", ".join(parts) + ".",
            created_at=last or now,
        ))

    # ---- 2. QC failures sitting in the system ----
    failed = db.query(models.Batch).filter(
        models.Batch.status == models.BatchStatusEnum.failed_qc).all()
    for batch in failed:
        last_test = (db.query(models.QualityTest)
                     .filter(models.QualityTest.batch_id == batch.id)
                     .order_by(models.QualityTest.tested_at.desc()).first())
        alerts.append(schemas.AlertOut(
            id=f"qc_failed:{batch.id}", type="qc_failed", severity="critical",
            batch_id=batch.id, batch_code=batch.batch_code, product_name=batch.product_name,
            message=(f"Batch failed QC (risk score {last_test.risk_score}). "
                     "Blocked from distribution until it passes a new test."),
            created_at=last_test.tested_at if last_test else batch.created_at,
        ))

    # ---- 3. Active recalls ----
    recalled = (db.query(models.Batch, models.RecallLog)
                .join(models.RecallLog, models.RecallLog.batch_id == models.Batch.id)
                .filter(models.Batch.status == models.BatchStatusEnum.recalled)
                .order_by(models.RecallLog.date.desc()).all())
    for batch, log in recalled:
        alerts.append(schemas.AlertOut(
            id=f"recalled:{batch.id}", type="recalled", severity="critical",
            batch_id=batch.id, batch_code=batch.batch_code, product_name=batch.product_name,
            message=f"Batch recalled — {log.reason}",
            created_at=log.date,
        ))

    # ---- 4. Cold-chain breaches in the last 24h ----
    breach_rows = (
        db.query(models.TemperatureReading.batch_id,
                 func.count(models.TemperatureReading.id),
                 func.max(models.TemperatureReading.temperature_c),
                 func.max(models.TemperatureReading.recorded_at))
        .filter(models.TemperatureReading.recorded_at >= since_24h,
                (models.TemperatureReading.temperature_c > 8) |
                (models.TemperatureReading.temperature_c < 0))
        .group_by(models.TemperatureReading.batch_id).all()
    )
    for bid, count, peak, last_at in breach_rows:
        batch = db.get(models.Batch, bid)
        if not batch or batch.status == models.BatchStatusEnum.recalled:
            continue   # already covered by the recall alert
        alerts.append(schemas.AlertOut(
            id=f"cold_chain:{bid}", type="cold_chain", severity="warning",
            batch_id=bid, batch_code=batch.batch_code, product_name=batch.product_name,
            message=f"Cold-chain breach: {count} readings outside 0–8 °C in 24h (peak {peak} °C).",
            created_at=last_at or now,
        ))

    # ---- 5. Expiring / expired stock ----
    horizon = now + timedelta(days=EXPIRY_WARNING_DAYS)
    expiring = db.query(models.Batch).filter(
        models.Batch.expiry_date.isnot(None),
        models.Batch.expiry_date <= horizon,
        models.Batch.status.notin_([
            models.BatchStatusEnum.recalled, models.BatchStatusEnum.failed_qc,
        ]),
    ).all()
    for batch in expiring:
        expired = batch.expiry_date <= now
        alerts.append(schemas.AlertOut(
            id=f"expiring:{batch.id}", type="expiring",
            severity="critical" if expired else "warning",
            batch_id=batch.id, batch_code=batch.batch_code, product_name=batch.product_name,
            message=("Expired " if expired else "Expires within "
                     f"{EXPIRY_WARNING_DAYS} days: {batch.expiry_date:%Y-%m-%d}."),
            created_at=batch.expiry_date,
        ))

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_rank.get(a.severity, 3), -a.created_at.timestamp()))
    return alerts
