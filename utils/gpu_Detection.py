# from models.image_enhancer_model import log
import cv2
# ──────────────────────────────────────────────
# GPU DETECTION
# ──────────────────────────────────────────────
import logging

log = logging.getLogger(__name__)


def _detect_backend():
    try:
        if (
            "CUDA" in cv2.getBuildInformation()
            and cv2.cuda.getCudaEnabledDeviceCount() > 0
        ):
            return cv2.dnn.DNN_BACKEND_CUDA, cv2.dnn.DNN_TARGET_CUDA, "CUDA"
    except Exception:
        pass
    return cv2.dnn.DNN_BACKEND_DEFAULT, cv2.dnn.DNN_TARGET_CPU, "CPU"

DNN_BACKEND, DNN_TARGET, COMPUTE_LABEL = _detect_backend()
log.info("Compute: %s", COMPUTE_LABEL)