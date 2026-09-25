import base64

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth
from app.ml.predict import risk_score, model_info, reload_model

router = APIRouter(prefix="/quality-tests", tags=["quality"])

MAX_CERT_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_CERT_MIMES = {"application/pdf", "image/png", "image/jpeg"}


@router.post("", response_model=schemas.QualityTestOut)
def create_quality_test(payload: schemas.QualityTestCreate, db: Session = Depends(get_db),
                         user: models.User = Depends(auth.require_roles("admin", "producer"))):
    batch = db.query(models.Batch).filter(models.Batch.id == payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.status == models.BatchStatusEnum.recalled:
        raise HTTPException(status_code=409,
                            detail="Batch has been recalled — quality results can no longer change its status.")

    scored = risk_score(
        ph=payload.ph, brix=payload.brix,
        microbial_cfu=payload.microbial_cfu, temperature_c=payload.temperature_c,
    )

    test = models.QualityTest(
        batch_id=payload.batch_id,
        ph=payload.ph,
        brix=payload.brix,
        microbial_cfu=payload.microbial_cfu,
        temperature_c=payload.temperature_c,
        notes=payload.notes,
        result=scored["result"],
        risk_score=scored["risk_score"],
        tested_by=user.id,
    )
    db.add(test)

    # Update batch status based on this test's outcome
    batch.status = (
        models.BatchStatusEnum.passed_qc if scored["result"] == "pass"
        else models.BatchStatusEnum.failed_qc
    )
    db.add(models.SupplyChainEvent(
        batch_id=batch.id, actor_id=user.id, event_type=models.EventTypeEnum.quality_check,
        location=user.organization or "QC Lab",
        notes=f"Result: {scored['result']} (risk score {scored['risk_score']})",
    ))
    db.commit()
    db.refresh(test)
    return test


@router.get("/batch/{batch_id}", response_model=List[schemas.QualityTestOut])
def get_tests_for_batch(batch_id: str, db: Session = Depends(get_db)):
    return db.query(models.QualityTest).filter(models.QualityTest.batch_id == batch_id).all()


@router.post("/predict")
def predict_only(ph: float = None, brix: float = None,
                  microbial_cfu: float = None, temperature_c: float = None,
                  user: models.User = Depends(auth.get_current_user)):
    """Score hypothetical readings without saving — useful for a 'what-if' UI panel."""
    return risk_score(ph=ph, brix=brix, microbial_cfu=microbial_cfu, temperature_c=temperature_c)


@router.get("/model-info", response_model=schemas.ModelInfoOut)
def get_model_info(user: models.User = Depends(auth.get_current_user)):
    """Training metrics, cross-validation results and feature importances."""
    return model_info()


@router.post("/retrain", response_model=schemas.ModelInfoOut)
def retrain(user: models.User = Depends(auth.require_roles("admin"))):
    """Retrain the RandomForest on fresh synthetic data and hot-reload it."""
    from app.ml.train_model import train
    metrics = train(verbose=False)
    reload_model()
    return model_info(extra=metrics)


# ---------- Lab certificates (PDF / image per test) ----------

def _get_test(db: Session, test_id: str) -> models.QualityTest:
    test = db.query(models.QualityTest).filter(models.QualityTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Quality test not found")
    return test


@router.post("/{test_id}/certificate")
async def upload_certificate(test_id: str, file: UploadFile = File(...),
                              db: Session = Depends(get_db),
                              user: models.User = Depends(auth.require_roles("admin", "producer"))):
    """Attach the lab's PDF/image certificate to a quality test."""
    test = _get_test(db, test_id)

    mime = (file.content_type or "").lower()
    if mime not in ALLOWED_CERT_MIMES:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported file type '{mime}'. Allowed: PDF, PNG, JPEG.")

    data = await file.read()
    if len(data) > MAX_CERT_BYTES:
        raise HTTPException(status_code=413, detail="Certificate larger than 5 MB")

    test.certificate_filename = file.filename or "certificate"
    test.certificate_mime = mime
    test.certificate_data = base64.b64encode(data).decode()
    db.commit()

    return {"test_id": test.id, "filename": test.certificate_filename, "mime": test.certificate_mime}


@router.get("/{test_id}/certificate")
def download_certificate(test_id: str, db: Session = Depends(get_db),
                          user: models.User = Depends(auth.get_current_user)):
    test = _get_test(db, test_id)
    if not test.certificate_data:
        raise HTTPException(status_code=404, detail="No certificate attached to this test")

    data = base64.b64decode(test.certificate_data)
    return Response(
        content=data,
        media_type=test.certificate_mime or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{test.certificate_filename or "certificate"}"'},
    )


@router.delete("/{test_id}/certificate")
def delete_certificate(test_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(auth.require_roles("admin", "producer"))):
    test = _get_test(db, test_id)
    test.certificate_filename = None
    test.certificate_mime = None
    test.certificate_data = None
    db.commit()
    return {"detail": "Certificate removed"}
