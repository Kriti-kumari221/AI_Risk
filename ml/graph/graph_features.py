import pandas as pd
import numpy as np
from collections import defaultdict
import logging

class GraphFeatureBuilder:
    def __init__(self):
        # We will maintain mappings of entity -> connected entities or counts
        # This is a lightweight representation of a bipartite/multipartite graph
        
        # Nodes: card, device, email
        self.card_to_devices = defaultdict(set)
        self.card_to_emails = defaultdict(set)
        self.card_to_tx_count = defaultdict(int)
        
        self.device_to_cards = defaultdict(set)
        self.device_to_emails = defaultdict(set)
        self.device_to_tx_count = defaultdict(int)
        
        self.email_to_cards = defaultdict(set)
        self.email_to_tx_count = defaultdict(int)

    def update_graph(self, transaction_dict: dict):
        """Updates the graph state with a new verified/historical transaction."""
        card = transaction_dict.get('card1')
        device = transaction_dict.get('DeviceInfo')
        email = transaction_dict.get('P_emaildomain')
        
        if card:
            self.card_to_tx_count[card] += 1
            if device:
                self.card_to_devices[card].add(device)
            if email:
                self.card_to_emails[card].add(email)
                
        if device:
            self.device_to_tx_count[device] += 1
            if card:
                self.device_to_cards[device].add(card)
            if email:
                self.device_to_emails[device].add(email)
                
        if email:
            self.email_to_tx_count[email] += 1
            if card:
                self.email_to_cards[email].add(card)

    def extract_features(self, transaction_dict: dict) -> dict:
        """Extracts graph features for a given transaction based on current graph state."""
        card = transaction_dict.get('card1')
        device = transaction_dict.get('DeviceInfo')
        email = transaction_dict.get('P_emaildomain')
        
        features = {
            'card_transaction_count': self.card_to_tx_count.get(card, 0),
            'card_unique_devices': len(self.card_to_devices.get(card, set())),
            'card_unique_emails': len(self.card_to_emails.get(card, set())),
            
            'device_transaction_count': self.device_to_tx_count.get(device, 0),
            'device_unique_cards': len(self.device_to_cards.get(device, set())),
            'device_unique_emails': len(self.device_to_emails.get(device, set())),
            
            'email_transaction_count': self.email_to_tx_count.get(email, 0),
            'email_unique_cards': len(self.email_to_cards.get(email, set()))
        }
        
        # Calculate shared counts and network density metrics
        features['shared_device_count'] = features['device_unique_cards'] # How many cards share this device
        features['shared_email_count'] = features['email_unique_cards']   # How many cards share this email
        
        return features

    def fit_from_dataframe(self, df: pd.DataFrame):
        """Batch update the graph from a historical dataframe."""
        for _, row in df.iterrows():
            self.update_graph(row.to_dict())
