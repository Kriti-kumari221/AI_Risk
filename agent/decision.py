import os

class CostAnalyzer:
    def __init__(self, merchant_profile=None):
        # Base costs could come from a config. We will hardcode some defaults for demo purposes.
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
        
        # Fraud loss = full amount + chargeback fee (assume $15)
        chargeback_cost = amount + 15
        
        # Risk probability should be between 0 and 1
        p_fraud = risk_probability
        p_legit = 1 - p_fraud
        
        # Expected Loss if ALLOW:
        # If legit = $0 loss. If fraud = chargeback_cost
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
            "chargeback_exposure": round(chargeback_cost, 2)
        }


class DecisionEngine:
    def __init__(self, policy=None):
        self.policy = policy or {
            "max_auto_block_risk": 95,
            "max_auto_allow_risk": 30,
            "require_review_above": 70,
            "verification_above": 50,
            "hard_block_amount": 10000
        }
        
    def authorize(self, agent_proposal: str, risk_score: int, transaction: dict) -> dict:
        """
        Policy engine that takes the agent's proposed action and ensures it is within bounds.
        """
        authorized_action = agent_proposal
        reason = "Agent proposal authorized."
        
        amount = transaction.get("TransactionAmt", 0)
        
        # 1. Hard constraints override everything
        if amount > self.policy["hard_block_amount"] and risk_score > 50:
            authorized_action = "BLOCK"
            reason = "Policy override: High amount + elevated risk requires blocking."
            return {"action": authorized_action, "reason": reason, "policy_check": "FAIL"}
            
        # 2. Prevent automated allowing of high risk
        if agent_proposal == "ALLOW" and risk_score >= self.policy["max_auto_allow_risk"]:
            authorized_action = "VERIFY" if risk_score < self.policy["require_review_above"] else "REVIEW"
            reason = f"Policy override: Risk score {risk_score} exceeds max auto-allow threshold."
            
        # 3. Prevent automated blocking of low risk (sanity check)
        if agent_proposal == "BLOCK" and risk_score < 70:
            authorized_action = "REVIEW"
            reason = f"Policy override: Blocking requires higher risk score."
            
        # 4. Mandatory reviews
        if risk_score >= self.policy["require_review_above"] and authorized_action not in ["REVIEW", "BLOCK"]:
            authorized_action = "REVIEW"
            reason = "Policy override: Mandatory review threshold exceeded."
            
        return {
            "action": authorized_action,
            "reason": reason,
            "policy_check": "PASS" if authorized_action == agent_proposal else "FAIL"
        }
