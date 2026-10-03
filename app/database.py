import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Database Connection URL
# Replace 'mahadev' with whatever password you set for the postgres user during installation
DEFAULT_PG_URL = "postgresql://postgres:mahadev@localhost:5432/task_intranet_db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_PG_URL)

# 2. Configure engine parameters based on database type
if "sqlite" in DATABASE_URL:
    # Local single-file database fallback for development
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # Production-ready PostgreSQL connection pooling for high concurrency (3,000 employees)
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,          # Maintains 20 persistent connections ready in memory
        max_overflow=40,       # Allows bursting up to 60 simultaneous connections during peak hours
        pool_pre_ping=True,    # Checks if connection is alive before issuing queries (avoids stale connection drops)
        pool_recycle=1800      # Recycles connections every 30 minutes
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()