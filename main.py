# ── Standard library ──────────────────────────────────────────────────────────
import logging
import os
import secrets
import time
import uuid
import zipfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import urlparse, quote
from services.clean_temp import start_temp_cleanup

# ── Third-party ───────────────────────────────────────────────────────────────
import cv2
import ffmpeg
import fitz          # PyMuPDF
import numpy as np
import pytesseract
import soundfile as sf
from dotenv import load_dotenv
from pdf2docx import Converter
from PIL import ExifTags, Image, UnidentifiedImageError
from PyPDF2 import PdfReader, PdfWriter
from rembg import remove

# ── Flask & extensions ────────────────────────────────────────────────────────
from flask import (
    Flask, abort, jsonify, redirect, render_template,
    request, send_file, send_from_directory, url_for
)
from flask_compress import Compress
from flask_cors import CORS

from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
    verify_jwt_in_request,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message

# ── Local imports ─────────────────────────────────────────────────────────────
from config import (
    BASE_DIR, FFMPEG_PATH, MODEL_DIR, TEMP_DIR,
    TESSERACT_PATH as TESSERACT_AVAILABLE,
    Config, log,
)
from database.db import get_db, get_db_of_short_link

#IMAGE enhancer model
from models.image_enhancer_model import (
    LIMITER_AVAILABLE, _active_lock, _model_cache, _model_ready,
    enhance, init_limiter, log,
)
from services.enhance_service import handle_enhance_image


#Noice reduction model
from models.noice_reduction_model import process_audio
from services.noice_reduction_service import handle_reduce_noise

from models.object_remover_models import lama_inpaint
from models.url_shortner_model import (
     url_shortner_model_initilizer,
)

from models.voice_to_text_model import parse_language, _FFMPEG_AVAILABLE
from services.auth_services import hash_password, is_strong_password, is_valid_email, verify_password
from services.compression_service import handle_compression
from services.email_template import password_reset_email

from services.image_edit_service import (
    handle_get_pages, handle_rebuild_pdf, handle_save_page, handle_upload_file,
)
from services.image_services import handle_image_conversion, process_inpaint

from services.ocr_service import handle_ocr
from services.obj_remover_service import remove_object_service
from services.pdf_service import (
    build_pages_only_pdf_response, get_temp_file_response,
    handle_cleanup, handle_pdf_upload, handle_rebuild_pdf_only,
    handle_restore_page, handle_save_page_only_pdf, safe_file_id,
)
from services.style_service import process_style_analysis
from services.token_service import cleanup_expired_tokens
from services.voice_to_text_service import (
    build_transcription_response, check_voice_rate_limit,
    convert_audio_to_wav, process_audio_input, transcribe_audio,
    validate_audio_upload,
)
from utils.audio_types import DEFAULT_QUALITY, PRESET_ALIAS, QUALITY_PROFILES
from utils.audio_utils import MAX_CONCURRENT_JOBS, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB , PIPELINE_TIMEOUT_SECONDS
from utils.check_ffmpeg import check_ffmpeg
from utils.check_rninoice import prepare_model
from utils.converters import b64_to_cv2, cv2_to_b64
from utils.gpu_Detection import COMPUTE_LABEL
from utils.handler import (
    MAX_PX, allowed_file, cleanup_files, delete_file_later,
    enable_compression, generate_code, get_client_ip, image_enhancer_error_handlers,
    logger, noice_reduction_errors,
)
from utils.helpers import (
    _get_short_link, _increment_clicks, _is_valid_code,
    _missing_url_sse, _progress_stream_response, _rate_limited_sse,
    create_page, refine_mask, validate_upload, verify_audio_stream,
)
from utils.image_types import ALLOWED_FORMATS
from utils.image_utils import (
    MAX_PIXELS, MAX_QUEUE, MAX_UPLOAD_MB, OUTPUT_FORMAT,
    OUTPUT_QUALITY, RATE_LIMIT, REDIS_URL, VALID_SCALES,
    _decode_image, _encode_image,
)
from utils.pdf_utils import ALLOWED_EXT, MAX_FILE_MB
from utils.url_Shortner_handles import (
    _check_rate_limit, _extract_url_from_request,
    _run_security_checks, is_rate_limited,
)




load_dotenv(override=True)
FRONTEND_URL = os.getenv("FRONTEND_URL")


app = Flask(
    __name__,
    template_folder="views",
    static_folder="public" ,
    static_url_path="/assets"
)


app.config.from_object(Config)



# ── Security / JWT ────────────────────────────────────────────────────────────
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
    seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "3600"))
)
app.config["JWT_TOKEN_LOCATION"] = ["headers", "cookies"]
app.config["JWT_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["JWT_COOKIE_CSRF_PROTECT"] = False          # set True + add CSRF tokens in prod
app.config["JWT_COOKIE_SAMESITE"] = "Lax"
app.config["JWT_ACCESS_COOKIE_NAME"] = "access_token_cookie"


# Max upload size: 100MB (as before, but with better enforcement)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# ---------------- MAIL  ----------------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_DEFAULT_SENDER=os.getenv("MAIL_USERNAME")
)

# # ── Extensions ────────────────────────────────────────────────────────────────
# ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
# CORS(app, origins=ALLOWED_ORIGINS or None, supports_credentials=True)
# _CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
CORS(app, origins=["http://localhost:5000", "http://127.0.0.1:5000"], supports_credentials=True)
jwt = JWTManager(app)
mail = Mail(app)
limiter  = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)


# ── JWT blocklist (in-memory; replace with DB set in production) ──────────────
_jwt_blocklist: set[str] = set()

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload: dict) -> bool:
    return jwt_payload.get("jti") in _jwt_blocklist


# old
# ── Security headers ──────────────────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"]    = "strict-origin-when-cross-origin"
    return response

@app.errorhandler(400)
def _err_400(e):
    desc = getattr(e, "description", "Bad request")
    return jsonify({"error": str(desc)}), 400

@app.errorhandler(404)
def _err_404(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(405)
def _err_405(e):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(413)
def _err_413(e):
    return jsonify({"error": "File too large — maximum upload size is 100 MB"}), 413

@app.errorhandler(429)
def _err_429(e):
    return jsonify({"error": "Too many requests — please slow down"}), 429

@app.errorhandler(Exception)
def _err_any(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    log.exception("Unhandled exception: %s", e)
    return jsonify({"error": "An internal server error occurred"}), 500





@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description) if hasattr(e, "description") else "Bad request"}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"error": "File too large. Maximum upload size is 100 MB."}), 413

@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({"error": "Too many requests — please slow down."}), 429

@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all: log the full traceback, return a safe JSON response."""
    log.exception("Unhandled exception: %s", e)
    # Re-raise HTTP exceptions so Flask handles them normally
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    return jsonify({"error": "An internal server error occurred."}), 500


def page_login_required(f):
    """Decorator for page routes: redirect to login if no valid JWT cookie."""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request(locations=["cookies"])
        except Exception:
            next_path = quote(request.path, safe="")
            return redirect(f"/loginSystem?next={next_path}")
        return f(*args, **kwargs)
    return decorated

# --------------------------------------------
# ----------------Login System----------------
# --------------------------------------------

# login Page
@app.route("/loginSystem")
def loginSystem():
    return render_template("login.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/forget")
def forget():
    return render_template("forget.html"  , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/reset-password")
def reset_password_page():
    return render_template("reset_password.html"  , FRONTEND_URL=os.getenv("FRONTEND_URL"))

    
# --------------------------------------------
# ----------------Login System----------------
# --------------------------------------------



# ---------------- REGISTER ----------------
@app.route("/register", methods=["POST"])
@limiter.limit("10 per hour")
def register():
    data =  request.get_json(silent=True) or {}
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not all([name, email, password]):
        return jsonify({"error": "All fields required"}), 400
    
    if not is_valid_email(email):
        return jsonify({"error": "Invalid email address"}), 400
   
    if not is_strong_password(password):
        return jsonify({
            "error": "Password must be 8+ chars with upper, lower, number & symbol"
        }), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cur.fetchone():
            return jsonify({"error": "Email already exists"}), 400

        cur.execute(
            "INSERT INTO users (username, email, password) VALUES (%s,%s,%s)",
            (name, email, hash_password(password))
        )
        db.commit()
        return jsonify({"message": "Registered successfully"}), 201
    except Exception:
        db.rollback()
        log.exception("register")
        return jsonify({"error": "Server error"}), 500
    finally:
        cur.close()
        db.close()




@app.route("/login", methods=["POST"])
@limiter.limit("20 per hour")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT id, password , username FROM users WHERE email=%s", (email,))
        user = cur.fetchone()

        if not user or not verify_password(password, user["password"]):
            return jsonify({"error": "Invalid credentials"}), 401

        token = create_access_token(identity=str(user["id"]))

        cur.execute("UPDATE users SET is_online=1 WHERE id=%s", (user["id"],))
        db.commit()
        response = jsonify({
            "access_token": token,
            "username": user["username"],
            "email": email,
            "user_id": user["id"]
        })
        # response = jsonify({
        #     "access_token": token,
        #     "name":  user.get("username") or email.split("@")[0],
        #     "email": email,
        # })
        set_access_cookies(response, token)
        return response, 200
    except Exception:
        log.exception("login")
        return jsonify({"error": "Server error"}), 500
    finally:
        cur.close()
        db.close()


# ── Logout ────────────────────────────────────────────────────────────────────
@app.route("/logout", methods=["POST"])
@jwt_required(locations=["headers", "cookies"], optional=True)
def logout():
    try:
        jwt_data = get_jwt()
        jti = jwt_data.get("jti")
        if jti:
            _jwt_blocklist.add(jti)

        user_id = get_jwt_identity()
        if user_id:
            db = get_db()
            cur = db.cursor()
            try:
                cur.execute("UPDATE users SET is_online=0 WHERE id=%s", (user_id,))
                db.commit()
            finally:
                cur.close()
                db.close()
    except Exception:
        pass

    response = jsonify({"message": "Logged out"})
    unset_jwt_cookies(response)
    return response, 200




# ---------------- FORGOT PASSWORD ----------------
@app.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per hour")
def forgot_password():
    SAME_RESPONSE = jsonify({"message": "If the email exists, a reset link has been sent."}), 200
    
    db = None
    cur = None
    try:
        data = request.get_json(silent=True) or {}
        email = request.json.get("email")


        if not email:
            return SAME_RESPONSE
        
        db = get_db()
        cur = db.cursor()

        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cur.fetchone()

        if user:
            token = secrets.token_urlsafe(48)
            expires = datetime.utcnow() + timedelta(minutes=15)

            cur.execute("""
                INSERT INTO password_resets (user_id, reset_token, expires_at)
                VALUES (%s, %s, %s)
            """, (user["id"], token, expires))
            db.commit()
            FRONTEND_URL = os.getenv("FRONTEND_URL" , request.url_root.rstrip("/"))
            reset_link = f"{FRONTEND_URL}/reset-password?token={token}"

            html_body = password_reset_email(reset_link)

            msg = Message(
                subject="Flarixo AI – Reset Your Password",
                recipients=[email],
                sender=("Flarixo AI Support", app.config["MAIL_USERNAME"]),
                body=f"""
You requested a password reset for your Flask account.

Reset link:
{reset_link}

This link expires in 15 minutes.
If you did not request this, ignore this email.

– Flask Team
""",
                html=html_body
            )

            mail.send(msg)

        return SAME_RESPONSE

    except Exception as e:
        print("FORGOT PASSWORD ERROR:", e)
        return jsonify({"error": "Server error"}), 500

    finally:
        try:
            cur.close()
            db.close()
        except:
            pass


import os
import hashlib
import secrets




# ---------------- RESET PASSWORD API ----------------
@app.route("/api/reset-password", methods=["POST"])
@limiter.limit("10 per hour")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    password = data.get("password")

    if not token or not password:
        return jsonify({"error": "Invalid request"}), 400

    if not is_strong_password(password):
        return jsonify({"error": "Weak password"}), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
        SELECT user_id FROM password_resets
        WHERE reset_token=%s AND expires_at > UTC_TIMESTAMP()
        """, (token,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Token expired or invalid"}), 400

        cur.execute(
            "UPDATE users SET password=%s WHERE id=%s",
            (hash_password(password), row["user_id"])
        )

        cur.execute("DELETE FROM password_resets WHERE user_id=%s", (row["user_id"],))
        db.commit()

        return jsonify({"message": "Password reset successful"}), 200
    except Exception:
        db.rollback()
        log.exception("reset-password")
        return jsonify({"error": "Server error"}), 500
    finally:
        cur.close()
        db.close()


        
        
# ── Current user ──────────────────────────────────────────────────────────────
@app.route("/api/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, username, email FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()
    db.close()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "id":    user["id"],
        "name":  user["username"],
        "email": user["email"],
    }), 200

# ---------------- pDf-to-Doc-converter ----------------


from pypdf import PdfReader, PdfWriter
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

# pdf2docx only used for the NON-OCR (native/digital) path now
from pdf2docx import Converter

# ---------------------------------------------------------------------------
# OCR HELPERS
# ---------------------------------------------------------------------------

def _ocr_page_to_text(page, zoom=2.6):
    """
    Render a single PyMuPDF page to an image at higher resolution and OCR it.
    Upscaling (zoom>1) materially improves accuracy on scanned/handwritten
    pages versus OCRing at native 72dpi render size.
    """
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(BytesIO(pix.tobytes("png")))

    # Light preprocessing: convert to grayscale. This alone tends to help
    # tesseract on photographed/scanned handwritten pages with uneven
    # lighting, without risking over-binarizing thin handwriting strokes.
    img = img.convert("L")

    config = "--oem 3 --psm 3"
    try:
        text = pytesseract.image_to_string(img, config=config)
        # Fallback: some single-column handwritten/note pages OCR better
        # with psm 6 (treat as a single uniform block of text) if psm 3
        # (full automatic layout detection) returns almost nothing.
        if len(text.strip()) < 5:
            text = pytesseract.image_to_string(img, config="--oem 3 --psm 6")
    except Exception as e:
        logging.error(f"OCR failed on a page: {e}")
        text = ""
    return text


import re

_LIST_ITEM_RE = re.compile(
    r"^(\d{1,2}[\.\)]\s+|[-•*]\s+|[a-zA-Z][\.\)]\s+)"
)


def _is_list_item_start(line):
    """True if a line looks like the start of a numbered/bulleted list item
    (e.g. '1. ', '2) ', '- ', '• ', 'a. ')."""
    return bool(_LIST_ITEM_RE.match(line.strip()))


def _clean_ocr_text_to_paragraphs(raw_text):
    """
    Tesseract output has hard line breaks wherever a visual line ends on the
    page, NOT wherever a sentence/paragraph ends. Rejoining those into real
    paragraphs is what makes the result read like 'normal text' in Word
    instead of one ragged line per row of handwriting.

    Rules:
      - A blank line (or sequence of blank lines) = paragraph break, keep it.
      - A line that looks like a new list item ('1.', '-', '•', etc.) always
        starts a new paragraph, even with no blank line before it -- this
        stops numbered/bulleted lists from being merged into one run-on line.
      - Any other single newline between two non-empty lines = mid-paragraph
        wrap, joined with a space instead of a line break.
    """
    if not raw_text or not raw_text.strip():
        return []

    raw_lines = raw_text.splitlines()
    paragraphs = []
    current = []

    for line in raw_lines:
        stripped = line.strip()
        if stripped == "":
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue

        if _is_list_item_start(stripped) and current:
            paragraphs.append(" ".join(current).strip())
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        paragraphs.append(" ".join(current).strip())

    # Drop empty/garbage paragraphs (e.g. OCR noise of just punctuation)
    return [p for p in paragraphs if p and any(c.isalnum() for c in p)]


def _build_docx_from_ocr(pdf_paths, output_path, zoom=2.6):
    """
    Build a single DOCX directly from OCR text extracted from one or more
    PDFs, as real Word paragraphs. No pdf2docx involved -- that's the whole
    point of the fix.
    """
    doc = Document()

    # Sensible default body style so OCR'd notes read like a normal document
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    multi_file = len(pdf_paths) > 1

    for file_idx, path in enumerate(pdf_paths):
        pdf = fitz.open(path)

        if multi_file:
            heading = doc.add_heading(f"Document {file_idx + 1}: {os.path.basename(path)}", level=1)

        if len(pdf) == 0:
            pdf.close()
            continue

        for page_num in range(len(pdf)):
            page = pdf[page_num]
            raw_text = _ocr_page_to_text(page, zoom=zoom)
            paragraphs = _clean_ocr_text_to_paragraphs(raw_text)

            if len(pdf) > 1:
                p_heading = doc.add_paragraph()
                run = p_heading.add_run(f"Page {page_num + 1}")
                run.bold = True
                run.font.size = Pt(10)
                run.font.color.rgb = None  # keep default theme color

            if not paragraphs:
                p = doc.add_paragraph()
                run = p.add_run("[No text could be recognized on this page.]")
                run.italic = True
            else:
                for para_text in paragraphs:
                    doc.add_paragraph(para_text)

            # Page break between source pages (but not after the very last
            # page of the very last file)
            is_last_page = (page_num == len(pdf) - 1)
            is_last_file = (file_idx == len(pdf_paths) - 1)
            if not (is_last_page and is_last_file):
                doc.add_page_break()

        pdf.close()

    doc.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# ROUTE
# ---------------------------------------------------------------------------

@app.route("/pdf-to-doc", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def pdf_to_doc():
    temp_pdf_paths = []
    merged_pdf_path = None
    output_docx_path = None
    try:
        pdf_files = request.files.getlist("pdf")
        ocr_enabled = request.form.get("ocr", "false").lower() == "true"

        if not pdf_files or all(f.filename == "" for f in pdf_files):
            return jsonify({"error": "No PDF files provided"}), 400
        if len(pdf_files) > 5:
            return jsonify({"error": "Maximum 5 PDFs allowed"}), 400

        for pdf_file in pdf_files:
            if pdf_file.content_length and pdf_file.content_length > 20 * 1024 * 1024:
                return jsonify({"error": f"{pdf_file.filename} exceeds 20MB"}), 400

        if ocr_enabled and not TESSERACT_AVAILABLE:
            return jsonify({
                "error": "OCR was requested but the OCR engine is unavailable on the server. "
                         "Please contact support or retry without OCR."
            }), 503

        # Save temp PDFs
        for pdf_file in pdf_files:
            temp_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{pdf_file.filename}")
            pdf_file.save(temp_path)
            temp_pdf_paths.append(temp_path)

        output_docx_path = os.path.join(TEMP_DIR, f"merged_{uuid.uuid4()}.docx")

        if ocr_enabled:
            # ---- OCR / HANDWRITTEN / SCANNED PATH ----
            # Build the DOCX directly from recognized text. pdf2docx is
            # intentionally NOT used here -- see module docstring for why
            # that combination was producing the bad results.
            _build_docx_from_ocr(temp_pdf_paths, output_docx_path)

        else:
            # ---- NATIVE / DIGITAL PDF PATH (unchanged approach) ----
            # These PDFs have real text+layout objects, so pdf2docx's
            # structure reconstruction is appropriate and works well here.
            merged_pdf_path = os.path.join(TEMP_DIR, f"merged_{uuid.uuid4()}.pdf")
            writer = PdfWriter()
            for path in temp_pdf_paths:
                reader = PdfReader(path)
                for page in reader.pages:
                    writer.add_page(page)
            with open(merged_pdf_path, "wb") as f:
                writer.write(f)

            cv = Converter(merged_pdf_path)
            cv.convert(output_docx_path)
            cv.close()

        # Send DOCX
        with open(output_docx_path, "rb") as f:
            file_bytes = BytesIO(f.read())

        # Cleanup
        cleanup_paths = temp_pdf_paths + (
            [merged_pdf_path] if merged_pdf_path else []
        ) + [output_docx_path]
        for path in cleanup_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    logging.warning(f"Could not delete {path} (permission error)")

        return send_file(
            file_bytes,
            as_attachment=True,
            download_name="converted.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        logging.error(f"PDF to DOCX error: {e}")
        cleanup_paths = temp_pdf_paths + (
            [merged_pdf_path] if merged_pdf_path else []
        ) + ([output_docx_path] if output_docx_path else [])
        for path in cleanup_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    logging.warning(f"Could not delete {path} (permission error)")
        return jsonify({"error": f"Conversion failed: {str(e)}"}), 500
# @app.route("/pdf-to-doc", methods=["POST"])
# @jwt_required(locations=["headers", "cookies"])
# def pdf_to_doc():
#     temp_pdf_paths = []
#     merged_pdf_path = None
#     output_docx_path = None
#     try:
#         pdf_files = request.files.getlist("pdf")
#         ocr_enabled = request.form.get("ocr", "false").lower() == "true"

#         if not pdf_files or all(f.filename == "" for f in pdf_files):
#             return jsonify({"error": "No PDF files provided"}), 400
#         if len(pdf_files) > 5:
#             return jsonify({"error": "Maximum 5 PDFs allowed"}), 400

#         for pdf_file in pdf_files:
#             if pdf_file.content_length > 20 * 1024 * 1024:
#                 return jsonify({"error": f"{pdf_file.filename} exceeds 20MB"}), 400

#         # Save temp PDFs
#         for pdf_file in pdf_files:
#             temp_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{pdf_file.filename}")
#             pdf_file.save(temp_path)
#             temp_pdf_paths.append(temp_path)

#         # OCR if enabled
#         if ocr_enabled and TESSERACT_AVAILABLE:
#             ocr_pdf_paths = []
#             for path in temp_pdf_paths:
#                 ocr_path = os.path.join(TEMP_DIR, f"ocr_{uuid.uuid4()}.pdf")
#                 doc = fitz.open(path)
#                 new_doc = fitz.open()
#                 for page_num in range(len(doc)):
#                     page = doc[page_num]
#                     pix = page.get_pixmap()
#                     img = Image.open(BytesIO(pix.tobytes()))
#                     try:
#                         text = pytesseract.image_to_string(img)
#                         new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
#                         new_page.insert_image(page.rect, pixmap=pix)
#                         new_page.insert_text((10, 10), text, fontsize=12, color=(0, 0, 0))
#                     except Exception as e:
#                         logging.error(f"OCR failed on page {page_num} of {path}: {e}")
#                         new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
#                         new_page.insert_image(page.rect, pixmap=pix)
#                 new_doc.save(ocr_path)
#                 doc.close()
#                 new_doc.close()
#                 ocr_pdf_paths.append(ocr_path)
#             temp_pdf_paths = ocr_pdf_paths
#         elif ocr_enabled:
#             logging.warning("OCR requested but Tesseract not available. Proceeding without OCR.")

#         # Merge PDFs
#         merged_pdf_path = os.path.join(TEMP_DIR, f"merged_{uuid.uuid4()}.pdf")
#         writer = PdfWriter()
#         for path in temp_pdf_paths:
#             reader = PdfReader(path)
#             for page in reader.pages:
#                 writer.add_page(page)
#         with open(merged_pdf_path, "wb") as f:
#             writer.write(f)

#         # Convert to DOCX
#         output_docx_path = os.path.join(TEMP_DIR, f"merged_{uuid.uuid4()}.docx")
#         cv = Converter(merged_pdf_path)
#         cv.convert(output_docx_path)
#         cv.close()

#         # Send DOCX
#         with open(output_docx_path, "rb") as f:
#             file_bytes = BytesIO(f.read())

#         # Cleanup
#         for path in temp_pdf_paths + [merged_pdf_path, output_docx_path]:
#             if path and os.path.exists(path):
#                 try:
#                     os.remove(path)
#                 except PermissionError:
#                     logging.warning(f"Could not delete {path} (permission error)")

#         return send_file(
#             file_bytes,
#             as_attachment=True,
#             download_name="converted.docx",
#             mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
#         )

#     except Exception as e:
#         logging.error(f"PDF to DOCX error: {e}")
#         for path in temp_pdf_paths + ([merged_pdf_path] if merged_pdf_path else []) + ([output_docx_path] if output_docx_path else []):
#             if path and os.path.exists(path):
#                 try:
#                     os.remove(path)
#                 except PermissionError:
#                     logging.warning(f"Could not delete {path} (permission error)")
#         return jsonify({"error": f"Conversion failed: {str(e)}"}), 500


# -------------------- Text Extractor OCR(MODEL)--------------------
@app.route('/extract-text', methods=['POST'])
@jwt_required(locations=["headers", "cookies"])
def extract_text():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image received"}), 400

        # Load image
        image = Image.open(request.files['image']).convert("RGB")
        img = np.array(image)

        # --- PREPROCESSING ---
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Increase contrast
        gray = cv2.bilateralFilter(gray, 9, 75, 75)

        # Adaptive threshold (BEST for documents)
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31, 2
        )

        # Optional: remove noise
        kernel = np.ones((1,1), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # --- TESSERACT CONFIG ---
        custom_config = r'--oem 3 --psm 6'

        text = pytesseract.image_to_string(
            thresh,
            lang='eng',
            config=custom_config
        )

        return jsonify({"text": text.strip()})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    



# -------------------- images to pdf--------------------
@app.route("/images-to-pdf", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def images_to_pdf():
    try:
        files = request.files.getlist('images')
        if not files or all(not file.filename for file in files):
            return jsonify({"error": "No images uploaded or invalid files"}), 400

        # Validate and filter files
        valid_files = [f for f in files if f and allowed_file(f.filename)]
        if not valid_files:
            return jsonify({"error": "No valid image files uploaded"}), 400

        # Check total size (rough estimate to prevent overload)
        total_size = sum(len(f.read()) for f in valid_files)
        if total_size > app.config['MAX_CONTENT_LENGTH']:
            return jsonify({"error": "Total upload size exceeds 100MB limit"}), 413
        # Reset file pointers
        for f in valid_files:
            f.seek(0)

        images = []
        for file in valid_files:
            try:
                img = Image.open(file)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Safe auto rotate with better error handling
                try:
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            if ExifTags.TAGS.get(tag) == 'Orientation':
                                if value == 3:
                                    img = img.rotate(180, expand=True)
                                elif value == 6:
                                    img = img.rotate(270, expand=True)
                                elif value == 8:
                                    img = img.rotate(90, expand=True)
                                break
                except (AttributeError, KeyError):
                    pass  # Ignore if no EXIF

                images.append(img)
            except Exception as e:
                logging.error(f"Error processing image {file.filename}: {e}")
                return jsonify({"error": f"Invalid image file: {file.filename}"}), 400

        # A4 portrait size at 300dpi (unchanged)
        A4_WIDTH, A4_HEIGHT = 2480, 3508
        MARGIN = 15

        pdf_pages = []
        current_page_images = []
        current_y = MARGIN

        for img in images:
            # Resize based on orientation (optimized for memory)
            if img.width > img.height:  # Landscape
                ratio = (A4_WIDTH - 2 * MARGIN) / img.width
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            else:  # Portrait or square
                if img.height <= A4_HEIGHT / 2:
                    ratio = (A4_WIDTH - 2 * MARGIN) / img.width
                    new_width = int(img.width * ratio)
                    new_height = int(img.height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    if img.width > A4_WIDTH - 2 * MARGIN:
                        ratio = (A4_WIDTH - 2 * MARGIN) / img.width
                        new_width = int(img.width * ratio)
                        new_height = int(img.height * ratio)
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Check if adding this image would exceed page height
            if current_y + img.height + MARGIN > A4_HEIGHT:
                page = create_page(current_page_images, A4_WIDTH, A4_HEIGHT, MARGIN)
                pdf_pages.append(page)
                current_page_images = []
                current_y = MARGIN

            current_page_images.append(img)
            current_y += img.height + MARGIN

            # Special rule for portrait images
            if img.height > img.width and img.height > A4_HEIGHT / 2:
                page = create_page(current_page_images, A4_WIDTH, A4_HEIGHT, MARGIN)
                pdf_pages.append(page)
                current_page_images = []
                current_y = MARGIN

            # Max images per page
            max_images = 2
            if len(current_page_images) >= 2 and all(i.height < 1000 for i in current_page_images):
                max_images = 3
            if len(current_page_images) >= max_images:
                page = create_page(current_page_images, A4_WIDTH, A4_HEIGHT, MARGIN)
                pdf_pages.append(page)
                current_page_images = []
                current_y = MARGIN

        # Add the last page
        if current_page_images:
            page = create_page(current_page_images, A4_WIDTH, A4_HEIGHT, MARGIN)
            pdf_pages.append(page)

        # Save to PDF in memory
        pdf_buffer = BytesIO()
        if pdf_pages:
            pdf_pages[0].save(
                pdf_buffer,
                format="PDF",
                save_all=True,
                append_images=pdf_pages[1:],
                quality=95
            )

        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="converted.pdf"
        )

    except OSError as e:
        logging.error(f"Disk space or I/O error: {e}")
        return jsonify({"error": "Server storage full. Please try again later or contact support."}), 507
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500



# -------------------- BACKGROUND REMOVAL --------------------
@app.route('/remove-bg', methods=['POST'])
@jwt_required(locations=["headers", "cookies"])
def remove_bg():
    try:
        img = Image.open(request.files['image'])
        out = remove(img)
        buffer = BytesIO()
        out.save(buffer, "PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype='image/png')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------- IMAGE CONVERTER --------------------

@app.route("/convert-image", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def convert_image():
    return handle_image_conversion(request)

# -------------------- FILE COMPRESSION --------------------
@app.route('/compress', methods=['POST'])
@jwt_required(locations=["headers", "cookies"])
def compress():
     return handle_compression(request)


# ── OBJECT REMOVAL ───────────────────────────────────────────────────────────
@app.route("/remove-object", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def remove_object():
    try:

        if "image" not in request.files or "mask" not in request.files:
            return jsonify({"error": "Both 'image' and 'mask' are required"}), 400

        t0 = time.perf_counter()

        buf = remove_object_service(
            request.files["image"],
            request.files["mask"],
            MAX_PX,
            refine_mask,
            lama_inpaint,
            log
        )

        elapsed = time.perf_counter() - t0
        log.info(f"[remove-object] ✓ done in {elapsed:.2f}s")

        return send_file(
            BytesIO(buf.tobytes()),
            mimetype="image/png",
            download_name="object-removed.png",
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    except MemoryError:
        return jsonify({"error": "Image too large — lower MAX_PX or add GPU"}), 500

    except Exception as e:
        log.error(f"[remove-object] {e}", exc_info=True)
        return jsonify({"error": "Server error"}), 500
 
# ── OCR ───────────────────────────────────────────────────────────────────────
@app.route("/ocr", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def ocr():

    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    return handle_ocr(
        request.files["image"],
        TESSERACT_AVAILABLE,
        log
    ) 
enable_compression(app) 
    

# -------------------- HELPERS --------------------


# -------------------- SHORTEN URL --------------------
url_shortner_model_initilizer(app)

@app.route("/shorten-url", methods=["POST", "OPTIONS"])
@jwt_required(locations=["headers", "cookies"])
def shorten_url():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    ip = get_client_ip()

    rate_error = _check_rate_limit(ip)
    if rate_error:
        return rate_error

    long_url, input_error = _extract_url_from_request()
    if input_error:
        return input_error

    security_error = _run_security_checks(long_url)
    if security_error:
        return security_error
    
    from services.url_shortner_service import _handle_shorten_db
    return _handle_shorten_db(long_url, ip)

@app.route("/shorten-progress", methods=["GET", "OPTIONS"])
@jwt_required(locations=["headers", "cookies"])
def shorten_progress():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    ip = get_client_ip()
    if is_rate_limited(ip):
        return _rate_limited_sse()

    url = request.args.get("url", "").strip()
    if not url:
        return _missing_url_sse()

    return _progress_stream_response(url, ip)




@app.route("/<code>")
def redirect_short_url(code):
    if not _is_valid_code(code):
        return jsonify({"error": "Invalid short code"}), 400

    try:
        record = _get_short_link(code)

        if not record:
            return jsonify({"error": "Short URL not found"}), 404

        if record.get("flagged"):
            return jsonify({
                "error": "This link has been flagged as unsafe and has been disabled."
            }), 403

        _increment_clicks(code)

        return redirect(record["original_url"])

    except Exception as e:
        app.logger.error(f"redirect error: {e}")
        return jsonify({"error": "Server error"}), 500
    

@app.route("/report/<code>", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def report_link(code):
    from services.url_shortner_service import _handle_report_link
    return _handle_report_link(code)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        app.static_folder,
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )
#---------------------NOICE REDUCTION-------------------

@app.route("/reduce-noise", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
@limiter.limit("5 per minute")
def reduce_noise():
   
    if "audio" not in request.files:
        return jsonify({
            "error": "No file uploaded. Use form-data key 'audio'.",
            "code": "MISSING_FILE"
        }), 400
    audio_file = request.files["audio"]

    preset = (
        request.form.get("preset") or
        request.form.get("quality") or
        DEFAULT_QUALITY
    ).strip().lower()
    
    
    return handle_reduce_noise( 
        audio_file,
        preset,
        validate_upload,
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        DEFAULT_QUALITY,
        PRESET_ALIAS,
        QUALITY_PROFILES,
        TEMP_DIR,
        verify_audio_stream,
        executor,
        process_audio,
        PIPELINE_TIMEOUT_SECONDS,
        cleanup_files,
        delete_file_later,
        logger
    )
noice_reduction_errors(app, MAX_FILE_SIZE_MB)



# after: app = Flask(__name__)


init_limiter(app, RATE_LIMIT, REDIS_URL)

@app.route("/enhance-image", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
@limiter.limit(RATE_LIMIT) if LIMITER_AVAILABLE else (lambda f: f)
def enhance_image():
    return handle_enhance_image(
        enhance,
        _decode_image,
        _encode_image,
        VALID_SCALES,
        OUTPUT_FORMAT,
        OUTPUT_QUALITY,
        MAX_PIXELS,
        MAX_QUEUE,
        _active_lock,
        log
    )
#error of image_enhancer
image_enhancer_error_handlers(app, log, MAX_UPLOAD_MB)

@app.route("/model-status", methods=["GET"])
def model_status():
    loaded = {
        f"{n}_x{s}": _model_cache.get((n, s)) is not None
        for n in ("LapSRN", "FSRCNN")
        for s in VALID_SCALES
    }
    best = {}
    for s in VALID_SCALES:
        for name in ("LapSRN", "FSRCNN"):
            if _model_cache.get((name, s)):
                best[f"x{s}"] = name
                break
        else:
            best[f"x{s}"] = "Lanczos"

    return jsonify({
        "ai_enabled":     any(loaded.values()),
        "models":         loaded,
        "best_per_scale": best,
        "compute":        COMPUTE_LABEL,
        "models_ready":   _model_ready.is_set(),
    }), 200



#pdf-image-edit
@app.route("/save-page-only-pdf/<file_id>/<int:page_index>", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def save_page_only_pdf(
    file_id,
    page_index
):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid file_id"
        }), 400

    return handle_save_page_only_pdf(
        file_id,
        page_index,
        request
    )


@app.route("/rebuild-pdf-only/<file_id>")
@jwt_required(locations=["headers", "cookies"])
def rebuild_pdf_only(file_id):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid file_id"
        }), 400

    return handle_rebuild_pdf_only(file_id)


@app.route("/restore-page/<file_id>/<int:page_index>",methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def restore_page(
    file_id,
    page_index
):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid file_id"
        }), 400

    return handle_restore_page(
        file_id,
        page_index
    )


@app.route("/cleanup/<file_id>", methods=["DELETE"])
@jwt_required(locations=["headers", "cookies"])
def cleanup(file_id):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid file_id"
        }), 400

    return handle_cleanup(file_id)


@app.route("/pdf-upload-file", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def pdf_upload_file():

    return handle_pdf_upload(
        file=request.files.get("file"),
        allowed_ext=ALLOWED_EXT,
        max_mb=MAX_FILE_MB,
        log=log,
    )


@app.route("/temp/<filename>")
@jwt_required(locations=["headers", "cookies"])
def temp_file(filename):

    resp, code = get_temp_file_response(
        filename
    )

    if resp is None:
        abort(code)

    return resp


@app.route("/get-pages-only-pdf/<file_id>")
@jwt_required(locations=["headers", "cookies"])
def get_pages_only_pdf(file_id):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid file_id"
        }), 400

    data, code = build_pages_only_pdf_response(
        file_id
    )

    return jsonify(data), code




@app.route("/inpaint", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def inpaint():

    try:

        data = request.get_json(
            force=True,
            silent=True
        ) or {}

        if not data.get("image"):
            return jsonify({
                "error": "No image"
            }), 400

        result, status = process_inpaint(data)

        return jsonify(result), status

    except Exception as e:

        log.exception("inpaint")

        return jsonify({
            "error": str(e)
        }), 500
        
        
@app.route("/analyze-style", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def analyze_style():

    try:

        data = request.get_json(
            force=True,
            silent=True
        ) or {}

        img_b64 = data.get("image")

        if not img_b64:
            return jsonify({
                "error": "No image"
            }), 400

        img = b64_to_cv2(img_b64)

        if img is None:
            return jsonify({
                "error": "Cannot decode"
            }), 400

        result = process_style_analysis(
            data,
            img
        )

        log.info(
            f"Style → bg:{result['bg_color']} "
            f"txt:{result['text_color']} "
            f"fs:{result['fs']} "
            f"bold:{result['bold']}"
        )

        return jsonify(result)

    except Exception as e:

        log.exception("analyze-style")

        return jsonify({
            "error": str(e)
        }), 500
        
        
from services.image_edit_service import (
     handle_upload_file , handle_get_pages , handle_save_page , handle_rebuild_pdf       
)    
#for image - eidt
@app.route("/upload-file", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def upload_file():

    return handle_upload_file(
        request.files.get("file")
    )


@app.route("/get-pages/<file_id>")
@jwt_required(locations=["headers", "cookies"])
def get_pages(file_id):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid"
        }), 400

    return handle_get_pages(file_id)


@app.route("/save-page/<file_id>/<int:page_index>", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def save_page(file_id, page_index):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid"
        }), 400

    return handle_save_page(
        file_id,
        page_index,
        request
    )


@app.route("/rebuild-pdf/<file_id>")
@jwt_required(locations=["headers", "cookies"])
def rebuild_pdf(file_id):

    if not safe_file_id(file_id):

        return jsonify({
            "error": "Invalid"
        }), 400

    return handle_rebuild_pdf(file_id)



#voice to text
try:
    from flask_compress import Compress
    _COMPRESS_AVAILABLE = True
except ImportError:
    _COMPRESS_AVAILABLE = False

os.makedirs(MODEL_DIR, exist_ok=True)
os.environ["HF_HOME"]               = MODEL_DIR
os.environ["HUGGINGFACE_HUB_CACHE"] = MODEL_DIR


app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024 

if _COMPRESS_AVAILABLE:
    Compress(app)          # gzip/br JSON responses automatically
    logging.info("Flask-Compress enabled — responses will be gzip-compressed.")


@app.route("/voice-to-text", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
def voice_to_text():

    rate_limit_response = check_voice_rate_limit()
    if rate_limit_response:
        return rate_limit_response

    file, error = validate_audio_upload()
    if error:
        return error

    raw_language = request.form.get(
        "language",
        ""
    ).strip()

    logging.info(
        f"[language] raw value from form: '{raw_language}'"
    )

    language = parse_language(
        raw_language
    )

    audio_bytes, cache_key, t0, error = process_audio_input(
        file,
        language
    )

    if error:
        return error

    if not _FFMPEG_AVAILABLE:
        return jsonify({
            "error": "FFmpeg not installed or not in PATH."
        }), 500

    input_path = None
    wav_path = None

    try:
        input_path, wav_path, ffmpeg_ms = convert_audio_to_wav(
            audio_bytes
        )

        text, info, whisper_s = transcribe_audio(
            wav_path,
            language,
            file.filename
        )

        resp = build_transcription_response(
            text,
            info,
            language,
            cache_key,
            t0,
            ffmpeg_ms,
            whisper_s
        )

        return resp, 200

    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Audio processing timeout."
        }), 500

    except Exception:
        logging.exception(
            "Voice-to-text error"
        )
        return jsonify({
            "error": "Internal server error."
        }), 500

    finally:
        for path in (input_path, wav_path):
            try:
                if path:
                    os.remove(path)
            except OSError:
                pass


# Home Page
@app.route("/")
def home():
    return render_template("index.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/tools")
@page_login_required
def tools():
    return render_template("tools.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/pricing")
def pricing():
    return render_template("pricing.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/api/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    current_password = data.get("current_password")
    new_password     = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"error": "Both current and new password are required"}), 400

    if not is_strong_password(new_password):
        return jsonify({
            "error": "New password must be 8+ chars with upper, lower, number & symbol"
        }), 400

    db  = get_db()
    cur = db.cursor()

    cur.execute("SELECT password FROM users WHERE id=%s", (user_id,))
    row = cur.fetchone()

    if not row or not verify_password(current_password, row["password"]):
        cur.close()
        db.close()
        return jsonify({"error": "Current password is incorrect"}), 401

    cur.execute(
        "UPDATE users SET password=%s WHERE id=%s",
        (hash_password(new_password), user_id)
    )
    db.commit()
    cur.close()
    db.close()

    return jsonify({"message": "Password updated successfully"}), 200


# Contact Page
@app.route("/contact")
@page_login_required
def contact():
    return render_template("contact.html", FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/image-edit-uploader")
@page_login_required
def image_edit_uploader():
    return render_template("image-editor-upload.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/pdf-edit-uploader")
@page_login_required
def pdf_edit_uploader():
    return render_template("pdf-editor-upload.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/bac-rem-tool")
@page_login_required
def bac_rem_tool():
    return render_template("bac-rem-tool.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))




@app.route("/file-compression")
@page_login_required
def file_compression():
    return render_template("file-compression.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/image-converter")
@page_login_required
def image_converter():
    return render_template("image-converter.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/image-enhancement")
@page_login_required
def image_enhancement():
    return render_template("image-enhancement.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/image-to-text")
@page_login_required
def image_to_text():
    return render_template("image-to-text.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/img-to-pdf")
@page_login_required
def img_to_pdf():
    return render_template("img-to-pdf.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))



@app.route("/noice-reduction")
@page_login_required
def noice_reduction():
    return render_template("noice-reduction.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/object-remover")
@page_login_required
def object_remover():
    return render_template("object-remover.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/pdf-to-document")
@page_login_required
def pdf_to_document():
    return render_template("pdf-to-doc.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/url-shortner")
@page_login_required
def url_shortner():
    return render_template("url-shortner.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))

@app.route("/voice-to-text_page")
@page_login_required
def voice_to_text_page():
    return render_template("voice-to-text.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/edit-pdf-page")
@page_login_required
def edit_pdf_page():
    return render_template("edit-pdf.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


@app.route("/edit-image-page")
@page_login_required
def edit_image_page():
    return render_template("for-image-edit.html" , FRONTEND_URL=os.getenv("FRONTEND_URL"))


       
# ── Contact form API ─────────────────────────────────────────────────────────
import re as _re

def _is_valid_email_contact(email):
      if not isinstance(email, str): return False
      return bool(_re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+.[a-zA-Z0-9-.]+$", email.strip())) and len(email) <= 255


@app.route("/api/contact", methods=["POST"])
@limiter.limit("3 per minute; 10 per hour")
def api_contact():
    """Receive contact form submission and email it to MAIL_USERNAME."""
    try:
        data    = request.get_json(silent=True) or {}
        name    = str(data.get("name",    "") or "").strip()
        email   = str(data.get("email",   "") or "").strip()
        message = str(data.get("message", "") or "").strip()

        if not all([name, email, message]):
            return jsonify({"error": "Name, email and message are all required"}), 400
        if not _is_valid_email_contact(email):
            return jsonify({"error": "Please enter a valid email address"}), 400
        if len(name) > 120:
            return jsonify({"error": "Name is too long"}), 400
        if len(message) > 5000:
            return jsonify({"error": "Message is too long (max 5 000 characters)"}), 400

        recipient = app.config.get("MAIL_USERNAME")
        if not recipient:
            log.error("MAIL_USERNAME not configured — cannot send contact email")
            return jsonify({"error": "Mail not configured on the server"}), 500

        from services.email_template import contact_email as _contact_email
        html_body = _contact_email(name=name, email=email, message=message)

        msg = Message(
              subject=f"Flarixo AI Query From {name}",
              recipients=[recipient],
              reply_to=email,
              html=html_body,
              body=f"From: {name} <{email}>\n\n{message}",
        )
        mail.send(msg)

        log.info("Contact email sent from %s <%s>", name, email)
        return jsonify({"message": "Your message has been sent! We will get back to you soon."}), 200

    except Exception:
        log.exception("Contact form error")
        return jsonify({"error": "Failed to send message. Please try again later."}), 500

# new

# ──────────────────────────────────────────────────────────────────────────
import requests
from urllib.parse import urlparse
import ipaddress
import socket


ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/gif", "image/bmp", "image/avif",
}
MAX_FETCH_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB, matches your upload UI copy


def _is_safe_public_url(url: str) -> bool:
    """
    Basic SSRF guard: block localhost / private / link-local IP ranges so the
    server can't be tricked into fetching internal services (e.g.
    http://127.0.0.1:5000/admin or http://169.254.169.254/ for cloud metadata).
    Not bulletproof (DNS rebinding etc.) but blocks the common cases.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False

        # Resolve hostname to IP and check it's not private/loopback/link-local
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except Exception:
        return False


#  ──────────────────────────────────────────────────────────────────────────
#  Add this route next to your existing /remove-bg route in app.py
#  ──────────────────────────────────────────────────────────────────────────
@app.route("/fetch-image-url", methods=["POST"])
@jwt_required(locations=["headers", "cookies"])
@limiter.limit("20 per hour")
def fetch_image_url():
    """
    Downloads an image from a remote URL server-side (bypassing browser CORS
    restrictions that block sites like Vecteezy/Unsplash/etc. from being
    fetched directly by client-side JS), validates it's actually an image,
    and returns the raw image bytes back to the frontend. The frontend then
    sends those bytes to /remove-bg exactly like a normal file upload.
    """
    try:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        if not _is_safe_public_url(url):
            return jsonify({"error": "That URL isn't allowed"}), 400

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=20,
                stream=True,
                allow_redirects=True,
            )
        except requests.exceptions.Timeout:
            return jsonify({"error": "The image took too long to load"}), 504
        except requests.exceptions.RequestException:
            return jsonify({"error": "Could not reach that URL"}), 502

        if resp.status_code != 200:
            return jsonify({"error": f"That URL returned status {resp.status_code}"}), 502

        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            return jsonify({
                "error": "That URL doesn't point to a supported image "
                         "(it returned: " + (content_type or "unknown") + ")"
            }), 415

        # Stream with a hard size cap to avoid memory blowups on huge files
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > MAX_FETCH_IMAGE_BYTES:
                return jsonify({"error": "Image exceeds the 20 MB limit"}), 413
            chunks.append(chunk)

        image_bytes = b"".join(chunks)
        if not image_bytes:
            return jsonify({"error": "The URL returned an empty response"}), 502

        # Validate it's actually a decodable image (catches mislabeled content-types)
        try:
            Image.open(BytesIO(image_bytes)).verify()
        except UnidentifiedImageError:
            return jsonify({"error": "The URL did not return a valid image"}), 415
        except Exception:
            return jsonify({"error": "The URL did not return a valid image"}), 415

        ext = content_type.split("/")[1].split("+")[0]
        buffer = BytesIO(image_bytes)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype=content_type,
            as_attachment=False,
            download_name=f"url-image.{ext}",
        )

    except Exception as e:
        log.exception("fetch-image-url")
        return jsonify({"error": "Server error while fetching the image"}), 500

try:
    cleanup_expired_tokens()
    prepare_model()
    check_ffmpeg()
    start_temp_cleanup()
    print(" Startup initialization completed.")
except Exception as e:
    print(f" Startup initialization failed: {e}")
    
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        use_reloader=False,
        threaded=True
    )
    




