from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("", response_model=schemas.SupplierOut)
def create_supplier(payload: schemas.SupplierCreate, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.require_roles("admin", "producer"))):
    supplier = models.Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("", response_model=List[schemas.SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    return db.query(models.Supplier).all()


@router.get("/stats", response_model=List[schemas.SupplierStatsOut])
def supplier_stats(db: Session = Depends(get_db),
                   user: models.User = Depends(auth.get_current_user)):
    """Supplier scorecard: lots received, batches produced from them, QC pass
    rate and recall count — who feeds the line, and how well it turns out."""
    suppliers = db.query(models.Supplier).all()
    lots = db.query(models.RawMaterialBatch).all()
    batches = db.query(models.Batch).all()
    tests = db.query(models.QualityTest).all()
    recalls = db.query(models.RecallLog).all()

    lot_supplier = {l.id: l.supplier_id for l in lots}
    qty_by_supplier = defaultdict(float)
    for l in lots:
        if l.quantity_kg is not None:
            qty_by_supplier[l.supplier_id] += l.quantity_kg

    batches_by_supplier = defaultdict(list)
    for b in batches:
        sid = lot_supplier.get(b.raw_material_id)
        if sid:
            batches_by_supplier[sid].append(b)

    batch_supplier = {b.id: sid for sid, bs in batches_by_supplier.items() for b in bs}
    tests_by_supplier = defaultdict(list)
    for t in tests:
        sid = batch_supplier.get(t.batch_id)
        if sid:
            tests_by_supplier[sid].append(t)
    recalls_by_supplier = defaultdict(int)
    for r in recalls:
        sid = batch_supplier.get(r.batch_id)
        if sid:
            recalls_by_supplier[sid] += 1

    out = []
    for s in suppliers:
        sbatches = batches_by_supplier[s.id]
        stests = tests_by_supplier[s.id]
        scored = [t.risk_score for t in stests if t.risk_score is not None]
        passed = sum(1 for t in stests if t.result == "pass")
        out.append(schemas.SupplierStatsOut(
            supplier_id=s.id,
            name=s.name,
            location=s.location,
            lots=sum(1 for l in lots if l.supplier_id == s.id),
            total_quantity_kg=round(qty_by_supplier[s.id], 1) if qty_by_supplier[s.id] else None,
            batches_linked=len(sbatches),
            qc_tests=len(stests),
            qc_pass_rate=round(passed / len(stests), 3) if stests else None,
            avg_risk_score=round(sum(scored) / len(scored), 1) if scored else None,
            recalls=recalls_by_supplier[s.id],
        ))
    return out


@router.post("/raw-materials", response_model=schemas.RawMaterialBatchOut)
def create_raw_material_batch(payload: schemas.RawMaterialBatchCreate, db: Session = Depends(get_db),
                               user: models.User = Depends(auth.require_roles("admin", "producer"))):
    rmb = models.RawMaterialBatch(**payload.model_dump())
    db.add(rmb)
    db.commit()
    db.refresh(rmb)
    return rmb


@router.get("/raw-materials", response_model=List[schemas.RawMaterialBatchOut])
def list_raw_material_batches(db: Session = Depends(get_db)):
    return db.query(models.RawMaterialBatch).all()
