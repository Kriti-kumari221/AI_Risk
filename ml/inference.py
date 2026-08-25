import pandas as pd
import numpy as np
import logging

class XGBoostRiskModel:
    def __init__(self, model, features):
        self.model = model
        self.features = features
        self.version = "xgb-v1"
        # Derive the set of one-hot prefix groups from the feature list
        self._ohe_prefixes = sorted(set(
            f.rsplit("_", 1)[0] for f in features
            if any(f.startswith(p) for p in [
                "P_emaildomain_", "R_emaildomain_", "DeviceType_",
                "card4_", "card6_", "M1_", "M2_", "M3_", "M4_",
                "M5_", "M6_", "M7_", "M8_", "M9_"
            ])
        ))

    def _preprocess(self, transaction_dict: dict) -> dict:
        """
        Expand raw categorical strings into one-hot columns matching training.
        Leaves all other numeric fields untouched.
        """
        row = dict(transaction_dict)

        # P_emaildomain: set the correct one-hot column
        email = str(row.pop("P_emaildomain", "") or "").strip().lower()
        col = f"P_emaildomain_{email}" if email else "P_emaildomain_Unknown"
        if col in self.features:
            row[col] = 1
        else:
            row["P_emaildomain_Unknown"] = 1  # unseen domain → Unknown bucket

        # DeviceInfo → DeviceType (mobile / desktop / Unknown)
        device = str(row.pop("DeviceInfo", "") or "").strip().lower()
        mobile_keywords = ["iphone", "android", "mobile", "samsung", "ipad", "tablet"]
        if any(k in device for k in mobile_keywords):
            device_type = "mobile"
        elif device and device not in ["", "unknown", "unknown_device"]:
            device_type = "desktop"
        else:
            device_type = "Unknown"
        row[f"DeviceType_{device_type}"] = 1

        # has_identity → M columns proxy (if not already set)
        # The model was trained with M1-M9 (T/F match flags), we fill with has_identity as proxy
        has_id = int(row.get("has_identity", 0))
        for m_col in ["M1_T", "M2_T", "M3_T", "M4_T", "M5_T", "M6_T", "M7_T", "M8_T", "M9_T"]:
            if m_col in self.features and m_col not in row:
                row[m_col] = has_id
        for m_col in ["M1_F", "M2_F", "M3_F", "M4_F", "M5_F", "M6_F", "M7_F", "M8_F", "M9_F"]:
            if m_col in self.features and m_col not in row:
                row[m_col] = 1 - has_id

        return row

    def predict(self, transaction_dict: dict) -> dict:
        processed = self._preprocess(transaction_dict)
        df = pd.DataFrame([processed])
        
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
            if hasattr(self.model, "predict_proba"):
                prob = self.model.predict_proba(df)[0, 1]
            else:
                dtest = self.model.get_booster().DMatrix(df) if hasattr(self.model, "get_booster") else df
                prob = self.model.predict(dtest)[0]
        except Exception as e:
            logging.error(f"XGBoost predict error: {e}")
            prob = 0.5
            
        risk_score = int(prob * 100)
        
        return {
            "fraud_probability": float(prob),
            "risk_score": risk_score,
            "model_version": self.version,
            "signal_quality": "HIGH" if not df.isna().all(axis=1).iloc[0] else "LOW",
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
