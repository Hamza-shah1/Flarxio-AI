import os
from dotenv import load_dotenv
import pytesseract
import os
import logging

    
load_dotenv()



# ── Rate limiting ─────────────────────────────────────────────────────────────

# ── Rate limiting ─────────────────────────────────────────────────────────────
RATE_RPS: float = float(os.environ.get("RATE_RPS", "2"))
RATE_BURST: int = int(os.environ.get("RATE_BURST", "5"))

# ── API key auth (optional – leave API_KEYS empty to disable) ─────────────────
_raw_keys = os.environ.get("API_KEYS", "")

# new
VALID_API_KEYS: frozenset[str] = (
    frozenset(k.strip() for k in _raw_keys.split(",") if k.strip())
    if _raw_keys
    else frozenset()
)
AUTH_ENABLED: bool = bool(VALID_API_KEYS)


# new
# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL", "86400"))
CACHE_KEY_PREFIX: str = "vtt:cache:"



# ── Task polling ──────────────────────────────────────────────────────────────
# How long /result/<id> will wait for a finished result before returning 202
POLL_TIMEOUT_S: float = float(os.environ.get("POLL_TIMEOUT_S", "0.5"))

# ── Supported audio extensions ────────────────────────────────────────────────
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {"mp3", "wav", "ogg", "webm", "m4a", "flac", "aac", "aiff"}
)

# ── Supported languages ───────────────────────────────────────────────────────
SUPPORTED_LANGUAGES: frozenset[str] = frozenset([
    "af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs",
    "cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu",
    "ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka",
    "kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml",
    "mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt",
    "ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw",
    "ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo",
    "zh","yue",
])

# ── FFmpeg audio filter chain ─────────────────────────────────────────────────
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

# ── Whisper transcription defaults ────────────────────────────────────────────
TRANSCRIBE_PARAMS_BASE: dict = dict(
    beam_size                   = 5,
    patience                    = 1.0,
    temperature                 = [0.0, 0.2, 0.4],
    vad_filter                  = True,
    vad_parameters              = dict(
        min_silence_duration_ms = 300,
        speech_pad_ms           = 80,
    ),
    condition_on_previous_text  = False,
    initial_prompt              = None,
    word_timestamps             = False,
    compression_ratio_threshold = 2.4,
    log_prob_threshold          = -0.6,
    no_speech_threshold         = 0.6,
)



# Base directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


#------------------Url Shortner--------------------------
BASE_URL                     = os.getenv("BASE_URL", "").rstrip("/")
GOOGLE_SAFE_BROWSING_API_KEY = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY", "")
WHOISXML_API_KEY             = os.getenv("WHOISXML_API_KEY", "")
#--------------------------------------------------------



#------------------for image enhancer----------------


MODEL_DIR = os.path.join(BASE_DIR, "models")
#------------------model cb.nnn for noice reduction
RNNOISE_DIR = os.path.join(BASE_DIR, "models", "rnnoise")
# Path to the RNNoise model
MODEL_PATH = os.path.join(RNNOISE_DIR, "cb.rnnn")
SAFE_MODEL_DIR = RNNOISE_DIR
SAFE_MODEL_PATH = os.path.join(SAFE_MODEL_DIR, "cb.rnnn")

# -------------------- TEMP DIRECTORY --------------------
TEMP_DIR = os.path.join(BASE_DIR, "temp")
# Make sure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


import shutil
import sys

# Smart FFmpeg path — works on Windows locally AND Linux on server
if sys.platform == "win32":
    # Your local Windows path
    _LOCAL_FFMPEG = os.path.join(BASE_DIR, "models", "ffmpeg", "bin", "ffmpeg.exe")
    FFMPEG_PATH = _LOCAL_FFMPEG if os.path.exists(_LOCAL_FFMPEG) else shutil.which("ffmpeg")
else:
    # On Linux server — use system ffmpeg
    FFMPEG_PATH = shutil.which("ffmpeg")

if not FFMPEG_PATH:
    logging.warning("FFmpeg not found!")
    
    
    
# # -------------------- FFMPEG PATH --------------------
# FFMPEG_PATH = os.path.join(
#     BASE_DIR,
#     "models",
#     "ffmpeg",
#     "bin",
#     "ffmpeg.exe"
# )

# -------------------- MAX UPLOAD SIZE --------------------
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

# -------------------- TESSERACT --------------------
import shutil
import sys

# Smart Tesseract path
if sys.platform == "win32":
    _LOCAL_TESSERACT = os.path.join(BASE_DIR, "instance", "tesseract.exe")
    TESSERACT_PATH = _LOCAL_TESSERACT if os.path.exists(_LOCAL_TESSERACT) else shutil.which("tesseract")
else:
    TESSERACT_PATH = shutil.which("tesseract")  # Linux server path

# Apply to pytesseract
if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    try:
        pytesseract.get_tesseract_version()
        TESSERACT_AVAILABLE = True
        logging.info("Tesseract detected and ready")
    except Exception as e:
        TESSERACT_AVAILABLE = False
        logging.error(f"Tesseract error: {e}")
else:
    TESSERACT_AVAILABLE = False
    logging.warning("Tesseract executable not found")

# TESSERACT_PATH = os.path.join(BASE_DIR, "instance", "tesseract.exe")
# pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# if os.path.exists(TESSERACT_PATH):
#     pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
#     try:
#         pytesseract.get_tesseract_version()
#         TESSERACT_AVAILABLE = True
#         logging.info("Tesseract detected and ready")
#     except Exception as e:
#         TESSERACT_AVAILABLE = False
#         logging.error(f"Tesseract error: {e}")
# else:
#     TESSERACT_AVAILABLE = False
#     logging.warning("Tesseract executable not found")
    
#----------Object remover related----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("app")   


class Config:
    # NEVER hardcode secrets – always use environment variables
    SECRET_KEY: str = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is not set. Refusing to start.")

    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY environment variable is not set. Refusing to start.")

    SQLALCHEMY_DATABASE_URI: str = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:"
        f"{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '3306')}/"
        f"{os.getenv('DB_NAME')}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000').split(',')
    API_KEY = os.environ.get('API_KEY', 'your-api-key-here')  # For auth
    #VOSK_MODEL_PATH = os.environ.get('VOSK_MODEL_PATH', './models/vosk-model-small-en-us-0.15')
    ESPCN_MODEL_PATH = os.environ.get('ESPCN_MODEL_PATH', './models/ESPCN_x4.pb')
    #TTS_MODEL_NAME = os.environ.get('TTS_MODEL_NAME', 'tts_models/en/vctk/vits')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    
    
    
    
    
# [phases.setup]
# nixPkgs = ["ffmpeg", "tesseract"]