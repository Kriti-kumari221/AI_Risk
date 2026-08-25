class GraphRiskTool:
    def __init__(self, graph_builder):
        self.graph_builder = graph_builder
        self.version = "graph-v1"

    def assess_risk(self, transaction_dict: dict) -> dict:
        """
        Assess risk based on the entity graph.
        Returns risk score 0-100 and evidence.
        """
        features = self.graph_builder.extract_features(transaction_dict)
        
        # Simple heuristic rule-based risk for the graph (can be a model later)
        risk_score = 0
        signals = []
        
        # Highly shared devices are extremely suspicious
        if features.get('shared_device_count', 0) > 3:
            risk_score += 40
            signals.append(f"Device is shared by {features['shared_device_count']} unique cards.")
            
        # Emails shared across many cards
        if features.get('shared_email_count', 0) > 2:
            risk_score += 30
            signals.append(f"Email is shared by {features['shared_email_count']} unique cards.")
            
        # High velocity on card with new device
        if features.get('card_transaction_count', 0) > 10 and features.get('device_transaction_count', 0) == 0:
            risk_score += 20
            signals.append("Established card being used on a previously unseen device.")
            
        # Normalize score
        risk_score = min(100, risk_score)
        
        return {
            "graph_risk_score": risk_score,
            "version": self.version,
            "signals": signals,
            "features": features
        }
