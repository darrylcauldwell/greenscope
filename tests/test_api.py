import os

# Set database to in-memory SQLite before any app imports
os.environ["GREENSCOPE_DATABASE_URL"] = "sqlite+aiosqlite://"

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    with patch("app.main.start_scheduler"), patch("app.main.stop_scheduler"):
        from app.main import app

        with TestClient(app) as c:
            yield c


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_current_sci_empty(client):
    """Returns empty scores when no data exists."""
    response = client.get("/api/sci/current")
    assert response.status_code == 200
    data = response.json()
    assert data["scores"] == []
    assert "carbon_intensity_source" in data


def test_history_requires_app_name(client):
    """History endpoint requires app_name parameter."""
    response = client.get("/api/sci/history")
    assert response.status_code == 422


def test_breakdown_not_found(client):
    """Breakdown returns 404 for unknown app."""
    response = client.get("/api/sci/breakdown/nonexistent")
    assert response.status_code == 404
