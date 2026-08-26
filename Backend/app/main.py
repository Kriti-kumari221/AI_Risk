from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ml.model_loader import ModelLoader
from ml.inference import XGBoostRiskModel, AnomalyRiskModel
from ml.graph.graph_features import GraphFeatureBuilder
from ml.graph.graph_risk_tool import GraphRiskTool
from ml.fusion import RiskFusion
from agent.decision import CostAnalyzer, DecisionEngine
from agent.orchestrator import RiskAgentOrchestrator
from Backend.app.db.database import (
    init_db, save_audit, get_db,
    get_reviews, get_review_by_id, get_review_counters,
    start_review, approve_review, reject_review, escalate_review
)

app = FastAPI(title="RazorShield AI Risk Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
if os.path.exists(frontend_path):
    app.mount("/ui", StaticFiles(directory=frontend_path, html=True), name="frontend")

@app.get("/")
def root_redirect():
    return RedirectResponse(url="/ui/")

# Global instances
orchestrator = None

@app.on_event("startup")
async def startup_event():
    global orchestrator
    print("Initializing Database...")
    init_db()
    
    print("Loading Models...")
    loader = ModelLoader(models_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"))
    
    xgb_model, xgb_features = loader.load_xgboost()
    anomaly_model, anomaly_features, anomaly_scaler = loader.load_anomaly()
    
    xgb_tool = XGBoostRiskModel(xgb_model, xgb_features)
    anomaly_tool = AnomalyRiskModel(anomaly_model, anomaly_features, anomaly_scaler)
    
    graph_builder = GraphFeatureBuilder()
    graph_tool = GraphRiskTool(graph_builder)
    
    fusion_engine = RiskFusion()
    cost_analyzer = CostAnalyzer()
    decision_engine = DecisionEngine()
    
    orchestrator = RiskAgentOrchestrator(
        xgb_model=xgb_tool,
        anomaly_model=anomaly_tool,
        graph_tool=graph_tool,
        fusion_engine=fusion_engine,
        cost_analyzer=cost_analyzer,
        decision_engine=decision_engine
    )
    print("RazorShield Agent Ready.")

@app.get("/health")
def health_check():
    return {"status": "ok", "agent_loaded": orchestrator is not None}

@app.post("/api/v1/risk/investigate")
def investigate_transaction(transaction: dict, background_tasks: BackgroundTasks):
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Agent not initialized")
        
    state = orchestrator.investigate(transaction)
    
    # Save audit async
    background_tasks.add_task(save_audit, state)
    
    return {
        "transaction_id":       state.get("transaction_id"),
        "agent_run_id":         state.get("agent_run_id"),
        "final_decision":       state.get("final_decision"),
        "confidence":           state.get("confidence"),
        "reason":               state.get("audit_reason"),
        "risk_factors":         state.get("risk_factors", []),
        "recommended_followup": state.get("recommended_followup", ""),
        "llm_engine":           state.get("llm_engine", "unknown"),
        "duration_ms":          state.get("duration_ms"),
        "trace_summary":        state.get("trace", []),
        "cost_analysis":        state.get("cost_analysis", {}),
        "risk_score":           state.get("evidence", {}).get("fusion", {}).get("final_risk_score", 0),
        "risk_level":           state.get("risk_level", "UNKNOWN"),
        "graph_evidence":       state.get("evidence", {}).get("graph", {}),
    }

class PolicyEvaluateRequest(BaseModel):
    risk_score: int
    amount: float
    agent_proposal: Optional[str] = None

@app.get("/api/v1/policy")
def get_policy():
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return orchestrator.decision_engine.get_policy_details()

@app.post("/api/v1/policy/evaluate")
def evaluate_policy(req: PolicyEvaluateRequest):
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return orchestrator.decision_engine.evaluate_policy(
        risk_score=req.risk_score,
        amount=req.amount,
        agent_proposal=req.agent_proposal
    )

@app.get("/api/v1/agent/{agent_run_id}/trace")
def get_trace(agent_run_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_events WHERE agent_run_id = ?", (agent_run_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Trace not found")
        
    return dict(row)

# ── Review Queue Pydantic Schemas ─────────────────────────────────────────────

class ReviewStartRequest(BaseModel):
    reviewer: Optional[str] = "Analyst_1"

class ReviewActionRequest(BaseModel):
    reviewer: Optional[str] = "Analyst_1"
    reason: Optional[str] = None

class ReviewEscalateRequest(BaseModel):
    reviewer: Optional[str] = "Analyst_1"
    reason: str

class ReviewResolveRequest(BaseModel):
    reviewer: Optional[str] = "Analyst_1"
    decision: str  # APPROVED or REJECTED
    reason: Optional[str] = None

# ── Review Queue Endpoints ───────────────────────────────────────────────────

@app.get("/api/v1/reviews")
def fetch_reviews(
    active_only: bool = Query(False),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    reviewer: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    search: Optional[str] = Query(None)
):
    return get_reviews(
        active_only=active_only,
        status=status,
        risk_level=risk_level,
        reviewer=reviewer,
        min_score=min_score,
        max_score=max_score,
        search=search
    )

@app.get("/api/v1/reviews/counters")
def fetch_review_counters():
    return get_review_counters()

@app.get("/api/v1/reviews/history")
def fetch_review_history(
    risk_level: Optional[str] = Query(None),
    reviewer: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    search: Optional[str] = Query(None)
):
    return get_reviews(
        active_only=False,
        status="RESOLVED",
        risk_level=risk_level,
        reviewer=reviewer,
        min_score=min_score,
        max_score=max_score,
        search=search
    )

@app.get("/api/v1/reviews/{review_id}")
def fetch_review_by_id(review_id: int):
    review = get_review_by_id(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review case not found")
    return review

@app.post("/api/v1/reviews/{review_id}/start")
def api_start_review(review_id: int, req: ReviewStartRequest):
    try:
        return start_review(review_id, req.reviewer or "Analyst_1")
    except ValueError as e:
        msg = str(e)
        status_code = 409 if "being reviewed" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg)

@app.post("/api/v1/reviews/{review_id}/approve")
def api_approve_review(review_id: int, req: ReviewActionRequest):
    try:
        return approve_review(review_id, req.reviewer or "Analyst_1", req.reason or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/reviews/{review_id}/reject")
def api_reject_review(review_id: int, req: ReviewActionRequest):
    try:
        return reject_review(review_id, req.reviewer or "Analyst_1", req.reason or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/reviews/{review_id}/escalate")
def api_escalate_review(review_id: int, req: ReviewEscalateRequest):
    try:
        return escalate_review(review_id, req.reviewer or "Analyst_1", req.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/reviews/{review_id}/resolve")
def api_resolve_review(review_id: int, req: ReviewResolveRequest):
    decision_upper = (req.decision or "").upper()
    try:
        if decision_upper == "APPROVED":
            return approve_review(review_id, req.reviewer or "Analyst_1", req.reason or "")
        elif decision_upper == "REJECTED":
            return reject_review(review_id, req.reviewer or "Analyst_1", req.reason or "")
        else:
            raise HTTPException(status_code=400, detail="Invalid decision. Must be APPROVED or REJECTED.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/reviews/{review_id}/audit")
def fetch_review_audit_trail(review_id: int):
    review = get_review_by_id(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review case not found")
    return review.get("audit_trail", [])

