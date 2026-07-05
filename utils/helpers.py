from PIL import Image , UnidentifiedImageError
from flask import Flask, request, jsonify, send_file
from io import BytesIO
from utils.image_types import ALLOWED_FORMATS
import zipfile
import uuid
import numpy as np
import cv2
import subprocess
import mimetypes
import os
from config import log
from utils.audio_utils import ALLOWED_EXTENSIONS , ALLOWED_MIMETYPES
from utils.image_utils import  VALID_SCALES
from models.image_enhancer_model import _model_ready     
from utils.handler import log
from utils.dowload_image_enhancer_models import _download_model

# -------------------- images to pdf helper--------------------
def create_page(images, width, height, margin):
    page = Image.new("RGB", (width, height), (255, 255, 255))
    total_img_height = sum(img.height for img in images)
    total_spacing = margin * (len(images) + 1)
    total_block_height = total_img_height + total_spacing
    start_y = (height - total_block_height) // 2 + margin
    y = start_y
    for img in images:
        x = (width - img.width) // 2
        page.paste(img, (x, y))
        y += img.height + margin
    return page


# -------------------- images Conversion for single image (type)(helper)--------------------
def process_single_image(file, target_format):
    try:
        img = Image.open(file)
    except UnidentifiedImageError:
        return jsonify({"error": "Invalid image file"}), 400

    if target_format in ["jpg", "jpeg"]:
        img = img.convert("RGB")

    buffer = BytesIO()
    img.save(buffer, ALLOWED_FORMATS[target_format])
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype=f"image/{target_format}",
        download_name=f"converted.{target_format}",
        as_attachment=True
    )
    
# -------------------- images Conversion for multiple imaages (type)-(helper)--------------------
def process_multiple_images(files, target_format):
    # MULTIPLE IMAGES → ZIP
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            img = Image.open(file)
            if target_format in ["jpg", "jpeg"]:
                img = img.convert("RGB")

            img_buffer = BytesIO()
            img.save(img_buffer, ALLOWED_FORMATS[target_format])
            img_buffer.seek(0)

            filename = f"{uuid.uuid4().hex}.{target_format}"
            zipf.writestr(filename, img_buffer.read())

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        download_name="converted_images.zip",
        as_attachment=True
    )
    
# --------------------Compression helpers--------------------
def validate_compression_request(request):
    if 'file' not in request.files:
        return None, (jsonify({"error": "No files uploaded"}), 400)

    files = request.files.getlist('file')

    if not files:
        return None, (jsonify({"error": "Empty upload"}), 400)

    return files, None


def get_settings(level):
    if level not in ['low', 'medium', 'high']:
        level = 'medium'

    settings = {
        'low':    {'image_q': 95, 'video_crf': 18},
        'medium': {'image_q': 75, 'video_crf': 23},
        'high':   {'image_q': 50, 'video_crf': 28}
    }

    return settings[level]


# --------------------Object Remover Helpers--------------------

def _feather_composite(
    inpainted : np.ndarray,
    original  : np.ndarray,
    mask      : np.ndarray,
    feather_px: int = 16,
) -> np.ndarray:
    
    dist_in  = cv2.distanceTransform(mask,       cv2.DIST_L2, 5).astype(np.float32)
    dist_out = cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5).astype(np.float32)
    alpha    = dist_in / (dist_in + dist_out + 1e-6)
    k = feather_px * 2 + 1
    alpha = cv2.GaussianBlur(alpha, (k, k), feather_px / 3.0)[:, :, np.newaxis]
    result = (inpainted.astype(np.float32) * alpha +
              original.astype(np.float32)  * (1.0 - alpha))
    return np.clip(result, 0, 255).astype(np.uint8)


def _opencv_inpaint(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Multi-scale TELEA + NS blend fallback — much better than naive single-pass.
    """
    log.warning("[fallback] OpenCV inpaint — install LaMa for best quality")
    H, W   = image.shape[:2]
    result = image.copy()

    # Downscale passes provide long-range context
    for scale in (0.2, 0.5, 1.0):
        sw = max(16, int(W * scale))
        sh = max(16, int(H * scale))
        img_s = cv2.resize(result, (sw, sh), cv2.INTER_AREA)
        msk_s = cv2.resize(mask,   (sw, sh), cv2.INTER_NEAREST)
        _, msk_s = cv2.threshold(msk_s, 127, 255, cv2.THRESH_BINARY)
        if msk_s.max() == 0:
            continue
        r_s   = max(3, int(np.sqrt(msk_s.sum() // 255) // 6))
        filled = cv2.inpaint(img_s, msk_s, r_s, cv2.INPAINT_TELEA)
        up     = cv2.resize(filled, (W, H), cv2.INTER_LANCZOS4)
        result[mask > 0] = up[mask > 0]

    r     = max(5, min(25, int(np.sqrt(mask.sum() // 255) // 6)))
    telea = cv2.inpaint(result, mask, r, cv2.INPAINT_TELEA)
    ns    = cv2.inpaint(result, mask, r, cv2.INPAINT_NS)
    blend = np.clip(telea.astype(np.float32) * 0.6 + ns.astype(np.float32) * 0.4, 0, 255).astype(np.uint8)
    return _feather_composite(blend, image, mask)


# ─── MASK QUALITY ENHANCEMENT ────────────────────────────────────────────────

def refine_mask(mask: np.ndarray) -> np.ndarray:
    """
    Clean up a user-painted brush mask:
      1. Close small holes
      2. Slight morphological dilation to cover brush fringing
      3. Optional Canny-guided refinement (snaps to object edges)
    """
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return mask
        

# ─── Noice reduction ────────────────────────────────────────────────  
# ─── ----------- ────────────────────────────────────────────────   
def validate_upload(file) -> tuple:
    if not file or file.filename == "":
        return False, "No file selected or empty filename."
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
    guessed_mime, _ = mimetypes.guess_type(file.filename)
    content_type    = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIMETYPES and (guessed_mime or "") not in ALLOWED_MIMETYPES:
        return False, f"Unsupported content type '{content_type}'."
    return True, ""

def verify_audio_stream(path: str):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise RuntimeError("File validation timed out.")
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found.")
    if result.returncode != 0 or "audio" not in result.stdout.lower():
        raise RuntimeError("Uploaded file does not contain a valid audio stream.")
    
# ─── IMage Enhancer ────────────────────────────────────────────────  
# ─── ----------- ────────────────────────────────────────────────   
from utils.image_utils import _encode_image , _decode_image
from utils.image_utils import MAX_PIXELS , OUTPUT_FORMAT , OUTPUT_QUALITY
from models.image_enhancer_model import enhance
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from flask import Flask, g, jsonify, request, send_file
from models.image_enhancer_model import log
# ──────────────────────────────────────────────
# BATCH ENDPOINT
# ──────────────────────────────────────────────

def _process_one_batch_item(f, scale, fmt, quality, rid):
    """Worker for concurrent batch processing."""
    raw = f.read()
    img = _decode_image(raw) if raw else None
    if img is None:
        return {"filename": f.filename, "error": "Invalid image"}

    h, w = img.shape[:2]
    if w * h > MAX_PIXELS:
        return {"filename": f.filename, "error": "Image too large"}

    try:
        enhanced, method   = enhance(img, scale)
        encoded, mime, ext = _encode_image(enhanced, fmt, quality)
        oh, ow = enhanced.shape[:2]
        return {
            "filename":    f.filename,
            "method":      method,
            "output_size": f"{ow}x{oh}",
            "format":      fmt,
            "data":        base64.b64encode(encoded).decode(),
            "mime":        mime,
        }
    except Exception as exc:
        log.error("[%s] batch %s failed: %s", rid, f.filename, exc)
        return {"filename": f.filename, "error": "Enhancement failed"}


def _batch_route():
    rid   = g.rid
    files = request.files.getlist("images[]")
    if not files:
        return jsonify({"error": "No images provided", "request_id": rid}), 400
    if len(files) > 5:
        return jsonify({"error": "Max 5 images per batch", "request_id": rid}), 400

    try:
        scale = int(request.form.get("scale", 2))
    except (ValueError, TypeError):
        scale = 2
    if scale not in VALID_SCALES:
        scale = 2

    fmt     = request.form.get("format", OUTPUT_FORMAT).lower()
    quality = int(request.form.get("quality", OUTPUT_QUALITY))
    if fmt not in ("png", "webp", "jpeg"):
        fmt = "png"

    # SPEEDUP: process batch images concurrently instead of sequentially.
    # For 5 images this is up to ~5x faster (I/O + CPU overlap).
    results_map = {}
    with ThreadPoolExecutor(max_workers=min(len(files), 5)) as pool:
        futs = {
            pool.submit(_process_one_batch_item, f, scale, fmt, quality, rid): f.filename
            for f in files
        }
        for fut in as_completed(futs):
            filename = futs[fut]
            try:
                results_map[filename] = fut.result()
            except Exception as exc:
                log.error("[%s] batch future %s: %s", rid, filename, exc)
                results_map[filename] = {"filename": filename, "error": "Enhancement failed"}

    # Preserve original file order in response
    results = [results_map[f.filename] for f in files if f.filename in results_map]
    return jsonify({"request_id": rid, "results": results}), 200
    


# ---------------------------------url shortner -- helper-----------

from database.db import get_db_of_short_link as get_db
import re
from flask import Flask, request, jsonify, redirect, Response, stream_with_context
from services.url_shortner_service import _generate_progress
from models.url_shortner_model import _sse


def _is_valid_code(code: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9]{4,12}$", code))

def _get_short_link(code: str):
    db = None
    cur = None
    try:
        db = get_db()
        cur = db.cursor()

        cur.execute(
            "SELECT original_url, flagged FROM short_links WHERE short_code=%s",
            (code,)
        )
        return cur.fetchone()

    finally:
        if cur:
            cur.close()
        if db:
            db.close()
            
def _increment_clicks(code: str):
    db = None
    cur = None
    try:
        db = get_db()
        cur = db.cursor()

        cur.execute(
            "UPDATE short_links SET clicks = clicks + 1 WHERE short_code=%s",
            (code,)
        )
        db.commit()

    except Exception:
        if db:
            db.rollback()
        raise

    finally:
        if cur:
            cur.close()
        if db:
            db.close()           

    
def _rate_limited_sse():
    def rate_err():
        yield _sse({
            "stage": "RateLimit",
            "status": "fail",
            "pct": 0,
            "reason": "Too many requests"
        })

    return Response(
        stream_with_context(rate_err()),
        mimetype="text/event-stream"
    )
 
def _missing_url_sse():
    def no_url():
        yield _sse({
            "stage": "Input",
            "status": "fail",
            "pct": 0,
            "reason": "URL is required"
        })

    return Response(
        stream_with_context(no_url()),
        mimetype="text/event-stream"
    )
    

def _progress_stream_response(url: str, ip: str):
    return Response(
        stream_with_context(_generate_progress(url, ip)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        },
    )
     
#------------for pdf-edit



