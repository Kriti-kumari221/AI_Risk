import pandas as pd
import numpy as np
import logging

class XGBoostRiskModel:
    def __init__(self, model, features):
        self.model = model
        self.features = features
        self.version = "xgb-v1"

    def predict(self, transaction_dict: dict) -> dict:
        df = pd.DataFrame([transaction_dict])
        
        # Ensure all required features are present, fill missing with np.nan
        for feature in self.features:
            if feature not in df.columns:
                df[feature] = np.nan
                
        # Reorder to match training
        df = df[self.features]
        
        # Ensure all columns are numeric
        df = df.apply(pd.to_numeric, errors='coerce').fillna(0)
        
        # Predict probability
        try:
            # Some versions of XGBoost might have different predict_proba signatures
            # We assume it's an sklearn API wrapper if predict_proba is available
            if hasattr(self.model, "predict_proba"):
                prob = self.model.predict_proba(df)[0, 1]
            else:
                dtest = self.model.get_booster().DMatrix(df) if hasattr(self.model, "get_booster") else df
                prob = self.model.predict(dtest)[0]
        except Exception as e:
            logging.error(f"XGBoost predict error: {e}")
            prob = 0.5 # fallback or error state
            
        risk_score = int(prob * 100)
        
        return {
            "fraud_probability": float(prob),
            "risk_score": risk_score,
            "model_version": self.version,
            "signal_quality": "HIGH" if not df.isna().all(axis=1).iloc[0] else "LOW",
            "top_features": [] # Mocked for now, can extract from SHAP if needed
        }

class AnomalyRiskModel:
    def __init__(self, model, features, scaler):
        self.model = model
        self.features = features
        self.scaler = scaler
        self.version = "anomaly-v1"

    def predict(self, transaction_dict: dict) -> dict:
        df = pd.DataFrame([transaction_dict])
        
        for feature in self.features:
            if feature not in df.columns:
                df[feature] = 0.0 # Standard fill for anomaly if missing
                
        df = df[self.features]
        
        try:
            # Scale
            scaled_features = self.scaler.transform(df)
            
            # Predict anomaly score
            # Isolation Forest returns negative scores for anomalies in sklearn, 
            # and positive for normal, or 1 for normal, -1 for anomaly.
            # We want an anomaly score 0-100 where 100 is highly anomalous.
            raw_score = self.model.decision_function(scaled_features)[0]
            
            # Normalize to 0-100. sklearn decision_function is typically between -0.5 and 0.5
            # Negative means anomaly. 
            # So lower score -> higher risk.
            normalized_score = 50 - (raw_score * 100)
            anomaly_score = max(0, min(100, int(normalized_score)))
            
        except Exception as e:
            logging.error(f"Anomaly predict error: {e}")
            anomaly_score = 50
            
        if anomaly_score > 70:
            novelty = "HIGH"
        elif anomaly_score > 40:
            novelty = "MEDIUM"
        else:
            novelty = "LOW"
            
        return {
            "anomaly_score": anomaly_score,
            "novelty_level": novelty,
            "signals": []
        }
