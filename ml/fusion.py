class RiskFusion:
    def __init__(self, weights=None):
        # Default weights derived from validation (can be configured)
        self.weights = weights or {
            "xgboost": 0.60,
            "anomaly": 0.20,
            "graph": 0.20
        }
        self.version = "fusion-v1"

    def fuse(self, xgb_result: dict, anomaly_result: dict, graph_result: dict) -> dict:
        xgb_score = xgb_result.get("risk_score", 0)
        anomaly_score = anomaly_result.get("anomaly_score", 0)
        graph_score = graph_result.get("graph_risk_score", 0)
        
        final_score = (
            (xgb_score * self.weights["xgboost"]) +
            (anomaly_score * self.weights["anomaly"]) +
            (graph_score * self.weights["graph"])
        )
        
        final_score = int(min(100, max(0, final_score)))
        
        # Conflict detection
        conflicts = []
        if xgb_score > 70 and graph_score < 30:
            conflicts.append("High model risk but low network risk.")
        if graph_score > 70 and xgb_score < 30:
            conflicts.append("High network risk but low model risk.")
            
        return {
            "final_risk_score": final_score,
            "fusion_weights": self.weights,
            "conflicts": conflicts,
            "version": self.version
        }
