import sys
import os
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath('.'))

from Backend.app.main import app, startup_event
import asyncio

def test_api():
    # Trigger startup event manually for test client
    asyncio.run(startup_event())
    
    client = TestClient(app)
    
    # 1. Health check
    response = client.get("/health")
    print("Health:", response.json())
    
    # 2. Investigate fake transaction
    transaction = {
        "TransactionID": "TEST-1234",
        "TransactionAmt": 15000.0,  # High amount should trigger investigation
        "TransactionHour": 3,       # Weird hour
        "TransactionDay": 5,
        "has_identity": 0,
        "card1": "1234",
        "DeviceInfo": "iPhone_New",
        "P_emaildomain": "anonymous.com"
    }
    
    response = client.post("/api/v1/risk/investigate", json=transaction)
    print("Investigate Status:", response.status_code)
    result = response.json()
    print("Investigate Result:", json.dumps(result, indent=2))
    
    # 3. Check trace
    agent_run_id = result.get("agent_run_id")
    if agent_run_id:
        response = client.get(f"/api/v1/agent/{agent_run_id}/trace")
        print("Trace API Status:", response.status_code)

if __name__ == "__main__":
    test_api()
