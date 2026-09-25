"""
Database setup.
Default: SQLite file (zero-config, great for demos/dev).
To switch to Postgres for production, just change DATABASE_URL, e.g.:
  postgresql://user:password@localhost:5432/beverage_traceability
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load backend/.env if present so local overrides need no export step.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./traceability.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
