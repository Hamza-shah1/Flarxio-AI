from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.dowload_image_enhancer_models import FSRCNN_URLS , LAPSRN_URLS ,  _download_model
from utils.image_utils import RATE_LIMIT , REDIS_URL ,  VALID_SCALES , FAST_MODE , MAX_QUEUE , MAX_PIXELS  
from utils.image_utils import OUTPUT_QUALITY , OUTPUT_FORMAT 
from utils.image_utils import _encode_image , _decode_image
import numpy as np
import cv2
import os
import threading
from flask import g, jsonify, request, send_file
from io import BytesIO
import time
import logging 
from utils.gpu_Detection import DNN_BACKEND ,DNN_TARGET, COMPUTE_LABEL



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# RATE LIMITER SETUP
# ──────────────────────────────────────────────

LIMITER_AVAILABLE = False
limiter = None

def init_limiter(app, RATE_LIMIT, REDIS_URL=None):
    global limiter, LIMITER_AVAILABLE

    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        _limiter_kwargs = {
            "key_func": get_remote_address,
            "default_limits": [RATE_LIMIT],
        }

        if REDIS_URL:
            _limiter_kwargs["storage_uri"] = REDIS_URL

        limiter = Limiter(**_limiter_kwargs)
        limiter.init_app(app)

        LIMITER_AVAILABLE = True
        log.info("Rate limiting enabled: %s", RATE_LIMIT)

    except ImportError:
        LIMITER_AVAILABLE = False
        log.warning("flask-limiter not installed — rate limiting disabled")

    

# ──────────────────────────────────────────────
# CONCURRENCY GUARD
# ──────────────────────────────────────────────
_active_lock  = threading.Lock()
_active_count = 0


# ──────────────────────────────────────────────
# MODEL CACHE
# ──────────────────────────────────────────────
_model_cache: dict = {}
_cache_lock         = threading.Lock()
_model_locks        = {s: threading.Lock() for s in VALID_SCALES}
_model_ready        = threading.Event()





# ──────────────────────────────────────────────
# PIPELINE STEPS
# ──────────────────────────────────────────────

def _load_sr_model(model_name: str, scale: int, url: str):
    filename = f"{model_name}_x{scale}.pb"
    path = _download_model(url, filename)
    if not path:
        return None
    try:
        from cv2 import dnn_superres
        sr = dnn_superres.DnnSuperResImpl_create()
        sr.readModel(path)
        sr.setModel(model_name.lower(), scale)
        sr.setPreferableBackend(DNN_BACKEND)
        sr.setPreferableTarget(DNN_TARGET)
        log.info("%s x%d ready [%s]", model_name, scale, COMPUTE_LABEL)
        return sr
    except Exception as exc:
        log.error("Model load failed %s x%d: %s", model_name, scale, exc)
        return None
    
def _load_one(model_name: str, scale: int, url: str):
    """Worker for parallel preload."""
    sr = _load_sr_model(model_name, scale, url)
    with _cache_lock:
        _model_cache[(model_name, scale)] = sr   
        
def _preload():
    """
    Load all models sequentially (OpenCV DNN is not thread-safe).
    Logic unchanged — only removed parallel execution to prevent
    'DepthToSpace already registered' error.
    """
    tasks = []

    for scale in VALID_SCALES:
        if scale in LAPSRN_URLS:
            tasks.append(("LapSRN", scale, LAPSRN_URLS[scale]))
        tasks.append(("FSRCNN", scale, FSRCNN_URLS[scale]))

    # Sequential loading (instead of ThreadPoolExecutor)
    for t in tasks:
        try:
            _load_one(*t)
        except Exception as exc:
            log.error("Preload task failed: %s", exc)

    _model_ready.set()
    log.info("All models ready.")
    
    


threading.Thread(target=_preload, daemon=True).start()
# ──────────────────────────────────────────────
# GAMMA LUT CACHE
# ──────────────────────────────────────────────
_gamma_lut_cache: dict[float, np.ndarray] = {}

def _get_gamma_lut(gamma: float) -> np.ndarray:
    """Cache gamma LUTs — recomputing (i/255)**inv_gamma*255 for every
    request is wasteful; with only 2 gamma values in use this hits every time."""
    if gamma not in _gamma_lut_cache:
        inv_gamma = 1.0 / gamma
        _gamma_lut_cache[gamma] = np.array(
            [((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
            dtype=np.uint8,
        )
    return _gamma_lut_cache[gamma]


# ──────────────────────────────────────────────
# IMAGE ANALYSIS
# ──────────────────────────────────────────────

def _classify_image(img: np.ndarray) -> dict:
    """
    SPEEDUP: Single BGR->GRAY conversion (was BGR->GRAY + BGR->HSV).
    Brightness is approximated from the grayscale mean — close enough for
    the thresholds used here and avoids a full HSV conversion per classify.
    HSV is still used downstream only in _saturation (one conversion total).
    """
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    noise      = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())          # ~same as HSV-V mean for our thresholds
    contrast   = float(gray.std())
    return {
        "noise":      noise,
        "brightness": brightness,
        "contrast":   contrast,
        "is_noisy":   noise < 300,
        "is_dark":    brightness < 80,
        "is_faded":   contrast < 35,
        "is_flat":    contrast < 20,
    }


def _denoise_fast(img: np.ndarray, noise_level: float) -> np.ndarray:
    if noise_level < 100:
        return cv2.bilateralFilter(img, d=5, sigmaColor=50, sigmaSpace=50)
    return cv2.bilateralFilter(img, d=5, sigmaColor=30, sigmaSpace=30)


def _gamma_correction(img: np.ndarray, gamma: float) -> np.ndarray:
    return cv2.LUT(img, _get_gamma_lut(gamma))


def _unsharp(img: np.ndarray, strength: float, sigma: float) -> np.ndarray:
    """
    SPEEDUP: Removed np.clip + .astype copy — cv2.addWeighted already
    saturates to [0,255] uint8, so the extra allocation was pure waste.
    """
    blurred = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1.0 + strength, blurred, -strength, 0)


def _clahe(img: np.ndarray, clip: float) -> np.ndarray:
    lab     = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe   = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    l       = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


# Precompute saturation LUTs for the two factor values used (1.08 and 1.12).
# _saturation is called on every image; building the LUT each time from scratch
# (including a full float32 array allocation) added ~2-4ms per call.
_SAT_LUTS: dict[float, np.ndarray] = {}

def _get_sat_lut(factor: float) -> np.ndarray:
    if factor not in _SAT_LUTS:
        lut = np.arange(256, dtype=np.float32) * factor
        np.clip(lut, 0, 255, out=lut)
        _SAT_LUTS[factor] = lut.astype(np.uint8)
    return _SAT_LUTS[factor]


def _saturation(img: np.ndarray, factor: float) -> np.ndarray:
    """
    SPEEDUP: LUT-based S-channel scaling instead of full float32 array
    conversion. Avoids allocating an entire float32 image copy (~4x faster
    for typical 4MP images).
    """
    hsv       = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v   = cv2.split(hsv)
    s         = cv2.LUT(s, _get_sat_lut(factor))
    return cv2.cvtColor(cv2.merge([h, s, v]), cv2.COLOR_HSV2BGR)


def _upscale(img: np.ndarray, scale: int):
    for model_name in ("LapSRN", "FSRCNN"):
        sr = _model_cache.get((model_name, scale))
        if sr is not None:
            try:
                with _model_locks[scale]:
                    result = sr.upsample(img)
                return result, f"{model_name} x{scale}"
            except Exception as exc:
                log.warning("%s x%d failed: %s", model_name, scale, exc)

    h, w = img.shape[:2]
    return (
        cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4),
        "Lanczos",
    )



# ──────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────

def enhance(img: np.ndarray, scale: int):
    info = _classify_image(img)

    # 1. Denoise
    if not FAST_MODE and info["is_noisy"]:
        img = _denoise_fast(img, info["noise"])

    # 2. Gamma correction
    if info["is_dark"]:
        gamma = 0.65 if info["brightness"] < 50 else 0.78
        img = _gamma_correction(img, gamma)

    # 3. Upscale
    img, method = _upscale(img, scale)

    # 4. Sharpening
    if info["is_flat"]:
        img = _unsharp(img, strength=0.30, sigma=0.8)
    elif info["noise"] > 800:
        img = _unsharp(img, strength=0.50, sigma=0.9)
    else:
        img = _unsharp(img, strength=0.55, sigma=1.0)

    # 5. CLAHE — SPEEDUP: skip entirely when image is already well-exposed
    # and contrast is high. Saves ~5-8ms per image for the common good-image case.
    needs_clahe = info["is_dark"] or info["is_faded"] or info["contrast"] < 60
    if needs_clahe:
        clip = 1.5 if (info["is_dark"] or info["is_faded"]) else 1.0
        img = _clahe(img, clip=clip)

    # 6. Saturation
    sat = 1.12 if info["is_faded"] else 1.08
    img = _saturation(img, factor=sat)

    return img, method



            
            
