from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/supply-chain", tags=["supply-chain"])

# Lifecycle rules: where each logistics event may start from.
# QC'd stock can move; untested/failed/recalled stock cannot.
ALLOWED_FROM = {
    "shipped": {models.BatchStatusEnum.passed_qc, models.BatchStatusEnum.in_transit},
    "received": {models.BatchStatusEnum.in_transit},
    "sold": {models.BatchStatusEnum.in_transit, models.BatchStatusEnum.delivered},
}
SYSTEM_EVENTS = {"produced", "quality_check", "recalled"}  # created by their own endpoints


@router.post("/events", response_model=schemas.SupplyChainEventOut)
def create_event(payload: schemas.SupplyChainEventCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_roles("admin", "producer", "distributor", "retailer"))):
    batch = db.query(models.Batch).filter(models.Batch.id == payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if payload.event_type not in [e.value for e in models.EventTypeEnum]:
        raise HTTPException(status_code=400, detail="Invalid event_type")

    if payload.event_type in SYSTEM_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"'{payload.event_type}' is logged automatically — use the batch, "
                   "quality-test or recall endpoint instead.",
        )

    if batch.status == models.BatchStatusEnum.recalled:
        raise HTTPException(status_code=409,
                            detail="Batch has been recalled — no further movement allowed.")

    allowed = ALLOWED_FROM.get(payload.event_type)
    if allowed and batch.status not in allowed:
        allowed_names = ", ".join(sorted(s.value for s in allowed))
        raise HTTPException(
            status_code=409,
            detail=f"Cannot log '{payload.event_type}' while batch is "
                   f"'{batch.status.value}'. Allowed from: {allowed_names}.",
        )

    event = models.SupplyChainEvent(
        batch_id=payload.batch_id,
        actor_id=user.id,
        event_type=payload.event_type,
        location=payload.location,
        notes=payload.notes,
    )
    db.add(event)

    # Keep batch status roughly in sync with its latest logistics event
    status_map = {
        "shipped": models.BatchStatusEnum.in_transit,
        "received": models.BatchStatusEnum.in_transit,
        "sold": models.BatchStatusEnum.delivered,
    }
    if payload.event_type in status_map:
        batch.status = status_map[payload.event_type]

    db.commit()
    db.refresh(event)
    return event


@router.get("/events/batch/{batch_id}", response_model=List[schemas.SupplyChainEventOut])
def get_events_for_batch(batch_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.SupplyChainEvent)
        .filter(models.SupplyChainEvent.batch_id == batch_id)
        .order_by(models.SupplyChainEvent.timestamp.asc())
        .all()
    )
