from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    total_batches = db.query(func.count(models.Batch.id)).scalar()
    passed = db.query(func.count(models.Batch.id)).filter(models.Batch.status == models.BatchStatusEnum.passed_qc).scalar()
    failed = db.query(func.count(models.Batch.id)).filter(models.Batch.status == models.BatchStatusEnum.failed_qc).scalar()
    recalled = db.query(func.count(models.Batch.id)).filter(models.Batch.status == models.BatchStatusEnum.recalled).scalar()
    in_transit = db.query(func.count(models.Batch.id)).filter(models.Batch.status == models.BatchStatusEnum.in_transit).scalar()

    avg_risk = db.query(func.avg(models.QualityTest.risk_score)).scalar()

    status_breakdown = (
        db.query(models.Batch.status, func.count(models.Batch.id))
        .group_by(models.Batch.status)
        .all()
    )

    # --- Anti-counterfeit: batches whose QR code is lighting up ---
    since_24h = models.utcnow() - timedelta(hours=24)
    velocity_flagged = {
        row[0] for row in (
            db.query(models.QRScan.batch_id)
            .filter(models.QRScan.scanned_at >= since_24h)
            .group_by(models.QRScan.batch_id)
            .having(func.count(models.QRScan.id) >= 5)
            .all()
        )
    }
    spread_flagged = {
        row[0] for row in (
            db.query(models.QRScan.batch_id)
            .filter(models.QRScan.scanned_at >= since_24h, models.QRScan.location.isnot(None))
            .group_by(models.QRScan.batch_id)
            .having(func.count(func.distinct(models.QRScan.location)) >= 3)
            .all()
        )
    }

    # --- Cold chain: readings outside 0-8C in the last 24h ---
    breaches_24h = (
        db.query(func.count(models.TemperatureReading.id))
        .filter(
            models.TemperatureReading.recorded_at >= since_24h,
            (models.TemperatureReading.temperature_c > 8) | (models.TemperatureReading.temperature_c < 0),
        )
        .scalar()
    )

    total_scans = db.query(func.count(models.QRScan.id)).scalar() or 0

    return {
        "total_batches": total_batches or 0,
        "passed_qc": passed or 0,
        "failed_qc": failed or 0,
        "recalled": recalled or 0,
        "in_transit": in_transit or 0,
        "average_risk_score": round(avg_risk, 1) if avg_risk else 0,
        "total_scans": total_scans,
        "flagged_batches": len(velocity_flagged | spread_flagged),
        "cold_chain_breaches_24h": breaches_24h or 0,
        "status_breakdown": [
            {"status": s.value if hasattr(s, "value") else s, "count": c}
            for s, c in status_breakdown
        ],
    }


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """14-day aligned time series (scans, cold-chain breaches, avg risk) plus
    risk buckets — feeds the dashboard charts."""
    today = models.utcnow().date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    start = datetime.combine(days[0], datetime.min.time())

    scan_rows = (
        db.query(func.date(models.QRScan.scanned_at), func.count(models.QRScan.id))
        .filter(models.QRScan.scanned_at >= start)
        .group_by(func.date(models.QRScan.scanned_at)).all()
    )
    scans = {str(d): c for d, c in scan_rows}

    breach_rows = (
        db.query(func.date(models.TemperatureReading.recorded_at),
                 func.count(models.TemperatureReading.id))
        .filter(models.TemperatureReading.recorded_at >= start,
                (models.TemperatureReading.temperature_c > 8) |
                (models.TemperatureReading.temperature_c < 0))
        .group_by(func.date(models.TemperatureReading.recorded_at)).all()
    )
    breaches = {str(d): c for d, c in breach_rows}

    risk_rows = (
        db.query(func.date(models.QualityTest.tested_at),
                 func.avg(models.QualityTest.risk_score))
        .filter(models.QualityTest.tested_at >= start)
        .group_by(func.date(models.QualityTest.tested_at)).all()
    )
    avg_risk = {str(d): round(float(r), 1) for d, r in risk_rows if r is not None}

    # Risk buckets across the latest test of every batch
    buckets = {"low": 0, "moderate": 0, "high": 0, "untested": 0}
    for batch in db.query(models.Batch).all():
        latest = (
            db.query(models.QualityTest)
            .filter(models.QualityTest.batch_id == batch.id)
            .order_by(models.QualityTest.tested_at.desc())
            .first()
        )
        if latest is None or latest.risk_score is None:
            buckets["untested"] += 1
        elif latest.risk_score >= 50:
            buckets["high"] += 1
        elif latest.risk_score >= 25:
            buckets["moderate"] += 1
        else:
            buckets["low"] += 1

    return {
        "days": [
            {
                "date": d.isoformat(),
                "scans": scans.get(str(d), 0),
                "breaches": breaches.get(str(d), 0),
                "avg_risk": avg_risk.get(str(d)),
            }
            for d in days
        ],
        "risk_buckets": [{"bucket": k, "count": v} for k, v in buckets.items()],
    }
