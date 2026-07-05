import os
import uuid
import logging
import subprocess
from flask_compress import Compress
from io import BytesIO
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from utils.image_types import ALLOWED_FORMATS
from config import TEMP_DIR, FFMPEG_PATH
from config import TESSERACT_PATH as TESSERACT_AVAILABLE
from flask import Flask, request, jsonify, send_file, after_this_request
import time
import torch
import threading
from utils.audio_utils import FFMPEG_TIMEOUT_SECONDS , MAX_FILE_SIZE_MB  
from concurrent.futures import ThreadPoolExecutor
import mimetypes
from flask import g
import string
import random

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_FORMATS




#------------------Compression Handler--------------
def process_file(file, settings, zipf):

    ext = file.filename.rsplit('.', 1)[-1].lower()
    uid = uuid.uuid4().hex

    temp_input = os.path.join(TEMP_DIR, f"in_{uid}.{ext}")
    temp_output = os.path.join(TEMP_DIR, f"out_{uid}.{ext}")

    try:
        file.save(temp_input)

        # ---------- IMAGE ----------
        if ext in ['jpg', 'jpeg', 'png', 'webp', 'bmp']:

            img = Image.open(temp_input)

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            if img.width > 2000 or img.height > 2000:
                img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)

            buf = BytesIO()
            img.save(
                buf,
                format="JPEG" if ext in ['jpg', 'jpeg'] else "PNG",
                quality=settings['image_q'],
                optimize=True
            )
            buf.seek(0)
            zipf.writestr(f"compressed_{file.filename}", buf.read())

        # ---------- VIDEO ----------
        elif ext in ['mp4', 'avi', 'mov', 'mkv']:

            cmd = [
                FFMPEG_PATH,
                "-y",
                "-i", temp_input,
                "-vcodec", "libx264",
                "-crf", str(settings['video_crf']),
                "-preset", "fast",
                "-acodec", "aac",
                temp_output
            ]

            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )

            with open(temp_output, 'rb') as f:
                zipf.writestr(f"compressed_{file.filename}", f.read())

        # ---------- PDF ----------
        elif ext == 'pdf':

            reader = PdfReader(temp_input)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            with open(temp_output, 'wb') as f:
                writer.write(f)

            with open(temp_output, 'rb') as f:
                zipf.writestr(f"compressed_{file.filename}", f.read())

        # ---------- UNSUPPORTED ----------
        else:
            with open(temp_input, 'rb') as f:
                zipf.writestr(f"original_{file.filename}", f.read())

    except Exception as e:
        logging.error(f"Failed: {file.filename} → {e}")

    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)
        if os.path.exists(temp_output):
            os.remove(temp_output)
            
            
            

# ── OBJECT REMOVAL ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("app")


def enable_compression(app):
    try:
        Compress(app)
        log.info("Gzip compression enabled")
    except ImportError:
        log.warning("flask-compress not installed — responses not gzip'd")
        
#  Gzip compression (install flask-compress: pip install flask-compress)
# try:
#     Compress(app)
#     log.info("Gzip compression enabled")
# except ImportError:
#     log.warning("flask-compress not installed — responses not gzip'd")
    
# ─── THREAD POOL ─────────────────────────────────────────────────────────────
_CPU_WORKERS = min(4, (os.cpu_count() or 2))
_executor    = ThreadPoolExecutor(max_workers=_CPU_WORKERS)

TILE_SIZE    = 1024   # Each tile is TILE_SIZE × TILE_SIZE pixels
TILE_OVERLAP = 256    # Overlap between adjacent tiles (feathering zone)
MAX_PX       = 6_000_000  # ~6 MP — raise on high-VRAM GPU

# ─── DEVICE DETECTION ────────────────────────────────────────────────────────
def _detect_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"

DEVICE = _detect_device()
log.info(f"Using device: {DEVICE}")


#------------------Noice reduction--------------

    
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


        
def delete_file_later(path: str, delay: float = 3.0):
    def _delete():
        time.sleep(delay)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"Failed to delete {path}: {e}")
    threading.Thread(target=_delete, daemon=True).start()
    
    
def cleanup_files(*paths):
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.warning(f"Cleanup failed for {path}: {e}")
                
                
def run_ffmpeg(command: list, label: str, cwd: str = None):
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd, timeout=FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{label} timed out after {FFMPEG_TIMEOUT_SECONDS}s.")
    except FileNotFoundError:
        raise RuntimeError(f"{label} failed: FFmpeg not found.")
    if result.returncode != 0:
        logger.error(f"[{label}] stderr:\n{result.stderr[-2000:]}")
        raise RuntimeError(f"{label} failed (exit {result.returncode}).")
    logger.info(f"[{label}] Done.")



# ==============================
# ERROR HANDLERS
# ==============================


def noice_reduction_errors(app, MAX_FILE_SIZE_MB):
    """
    Register all global Flask error handlers.
    Call this once inside new-app.py after app is created.
    """

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return jsonify({
            "error": f"File too large. Max {MAX_FILE_SIZE_MB}MB.",
            "code": "FILE_TOO_LARGE"
        }), 413

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({
            "error": "Bad request.",
            "code": "BAD_REQUEST"
        }), 400

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            "error": "Method not allowed.",
            "code": "METHOD_NOT_ALLOWED"
        }), 405

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({
            "error": "Too many requests. Please wait.",
            "code": "RATE_LIMITED"
        }), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception(f"Unhandled exception: {e}")
        return jsonify({
            "error": "Internal server error.",
            "code": "INTERNAL_ERROR"
        }), 500




#------------------Image Enhancer----------------


# ──────────────────────────────────────────────
# REQUEST HOOKS
# ──────────────────────────────────────────────
def image_enhancer_error_handlers(app, log, MAX_UPLOAD_MB):
    
    
    @app.before_request
    def _before():
        g.rid = str(uuid.uuid4())[:8]
        g.t0  = time.time()


    @app.after_request
    def _after(resp):
        resp.headers["X-Request-Id"] = getattr(g, "rid", "")
        return resp

    @app.errorhandler(413)
    def _err_413(_):
        return jsonify({
            "error": f"File exceeds {MAX_UPLOAD_MB}MB limit"
        }), 413

    @app.errorhandler(429)
    def _err_429(_):
        return jsonify({
            "error": "Rate limit exceeded — retry later"
        }), 429

    @app.errorhandler(404)
    def _err_404(_):
        return jsonify({
            "error": "Not found"
        }), 404

    @app.errorhandler(405)
    def _err_405(_):
        return jsonify({
            "error": "Method not allowed"
        }), 405

    @app.errorhandler(500)
    def _err_500(exc):
        log.exception("Unhandled: %s", exc)
        return jsonify({
            "error": "Internal server error"
        }), 500
        
#--------------------------Url Shortner------------------    
from config import BASE_URL , GOOGLE_SAFE_BROWSING_API_KEY , WHOISXML_API_KEY  

   
def generate_code(length=6):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def get_base_url():
    return BASE_URL or request.host_url.rstrip("/")


def get_client_ip():
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
    )
