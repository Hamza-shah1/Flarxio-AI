import cv2
import numpy as np
import os

#---------------------------Image Enhancer---------------
MAX_PIXELS     = int(os.getenv("MAX_PIXELS",    4_000_000))
MAX_UPLOAD_MB  = int(os.getenv("MAX_UPLOAD_MB", 25))
MAX_QUEUE      = int(os.getenv("MAX_QUEUE",     20))
RATE_LIMIT     = os.getenv("RATE_LIMIT",        "10 per minute")
REDIS_URL      = os.getenv("REDIS_URL",         None)
OUTPUT_FORMAT  = os.getenv("OUTPUT_FORMAT",     "png").lower()
OUTPUT_QUALITY = int(os.getenv("OUTPUT_QUALITY", 92))
FAST_MODE      = os.getenv("FAST_MODE",         "false").lower() == "true"



VALID_SCALES = (2, 3, 4)


# ──────────────────────────────────────────────
# ENCODE OUTPUT
# ──────────────────────────────────────────────

def _encode_image(img: np.ndarray, fmt: str, quality: int):
    if fmt == "webp":
        ok, buf = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, min(quality, 100)])
        mime, ext = "image/webp", ".webp"
    elif fmt == "jpeg":
        ok, buf = cv2.imencode(
            ".jpg", img,
            [cv2.IMWRITE_JPEG_QUALITY, min(quality, 100), cv2.IMWRITE_JPEG_OPTIMIZE, 1],
        )
        mime, ext = "image/jpeg", ".jpg"
    else:
        # SPEEDUP: PNG level 1 vs level 3 — lossless either way, ~40% faster encode.
        ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        mime, ext = "image/png", ".png"

    if not ok:
        raise RuntimeError(f"{fmt.upper()} encoding failed")
    return buf.tobytes(), mime, ext


def _decode_image(data: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


#---------------------------object remover------------------
def decode_image(file):
    raw = np.frombuffer(file.read(), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("Cannot decode image")

    return image


def decode_mask(file):
    raw = np.frombuffer(file.read(), dtype=np.uint8)
    mask = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        raise ValueError("Cannot decode mask")

    return mask


def encode_png(image):
    ok, buf = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 3])

    if not ok:
        raise RuntimeError("Encoding failed")

    return buf


