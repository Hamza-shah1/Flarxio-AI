"""
═══════════════════════════════════════════════════════════════════════════════
FLARXIO-AI: PRODUCTION CONFIG FOR LINUX/RAILWAY DEPLOYMENT
═══════════════════════════════════════════════════════════════════════════════
Last Updated: 2024
Compatible with: Python 3.9+, Linux (Ubuntu/Debian), Railway, Docker
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import shutil
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("app")

# ═══════════════════════════════════════════════════════════════════════════════
# 1. RATE LIMITING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
RATE_RPS: float = float(os.environ.get("RATE_RPS", "2"))
RATE_BURST: int = int(os.environ.get("RATE_BURST", "5"))

# ═══════════════════════════════════════════════════════════════════════════════
# 2. API KEY AUTHENTICATION (OPTIONAL)
# ═══════════════════════════════════════════════════════════════════════════════
_raw_keys = os.environ.get("API_KEYS", "")
VALID_API_KEYS: frozenset[str] = (
    frozenset(k.strip() for k in _raw_keys.split(",") if k.strip())
    if _raw_keys
    else frozenset()
)
AUTH_ENABLED: bool = bool(VALID_API_KEYS)

# ═══════════════════════════════════════════════════════════════════════════════
# 3. CACHE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL", "86400"))
CACHE_KEY_PREFIX: str = "vtt:cache:"

# ═══════════════════════════════════════════════════════════════════════════════
# 4. TASK POLLING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
# How long /result/<id> will wait for a finished result before returning 202
POLL_TIMEOUT_S: float = float(os.environ.get("POLL_TIMEOUT_S", "0.5"))

# ═══════════════════════════════════════════════════════════════════════════════
# 5. SUPPORTED AUDIO EXTENSIONS
# ═══════════════════════════════════════════════════════════════════════════════
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {"mp3", "wav", "ogg", "webm", "m4a", "flac", "aac", "aiff"}
)

# ═══════════════════════════════════════════════════════════════════════════════
# 6. SUPPORTED LANGUAGES FOR TRANSCRIPTION
# ═══════════════════════════════════════════════════════════════════════════════
SUPPORTED_LANGUAGES: frozenset[str] = frozenset([
    "af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca", "cs",
    "cy", "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr", "gl", "gu",
    "ha", "haw", "he", "hi", "hr", "ht", "hu", "hy", "id", "is", "it", "ja", "jw", "ka",
    "kk", "km", "kn", "ko", "la", "lb", "ln", "lo", "lt", "lv", "mg", "mi", "mk", "ml",
    "mn", "mr", "ms", "mt", "my", "ne", "nl", "nn", "no", "oc", "pa", "pl", "ps", "pt",
    "ro", "ru", "sa", "sd", "si", "sk", "sl", "sn", "so", "sq", "sr", "su", "sv", "sw",
    "ta", "te", "tg", "th", "tk", "tl", "tr", "tt", "uk", "ur", "uz", "vi", "yi", "yo",
    "zh", "yue",
])

# ═══════════════════════════════════════════════════════════════════════════════
# 7. FFMPEG AUDIO FILTER CHAIN
# ═══════════════════════════════════════════════════════════════════════════════
# Used for audio preprocessing and quality enhancement
_FFMPEG_FILTER: str = (
    "afftdn=nf=-25,"
    "highpass=f=80,"
    "lowpass=f=8000,"
    "loudnorm=I=-16:TP=-1:LRA=11,"
    "silenceremove=start_periods=1:start_silence=0:start_threshold=-45dB,"
    "areverse,"
    "silenceremove=start_periods=1:start_silence=0:start_threshold=-45dB,"
    "areverse"
)

# ═══════════════════════════════════════════════════════════════════════════════
# 8. WHISPER TRANSCRIPTION PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════════
TRANSCRIBE_PARAMS_BASE: dict = dict(
    beam_size=5,
    patience=1.0,
    temperature=[0.0, 0.2, 0.4],
    vad_filter=True,
    vad_parameters=dict(
        min_silence_duration_ms=300,
        speech_pad_ms=80,
    ),
    condition_on_previous_text=False,
    initial_prompt=None,
    word_timestamps=False,
    compression_ratio_threshold=2.4,
    log_prob_threshold=-0.6,
    no_speech_threshold=0.6,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 9. DIRECTORY CONFIGURATION
# ══════════════════════════════��════════════════════════════════════════════════
# Base directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Models directory (for AI models, Whisper, image enhancers, etc.)
MODEL_DIR = os.path.join(BASE_DIR, "models")

# RNNoise model directory (for noise reduction)
RNNOISE_DIR = os.path.join(BASE_DIR, "models", "rnnoise")
MODEL_PATH = os.path.join(RNNOISE_DIR, "cb.rnnn")
SAFE_MODEL_DIR = RNNOISE_DIR
SAFE_MODEL_PATH = os.path.join(SAFE_MODEL_DIR, "cb.rnnn")

# Temporary directory (for file uploads, conversions, etc.)
TEMP_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(RNNOISE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 10. REDIS CONFIGURATION (For caching and rate limiting)
# ═══════════════════════════════════════════════════════════════════════════════
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ═══════════════════════════════════════════════════════════════════════════════
# 11. URL SHORTENER CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
GOOGLE_SAFE_BROWSING_API_KEY = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY", "")
WHOISXML_API_KEY = os.getenv("WHOISXML_API_KEY", "")

# ═══════════════════════════════════════════════════════════════════════════════
# 12. FFMPEG PATH DETECTION (Smart Detection for Windows/Linux)
# ═══════════════════════════════════════════════════════════════════════════════
"""
PRODUCTION-READY FFMPEG DETECTION:
- On Linux (Railway, Docker): Uses system FFmpeg from apt-get install ffmpeg
- On Windows (local dev): Looks for bundled FFmpeg in models/ffmpeg/bin/
"""
if sys.platform == "win32":
    # Windows: Look for bundled FFmpeg first, then system FFmpeg
    _LOCAL_FFMPEG = os.path.join(BASE_DIR, "models", "ffmpeg", "bin", "ffmpeg.exe")
    FFMPEG_PATH = _LOCAL_FFMPEG if os.path.exists(_LOCAL_FFMPEG) else shutil.which("ffmpeg")
else:
    # Linux (Railway, Docker): Use system FFmpeg only
    FFMPEG_PATH = shutil.which("ffmpeg")

if not FFMPEG_PATH:
    log.warning(
        "⚠️  FFmpeg NOT FOUND! "
        "Audio/video features will fail. "
        "Fix: apt-get install ffmpeg (Linux) or download FFmpeg (Windows)"
    )
else:
    log.info(f"✓ FFmpeg detected at: {FFMPEG_PATH}")

# ═══════════════════════════════════════════════════════════════════════════════
# 13. TESSERACT PATH DETECTION (Smart Detection for Windows/Linux)
# ═══════════════════════════════════════════════════════════════════════════════
"""
PRODUCTION-READY TESSERACT DETECTION:
- On Linux (Railway, Docker): Uses system Tesseract from apt-get install tesseract-ocr
- On Windows (local dev): Looks for bundled Tesseract in instance/
"""
import pytesseract

if sys.platform == "win32":
    # Windows: Look for bundled Tesseract first, then system Tesseract
    _LOCAL_TESSERACT = os.path.join(BASE_DIR, "instance", "tesseract.exe")
    TESSERACT_PATH = _LOCAL_TESSERACT if os.path.exists(_LOCAL_TESSERACT) else shutil.which("tesseract")
else:
    # Linux (Railway, Docker): Use system Tesseract only
    TESSERACT_PATH = shutil.which("tesseract")

# Apply Tesseract path to pytesseract and test availability
TESSERACT_AVAILABLE = False
if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    try:
        pytesseract.get_tesseract_version()
        TESSERACT_AVAILABLE = True
        log.info(f"✓ Tesseract OCR detected at: {TESSERACT_PATH}")
    except Exception as e:
        TESSERACT_AVAILABLE = False
        log.error(f"✗ Tesseract error: {e}")
else:
    TESSERACT_AVAILABLE = False
    log.warning(
        "⚠️  Tesseract OCR NOT FOUND! "
        "OCR features will be unavailable. "
        "Fix: apt-get install tesseract-ocr (Linux) or download Tesseract (Windows)"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 14. HUGGINGFACE MODEL CACHE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
# Point Hugging Face to models directory to avoid re-downloading on each startup
os.environ["HF_HOME"] = MODEL_DIR
os.environ["HUGGINGFACE_HUB_CACHE"] = MODEL_DIR

# ═══════════════════════════════════════════════════════════════════════════════
# 15. UPLOAD SIZE LIMITS
# ═══════════════════════════════════════════════════════════════════════════════
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload size

# ═══════════════════════════════════════════════════════════════════════════════
# 16. FLASK APPLICATION CONFIGURATION CLASS
# ═══════════════════════════════════════════════════════════════════════════════
class Config:
    """
    Flask application configuration.
    All secrets are loaded from environment variables (never hardcoded).
    """

    # ─── SECURITY ───────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "❌ CRITICAL: SECRET_KEY environment variable is not set. "
            "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )

    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "❌ CRITICAL: JWT_SECRET_KEY environment variable is not set. "
            "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )

    # ─── DATABASE ───────────────────────────────────────────────────────────
    # MySQL connection string (uses pymysql driver)
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "flarxio_db")

    SQLALCHEMY_DATABASE_URI: str = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ─── FILE UPLOAD ────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

    # ─── CORS ───────────────────────────────────────────────────────────────
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

    # ─── API AUTHENTICATION ─────────────────────────────────────────────────
    API_KEY = os.environ.get("API_KEY", "your-api-key-here")

    # ─── LOGGING ─────────────────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    # ─── ESPCN MODEL PATH (Image Enhancement) ───────────────────────────────
    ESPCN_MODEL_PATH = os.environ.get("ESPCN_MODEL_PATH", "./models/ESPCN_x4.pb")


# ═══════════════════════════════════════════════════════════════════════════════
# 17. ENVIRONMENT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
def validate_production_config():
    """
    Validate that all critical environment variables are set for production.
    Called on app startup.
    """
    required_vars = [
        "SECRET_KEY",
        "JWT_SECRET_KEY",
        "DB_HOST",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
    ]

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        log.error(
            f"❌ Missing critical environment variables: {', '.join(missing)}"
        )
        return False

    log.info("✓ All critical environment variables are set")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 18. DEPLOYMENT INFORMATION
# ═══════════════════════════════════════════════════════════════════════════════
"""
DEPLOYMENT CHECKLIST:

✓ config.py Loaded Successfully

Before deploying to Railway:

1. Database Setup:
   - Create MySQL database instance on Railway
   - Copy credentials to .env: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

2. Security Keys:
   - Generate SECRET_KEY and JWT_SECRET_KEY
   - Run: python -c 'import secrets; print(secrets.token_hex(32))'
   - Add to .env file

3. System Dependencies:
   - FFmpeg: apt-get install ffmpeg
   - Tesseract: apt-get install tesseract-ocr
   - Libraries: libsndfile1, libsm6, libxext6, libxrender-dev

4. Environment Variables (.env):
   FLASK_ENV=production
   FLASK_DEBUG=false
   SECRET_KEY=<generated>
   JWT_SECRET_KEY=<generated>
   DB_HOST=<railway-mysql-host>
   DB_USER=root
   DB_PASSWORD=<password>
   DB_NAME=flarxio_db
   FRONTEND_URL=https://your-domain.com
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=<app-password>

5. Deploy:
   - Push to GitHub
   - Railway auto-deploys on push
   - Monitor logs: railway logs

TROUBLESHOOTING:

- FFmpeg not found: Install with apt-get in Dockerfile
- Tesseract not found: Install with apt-get in Dockerfile
- Database connection failed: Check DB_HOST, DB_USER, DB_PASSWORD
- Import errors: Ensure all packages in requirements.txt are installed
- Port issues: Railway automatically assigns PORT env variable
"""
