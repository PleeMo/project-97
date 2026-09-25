"""
SQLAlchemy ORM models for the Beverage Quality Verification & Traceability System.

Core flow:
  Supplier -> RawMaterialBatch -> Batch (production) -> QualityTest(s)
  Batch -> SupplyChainEvent(s) (produced -> shipped -> received -> sold)
  Batch -> QRCode (public verification)
  Batch -> RecallLog (if it fails / needs recall)
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, Enum, Boolean, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow() -> datetime:
    """Timezone-naive UTC now — what SQLite stores; avoids the deprecated
    datetime.utcnow() on Python 3.12+."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def gen_uuid():
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    admin = "admin"
    producer = "producer"
    distributor = "distributor"
    retailer = "retailer"


class BatchStatusEnum(str, enum.Enum):
    in_production = "in_production"
    passed_qc = "passed_qc"
    failed_qc = "failed_qc"
    in_transit = "in_transit"
    delivered = "delivered"
    recalled = "recalled"


class EventTypeEnum(str, enum.Enum):
    produced = "produced"
    quality_check = "quality_check"
    shipped = "shipped"
    received = "received"
    sold = "sold"
    recalled = "recalled"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.producer)
    organization = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    contact = Column(String, nullable=True)

    raw_material_batches = relationship("RawMaterialBatch", back_populates="supplier")


class RawMaterialBatch(Base):
    __tablename__ = "raw_material_batches"
    id = Column(String, primary_key=True, default=gen_uuid)
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=False)
    material_type = Column(String, nullable=False)  # e.g. "Oranges", "Milk"
    quantity_kg = Column(Float, nullable=True)
    received_date = Column(DateTime, default=utcnow)

    supplier = relationship("Supplier", back_populates="raw_material_batches")
    batches = relationship("Batch", back_populates="raw_material")


class Batch(Base):
    __tablename__ = "batches"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_code = Column(String, unique=True, nullable=False, index=True)  # human readable e.g. BQ-2026-0001
    product_name = Column(String, nullable=False)
    raw_material_id = Column(String, ForeignKey("raw_material_batches.id"), nullable=True)
    production_date = Column(DateTime, default=utcnow)
    expiry_date = Column(DateTime, nullable=True)
    volume_liters = Column(Float, nullable=True)
    status = Column(Enum(BatchStatusEnum), default=BatchStatusEnum.in_production)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    raw_material = relationship("RawMaterialBatch", back_populates="batches")
    quality_tests = relationship("QualityTest", back_populates="batch", cascade="all, delete-orphan")
    events = relationship("SupplyChainEvent", back_populates="batch", cascade="all, delete-orphan")
    qr_code = relationship("QRCode", back_populates="batch", uselist=False, cascade="all, delete-orphan")
    recall_logs = relationship("RecallLog", back_populates="batch", cascade="all, delete-orphan")
    temperature_readings = relationship("TemperatureReading", back_populates="batch", cascade="all, delete-orphan")
    scan_events = relationship("QRScan", back_populates="batch", cascade="all, delete-orphan")


class QualityTest(Base):
    __tablename__ = "quality_tests"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False)
    ph = Column(Float, nullable=True)
    brix = Column(Float, nullable=True)              # sugar content
    microbial_cfu = Column(Float, nullable=True)      # colony forming units / mL
    temperature_c = Column(Float, nullable=True)
    result = Column(String, nullable=True)             # "pass" / "fail" (rule-based)
    risk_score = Column(Float, nullable=True)          # ML model output 0-100
    tested_by = Column(String, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    tested_at = Column(DateTime, default=utcnow)

    # Lab certificate attached to this test (PDF/image kept as base64 so the
    # demo stays zero-config — swap to S3/object storage for real deployments)
    certificate_filename = Column(String, nullable=True)
    certificate_mime = Column(String, nullable=True)
    certificate_data = Column(Text, nullable=True)

    batch = relationship("Batch", back_populates="quality_tests")


class SupplyChainEvent(Base):
    __tablename__ = "supply_chain_events"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    event_type = Column(Enum(EventTypeEnum), nullable=False)
    location = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    batch = relationship("Batch", back_populates="events")


class QRCode(Base):
    __tablename__ = "qr_codes"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), unique=True, nullable=False)
    code_value = Column(String, unique=True, nullable=False)  # what's encoded / looked up
    scan_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    batch = relationship("Batch", back_populates="qr_code")


class RecallLog(Base):
    __tablename__ = "recall_logs"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False)
    reason = Column(Text, nullable=False)
    triggered_by = Column(String, ForeignKey("users.id"), nullable=True)
    date = Column(DateTime, default=utcnow)
    affected_locations = Column(Text, nullable=True)  # comma separated snapshot

    batch = relationship("Batch", back_populates="recall_logs")


class TemperatureReading(Base):
    """Cold-chain telemetry: a sensor reading pushed by an IoT device or the
    simulator (app/simulate_cold_chain.py)."""
    __tablename__ = "temperature_readings"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False, index=True)
    temperature_c = Column(Float, nullable=False)
    location = Column(String, nullable=True)
    device_id = Column(String, nullable=True)
    recorded_at = Column(DateTime, default=utcnow, index=True)

    batch = relationship("Batch", back_populates="temperature_readings")


class QRScan(Base):
    """Every public verification attempt (QR scan). Feeds the anti-counterfeit
    analysis: a genuine code is scanned rarely, from few places; a cloned code
    lights up from everywhere at once."""
    __tablename__ = "qr_scans"
    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False, index=True)
    location = Column(String, nullable=True)   # client timezone/region, if provided
    user_agent = Column(String, nullable=True)
    ip_hash = Column(String, nullable=True)    # hashed — raw IPs are never stored
    scanned_at = Column(DateTime, default=utcnow, index=True)

    batch = relationship("Batch", back_populates="scan_events")
