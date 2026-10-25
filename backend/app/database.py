import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./harbor.db"
DATABASE_URL = os.getenv("HARBOR_DATABASE_URL", DEFAULT_DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        # Serialize inspection + ALTER across workers. All identifiers below
        # are fixed application constants, never request-controlled values.
        additions = {
            "incidents": {"water_depth_cm": "FLOAT", "observed_at": "DATETIME", "location": "VARCHAR(240)"},
            "resources": {"latitude": "FLOAT", "longitude": "FLOAT"},
            "critical_alerts": {
                "acknowledged_by": "VARCHAR(120)",
                "verified_at": "DATETIME",
                "verified_by": "VARCHAR(120)",
                "verification_evidence": "TEXT",
                "dispatch_status": "VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUESTED'",
                "dispatch_operator": "VARCHAR(120)",
                "dispatch_reference": "VARCHAR(240)",
                "dispatch_updated_at": "DATETIME",
            },
        }
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                for table, columns in additions.items():
                    existing = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")')}
                    for column, sql_type in columns.items():
                        if column not in existing:
                            connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}')
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def database_file_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    return Path(DATABASE_URL.replace("sqlite:///", "", 1)).resolve()


def database_is_online() -> bool:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False
