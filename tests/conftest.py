import pytest

from database import init_database


@pytest.fixture()
def db_path(tmp_path):
    """A fresh, isolated database for every test (never touches data/students.db)."""
    return init_database(tmp_path / "test.db")
