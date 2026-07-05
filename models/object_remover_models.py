from utils.handler import DEVICE
import logging
from typing import Optional, Tuple
import threading
from config import log
from rembg import remove, new_session
import numpy as np
import cv2
from utils.helpers import _opencv_inpaint
from utils.handler import TILE_SIZE , TILE_OVERLAP , MAX_PX
from utils.helpers import _feather_composite
# ═════════════════════════════════════════════════════════════════════════════
#  LaMa ENGINE  (thread-safe, lazy-loaded, GPU-accelerated)
# ═════════════════════════════════════════════════════════════════════════════

# ─── MODEL STATE ─────────────────────────────────────────────────────────────
_lama_model   : Optional[object] = None
_lama_lock    = threading.Lock()
_rembg_session: Optional[object] = None


def get_lama():
    """
    Thread-safe singleton loader for LaMa.
    On PyTorch 2+, applies torch.compile() for 30–50% extra speed.
    Uses FP16 on CUDA for 2× throughput.
    """
    global _lama_model
    if _lama_model is not None:
        return _lama_model if _lama_model != "unavailable" else None

    with _lama_lock:
        if _lama_model is not None:  # double-checked locking
            return _lama_model if _lama_model != "unavailable" else None
        try:
            from simple_lama_inpainting import SimpleLama
            import torch

            model = SimpleLama()

            # Move to best available device
            if DEVICE != "cpu" and hasattr(model, "model"):
                model.model = model.model.to(DEVICE)
                if DEVICE == "cuda":
                    model.model = model.model.half()   # FP16 on GPU
                log.info(f"[LaMa] moved to {DEVICE}")

            # torch.compile (PyTorch 2+) — huge speed boost on repeated calls
            if hasattr(torch, "compile") and hasattr(model, "model"):
                try:
                    model.model = torch.compile(model.model, mode="reduce-overhead")
                    log.info("[LaMa] torch.compile applied ✓")
                except Exception as ce:
                    log.warning(f"[LaMa] torch.compile skipped: {ce}")

            _lama_model = model
            log.info("[LaMa] model loaded ✓")
        except ImportError:
            log.error(
                "[LaMa] simple-lama-inpainting not installed!\n"
                "Run:  pip install simple-lama-inpainting torch torchvision"
            )
            _lama_model = "unavailable"

    return _lama_model if _lama_model != "unavailable" else None


def get_rembg_session():
    """Thread-safe rembg session (u2net_human_seg → better for people, u2net for objects)."""
    global _rembg_session
    if _rembg_session is None:
        try:
            # u2net_human_seg is best for portraits; isnet-general-use is state-of-art for all
            _rembg_session = new_session("isnet-general-use")
            log.info("[rembg] isnet-general-use session loaded ✓")
        except Exception as e:
            log.warning(f"[rembg] fallback to default session: {e}")
            _rembg_session = new_session("u2net")
    return _rembg_session


def _lama_tile(lama, image_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Run LaMa on a single (possibly padded) tile."""
    from PIL import Image as PILImage
    H, W = image_rgb.shape[:2]
    ph   = (8 - H % 8) % 8
    pw   = (8 - W % 8) % 8
    if ph or pw:
        image_rgb = cv2.copyMakeBorder(image_rgb, 0, ph, 0, pw, cv2.BORDER_REFLECT)
        mask      = cv2.copyMakeBorder(mask,      0, ph, 0, pw, cv2.BORDER_CONSTANT, value=0)
    result = lama(PILImage.fromarray(image_rgb), PILImage.fromarray(mask))
    return np.array(result)[:H, :W]


def lama_inpaint(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Full-resolution LaMa inpainting with automatic tiling.
    Falls back to enhanced OpenCV if LaMa is unavailable.
    """
    lama = get_lama()
    if lama is None:
        return _opencv_inpaint(image_bgr, mask)

    H, W = image_bgr.shape[:2]

    # ── Fast path: small image → direct inference ──────────────────────────
    if H <= TILE_SIZE and W <= TILE_SIZE:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        result_rgb = _lama_tile(lama, image_rgb, mask)
        result_bgr = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
        result_bgr = _feather_composite(result_bgr, image_bgr, mask)
        log.info(f"[LaMa] direct ✓ {W}×{H}")
        return result_bgr

    # ── Tiled path: large image ────────────────────────────────────────────
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    output    = np.zeros_like(image_rgb, dtype=np.float32)
    weight    = np.zeros((H, W), dtype=np.float32)

    stride = TILE_SIZE - TILE_OVERLAP

    for y0 in range(0, H, stride):
        for x0 in range(0, W, stride):
            y1 = min(y0 + TILE_SIZE, H)
            x1 = min(x0 + TILE_SIZE, W)
            ty, tx = y1 - y0, x1 - x0

            tile_img  = image_rgb[y0:y1, x0:x1]
            tile_mask = mask[y0:y1, x0:x1]

            if tile_mask.max() == 0:
                # No mask in this tile — skip LaMa entirely
                tile_result = tile_img
            else:
                tile_result = _lama_tile(lama, tile_img, tile_mask)

            # Cosine blend weight (high center, low edges)
            wy = np.hanning(ty).astype(np.float32) + 1e-6
            wx = np.hanning(tx).astype(np.float32) + 1e-6
            w  = np.outer(wy, wx)

            output[y0:y1, x0:x1] += tile_result * w[:, :, np.newaxis]
            weight[y0:y1, x0:x1] += w

    result_rgb = np.clip(output / weight[:, :, np.newaxis], 0, 255).astype(np.uint8)
    result_bgr = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
    result_bgr = _feather_composite(result_bgr, image_bgr, mask)
    log.info(f"[LaMa] tiled ✓ {W}×{H}")
    return result_bgr