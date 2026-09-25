#!/usr/bin/env python
"""
Pre-deployment checklist — run this against the production environment before
going live:

    python scripts/deploy_check.py           # report (always exits 0 on warns)
    python scripts/deploy_check.py --strict  # exit 1 if any check FAILs

Verifies the environment the way an ops review would: secrets, CORS, absolute
QR URLs, database connectivity, ML model artifacts, required packages and a
frontend build.
"""
import importlib.util
import os
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Windows consoles default to cp1252 — the ✓/✗ markers need UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

DEFAULT_JWT_SECRET = "dev-secret-change-me-in-production"
DEFAULT_SALT = "tracecert-dev-salt"  # keep in sync with routers/verify.py

results = []  # (level, name, detail) with level in {"ok", "warn", "fail"}


def ok(name, detail=""):
    results.append(("ok", name, detail))


def warn(name, detail=""):
    results.append(("warn", name, detail))


def fail(name, detail=""):
    results.append(("fail", name, detail))


def check_python_version():
    v = sys.version_info
    if v >= (3, 10):
        ok("Python version", f"{v.major}.{v.minor}.{v.micro}")
    else:
        fail("Python version", f"{v.major}.{v.minor}.{v.micro} — need >= 3.10")


def check_packages():
    required = ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "jose",
                "passlib", "bcrypt", "qrcode", "sklearn", "pandas", "numpy"]
    missing = [p for p in required if importlib.util.find_spec(p) is None]
    if missing:
        fail("Required packages", "missing: " + ", ".join(missing))
    else:
        ok("Required packages", f"{len(required)} importable")


def check_env():
    # JWT_SECRET
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        warn("JWT_SECRET", "not set — dev placeholder will sign tokens")
    elif secret == DEFAULT_JWT_SECRET or len(secret) < 16:
        fail("JWT_SECRET", "still the default/too short — generate a long random value")
    else:
        ok("JWT_SECRET", f"set ({len(secret)} chars)")

    # CORS
    cors = os.getenv("CORS_ORIGINS", "*")
    if cors.strip() in ("*", ""):
        warn("CORS_ORIGINS", "wide open (*) — restrict to the frontend origin")
    else:
        ok("CORS_ORIGINS", cors)

    # QR codes need absolute URLs
    frontend = os.getenv("FRONTEND_URL", "")
    if not frontend:
        warn("FRONTEND_URL", "not set — QR codes encode relative paths (won't scan off-device)")
    elif not frontend.startswith("https://"):
        warn("FRONTEND_URL", f"not https: {frontend}")
    else:
        ok("FRONTEND_URL", frontend)

    # Database
    db_url = os.getenv("DATABASE_URL", "sqlite:///./traceability.db")
    if db_url.startswith("sqlite"):
        warn("DATABASE_URL", "SQLite — fine for demos, consider Postgres in production")
    else:
        ok("DATABASE_URL", db_url.split("://")[0] + " database")
        driver = "psycopg2" if db_url.startswith("postgres") else None
        if driver and importlib.util.find_spec(driver) is None:
            fail("DB driver", f"{driver} not installed for {db_url.split('://')[0]}")

    # IP hashing salt
    salt = os.getenv("IP_HASH_SALT", "")
    if not salt or salt == DEFAULT_SALT:
        warn("IP_HASH_SALT", "default/missing — scan IP hashes won't be unique per deployment")
    else:
        ok("IP_HASH_SALT", "set")


def check_database():
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        ok("Database connectivity", "SELECT 1 ok")
    except Exception as e:
        fail("Database connectivity", str(e))


def check_ml_model():
    ml_dir = BACKEND_DIR / "app" / "ml"
    model, metrics = ml_dir / "model.pkl", ml_dir / "metrics.json"
    if model.exists() and metrics.exists():
        size_kb = model.stat().st_size // 1024
        ok("ML model artifacts", f"model.pkl ({size_kb} kB) + metrics.json")
    else:
        warn("ML model artifacts", "missing — run: python -m app.ml.train_model")


def check_app_import():
    try:
        from app.main import app  # noqa: F401
        routes = len(app.routes)
        ok("Application import", f"{routes} routes")
    except Exception as e:
        fail("Application import", f"{type(e).__name__}: {e}")


def check_frontend_build():
    dist = BACKEND_DIR.parent / "frontend" / "dist" / "index.html"
    if dist.exists():
        ok("Frontend build", "frontend/dist present")
    else:
        warn("Frontend build", "missing — run: cd frontend && npm run build")


def main():
    strict = "--strict" in sys.argv
    for fn in (check_python_version, check_packages, check_env, check_database,
               check_ml_model, check_app_import, check_frontend_build):
        fn()

    icons = {"ok": "✓", "warn": "!", "fail": "✗"}
    width = max(len(name) for _, name, _ in results)
    print("\nTraceCert deployment checklist")
    print("=" * (width + 12))
    for level, name, detail in results:
        print(f" {icons[level]} {name.ljust(width)}  {detail}")
    counts = {k: sum(1 for lv, _, _ in results if lv == k) for k in ("ok", "warn", "fail")}
    print("=" * (width + 12))
    print(f" {counts['ok']} ok · {counts['warn']} warnings · {counts['fail']} failed")

    if counts["fail"] and strict:
        print("\nSTRICT mode: failing because of the ✗ items above.")
        sys.exit(1)
    if counts["fail"]:
        print("\nNote: failures above must be fixed before deploying (--strict to enforce).")
    elif counts["warn"]:
        print("\nWarnings are acceptable for demos; address them for production.")


if __name__ == "__main__":
    main()
