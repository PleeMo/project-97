"""
Public consumer verification — the endpoint the QR code points at.

No auth. Every call is recorded as a QRScan (client timezone + user agent +
hashed IP, raw IPs are never stored), which feeds the anti-counterfeit
analysis in routers/scans.py.
"""
import hashlib
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/verify", tags=["public-verification"])

IP_HASH_SALT = os.getenv("IP_HASH_SALT", "tracecert-dev-salt")


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{IP_HASH_SALT}:{ip}".encode()).hexdigest()[:32]


@router.get("/{batch_code}", response_model=schemas.VerificationOut)
def verify_batch(batch_code: str, request: Request, tz: str = None,
                 db: Session = Depends(get_db)):
    """
    PUBLIC endpoint (no auth) — this is what a consumer hits after scanning the
    QR code on the product. Returns origin, quality status, the supply chain
    journey, and any anti-counterfeit warning raised by scan patterns.

    `tz` is the browser's timezone (e.g. Africa/Kigali) — a permission-free
    approximation of "where was this scanned", used for clone detection.
    """
    batch = db.query(models.Batch).filter(models.Batch.batch_code == batch_code).first()
    if not batch:
        return schemas.VerificationOut(
            valid=False,
            message="No record found for this code. This product may be counterfeit "
                    "or the code was entered incorrectly.",
        )

    client_ip = request.client.host if request.client else "unknown"
    scan = models.QRScan(
        batch_id=batch.id,
        location=tz,
        user_agent=(request.headers.get("user-agent") or "")[:250],
        ip_hash=_hash_ip(client_ip),
        scanned_at=models.utcnow(),
    )
    db.add(scan)
    if batch.qr_code:
        batch.qr_code.scan_count = (batch.qr_code.scan_count or 0) + 1
    db.commit()

    latest_test = (
        db.query(models.QualityTest)
        .filter(models.QualityTest.batch_id == batch.id)
        .order_by(models.QualityTest.tested_at.desc())
        .first()
    )

    supplier_name = None
    if batch.raw_material and batch.raw_material.supplier:
        supplier_name = batch.raw_material.supplier.name

    journey = (
        db.query(models.SupplyChainEvent)
        .filter(models.SupplyChainEvent.batch_id == batch.id)
        .order_by(models.SupplyChainEvent.timestamp.asc())
        .all()
    )

    # --- Anti-counterfeit signal shown to the consumer ---
    since_24h = models.utcnow() - timedelta(hours=24)
    recent = (
        db.query(models.QRScan)
        .filter(models.QRScan.batch_id == batch.id, models.QRScan.scanned_at >= since_24h)
        .all()
    )
    recent_locs = {s.location for s in recent if s.location}
    alert = None
    if len(recent) >= 5 or len(recent_locs) >= 3:
        alert = ("This code has been scanned unusually often or from several "
                 "different places recently. It may have been copied — if the "
                 "packaging also looks tampered with, do not consume it.")

    if batch.status == models.BatchStatusEnum.recalled:
        message = "WARNING: This batch has been recalled."
    elif batch.status == models.BatchStatusEnum.failed_qc:
        message = "This batch did not pass quality control."
    else:
        message = "Verified genuine product."

    return schemas.VerificationOut(
        valid=True,
        batch_code=batch.batch_code,
        product_name=batch.product_name,
        status=batch.status.value if hasattr(batch.status, "value") else batch.status,
        production_date=batch.production_date,
        expiry_date=batch.expiry_date,
        supplier_name=supplier_name,
        latest_quality_result=latest_test.result if latest_test else None,
        risk_score=latest_test.risk_score if latest_test else None,
        journey=journey,
        message=message,
        scan_count=batch.qr_code.scan_count if batch.qr_code else None,
        alert=alert,
    )
