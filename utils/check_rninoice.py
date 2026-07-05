from config import MODEL_PATH
from config import SAFE_MODEL_PATH , SAFE_MODEL_DIR
import os
from utils.handler import logger
import shutil
import logging

def prepare_model():
    
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"RNNoise model not found at: {MODEL_PATH}")

    os.makedirs(SAFE_MODEL_DIR, exist_ok=True)

    if not os.path.exists(SAFE_MODEL_PATH):
        shutil.copy2(MODEL_PATH, SAFE_MODEL_PATH)
        logger.info(f"RNNoise model copied to: {SAFE_MODEL_PATH}")
    else:
        logger.info(f"RNNoise model already exists: {SAFE_MODEL_PATH}")