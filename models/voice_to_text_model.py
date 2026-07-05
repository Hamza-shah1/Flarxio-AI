from config import _FFMPEG_FILTER , FFMPEG_PATH
import logging
import os
import shutil
from utils.voice_to_text_utils import _RateLimiterStore
from flask import Flask, request


_rate_store = _RateLimiterStore()


def _check_rate_limit() -> tuple[bool, float]:
    """Return (allowed, retry_after_seconds) for the current request's IP."""
    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )
    return _rate_store.get_bucket(ip).consume()

# ════════════════════════════════════════════════════════════════════════════════
# SUPPORTED LANGUAGES
# ════════════════════════════════════════════════════════════════════════════════
SUPPORTED_LANGUAGES = frozenset([
    "af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs",
    "cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu",
    "ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka",
    "kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml",
    "mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt",
    "ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw",
    "ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo",
    "zh","yue",
])



# ════════════════════════════════════════════════════════════════════════════════
# SEGMENT COLLECTION  (performance: pre-size list, skip empty early)
# ════════════════════════════════════════════════════════════════════════════════
def collect_segments(segments_generator) -> str:
    buf: list[str] = []
    for seg in segments_generator:
        t = seg.text
        if t:
            s = t.strip()
            if s:
                buf.append(s)
    return " ".join(buf)



    

def build_ffmpeg_cmd_to_file(input_path: str, wav_path: str) -> list[str]:
    """Standard ffmpeg → WAV file (reliable for all formats)."""
    return [
        FFMPEG_PATH, "-y",
        "-i",          input_path,
        "-af",         _FFMPEG_FILTER,
        "-ar",         "16000",
        "-ac",         "1",
        "-sample_fmt", "s16",
        wav_path,
    ]
    

# ════════════════════════════════════════════════════════════════════════════════
# TRANSCRIPTION PARAMS  (built once; shallow-copied per request)
# ════════════════════════════════════════════════════════════════════════════════
_TRANSCRIBE_PARAMS_BASE: dict = dict(
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

_BASE_ITEMS: tuple = tuple(_TRANSCRIBE_PARAMS_BASE.items())
    
    
    
# ════════════════════════════════════════════════════════════════════════════════
# STARTUP CHECKS
# ════════════════════════════════════════════════════════════════════════════════
_FFMPEG_AVAILABLE: bool = os.path.isfile(FFMPEG_PATH) or shutil.which(FFMPEG_PATH) is not None
if not _FFMPEG_AVAILABLE:
    logging.warning(
        f"FFmpeg not found at '{FFMPEG_PATH}'. "
        "All transcription requests will fail until it is installed."
    )
    



def parse_language(raw: str | None) -> str | None:
    if not raw:
        return None
    code = raw.strip().lower()
    if code in ("", "auto", "null", "none"):
        return None
    if code in SUPPORTED_LANGUAGES:
        logging.info(f"[language] accepted: '{code}'")
        return code
    logging.warning(f"[language] unrecognised code '{raw}' — falling back to auto-detect.")
    return None