import logging
import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import Base, engine, SessionLocal
from app.routers import (
    auth_router, suppliers, batches, quality, supply_chain, qr, verify,
    recall, dashboard, cold_chain, scans, alerts, export,
)

VERSION = "1.0.0"
STARTED_AT = time.time()

# ---- logging: one structured access line per request (request id included) ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tracecert.access")
# uvicorn's own access log would duplicate our lines
logging.getLogger("uvicorn.access").handlers = []

# ---- rate limiting for the public verify endpoint (per process, per IP) ----
VERIFY_RATE_LIMIT = int(os.getenv("VERIFY_RATE_LIMIT", "60"))  # requests / window
VERIFY_RATE_WINDOW = int(os.getenv("VERIFY_RATE_WINDOW", "60"))  # seconds
_verify_hits: "dict[str, deque]" = defaultdict(deque)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Beverage Quality Verification & Traceability System",
    description="Batch tracking, QC scoring (rule-based + ML), supply-chain traceability, "
                "QR-based consumer verification, recall management, cold-chain monitoring, "
                "and anti-counterfeit scan analysis.",
    version=VERSION,
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
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id (echoed as X-Request-ID), rate limiting for public verify,
    and a single structured access log line per request."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    started = time.perf_counter()

    # Rate limit only the public, unauthenticated verify route.
    if request.method == "GET" and request.url.path.startswith("/verify"):
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = _verify_hits[ip]
        while hits and now - hits[0] > VERIFY_RATE_WINDOW:
            hits.popleft()
        if len(hits) >= VERIFY_RATE_LIMIT:
            retry_after = max(1, int(VERIFY_RATE_WINDOW - (now - hits[0])) + 1)
            logger.info("%s %s -> 429 rate-limited in %.1fms rid=%s",
                        request.method, request.url.path, (time.perf_counter() - started) * 1000, rid)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many verification requests — try again shortly."},
                headers={"X-Request-ID": rid, "Retry-After": str(retry_after)},
            )
        hits.append(now)

    try:
        response = await call_next(request)
    except Exception:
        # log with the request id, then let Starlette's error middleware handle it
        logger.exception("%s %s -> 500 rid=%s", request.method, request.url.path, rid)
        raise

    response.headers["X-Request-ID"] = rid
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info("%s %s -> %s in %.1fms rid=%s",
                request.method, request.url.path, response.status_code, duration_ms, rid)
    return response


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
        "version": VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    """Liveness + readiness probe: database reachability, ML model presence and
    process uptime. Safe for load balancers (200 when ok, 503 when degraded)."""
    # database
    db_status = "ok"
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # ML model files (model.pkl + metrics.json ship with the repo)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    has_model = os.path.exists(os.path.join(base_dir, "ml", "model.pkl"))
    has_metrics = os.path.exists(os.path.join(base_dir, "ml", "metrics.json"))
    model_status = "ml" if (has_model and has_metrics) else "untrained"

    status = "ok" if db_status == "ok" else "degraded"
    body = {
        "status": status,
        "version": VERSION,
        "database": db_status,
        "model": model_status,
        "uptime_seconds": int(time.time() - STARTED_AT),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return JSONResponse(status_code=200 if status == "ok" else 503, content=body)
