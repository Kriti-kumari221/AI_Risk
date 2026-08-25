import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from ml.model_loader import ModelLoader
from ml.inference import XGBoostRiskModel, AnomalyRiskModel

def test_models():
    loader = ModelLoader(models_dir="models")
    xgb_model, xgb_features = loader.load_xgboost()
    print("XGBoost loaded. Features count:", len(xgb_features))
    
    anomaly_model, anomaly_features, anomaly_scaler = loader.load_anomaly()
    print("Anomaly loaded. Features count:", len(anomaly_features))
    
    xgb_risk = XGBoostRiskModel(xgb_model, xgb_features)
    anomaly_risk = AnomalyRiskModel(anomaly_model, anomaly_features, anomaly_scaler)
    
    test_transaction = {
        "TransactionAmt": 150.0,
        "TransactionHour": 12,
        "TransactionDay": 5,
        "has_identity": 1
    }
    
    xgb_res = xgb_risk.predict(test_transaction)
    print("XGBoost Result:", xgb_res)
    
    anomaly_res = anomaly_risk.predict(test_transaction)
    print("Anomaly Result:", anomaly_res)

if __name__ == "__main__":
    test_models()
