"""
Anti-counterfeit analysis built on QR scan telemetry.

A genuine batch code is scanned occasionally, from few places. A cloned code
(photographed and stuck on counterfeit bottles) lights up from many locations
in a short window — so we flag scan velocity + geographic spread.
"""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/scans", tags=["anti-counterfeit"])

# Thresholds — tune for your market. A shelf-stable product in one city will
# legitimately scan far less often than a national campaign.
HIGH_VELOCITY_24H = 20      # scans/day before we call it high risk
MED_VELOCITY_24H = 5
HIGH_SPREAD_24H = 3         # distinct locations within 24h
HIGH_SPREAD_7D = 5


def analyse(db: Session, batch: models.Batch) -> schemas.ScanAnalysisOut:
    now = models.utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    scans: List[models.QRScan] = (
        db.query(models.QRScan)
        .filter(models.QRScan.batch_id == batch.id)
        .order_by(models.QRScan.scanned_at.desc())
        .all()
    )
    s24 = [s for s in scans if s.scanned_at >= since_24h]
    s7 = [s for s in scans if s.scanned_at >= since_7d]

    locs_24h = {s.location for s in s24 if s.location}
    locs_7d = {s.location for s in s7 if s.location}

    flags: List[str] = []
    risk = "low"

    if len(s24) >= HIGH_VELOCITY_24H:
        flags.append(f"Unusual scan velocity: {len(s24)} scans in the last 24h.")
        risk = "high"
    elif len(s24) >= MED_VELOCITY_24H:
        flags.append(f"Elevated scan volume: {len(s24)} scans in the last 24h.")
        risk = "medium"

    if len(locs_24h) >= HIGH_SPREAD_24H:
        flags.append(f"Scanned from {len(locs_24h)} different locations within 24h — a genuine bottle can only be in one place.")
        risk = "high"
    elif len(locs_7d) >= HIGH_SPREAD_7D:
        flags.append(f"Scanned from {len(locs_7d)} different locations within 7 days.")
        risk = "high" if risk == "high" else "medium"
    elif len(locs_7d) >= 3 and risk == "low":
        flags.append(f"Scanned from {len(locs_7d)} different locations within 7 days.")
        risk = "medium"

    # Scan before the batch was even produced is a strong counterfeit hint
    if batch.qr_code and scans and batch.production_date:
        early = [s for s in scans if s.scanned_at < batch.production_date]
        if early:
            flags.append("This code was scanned before the batch was produced.")
            risk = "high"

    return schemas.ScanAnalysisOut(
        batch_id=batch.id,
        code_value=batch.qr_code.code_value if batch.qr_code else None,
        total_scans=len(scans),
        scans_24h=len(s24),
        scans_7d=len(s7),
        distinct_locations_24h=len(locs_24h),
        distinct_locations_7d=len(locs_7d),
        first_scan_at=scans[-1].scanned_at if scans else None,
        last_scan_at=scans[0].scanned_at if scans else None,
        risk_level=risk,
        flags=flags,
        recent_scans=scans[:10],
    )


@router.get("/batch/{batch_id}", response_model=schemas.ScanAnalysisOut)
def scan_analysis(batch_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_roles("admin", "producer"))):
    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return analyse(db, batch)
