"""
SQLAlchemy engine/session setup. Why Postgres at all (rather than just
returning JSON and forgetting it): storing each analysis run lets the
frontend list past uploads, and storing per-customer scores is what makes
the "high-risk customer table" and campaign export usable outside the
single request/response cycle.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
