import sys
import os
import json
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath('.'))

from Backend.app.main import app, startup_event
from Backend.app.db.database import get_db, save_audit, init_db

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_module():
    init_db()

def create_sample_review_case(tx_id="TEST-TXN-101"):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM reviews WHERE transaction_id = ?", (tx_id,))
    c.execute("DELETE FROM audit_events WHERE transaction_id = ?", (tx_id,))
    c.execute("DELETE FROM review_audit_events WHERE transaction_id = ?", (tx_id,))
    conn.commit()
    conn.close()

    state = {
        "transaction_id": tx_id,
        "agent_run_id": f"test-run-{tx_id}",
        "final_decision": "REVIEW",
        "recommended_action": "REVIEW",
        "audit_reason": "High fraud probability trigger",
        "policy_reason": "Policy Rule 3: Manual review above risk threshold",
        "confidence": "HIGH",
        "risk_level": "HIGH RISK",
        "amount": 25000.0,
        "llm_engine": "Groq llama-3.3-70b",
        "llm_summary": "Suspicious late night transaction from new device.",
        "risk_factors": ["High Transaction Amount", "Unknown Device", "Suspicious Hour"],
        "recommended_followup": "Contact customer to verify identity.",
        "trace": [
            {"timestamp": "2026-08-26T12:00:00Z", "step": "RECEIVED", "details": "Received"},
            {"timestamp": "2026-08-26T12:00:01Z", "step": "ACTION_AUTHORIZED", "details": "REVIEW"}
        ],
        "evidence": {
            "xgboost": {"risk_score": 85, "top_features": ["amount", "hour"]},
            "anomaly": {"anomaly_score": 75, "novelty_level": "HIGH"},
            "graph": {"graph_risk_score": 60, "signals": ["shared_device_count > 2"]},
            "fusion": {"final_risk_score": 82}
        },
        "cost_analysis": {
            "costs": {"ALLOW": 15000, "VERIFY": 200, "REVIEW": 50, "BLOCK": 500},
            "recommended_action_by_cost": "REVIEW",
            "chargeback_exposure": 25000
        }
    }
    save_audit(state)
    
    # Get the created review ID
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM reviews WHERE transaction_id = ?", (tx_id,))
    row = c.fetchone()
    conn.close()
    return row["id"]

def test_counters_api():
    res = client.get("/api/v1/reviews/counters")
    assert res.status_code == 200
    data = res.json()
    assert "pending" in data
    assert "in_review" in data
    assert "escalated" in data
    assert "resolved_today" in data

def test_full_review_lifecycle_approve():
    tx_id = "TXN-LIFECYCLE-APPROVE"
    review_id = create_sample_review_case(tx_id)
    
    # 1. Fetch active queue - case should be present as PENDING
    active_res = client.get("/api/v1/reviews?active_only=true")
    assert active_res.status_code == 200
    active_cases = active_res.json()
    case = next((c for c in active_cases if c["id"] == review_id), None)
    assert case is not None
    assert case["status"] == "PENDING"
    
    # 2. Start Review: PENDING -> IN_REVIEW
    start_res = client.post(f"/api/v1/reviews/{review_id}/start", json={"reviewer": "Analyst_Alice"})
    assert start_res.status_code == 200
    started_case = start_res.json()
    assert started_case["status"] == "IN_REVIEW"
    assert started_case["reviewer"] == "Analyst_Alice"
    assert started_case["started_at"] is not None
    
    # 3. Concurrency check: another reviewer tries to start
    conflict_res = client.post(f"/api/v1/reviews/{review_id}/start", json={"reviewer": "Analyst_Bob"})
    assert conflict_res.status_code == 409
    
    # 4. Approve Case: IN_REVIEW -> RESOLVED
    approve_res = client.post(f"/api/v1/reviews/{review_id}/approve", json={
        "reviewer": "Analyst_Alice",
        "reason": "Verified user via phone call."
    })
    assert approve_res.status_code == 200
    approved_case = approve_res.json()
    assert approved_case["status"] == "RESOLVED"
    assert approved_case["reviewer_decision"] == "APPROVED"
    assert approved_case["reviewer_reason"] == "Verified user via phone call."
    assert approved_case["reviewed_at"] is not None
    
    # 5. Verify case immediately disappears from active queue
    active_res_after = client.get("/api/v1/reviews?active_only=true")
    active_ids = [c["id"] for c in active_res_after.json()]
    assert review_id not in active_ids
    
    # 6. Verify case appears in Review History
    history_res = client.get("/api/v1/reviews/history")
    assert history_res.status_code == 200
    history_ids = [c["id"] for c in history_res.json()]
    assert review_id in history_ids
    
    # 7. Audit trail check
    audit_res = client.get(f"/api/v1/reviews/{review_id}/audit")
    assert audit_res.status_code == 200
    trail = audit_res.json()
    actions = [t["action"] for t in trail]
    assert "REVIEW_CREATED" in actions
    assert "REVIEW_STARTED" in actions
    assert "REVIEW_APPROVED" in actions
    assert "REVIEW_RESOLVED" in actions

def test_full_review_lifecycle_escalate_and_reject():
    tx_id = "TXN-LIFECYCLE-ESCALATE"
    review_id = create_sample_review_case(tx_id)
    
    # 1. Start Review
    client.post(f"/api/v1/reviews/{review_id}/start", json={"reviewer": "Analyst_Bob"})
    
    # 2. Escalate Case without reason (should fail with 400)
    fail_esc = client.post(f"/api/v1/reviews/{review_id}/escalate", json={"reviewer": "Analyst_Bob", "reason": ""})
    assert fail_esc.status_code == 400
    
    # 3. Escalate Case with valid reason: IN_REVIEW -> ESCALATED
    esc_res = client.post(f"/api/v1/reviews/{review_id}/escalate", json={
        "reviewer": "Analyst_Bob",
        "reason": "Conflicting device signals; requires senior review"
    })
    assert esc_res.status_code == 200
    esc_case = esc_res.json()
    assert esc_case["status"] == "ESCALATED"
    assert esc_case["escalation_reason"] == "Conflicting device signals; requires senior review"
    
    # 4. Verify case REMAINS in active queue while ESCALATED
    active_res = client.get("/api/v1/reviews?active_only=true")
    active_ids = [c["id"] for c in active_res.json()]
    assert review_id in active_ids
    
    # 5. Reject Case (Resolve): ESCALATED -> RESOLVED
    reject_res = client.post(f"/api/v1/reviews/{review_id}/reject", json={
        "reviewer": "Senior_Analyst_Charlie",
        "reason": "Confirmed stolen card credentials."
    })
    assert reject_res.status_code == 200
    resolved_case = reject_res.json()
    assert resolved_case["status"] == "RESOLVED"
    assert resolved_case["reviewer_decision"] == "REJECTED"
    
    # 6. Verify case no longer in active queue
    active_res_after = client.get("/api/v1/reviews?active_only=true")
    active_ids_after = [c["id"] for c in active_res_after.json()]
    assert review_id not in active_ids_after

if __name__ == "__main__":
    pytest.main(["-v", __file__])
