import os

class CostAnalyzer:
    def __init__(self, merchant_profile=None):
        self.profile = merchant_profile or {
            "false_positive_cost": 50,  # Cost of blocking a good transaction (friction/lost LTV)
            "review_cost": 10,          # Cost of a human review
            "verify_cost": 2,           # Cost of SMS/Email OTP step-up
            "margin_pct": 0.20          # Merchant profit margin
        }

    def analyze(self, transaction_dict: dict, risk_probability: float) -> dict:
        """
        Calculates expected cost of different actions based on risk probability.
        """
        amount = transaction_dict.get("TransactionAmt", 0)
        if amount is None or amount <= 0:
            return {
                "costs": {"ALLOW": "Not configured", "VERIFY": "Not configured", "REVIEW": "Not configured", "BLOCK": "Not configured"},
                "recommended_action_by_cost": "Unavailable",
                "chargeback_exposure": 0.0,
                "cost_note": "Configured Demo Cost Assumptions require valid transaction amount"
            }
        
        # Fraud loss = full amount + chargeback fee (assume ₹15)
        chargeback_cost = amount + 15
        
        # Risk probability should be between 0 and 1
        p_fraud = max(0.0, min(1.0, float(risk_probability)))
        p_legit = 1 - p_fraud
        
        # Expected Loss if ALLOW:
        expected_loss_allow = p_fraud * chargeback_cost
        
        # Expected Cost if VERIFY:
        # Flat verify cost + (If fraud and defeats verify, chargeback_cost)
        # Assume verify stops 90% of fraud
        expected_cost_verify = self.profile["verify_cost"] + (p_fraud * 0.10 * chargeback_cost)
        
        # Expected Cost if REVIEW:
        # Flat review cost + assume human catches 95% of fraud
        expected_cost_review = self.profile["review_cost"] + (p_fraud * 0.05 * chargeback_cost)
        
        # Expected Cost if BLOCK:
        # If legit = false_positive_cost. If fraud = $0 loss
        expected_cost_block = p_legit * self.profile["false_positive_cost"]
        
        costs = {
            "ALLOW": round(expected_loss_allow, 2),
            "VERIFY": round(expected_cost_verify, 2),
            "REVIEW": round(expected_cost_review, 2),
            "BLOCK": round(expected_cost_block, 2)
        }
        
        # Find minimum cost action
        recommended_action = min(costs, key=costs.get)
        
        return {
            "costs": costs,
            "recommended_action_by_cost": recommended_action,
            "chargeback_exposure": round(chargeback_cost, 2),
            "cost_note": "Configured Demo Cost Assumptions"
        }


class DecisionEngine:
    def __init__(self, policy=None):
        self.policy = policy or {
            "policy_version": "v1.2.0",
            "status": "ACTIVE",
            "last_updated": "2026-08-26T00:00:00Z",
            "merchant_profile": "Standard Enterprise Risk",
            "max_auto_block_risk": 95,
            "max_auto_allow_risk": 30,
            "require_review_above": 70,
            "verification_above": 50,
            "hard_block_amount": 10000
        }
        self.cost_analyzer = CostAnalyzer()

    def get_policy_details(self) -> dict:
        """
        Returns full structured policy metadata for frontend rendering.
        """
        return {
            "policy_version": self.policy.get("policy_version", "v1.2.0"),
            "status": self.policy.get("status", "ACTIVE"),
            "last_updated": self.policy.get("last_updated", "Live Production Guardrails"),
            "merchant_profile": self.policy.get("merchant_profile", "Standard Enterprise Risk"),
            "thresholds": {
                "max_auto_allow_risk": self.policy["max_auto_allow_risk"],
                "verification_above": self.policy["verification_above"],
                "require_review_above": self.policy["require_review_above"],
                "max_auto_block_risk": self.policy["max_auto_block_risk"],
                "hard_block_amount": self.policy["hard_block_amount"]
            },
            "rules": [
                {
                    "id": "RULE-01",
                    "name": "Auto-Allow Low Risk",
                    "condition": f"Risk Score < {self.policy['max_auto_allow_risk']}",
                    "action": "ALLOW",
                    "description": f"Transactions with risk score below {self.policy['max_auto_allow_risk']} are automatically approved."
                },
                {
                    "id": "RULE-02",
                    "name": "Step-up Verification",
                    "condition": f"Risk Score {self.policy['verification_above']} - {self.policy['require_review_above'] - 1}",
                    "action": "VERIFY",
                    "description": "Elevated risk triggers step-up verification (SMS/Email OTP)."
                },
                {
                    "id": "RULE-03",
                    "name": "Mandatory Human Review",
                    "condition": f"Risk Score >= {self.policy['require_review_above']}",
                    "action": "REVIEW",
                    "description": f"High risk scores (>= {self.policy['require_review_above']}) are routed to the Human Review Queue."
                },
                {
                    "id": "RULE-04",
                    "name": "Hard Auto-Block Threshold",
                    "condition": f"Risk Score >= {self.policy['max_auto_block_risk']}",
                    "action": "BLOCK",
                    "description": f"Critical risk scores (>= {self.policy['max_auto_block_risk']}) trigger automated blocking."
                },
                {
                    "id": "RULE-05",
                    "name": "High-Value Transaction Guardrail",
                    "condition": f"Amount > ₹{self.policy['hard_block_amount']:,} & Risk Score > {self.policy['verification_above']}",
                    "action": "BLOCK",
                    "description": f"High transaction amounts (> ₹{self.policy['hard_block_amount']:,}) with elevated risk (> {self.policy['verification_above']}) are hard-blocked to cap exposure."
                }
            ],
            "explanations": {
                "LOW": f"Risk Score < {self.policy['max_auto_allow_risk']}. Low-risk transactions are automatically approved.",
                "ELEVATED": f"Risk Score {self.policy['verification_above']}-{self.policy['require_review_above'] - 1}. Additional step-up verification required.",
                "HIGH": f"Risk Score {self.policy['require_review_above']}-{self.policy['max_auto_block_risk'] - 1}. Manual review required by risk analyst.",
                "CRITICAL": f"Risk Score >= {self.policy['max_auto_block_risk']}. Automated transaction block enforced according to merchant policy."
            }
        }
        
    def get_risk_level(self, risk_score: int) -> str:
        if risk_score >= self.policy["max_auto_block_risk"]:
            return "CRITICAL"
        elif risk_score >= self.policy["require_review_above"]:
            return "HIGH RISK"
        elif risk_score >= self.policy["verification_above"]:
            return "ELEVATED"
        else:
            return "LOW"
            
    def authorize(self, agent_proposal: str, risk_score: int, transaction: dict) -> dict:
        """
        Policy engine that takes the agent's proposed action and ensures it is within bounds.
        """
        agent_proposal = (agent_proposal or "ALLOW").upper()
        authorized_action = agent_proposal
        reason = "Agent proposal complies with policy guardrails."
        applicable_rule = "RULE-01: Auto-Allow Low Risk"
        policy_override = False
        
        amount = transaction.get("TransactionAmt", 0) or 0
        risk_level = self.get_risk_level(risk_score)
        
        # 1. Hard constraints override everything (High amount + elevated risk)
        if amount > self.policy["hard_block_amount"] and risk_score > self.policy["verification_above"]:
            authorized_action = "BLOCK"
            applicable_rule = "RULE-05: High-Value Transaction Guardrail"
            reason = f"Policy override: High amount (₹{amount:,.2f}) exceeds ₹{self.policy['hard_block_amount']:,} threshold with elevated risk (score {risk_score} > {self.policy['verification_above']})."
            policy_override = (authorized_action != agent_proposal)
            return {
                "action": authorized_action,
                "agent_proposal": agent_proposal,
                "policy_override": policy_override,
                "reason": reason,
                "applicable_rule": applicable_rule,
                "policy_check": "FAIL" if policy_override else "PASS",
                "risk_level": risk_level
            }

        # 2. Critical risk threshold (>= max_auto_block_risk)
        if risk_score >= self.policy["max_auto_block_risk"]:
            authorized_action = "BLOCK"
            applicable_rule = "RULE-04: Hard Auto-Block Threshold"
            if agent_proposal != "BLOCK":
                policy_override = True
                reason = f"Policy override: Critical risk score ({risk_score}/100) requires automated block."
            else:
                reason = f"Automated block authorized for critical risk score ({risk_score}/100)."
            return {
                "action": authorized_action,
                "agent_proposal": agent_proposal,
                "policy_override": policy_override,
                "reason": reason,
                "applicable_rule": applicable_rule,
                "policy_check": "FAIL" if policy_override else "PASS",
                "risk_level": risk_level
            }
            
        # 3. Prevent automated allowing of elevated/high risk
        if agent_proposal == "ALLOW" and risk_score >= self.policy["max_auto_allow_risk"]:
            authorized_action = "VERIFY" if risk_score < self.policy["require_review_above"] else "REVIEW"
            applicable_rule = "RULE-02: Step-up Verification" if authorized_action == "VERIFY" else "RULE-03: Mandatory Human Review"
            policy_override = True
            reason = f"Policy override: Risk score {risk_score} exceeds max auto-allow threshold ({self.policy['max_auto_allow_risk']}). Routing to {authorized_action}."
            
        # 4. Mandatory reviews for high risk
        elif risk_score >= self.policy["require_review_above"] and authorized_action not in ["REVIEW", "BLOCK"]:
            authorized_action = "REVIEW"
            applicable_rule = "RULE-03: Mandatory Human Review"
            policy_override = True
            reason = f"Policy override: Mandatory review threshold ({self.policy['require_review_above']}) exceeded."

        # 5. Prevent premature automated block for low risk (sanity check)
        elif agent_proposal == "BLOCK" and risk_score < self.policy["require_review_above"]:
            authorized_action = "REVIEW"
            applicable_rule = "RULE-03: Mandatory Human Review"
            policy_override = True
            reason = f"Policy override: Blocking requires risk score >= {self.policy['require_review_above']} or high-value guardrail."

        else:
            if risk_score < self.policy["max_auto_allow_risk"]:
                applicable_rule = "RULE-01: Auto-Allow Low Risk"
            elif risk_score < self.policy["require_review_above"]:
                applicable_rule = "RULE-02: Step-up Verification"
            else:
                applicable_rule = "RULE-03: Mandatory Human Review"
            
        return {
            "action": authorized_action,
            "agent_proposal": agent_proposal,
            "policy_override": policy_override,
            "reason": reason,
            "applicable_rule": applicable_rule,
            "policy_check": "FAIL" if policy_override else "PASS",
            "risk_level": risk_level
        }

    def evaluate_policy(self, risk_score: int, amount: float, agent_proposal: str = None) -> dict:
        """
        Policy simulator evaluation method for API and frontend testing.
        """
        # Determine default agent proposal if not explicitly provided
        if not agent_proposal:
            if risk_score < self.policy["max_auto_allow_risk"]:
                agent_proposal = "ALLOW"
            elif risk_score < self.policy["verification_above"]:
                agent_proposal = "VERIFY"
            elif risk_score < self.policy["require_review_above"]:
                agent_proposal = "VERIFY"
            elif risk_score < self.policy["max_auto_block_risk"]:
                agent_proposal = "REVIEW"
            else:
                agent_proposal = "BLOCK"

        transaction = {"TransactionAmt": float(amount or 0)}
        auth_result = self.authorize(agent_proposal, int(risk_score), transaction)

        # Compute cost analysis
        risk_prob = max(0.0, min(1.0, float(risk_score) / 100.0))
        cost_res = self.cost_analyzer.analyze(transaction, risk_prob)

        return {
            "risk_score": int(risk_score),
            "amount": float(amount or 0),
            "risk_level": auth_result["risk_level"],
            "agent_recommendation": auth_result["agent_proposal"],
            "policy_decision": auth_result["action"],
            "policy_override": auth_result["policy_override"],
            "reason": auth_result["reason"],
            "applicable_rule": auth_result["applicable_rule"],
            "policy_check": auth_result["policy_check"],
            "cost_analysis": cost_res,
            "policy_metadata": self.get_policy_details()
        }

