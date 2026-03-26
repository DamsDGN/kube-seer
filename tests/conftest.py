import pytest
from datetime import datetime, timezone


@pytest.fixture
def sample_timestamp():
    return datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
