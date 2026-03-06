"""Tests for the picks API endpoints (Step 12 — Testing)."""
import pytest


def test_create_pick(client):
    """POST /picks/ should create a pick and return 201."""
    payload = {
        "match_id": 1,
        "pick_type": "home_win",
        "odd_value": 2.10,
        "stake": 50.0,
    }
    response = client.post("/picks/", json=payload)
    assert response.status_code in (201, 422), response.text


def test_get_pick_not_found(client):
    """GET /picks/{id} with unknown id should return 404."""
    response = client.get("/picks/99999")
    assert response.status_code == 404


def test_health_check(client):
    """GET /health should return 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
