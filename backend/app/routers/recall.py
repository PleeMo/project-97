from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/recalls", tags=["recalls"])


@router.post("", response_model=schemas.RecallOut)
def trigger_recall(payload: schemas.RecallCreate, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.require_roles("admin", "producer"))):
    batch = db.query(models.Batch).filter(models.Batch.id == payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.status == models.BatchStatusEnum.recalled:
        raise HTTPException(status_code=409, detail="Batch is already recalled.")

    # Snapshot every downstream location this batch has touched — this is the
    # "which retailers/distributors are affected" demo moment.
    events = db.query(models.SupplyChainEvent).filter(models.SupplyChainEvent.batch_id == batch.id).all()
    locations = sorted({e.location for e in events if e.location})

    recall = models.RecallLog(
        batch_id=batch.id,
        reason=payload.reason,
        triggered_by=user.id,
        affected_locations=", ".join(locations) if locations else "No downstream locations recorded",
    )
    db.add(recall)

    batch.status = models.BatchStatusEnum.recalled
    db.add(models.SupplyChainEvent(
        batch_id=batch.id, actor_id=user.id, event_type=models.EventTypeEnum.recalled,
        location="System-wide", notes=payload.reason,
    ))
    db.commit()
    db.refresh(recall)
    return recall


@router.get("", response_model=List[schemas.RecallOut])
def list_recalls(db: Session = Depends(get_db)):
    return db.query(models.RecallLog).order_by(models.RecallLog.date.desc()).all()
