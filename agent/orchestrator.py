import uuid
import time
import logging
from datetime import datetime
from agent.llm_reasoner import LLMFraudAnalyst

logger = logging.getLogger(__name__)


class RiskAgentOrchestrator:
    """
    RazorShield Agentic Orchestrator.

    Workflow: OBSERVE → SCREEN → INVESTIGATE (adaptive) → FUSE → COST → DECIDE → ACT → LLM SYNTHESIZE → AUDIT
    """

    def __init__(self, xgb_model, anomaly_model, graph_tool, fusion_engine, cost_analyzer, decision_engine):
        self.xgb_model      = xgb_model
        self.anomaly_model  = anomaly_model
        self.graph_tool     = graph_tool
        self.fusion_engine  = fusion_engine
        self.cost_analyzer  = cost_analyzer
        self.decision_engine = decision_engine

        # LLM Analyst: Groq first, template fallback built-in
        self.llm_analyst = LLMFraudAnalyst()
        logger.info("RiskAgentOrchestrator initialized.")

    # ────────────────────────────────────────────────────────────────────────────
    # Core Investigation Pipeline
    # ────────────────────────────────────────────────────────────────────────────

    def investigate(self, transaction: dict) -> dict:
        """
        Main entry point. Returns a full agent state dict with:
        - evidence, trace, cost_analysis, final_decision, llm_summary,
          risk_factors, recommended_followup, duration_ms
        """
        agent_run_id = str(uuid.uuid4())
        start_time   = time.time()

        trace = []
        def log_step(step: str, details: str = ""):
            trace.append({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "step":      step,
                "details":   details,
            })
            logger.debug("[%s] %s — %s", agent_run_id[:8], step, details)

        # ── OBSERVE ──────────────────────────────────────────────────────────
        amount    = transaction.get("TransactionAmt", 0)
        hour      = transaction.get("TransactionHour", 12)
        device    = str(transaction.get("DeviceInfo", "")).lower()
        email_dom = str(transaction.get("P_emaildomain", "")).lower()

        log_step("RECEIVED", f"Transaction {transaction.get('TransactionID')} | Amt: ₹{amount:,.2f} | Hour: {hour}h")

        state = {
            "transaction_id": transaction.get("TransactionID", "UNKNOWN"),
            "agent_run_id":   agent_run_id,
            "evidence":       {},
            "conflicts":      [],
            "confidence":     "HIGH",
            "tools_called":   [],
        }

        # ── SCREEN (XGBoost) ─────────────────────────────────────────────────
        log_step("SCREENING", "XGBoost primary risk scoring")
        xgb_result = self.xgb_model.predict(transaction)
        state["evidence"]["xgboost"] = xgb_result
        state["tools_called"].append("xgboost")
        xgb_score = xgb_result["risk_score"]

        # ── ADAPTIVE PLANNING ────────────────────────────────────────────────
        # Heuristics that trigger deep investigation:
        suspicious_hour   = hour < 5 or hour > 23            # late night / early morning
        suspicious_device = "unknown" in device or device == ""
        suspicious_email  = any(d in email_dom for d in ["anonymous", "temp", "guerrilla", "yopmail", "mailinator"])
        high_amount       = amount > 1000

        needs_investigation = (
            xgb_score > 5
            or high_amount
            or suspicious_hour
            or suspicious_device
            or suspicious_email
        )

        investigation_triggers = []
        if xgb_score > 5:           investigation_triggers.append(f"XGBoost score {xgb_score}")
        if high_amount:             investigation_triggers.append(f"High amount ₹{amount:,.2f}")
        if suspicious_hour:         investigation_triggers.append(f"Suspicious hour ({hour}h)")
        if suspicious_device:       investigation_triggers.append(f"Unknown device ({device})")
        if suspicious_email:        investigation_triggers.append(f"Suspicious email domain ({email_dom})")

        if needs_investigation:
            log_step("INVESTIGATING", "Triggers: " + " | ".join(investigation_triggers))

            # ── ANOMALY TOOL ─────────────────────────────────────────────────
            log_step("TOOL_CALL", "Isolation Forest anomaly detection")
            anomaly_result = self.anomaly_model.predict(transaction)
            state["evidence"]["anomaly"] = anomaly_result
            state["tools_called"].append("anomaly_isolation_forest")

            # ── GRAPH TOOL ───────────────────────────────────────────────────
            log_step("TOOL_CALL", "Graph intelligence — entity relationship risk")
            graph_result = self.graph_tool.assess_risk(transaction)
            state["evidence"]["graph"] = graph_result
            state["tools_called"].append("graph_risk_tool")

        else:
            log_step("REASONING", "Low-risk profile. Bypassing deep investigation to reduce latency.")
            anomaly_result = {"anomaly_score": 0, "novelty_level": "LOW", "signals": []}
            graph_result   = {"graph_risk_score": 0}
            state["evidence"]["anomaly"] = anomaly_result
            state["evidence"]["graph"]   = graph_result

        # ── RISK FUSION ──────────────────────────────────────────────────────
        log_step("RISK_FUSED", "Fusing XGBoost + Anomaly + Graph signals")
        fusion_result = self.fusion_engine.fuse(xgb_result, anomaly_result, graph_result)
        state["evidence"]["fusion"] = fusion_result
        final_risk    = fusion_result["final_risk_score"]
        state["conflicts"].extend(fusion_result["conflicts"])

        if state["conflicts"]:
            state["confidence"] = "MEDIUM"
            log_step("REASONING", f"⚠️  Conflicting signals detected: {state['conflicts']}. Confidence downgraded.")

        # ── COST ANALYSIS ────────────────────────────────────────────────────
        log_step("COST_ANALYZED", "Computing expected costs for each possible action")
        risk_prob   = final_risk / 100.0
        cost_result = self.cost_analyzer.analyze(transaction, risk_prob)
        state["cost_analysis"] = cost_result

        # ── DECISION PROPOSAL ────────────────────────────────────────────────
        proposed_action = cost_result["recommended_action_by_cost"]

        # Agent defensive override: if confidence is reduced and cost says ALLOW,
        # escalate to VERIFY to be safe.
        if state["confidence"] == "MEDIUM" and proposed_action == "ALLOW":
            proposed_action = "VERIFY"
            log_step("REASONING", "Confidence MEDIUM + ALLOW proposal → overriding to VERIFY (defensive).")

        # Extra: very suspicious late-night + unknown device → force at least REVIEW
        if suspicious_hour and suspicious_device and proposed_action == "ALLOW":
            proposed_action = "REVIEW"
            log_step("REASONING", "Suspicious hour + unknown device → overriding to REVIEW.")

        log_step("DECISION_PROPOSED", f"Agent proposes: {proposed_action}")
        state["recommended_action"] = proposed_action

        # ── POLICY ENGINE ────────────────────────────────────────────────────
        log_step("POLICY_CHECK", "Validating proposal against merchant risk policy")
        policy_result = self.decision_engine.authorize(proposed_action, final_risk, transaction)
        state["policy_check"] = policy_result
        final_action  = policy_result["action"]
        log_step("ACTION_AUTHORIZED", f"Final action: {final_action} | Policy: {policy_result['policy_check']} | {policy_result['reason']}")
        state["final_decision"] = final_action
        state["policy_reason"] = policy_result["reason"]
        state["risk_level"] = policy_result.get("risk_level", "UNKNOWN")
        # Enrich graph evidence with runtime signals for frontend rendering
        state["evidence"]["graph"]["suspicious_hour"] = suspicious_hour

        # ── EXECUTION ────────────────────────────────────────────────────────
        log_step("ACTION_EXECUTED", f"Simulated execution of {final_action} for transaction {state['transaction_id']}")

        # ── LLM SYNTHESIS (Groq → Template fallback) ─────────────────────────
        duration_ms = int((time.time() - start_time) * 1000)
        log_step("GENAI_SYNTHESIS", "Groq LLM synthesizing case evidence into natural language report")

        llm_report = self.llm_analyst.synthesize_case(
            transaction=transaction,
            evidence=state["evidence"],
            cost=state["cost_analysis"],
            policy_decision=policy_result,
        )

        log_step("AUDITED", f"Investigation complete in {duration_ms}ms | Engine: {llm_report.get('generated_by', 'unknown')}")

        # ── ASSEMBLE FINAL STATE ─────────────────────────────────────────────
        state["trace"]                = trace
        state["duration_ms"]          = duration_ms
        state["llm_summary"]          = llm_report.get("analyst_summary", "")
        state["audit_reason"]         = llm_report.get("analyst_summary", "")
        state["risk_factors"]         = llm_report.get("risk_factors", [])
        state["recommended_followup"] = llm_report.get("recommended_followup", "")
        state["llm_engine"]           = llm_report.get("generated_by", "unknown")
        state["amount"]               = amount

        return state
