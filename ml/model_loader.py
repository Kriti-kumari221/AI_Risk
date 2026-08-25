import joblib
import pandas as pd
import numpy as np
import os
import xgboost as xgb

class ModelLoader:
    def __init__(self, models_dir="models"):
        self.models_dir = models_dir
        self.xgb_model = None
        self.xgb_features = None
        self.anomaly_model = None
        self.anomaly_features = None
        self.anomaly_scaler = None

    def load_xgboost(self, model_name="razorshield_xgboost_590k.pkl", features_name="razorshield_xgboost_590k_features.pkl"):
        model_path = os.path.join(self.models_dir, model_name)
        features_path = os.path.join(self.models_dir, features_name)
        
        self.xgb_model = joblib.load(model_path)
        self.xgb_features = joblib.load(features_path)
            
        return self.xgb_model, self.xgb_features

    def load_anomaly(self, model_name="razorshield_isolation_forest_590k.pkl", features_name="razorshield_anomaly_features_590k.pkl", scaler_name="razorshield_anomaly_scaler_590k.pkl"):
        model_path = os.path.join(self.models_dir, model_name)
        features_path = os.path.join(self.models_dir, features_name)
        scaler_path = os.path.join(self.models_dir, scaler_name)
        
        self.anomaly_model = joblib.load(model_path)
        self.anomaly_features = joblib.load(features_path)
        self.anomaly_scaler = joblib.load(scaler_path)
            
        return self.anomaly_model, self.anomaly_features, self.anomaly_scaler
