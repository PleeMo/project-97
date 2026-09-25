import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import (
    auth_router, suppliers, batches, quality, supply_chain, qr, verify,
    recall, dashboard, cold_chain, scans, alerts, export,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Beverage Quality Verification & Traceability System",
    description="Batch tracking, QC scoring (rule-based + ML), supply-chain traceability, "
                "QR-based consumer verification, recall management, cold-chain monitoring, "
                "and anti-counterfeit scan analysis.",
    version="1.0.0",
)

# Comma-separated list of allowed origins. Defaults to wide open for local dev —
# set CORS_ORIGINS=https://your-frontend.example.com before deploying.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(suppliers.router)
app.include_router(batches.router)
app.include_router(quality.router)
app.include_router(supply_chain.router)
app.include_router(qr.router)
app.include_router(verify.router)
app.include_router(recall.router)
app.include_router(dashboard.router)
app.include_router(cold_chain.router)
app.include_router(scans.router)
app.include_router(alerts.router)
app.include_router(export.router)


@app.get("/")
def root():
    return {
        "service": "Beverage Quality Verification & Traceability System API",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
