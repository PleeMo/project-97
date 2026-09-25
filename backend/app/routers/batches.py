import random
import string
from datetime import datetime
from math import ceil
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth
from app.routers.cold_chain import SAFE_MIN_C, SAFE_MAX_C

router = APIRouter(prefix="/batches", tags=["batches"])

# Columns the API accepts for sorting (whitelist — no raw SQL identifiers).
SORTABLE = {
    "production_date": models.Batch.production_date,
    "batch_code": models.Batch.batch_code,
    "product_name": models.Batch.product_name,
    "status": models.Batch.status,
    "expiry_date": models.Batch.expiry_date,
    "created_at": models.Batch.created_at,
}


def generate_batch_code(db: Session) -> str:
    year = models.utcnow().year
    while True:
        suffix = "".join(random.choices(string.digits, k=5))
        code = f"BQ-{year}-{suffix}"
        if not db.query(models.Batch).filter(models.Batch.batch_code == code).first():
            return code


@router.post("", response_model=schemas.BatchOut)
def create_batch(payload: schemas.BatchCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_roles("admin", "producer"))):
    batch = models.Batch(
        batch_code=generate_batch_code(db),
        product_name=payload.product_name,
        raw_material_id=payload.raw_material_id,
        expiry_date=payload.expiry_date,
        volume_liters=payload.volume_liters,
        created_by=user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # Auto-create QR code + "produced" event
    qr = models.QRCode(batch_id=batch.id, code_value=batch.batch_code)
    db.add(qr)
    event = models.SupplyChainEvent(
        batch_id=batch.id, actor_id=user.id, event_type=models.EventTypeEnum.produced,
        location=user.organization or "Production facility",
    )
    db.add(event)
    db.commit()

    return batch


@router.get("", response_model=Union[List[schemas.BatchOut], schemas.BatchPageOut])
def list_batches(
    db: Session = Depends(get_db),
    page: Optional[int] = Query(None, ge=1, description="Page number — omit for the full (legacy) list"),
    page_size: int = Query(20, ge=1, le=100, description="Rows per page (max 100)"),
    sort: Optional[str] = Query(None, description=f"Sort column: {', '.join(SORTABLE)}"),
    order: str = Query("desc", pattern="^(asc|desc)$", description="Sort direction"),
):
    """List batches.

    Without `page` this returns the full array (backwards compatible).
    With `page` it returns an envelope `{items, total, page, page_size, pages}`.
    `sort`/`order` apply in both modes.
    """
    if sort is not None and sort not in SORTABLE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sort by '{sort}'. Valid fields: {', '.join(sorted(SORTABLE))}",
        )

    query = db.query(models.Batch)
    if sort is None:
        query = query.order_by(models.Batch.created_at.desc())   # historical default
    else:
        column = SORTABLE[sort]
        query = query.order_by(column.desc() if order == "desc" else column.asc())

    if page is None:
        return query.all()

    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return schemas.BatchPageOut(
        items=rows,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, ceil(total / page_size)),
    )


@router.get("/{batch_id}", response_model=schemas.BatchDetailOut)
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


# Supply-chain events that carry their own entry elsewhere on the timeline
# (production and recalls are rendered from richer sources below).
_TIMELINE_SKIP_EVENTS = {"produced", "recalled"}


@router.get("/{batch_id}/timeline", response_model=schemas.BatchTimelineOut)
def batch_timeline(batch_id: str, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    """One chronological story of the batch: production, QC tests, logistics,
    QR scans, cold-chain breaches and recalls — newest first."""
    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    entries: List[schemas.TimelineEntry] = []

    # 1. Production
    produced = next((e for e in batch.events
                     if getattr(e.event_type, "value", e.event_type) == "produced"), None)
    entries.append(schemas.TimelineEntry(
        at=(produced.timestamp if produced else batch.created_at),
        kind="production",
        title="Batch produced",
        detail=(produced.location if produced and produced.location else batch.product_name),
        severity="info",
    ))

    # 2. Quality tests
    for t in batch.quality_tests:
        bits = []
        if t.risk_score is not None:
            bits.append(f"risk {round(t.risk_score, 1)}/100")
        if t.ph is not None:
            bits.append(f"pH {t.ph}")
        if t.microbial_cfu is not None:
            bits.append(f"CFU {t.microbial_cfu}")
        if t.certificate_filename:
            bits.append(f"cert: {t.certificate_filename}")
        if t.notes:
            bits.append(t.notes)
        failed = getattr(t.result, "value", t.result) == "fail"
        entries.append(schemas.TimelineEntry(
            at=t.tested_at,
            kind="qc",
            title="QC test failed" if failed else "QC test passed",
            detail=" · ".join(bits) or "no measurements",
            severity="critical" if failed else "info",
        ))

    # 3. Logistics events (shipped / received / sold / quality_check)
    for e in batch.events:
        etype = getattr(e.event_type, "value", e.event_type)
        if etype in _TIMELINE_SKIP_EVENTS:
            continue
        detail = " — ".join(x for x in [e.location, e.notes] if x) or None
        entries.append(schemas.TimelineEntry(
            at=e.timestamp,
            kind="event",
            title=etype.replace("_", " ").capitalize(),
            detail=detail,
            severity="info",
        ))

    # 4. Cold-chain breaches (only out-of-range readings — routine readings
    #    would bury the timeline; the chart already shows them all)
    for r in batch.temperature_readings:
        if SAFE_MIN_C <= r.temperature_c <= SAFE_MAX_C:
            continue
        where = " — ".join(x for x in [r.location, r.device_id] if x) or None
        entries.append(schemas.TimelineEntry(
            at=r.recorded_at,
            kind="breach",
            title=f"Cold-chain breach: {round(r.temperature_c, 1)}°C",
            detail=where,
            severity="warning",
        ))

    # 5. QR scans
    for s in batch.scan_events:
        entries.append(schemas.TimelineEntry(
            at=s.scanned_at,
            kind="scan",
            title="QR code scanned",
            detail=s.location or "unknown location",
            severity="info",
        ))

    # 6. Recalls
    for r in batch.recall_logs:
        detail = r.reason or "no reason recorded"
        if r.affected_locations:
            detail += f" — reached: {r.affected_locations}"
        entries.append(schemas.TimelineEntry(
            at=r.date,
            kind="recall",
            title="Batch recalled",
            detail=detail,
            severity="critical",
        ))

    entries.sort(key=lambda e: e.at, reverse=True)
    counts = {"total": len(entries)}
    for e in entries:
        counts[e.kind] = counts.get(e.kind, 0) + 1

    return schemas.BatchTimelineOut(
        batch_id=batch.id, batch_code=batch.batch_code,
        entries=entries, counts=counts,
    )
