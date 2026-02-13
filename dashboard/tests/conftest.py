import os
import sys
import tempfile
import pytest

# Add dashboard directory to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.db import BenchmarkDB


@pytest.fixture
def db():
    """Provide an in-memory BenchmarkDB for testing."""
    return BenchmarkDB(":memory:")


@pytest.fixture
def db_file(tmp_path):
    """Provide a file-backed BenchmarkDB for testing."""
    db_path = str(tmp_path / "test_benchmarks.db")
    return BenchmarkDB(db_path)
