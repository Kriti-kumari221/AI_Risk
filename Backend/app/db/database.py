import sqlite3
import json
import os
from datetime import datetime

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
            started_at TEXT,
            reviewed_at TEXT,
            status TEXT DEFAULT 'PENDING', -- PENDING, IN_REVIEW, ESCALATED, RESOLVED
            agent_recommended_action TEXT,
            policy_decision TEXT,
            risk_score INTEGER,
            risk_level TEXT,
            amount REAL,
            reviewer TEXT,
            reviewer_decision TEXT,
            reviewer_reason TEXT,
            escalation_reason TEXT,
            evidence_json TEXT,
            is_demo INTEGER DEFAULT 0
        )
    ''')

    # Detailed Human Review Audit Trail Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS review_audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER,
            transaction_id TEXT,
            reviewer TEXT,
            timestamp TEXT,
            previous_status TEXT,
            new_status TEXT,
            action TEXT,
            reason TEXT
        )
    ''')
    
    # Handle schema migrations for existing databases
    migrations = [
        ("started_at", "TEXT"),
        ("policy_decision", "TEXT"),
        ("risk_level", "TEXT"),
        ("reviewer", "TEXT"),
        ("evidence_json", "TEXT"),
        ("is_demo", "INTEGER DEFAULT 0"),
        ("escalation_reason", "TEXT")
    ]
    for col_name, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE reviews ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass # Column already exists

    # Migrate historical un-scoped pending records to demo/resolved status so active queue starts clean
    cursor.execute("UPDATE reviews SET is_demo = 1, status = 'RESOLVED', reviewer_decision = 'RESOLVED', reviewer = 'System', reviewer_reason = 'Historical demo record preserved' WHERE is_demo IS NULL OR (status = 'PENDING' AND created_at < '2026-08-26')")
    
    conn.commit()
    conn.close()

def record_review_audit(conn, review_id: int, transaction_id: str, reviewer: str, previous_status: str, new_status: str, action: str, reason: str):
    cursor = conn.cursor()
    now_iso = datetime.utcnow().isoformat() + "Z"
    cursor.execute('''
        INSERT INTO review_audit_events
        (review_id, transaction_id, reviewer, timestamp, previous_status, new_status, action, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (review_id, transaction_id, reviewer or "Analyst", now_iso, previous_status, new_status, action, reason))

def save_audit(state: dict):
    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.utcnow().isoformat() + "Z"
    
    cursor.execute('''
        INSERT INTO audit_events 
        (transaction_id, agent_run_id, timestamp, action, reason, trace_json, evidence_json, confidence, cost_analysis_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        state.get("transaction_id"),
        state.get("agent_run_id"),
        state.get("trace")[-1]["timestamp"] if state.get("trace") else now_iso,
        state.get("final_decision"),
        state.get("audit_reason"),
        json.dumps(state.get("trace", [])),
        json.dumps(state.get("evidence", {})),
        state.get("confidence"),
        json.dumps(state.get("cost_analysis", {}))
    ))
    
    # If decision is REVIEW, add to review queue
    if state.get("final_decision") == "REVIEW":
        cursor.execute("SELECT id FROM reviews WHERE transaction_id = ?", (state.get("transaction_id"),))
        existing = cursor.fetchone()
        if not existing:
            created_at = state.get("trace")[0]["timestamp"] if state.get("trace") else now_iso
            evidence_payload = {
                "evidence": state.get("evidence", {}),
                "cost_analysis": state.get("cost_analysis", {}),
                "risk_factors": state.get("risk_factors", []),
                "recommended_followup": state.get("recommended_followup", ""),
                "llm_engine": state.get("llm_engine", ""),
                "llm_summary": state.get("llm_summary", ""),
                "trace": state.get("trace", []),
                "confidence": state.get("confidence", "HIGH")
            }

            cursor.execute('''
                INSERT INTO reviews
                (transaction_id, agent_run_id, created_at, status, agent_recommended_action, policy_decision, risk_score, risk_level, amount, escalation_reason, evidence_json, is_demo)
                VALUES (?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?, ?, 0)
            ''', (
                state.get("transaction_id"),
                state.get("agent_run_id"),
                created_at,
                state.get("recommended_action", "REVIEW"),
                state.get("final_decision", "REVIEW"),
                state.get("evidence", {}).get("fusion", {}).get("final_risk_score", 0),
                state.get("risk_level", "ELEVATED"),
                state.get("amount", 0),
                state.get("policy_reason", "Manual Review Triggered"),
                json.dumps(evidence_payload)
            ))
            review_id = cursor.lastrowid
            
            record_review_audit(
                conn, review_id, state.get("transaction_id"), "System (AI Engine)",
                None, "PENDING", "REVIEW_CREATED", state.get("policy_reason", "Triggered by AI Risk Engine")
            )
            
    conn.commit()
    conn.close()

# ── Review Queue Queries & Lifecycle Methods ─────────────────────────────────

def parse_review_row(row):
    if not row:
        return None
    r = dict(row)
    # Parse evidence_json
    if r.get("evidence_json"):
        try:
            r["evidence_details"] = json.loads(r["evidence_json"])
        except Exception:
            r["evidence_details"] = {}
    else:
        r["evidence_details"] = {}
    return r

def get_reviews(active_only=False, status=None, risk_level=None, reviewer=None, min_score=None, max_score=None, search=None):
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM reviews WHERE 1=1"
    params = []
    
    if active_only:
        query += " AND status IN ('PENDING', 'IN_REVIEW', 'ESCALATED')"
    elif status:
        query += " AND status = ?"
        params.append(status)
        
    if risk_level:
        query += " AND risk_level = ?"
        params.append(risk_level)

    if reviewer:
        query += " AND reviewer LIKE ?"
        params.append(f"%{reviewer}%")

    if min_score is not None:
        query += " AND risk_score >= ?"
        params.append(min_score)

    if max_score is not None:
        query += " AND risk_score <= ?"
        params.append(max_score)

    if search:
        query += " AND (transaction_id LIKE ? OR reviewer_reason LIKE ? OR escalation_reason LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        
    query += " ORDER BY id DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [parse_review_row(r) for r in rows]

def get_review_by_id(review_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    r = parse_review_row(row)
    
    # Get audit events for this review
    cursor.execute("SELECT * FROM review_audit_events WHERE review_id = ? ORDER BY id ASC", (review_id,))
    r["audit_trail"] = [dict(a) for a in cursor.fetchall()]
    conn.close()
    return r

def get_review_counters():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'PENDING'")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'IN_REVIEW'")
    in_review = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'ESCALATED'")
    escalated = cursor.fetchone()[0]
    
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'RESOLVED' AND (reviewed_at LIKE ? OR created_at LIKE ?)", (f"{today_str}%", f"{today_str}%"))
    resolved_today = cursor.fetchone()[0]
    
    conn.close()
    return {
        "pending": pending,
        "in_review": in_review,
        "escalated": escalated,
        "resolved_today": resolved_today
    }

def start_review(review_id: int, reviewer: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise ValueError("Review case not found")
        
    current_status = row["status"]
    current_reviewer = row["reviewer"]
    
    if current_status == "RESOLVED":
        conn.close()
        raise ValueError("Case is already resolved and cannot be started.")
        
    if current_status == "IN_REVIEW" and current_reviewer and current_reviewer != reviewer:
        conn.close()
        raise ValueError(f"Case is currently being reviewed by '{current_reviewer}'.")
        
    now_iso = datetime.utcnow().isoformat() + "Z"
    started_at = row["started_at"] or now_iso
    
    cursor.execute('''
        UPDATE reviews
        SET status = 'IN_REVIEW', started_at = ?, reviewer = ?
        WHERE id = ?
    ''', (started_at, reviewer, review_id))
    
    record_review_audit(
        conn, review_id, row["transaction_id"], reviewer,
        current_status, "IN_REVIEW", "REVIEW_STARTED", f"Review started by {reviewer}"
    )
    
    conn.commit()
    conn.close()
    return get_review_by_id(review_id)

def approve_review(review_id: int, reviewer: str, reason: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise ValueError("Review case not found")
        
    current_status = row["status"]
    if current_status == "RESOLVED":
        conn.close()
        raise ValueError("Case is already resolved.")
        
    now_iso = datetime.utcnow().isoformat() + "Z"
    reviewer_name = reviewer or row["reviewer"] or "Analyst"
    review_reason = reason or "Transaction approved by analyst after review."
    
    cursor.execute('''
        UPDATE reviews
        SET status = 'RESOLVED', reviewer_decision = 'APPROVED', reviewer_reason = ?, reviewed_at = ?, reviewer = ?
        WHERE id = ?
    ''', (review_reason, now_iso, reviewer_name, review_id))
    
    record_review_audit(
        conn, review_id, row["transaction_id"], reviewer_name,
        current_status, "RESOLVED", "REVIEW_APPROVED", review_reason
    )
    record_review_audit(
        conn, review_id, row["transaction_id"], reviewer_name,
        "RESOLVED", "RESOLVED", "REVIEW_RESOLVED", "Case resolved with decision: APPROVED"
    )
    
    conn.commit()
    conn.close()
    return get_review_by_id(review_id)

def reject_review(review_id: int, reviewer: str, reason: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise ValueError("Review case not found")
        
    current_status = row["status"]
    if current_status == "RESOLVED":
        conn.close()
        raise ValueError("Case is already resolved.")
        
    now_iso = datetime.utcnow().isoformat() + "Z"
    reviewer_name = reviewer or row["reviewer"] or "Analyst"
    review_reason = reason or "Transaction rejected due to confirmed risk."
    
    cursor.execute('''
        UPDATE reviews
        SET status = 'RESOLVED', reviewer_decision = 'REJECTED', reviewer_reason = ?, reviewed_at = ?, reviewer = ?
        WHERE id = ?
    ''', (review_reason, now_iso, reviewer_name, review_id))
    
    record_review_audit(
        conn, review_id, row["transaction_id"], reviewer_name,
        current_status, "RESOLVED", "REVIEW_REJECTED", review_reason
    )
    record_review_audit(
        conn, review_id, row["transaction_id"], reviewer_name,
        "RESOLVED", "RESOLVED", "REVIEW_RESOLVED", "Case resolved with decision: REJECTED"
    )
    
    conn.commit()
    conn.close()
    return get_review_by_id(review_id)

def escalate_review(review_id: int, reviewer: str, reason: str):
    if not reason or not reason.strip():
        raise ValueError("Escalation reason is required.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise ValueError("Review case not found")
        
    current_status = row["status"]
    if current_status == "RESOLVED":
        conn.close()
        raise ValueError("Case is already resolved.")
        
    reviewer_name = reviewer or row["reviewer"] or "Analyst"
    
    cursor.execute('''
        UPDATE reviews
        SET status = 'ESCALATED', escalation_reason = ?, reviewer = ?
        WHERE id = ?
    ''', (reason.strip(), reviewer_name, review_id))
    
    record_review_audit(
        conn, review_id, row["transaction_id"], reviewer_name,
        current_status, "ESCALATED", "REVIEW_ESCALATED", reason.strip()
    )
    
    conn.commit()
    conn.close()
    return get_review_by_id(review_id)

