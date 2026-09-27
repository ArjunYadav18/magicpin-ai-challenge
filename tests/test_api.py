import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_healthz():
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "contexts_loaded" in data

def test_metadata():
    response = client.get("/v1/metadata")
    assert response.status_code == 200
    data = response.json()
    assert "team_name" in data
    assert "version" in data

def test_context_idempotency():
    # Push v1
    payload_v1 = {
        "scope": "merchant",
        "context_id": "m_1",
        "version": 1,
        "payload": {"name": "Test"},
        "delivered_at": "2026-01-01T00:00:00Z"
    }
    r1 = client.post("/v1/context", json=payload_v1)
    assert r1.status_code == 200
    assert r1.json()["accepted"] is True
    
    # Push same v1 -> 409
    r2 = client.post("/v1/context", json=payload_v1)
    assert r2.status_code == 409
    assert r2.json()["reason"] == "stale_version"
    
    # Push v2 -> 200
    payload_v2 = {**payload_v1, "version": 2}
    r3 = client.post("/v1/context", json=payload_v2)
    assert r3.status_code == 200
    assert r3.json()["accepted"] is True
    
    # Push v1 again -> 409
    r4 = client.post("/v1/context", json=payload_v1)
    assert r4.status_code == 409

def test_tick_empty():
    response = client.post("/v1/tick", json={"now": "2026-01-01T00:00:00Z", "available_triggers": []})
    assert response.status_code == 200
    assert response.json() == {"actions": []}


def test_low_score_does_not_set_skip_reason():
    from app.decision import DecisionEngine
    from app.store import ContextStore

    store = ContextStore()
    engine = DecisionEngine(store)
    trigger = {
        "kind": "perf_dip",
        "scope": "merchant",
        "payload": {"metric": "calls", "delta_pct": -40},
        "urgency": 2,
    }
    merchant = {
        "merchant_id": "m_1",
        "category_slug": "dentists",
        "identity": {"owner_first_name": "Arjun"},
        "signals": [],
        "performance": {"calls": 120},
        "conversation_history": [],
        "offers": [],
    }
    category = {"slug": "dentists", "digest": []}

    result = engine.evaluate("t_1", trigger, merchant, category, None, None)
    assert result.skip_reason is None


def test_deterministic_performance_fallback_keeps_delta():
    from app.composer import LLMComposer

    composer = LLMComposer()
    merchant = {"identity": {"owner_first_name": "Arjun"}}
    trigger = {"payload": {"metric": "calls", "delta_pct": -40}}

    body, cta, rationale = composer._deterministic_tick(trigger, merchant, None, "performance", False)

    assert "-40%" in body or "40%" in body
    assert "calls" in body.lower()
    assert cta == "binary_yes_no" or cta == "open_ended"
