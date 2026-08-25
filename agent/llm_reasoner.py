import os
import logging
import json

logger = logging.getLogger(__name__)

# ─── Groq API Key ──────────────────────────────────────────────────────────────
# Priority 1: passed explicitly | Priority 2: env var | Priority 3: hardcoded fallback
GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    ""
)
# Model priority list — first working model is used
GROQ_MODELS = ["groq/compound", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
GROQ_MODEL  = GROQ_MODELS[0]


class LLMFraudAnalyst:
    """
    RazorShield AI Analyst powered by Groq (llama-3.3-70b).
    Falls back to deterministic template synthesis if Groq is unavailable.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GROQ_API_KEY
        self.client = None
        self._init_groq()

    def _init_groq(self):
        """Try to initialize Groq client. Probes model list to pick the first working one."""
        global GROQ_MODEL
        try:
            from groq import Groq
            self.client = Groq(api_key=self.api_key)
            # Probe models to find one that responds
            for model in GROQ_MODELS:
                try:
                    probe = self.client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "Reply with: OK"}],
                        max_tokens=5,
                    )
                    if probe.choices[0].message.content.strip():
                        GROQ_MODEL = model
                        logger.info("✅ Groq LLM ready — model: %s", GROQ_MODEL)
                        return
                except Exception:
                    continue
            logger.warning("⚠️  No Groq models responded — using template fallback.")
            self.client = None
        except Exception as e:
            logger.warning("⚠️  Groq unavailable: %s — using template fallback.", e)
            self.client = None

    # ── Public API ──────────────────────────────────────────────────────────────

    def synthesize_case(
        self,
        transaction: dict,
        evidence: dict,
        cost: dict,
        policy_decision: dict,
    ) -> dict:
        """
        Primary entry-point.  Tries Groq first; falls back to templates.
        Returns:
            {
                "analyst_summary": str,       # 3-sentence case summary
                "risk_factors": list[str],    # key fraud signals identified
                "recommended_followup": str,  # what the analyst suggests next
                "generated_by": str,
            }
        """
        if self.client:
            try:
                return self._call_groq(transaction, evidence, cost, policy_decision)
            except Exception as e:
                logger.warning("Groq call failed (%s) — switching to fallback.", e)

        return self._template_fallback(transaction, evidence, cost, policy_decision)

    # ── Groq Integration ────────────────────────────────────────────────────────

    def _call_groq(self, transaction, evidence, cost, policy_decision) -> dict:
        xgb   = evidence.get("xgboost", {})
        anom  = evidence.get("anomaly", {})
        graph = evidence.get("graph", {})
        fusion = evidence.get("fusion", {})

        # Build a rich structured prompt
        system_prompt = (
            "You are RazorShield, an elite AI Fraud Analyst at Razorpay. "
            "You receive structured JSON evidence from multiple ML models and must "
            "produce a concise, professional fraud analysis report. "
            "Be specific, cite the numbers, and sound like a senior risk officer. "
            "Never make things up — reason strictly from the data provided."
        )

        user_prompt = f"""
## Transaction Under Investigation
- **Transaction ID**: {transaction.get('TransactionID', 'UNKNOWN')}
- **Amount**: ₹{transaction.get('TransactionAmt', 0):,.2f}
- **Hour of Day**: {transaction.get('TransactionHour', 'N/A')}  (0=midnight, 14=2PM)
- **Card**: {transaction.get('card1', 'N/A')}
- **Device**: {transaction.get('DeviceInfo', 'N/A')}
- **Email Domain**: {transaction.get('P_emaildomain', 'N/A')}
- **Has Identity Record**: {transaction.get('has_identity', 'N/A')}

## ML Evidence
- **XGBoost Risk Score**: {xgb.get('risk_score', 0)}/100  (fraud probability: {xgb.get('fraud_probability', 0):.2%})
- **Isolation Forest Anomaly Score**: {anom.get('anomaly_score', 0)}/100  (novelty: {anom.get('novelty_level', 'N/A')})
- **Graph Network Risk Score**: {graph.get('graph_risk_score', 0)}/100
- **Fused Final Risk Score**: {fusion.get('final_risk_score', 0)}/100
- **Signal Conflicts**: {fusion.get('conflicts', [])}

## Cost Analysis
- Expected loss if ALLOW: ₹{cost.get('costs', {}).get('ALLOW', 0)}
- Expected cost if VERIFY: ₹{cost.get('costs', {}).get('VERIFY', 0)}
- Expected cost if REVIEW: ₹{cost.get('costs', {}).get('REVIEW', 0)}
- Expected cost if BLOCK: ₹{cost.get('costs', {}).get('BLOCK', 0)}
- Chargeback exposure: ₹{cost.get('chargeback_exposure', 0)}

## Final Policy Decision
- **Action**: {policy_decision.get('action', 'N/A')}
- **Policy Check**: {policy_decision.get('policy_check', 'N/A')}
- **Reason**: {policy_decision.get('reason', 'N/A')}

## Your Task
Respond ONLY with a valid JSON object (no markdown, no extra text) in this exact format:
{{
  "analyst_summary": "<3-sentence professional case summary justifying the final action>",
  "risk_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "recommended_followup": "<one actionable next step for the risk team>"
}}
"""

        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=512,
        )

        raw = response.choices[0].message.content.strip()

        # Strip possible markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        parsed["generated_by"] = f"Groq · {GROQ_MODEL}"
        return parsed

    # ── Template Fallback ───────────────────────────────────────────────────────

    def _template_fallback(self, transaction, evidence, cost, policy_decision) -> dict:
        xgb_score    = evidence.get("xgboost", {}).get("risk_score", 0)
        anomaly_score = evidence.get("anomaly", {}).get("anomaly_score", 0)
        graph_score  = evidence.get("graph", {}).get("graph_risk_score", 0)
        fusion_score = evidence.get("fusion", {}).get("final_risk_score", 0)
        action       = policy_decision.get("action", "REVIEW")
        amount       = transaction.get("TransactionAmt", 0)
        txn_id       = transaction.get("TransactionID", "UNKNOWN")

        risk_factors = []
        if xgb_score > 60:
            risk_factors.append(f"High XGBoost fraud probability ({xgb_score}/100)")
        if anomaly_score > 60:
            risk_factors.append(f"Behavioral anomaly detected ({anomaly_score}/100)")
        if graph_score > 60:
            risk_factors.append(f"Suspicious network associations ({graph_score}/100)")
        if transaction.get("TransactionHour", 12) < 5:
            risk_factors.append("Transaction at unusual hour (late night / early morning)")
        if transaction.get("DeviceInfo", "").lower() in ["unknown", "unknown_device", ""]:
            risk_factors.append("Unrecognized or unknown device")
        if not risk_factors:
            risk_factors.append("All ML signals within normal range")

        followup_map = {
            "BLOCK":  "File a suspicious activity report (SAR) and alert the cardholder.",
            "VERIFY": "Trigger OTP step-up; escalate to BLOCK if verification fails.",
            "REVIEW": "Assign to L2 fraud analyst for manual inspection within 4 hours.",
            "ALLOW":  "No action required. Continue passive monitoring for 24 hours.",
        }

        if action == "BLOCK":
            summary = (
                f"RazorShield AI recommends an immediate BLOCK on Transaction {txn_id} (₹{amount:,.2f}). "
                f"The fused risk score of {fusion_score}/100 — driven by XGBoost ({xgb_score}) and anomaly ({anomaly_score}) signals — "
                f"indicates a high-confidence fraud attempt with significant chargeback exposure of ₹{cost.get('chargeback_exposure', 0):,.2f}."
            )
        elif action == "VERIFY":
            summary = (
                f"RazorShield AI recommends a step-up VERIFY action for Transaction {txn_id} (₹{amount:,.2f}). "
                f"The fused risk score ({fusion_score}/100) is elevated but not conclusive, "
                f"making low-friction OTP verification the optimal cost-risk trade-off at ₹{cost.get('costs', {}).get('VERIFY', 0)} expected cost."
            )
        elif action == "ALLOW":
            summary = (
                f"RazorShield AI has cleared Transaction {txn_id} (₹{amount:,.2f}) for ALLOW. "
                f"All ML signals indicate nominal behavior (fused score: {fusion_score}/100), "
                f"and intervention would introduce unnecessary customer friction with no material risk reduction."
            )
        else:
            summary = (
                f"RazorShield AI is escalating Transaction {txn_id} (₹{amount:,.2f}) to manual REVIEW. "
                f"Conflicting signals between ML models (fused: {fusion_score}/100) prevent an automated determination. "
                f"Human oversight is required to resolve the ambiguity before a final decision."
            )

        return {
            "analyst_summary": summary,
            "risk_factors": risk_factors,
            "recommended_followup": followup_map.get(action, "Escalate to senior analyst."),
            "generated_by": "RazorShield Template Engine (Groq unavailable)",
        }
