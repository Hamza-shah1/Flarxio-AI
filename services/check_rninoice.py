from config import MODEL_PATH 
import os
import logging

def prepare_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"RNNoise model not found at: {MODEL_PATH}")
    else:
        print("Rninoice model exits") 