"""Pydantic schemas (request/response models)."""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, EmailStr, ConfigDict


# ---------- Auth / Users ----------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "producer"
    organization: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    email: EmailStr
    role: str
    organization: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Supplier ----------
class SupplierCreate(BaseModel):
    name: str
    location: Optional[str] = None
    contact: Optional[str] = None


class SupplierOut(SupplierCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


# ---------- Raw Material ----------
class RawMaterialBatchCreate(BaseModel):
    supplier_id: str
    material_type: str
    quantity_kg: Optional[float] = None


class SupplierBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    location: Optional[str] = None


class RawMaterialBatchOut(RawMaterialBatchCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    received_date: datetime
    supplier: Optional[SupplierBrief] = None


# ---------- Batch ----------
class BatchCreate(BaseModel):
    product_name: str
    raw_material_id: Optional[str] = None
    expiry_date: Optional[datetime] = None
    volume_liters: Optional[float] = None


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_code: str
    product_name: str
    production_date: datetime
    expiry_date: Optional[datetime] = None
    volume_liters: Optional[float] = None
    status: str


class BatchDetailOut(BatchOut):
    quality_tests: List["QualityTestOut"] = []
    events: List["SupplyChainEventOut"] = []
    raw_material: Optional[RawMaterialBatchOut] = None


# ---------- Quality Test ----------
class QualityTestCreate(BaseModel):
    batch_id: str
    ph: Optional[float] = None
    brix: Optional[float] = None
    microbial_cfu: Optional[float] = None
    temperature_c: Optional[float] = None
    notes: Optional[str] = None


class QualityTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    ph: Optional[float] = None
    brix: Optional[float] = None
    microbial_cfu: Optional[float] = None
    temperature_c: Optional[float] = None
    result: Optional[str] = None
    risk_score: Optional[float] = None
    notes: Optional[str] = None
    tested_at: datetime
    certificate_filename: Optional[str] = None  # non-null => a lab certificate is attached


# ---------- Supply Chain Event ----------
class SupplyChainEventCreate(BaseModel):
    batch_id: str
    event_type: str
    location: Optional[str] = None
    notes: Optional[str] = None


class SupplyChainEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    event_type: str
    location: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime


# ---------- QR ----------
class QRCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    code_value: str
    scan_count: int


# ---------- Cold chain (IoT temperature readings) ----------
class TemperatureReadingCreate(BaseModel):
    batch_id: str
    temperature_c: float
    location: Optional[str] = None
    device_id: Optional[str] = None
    recorded_at: Optional[datetime] = None


class TemperatureReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    temperature_c: float
    location: Optional[str] = None
    device_id: Optional[str] = None
    recorded_at: datetime


class ColdChainStats(BaseModel):
    readings: int
    min_c: Optional[float] = None
    max_c: Optional[float] = None
    avg_c: Optional[float] = None
    breaches: int = 0          # readings outside the safe range
    breach_pct: float = 0.0
    safe_min_c: float
    safe_max_c: float
    last_reading_at: Optional[datetime] = None


class ColdChainOut(BaseModel):
    batch_id: str
    stats: ColdChainStats
    readings: List[TemperatureReadingOut] = []


class ColdChainSimulateRequest(BaseModel):
    hours: int = 24
    interval_minutes: int = 30
    induce_breach: bool = False
    location: Optional[str] = None


# ---------- Anti-counterfeit scan analysis ----------
class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    location: Optional[str] = None
    user_agent: Optional[str] = None
    scanned_at: datetime


class ScanAnalysisOut(BaseModel):
    batch_id: str
    code_value: Optional[str] = None
    total_scans: int
    scans_24h: int
    scans_7d: int
    distinct_locations_24h: int
    distinct_locations_7d: int
    first_scan_at: Optional[datetime] = None
    last_scan_at: Optional[datetime] = None
    risk_level: str                 # "low" | "medium" | "high"
    flags: List[str] = []
    recent_scans: List[ScanOut] = []


# ---------- Recall ----------
class RecallCreate(BaseModel):
    batch_id: str
    reason: str


class RecallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    reason: str
    date: datetime
    affected_locations: Optional[str] = None


# ---------- Public Verification ----------
class VerificationOut(BaseModel):
    valid: bool
    batch_code: Optional[str] = None
    product_name: Optional[str] = None
    status: Optional[str] = None
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    supplier_name: Optional[str] = None
    latest_quality_result: Optional[str] = None
    risk_score: Optional[float] = None
    journey: List[SupplyChainEventOut] = []
    message: Optional[str] = None
    scan_count: Optional[int] = None
    alert: Optional[str] = None     # anti-counterfeit warning shown to consumers


# ---------- Alerts ----------
class AlertOut(BaseModel):
    id: str                         # stable id, e.g. "counterfeit:<batch_id>"
    type: str                       # counterfeit | qc_failed | recalled | cold_chain | expiring
    severity: str                   # critical | warning | info
    batch_id: str
    batch_code: Optional[str] = None
    product_name: Optional[str] = None
    message: str
    created_at: datetime


# ---------- Supplier performance ----------
class SupplierStatsOut(BaseModel):
    supplier_id: str
    name: str
    location: Optional[str] = None
    lots: int = 0                      # raw material lots received
    total_quantity_kg: Optional[float] = None
    batches_linked: int = 0            # batches produced from this supplier's lots
    qc_tests: int = 0                  # QC tests across those batches
    qc_pass_rate: Optional[float] = None   # 0..1, None when nothing was tested
    avg_risk_score: Optional[float] = None # mean ML risk across those tests
    recalls: int = 0                   # recalls among linked batches


# ---------- Batch timeline ----------
class TimelineEntry(BaseModel):
    at: datetime
    kind: str                   # production | qc | event | scan | breach | recall
    title: str
    detail: Optional[str] = None
    severity: str = "info"      # info | warning | critical


class BatchTimelineOut(BaseModel):
    batch_id: str
    batch_code: str
    entries: List[TimelineEntry] = []
    counts: Dict[str, int] = {}     # per-kind counts plus "total"


# ---------- ML model info ----------
class ModelInfoOut(BaseModel):
    source: str                     # "ml" | "rule_based"
    trained_at: Optional[str] = None
    sklearn_version: Optional[str] = None
    n_samples: Optional[int] = None
    positive_rate: Optional[float] = None
    holdout: Optional[dict] = None
    cross_validation: Optional[dict] = None
    feature_importances: Optional[list] = None
    confusion: Optional[dict] = None
    message: Optional[str] = None


BatchDetailOut.model_rebuild()
