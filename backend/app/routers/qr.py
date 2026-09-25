import base64
import os
from io import BytesIO
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/qr", tags=["qr"])

# Absolute base URL baked into the QR code when set (e.g. https://app.example.com),
# so scans from any phone resolve. Empty => relative path, fine for local dev.
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")


@router.get("/{batch_id}")
def get_qr_image(batch_id: str, db: Session = Depends(get_db)):
    """
    Returns a base64 PNG data URI of the QR code for a batch.
    Frontend renders it directly as <img src="data:image/png;base64,...">.
    The QR encodes a public verification URL: {FRONTEND_URL}/verify/{batch_code}
    """
    qr_row = db.query(models.QRCode).filter(models.QRCode.batch_id == batch_id).first()
    if not qr_row:
        raise HTTPException(status_code=404, detail="QR code not found for this batch")

    verify_path = f"/verify/{qr_row.code_value}"  # frontend route
    verify_url = f"{FRONTEND_URL}{verify_path}"   # absolute URL when FRONTEND_URL is set
    img = qrcode.make(verify_url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "batch_code": qr_row.code_value,
        "verify_path": verify_path,
        "verify_url": verify_url,
        "scan_count": qr_row.scan_count,
        "image_base64": f"data:image/png;base64,{b64}",
    }
