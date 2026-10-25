import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import tempfile

import pytest

# Never reuse a developer/live database, even if the shell exports its URL.
_TEST_DATABASE_DIR = tempfile.TemporaryDirectory(prefix="harbor-tests-")
os.environ["HARBOR_DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE_DIR.name}/harbor.db"


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    # Legacy tests construct TestClient without a lifespan context manager.
    from backend.app.database import init_db
    init_db()
