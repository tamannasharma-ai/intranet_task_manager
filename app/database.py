"""Disposable demo storage: no database file or external connection."""
from threading import Lock
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# DATABASE_URL is intentionally ignored on this demo branch.
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
session_lock = Lock()

def get_db():
    # One shared connection: serialize request transactions across worker threads.
    with session_lock:
        with SessionLocal() as db:
            yield db
