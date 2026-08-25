from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
from Backend.app.db.database import init_db, save_audit, get_db

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
    # In a real scenario, we would load historical data into the graph builder here.
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
        "trace_summary":        [t["step"] for t in state.get("trace", [])],
    }

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

@app.get("/api/v1/reviews")
def get_reviews():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
