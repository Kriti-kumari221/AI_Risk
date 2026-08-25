import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "razorshield.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Audit Events Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT,
            agent_run_id TEXT,
            timestamp TEXT,
            action TEXT,
            reason TEXT,
            trace_json TEXT,
            evidence_json TEXT,
            confidence TEXT,
            cost_analysis_json TEXT
        )
    ''')
    
    # Human Review Queue Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT,
            agent_run_id TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
            agent_recommended_action TEXT,
            risk_score INTEGER,
            amount REAL,
            reviewer_decision TEXT,
            reviewer_reason TEXT,
            reviewed_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def save_audit(state: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO audit_events 
        (transaction_id, agent_run_id, timestamp, action, reason, trace_json, evidence_json, confidence, cost_analysis_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        state.get("transaction_id"),
        state.get("agent_run_id"),
        state.get("trace")[-1]["timestamp"] if state.get("trace") else "",
        state.get("final_decision"),
        state.get("audit_reason"),
        json.dumps(state.get("trace", [])),
        json.dumps(state.get("evidence", {})),
        state.get("confidence"),
        json.dumps(state.get("cost_analysis", {}))
    ))
    
    # If decision is REVIEW, add to queue
    if state.get("final_decision") == "REVIEW":
        # Check if already exists to prevent dupes in demo
        cursor.execute("SELECT id FROM reviews WHERE transaction_id = ?", (state.get("transaction_id"),))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO reviews
                (transaction_id, agent_run_id, created_at, agent_recommended_action, risk_score, amount)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                state.get("transaction_id"),
                state.get("agent_run_id"),
                state.get("trace")[0]["timestamp"] if state.get("trace") else "",
                state.get("recommended_action"),
                state.get("evidence", {}).get("fusion", {}).get("final_risk_score", 0),
                0 # Amount would come from original transaction, handled at app level
            ))
            
    conn.commit()
    conn.close()
