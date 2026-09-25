"""
Cold-chain monitoring.

Temperature readings arrive either one-by-one from an IoT device
(POST /cold-chain/readings) or in bulk from the simulator
(POST /cold-chain/simulate/{batch_id} or the CLI at app/simulate_cold_chain.py).
Readings outside the safe range are counted as "breaches" and feed the
QC / recall story.
"""
import random
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/cold-chain", tags=["cold-chain"])

# Chilled beverage cold chain. Tune for your product (frozen = different range).
SAFE_MIN_C = 0.0
SAFE_MAX_C = 8.0


def build_stats(readings: List[models.TemperatureReading]) -> schemas.ColdChainStats:
    if not readings:
        return schemas.ColdChainStats(readings=0, safe_min_c=SAFE_MIN_C, safe_max_c=SAFE_MAX_C)

    temps = [r.temperature_c for r in readings]
    breaches = sum(1 for t in temps if t < SAFE_MIN_C or t > SAFE_MAX_C)
    return schemas.ColdChainStats(
        readings=len(temps),
        min_c=round(min(temps), 2),
        max_c=round(max(temps), 2),
        avg_c=round(sum(temps) / len(temps), 2),
        breaches=breaches,
        breach_pct=round(100 * breaches / len(temps), 1),
        safe_min_c=SAFE_MIN_C,
        safe_max_c=SAFE_MAX_C,
        last_reading_at=readings[-1].recorded_at,
    )


def get_batch_or_404(db: Session, batch_id: str) -> models.Batch:
    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


def generate_readings(batch: models.Batch, hours: int = 24, interval_minutes: int = 30,
                      induce_breach: bool = False, location: str = None,
                      end_at: datetime = None) -> List[models.TemperatureReading]:
    """Random walk around the 4°C setpoint; optionally a refrigeration failure
    partway through. Returns detached TemperatureReading objects (not added)."""
    hours = max(1, int(hours))
    interval_minutes = max(1, int(interval_minutes))
    points = min(max(1, int((hours * 60) / interval_minutes)), 2000)
    end_at = end_at or models.utcnow()
    start = end_at - timedelta(minutes=interval_minutes * (points - 1))
    location = location or (
        batch.raw_material.supplier.name
        if batch.raw_material and batch.raw_material.supplier else "In transit"
    )

    temp = random.uniform(3.5, 5.0)
    readings = []
    for i in range(points):
        if induce_breach and i > points * 0.55:
            # refrigeration failure: drifts up above the safe ceiling
            target = random.uniform(9.5, 13.0)
            temp += (target - temp) * 0.35 + random.uniform(-0.3, 0.3)
        else:
            temp += random.uniform(-0.6, 0.6)
            temp += (4.2 - temp) * 0.15          # pull back toward setpoint
        temp = max(-1.0, min(18.0, temp))

        readings.append(models.TemperatureReading(
            batch_id=batch.id,
            temperature_c=round(temp, 2),
            location=location,
            device_id="sim-gateway-01",
            recorded_at=start + timedelta(minutes=interval_minutes * i),
        ))
    return readings


@router.post("/readings", response_model=schemas.TemperatureReadingOut)
def record_reading(payload: schemas.TemperatureReadingCreate,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_roles("admin", "producer", "distributor"))):
    """Single reading pushed by a sensor/gateway (auth required — devices use a service account)."""
    get_batch_or_404(db, payload.batch_id)

    reading = models.TemperatureReading(
        batch_id=payload.batch_id,
        temperature_c=payload.temperature_c,
        location=payload.location,
        device_id=payload.device_id,
        recorded_at=payload.recorded_at or models.utcnow(),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.get("/batch/{batch_id}", response_model=schemas.ColdChainOut)
def get_cold_chain(batch_id: str, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.get_current_user)):
    """Full reading history (chronological) + min/avg/max/breach stats."""
    get_batch_or_404(db, batch_id)
    readings = (
        db.query(models.TemperatureReading)
        .filter(models.TemperatureReading.batch_id == batch_id)
        .order_by(models.TemperatureReading.recorded_at.asc())
        .all()
    )
    return schemas.ColdChainOut(
        batch_id=batch_id,
        stats=build_stats(readings),
        readings=readings,
    )


@router.post("/simulate/{batch_id}", response_model=schemas.ColdChainOut)
def simulate_readings(batch_id: str, payload: schemas.ColdChainSimulateRequest,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(auth.require_roles("admin", "producer", "distributor"))):
    """
    Generate a realistic-looking shipment history of readings in one call —
    a random walk around 4°C, optionally crossing the safe range partway
    through (a refrigeration failure) so there is something to demo.
    """
    batch = get_batch_or_404(db, batch_id)
    if payload.hours <= 0 or payload.interval_minutes <= 0:
        raise HTTPException(status_code=400, detail="hours and interval_minutes must be positive")

    created = generate_readings(
        batch,
        hours=payload.hours,
        interval_minutes=payload.interval_minutes,
        induce_breach=payload.induce_breach,
        location=payload.location,
    )
    for r in created:
        db.add(r)
    db.commit()
    for r in created:
        db.refresh(r)

    # Stats cover the batch's whole history (not just what we generated) so
    # this response matches what GET /cold-chain/batch/{id} would return.
    history = (
        db.query(models.TemperatureReading)
        .filter(models.TemperatureReading.batch_id == batch_id)
        .order_by(models.TemperatureReading.recorded_at.asc())
        .all()
    )
    return schemas.ColdChainOut(batch_id=batch_id, stats=build_stats(history), readings=created)
