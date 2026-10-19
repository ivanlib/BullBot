# Tests for the FastAPI app in offline demo mode, via TestClient (no network, no AWS).

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
sys.path.insert(0, WEB_DIR)


# Build a fresh app with demo mode on and AWS client creation blocked.
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BULLBOT_DEMO_MODE", "1")
    monkeypatch.delenv("BULLBOT_KB_ID", raising=False)
    monkeypatch.delenv("BULLBOT_GUARDRAIL_ID", raising=False)

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("AWS client created in demo mode")))

    import bullbot_core
    importlib.reload(bullbot_core)
    import app
    importlib.reload(app)
    return TestClient(app.app)


def test_health_reports_demo_mode(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_mode"] is True
    assert body["configured"] is True  # demo mode needs no AWS config


def test_chat_returns_answer_in_demo_mode(client):
    r = client.post("/api/chat",
                    json={"message": "What are the Cal Grant B renewal requirements?"})
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is False
    assert "cal-grant-b-policy.md" in body["answer"]
    assert body["session_id"]


def test_chat_blocks_pii_in_demo_mode(client):
    r = client.post("/api/chat", json={"message": "my ssn is 123-45-6789"})
    assert r.status_code == 200
    assert r.json()["blocked"] is True


def test_index_page_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "BullBot" in r.text


def test_empty_message_rejected(client):
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422  # pydantic min_length validation
