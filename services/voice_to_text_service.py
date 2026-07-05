from utils.voice_to_text_utils import cache_get , hash_bytes , cache_put , allowed_file
import logging
from flask import request, jsonify
from config import RATE_BURST , TEMP_DIR
import time
import uuid 
import subprocess
from models.voice_to_text_model import collect_segments , build_ffmpeg_cmd_to_file , _BASE_ITEMS ,  _check_rate_limit 
import os
from faster_whisper import WhisperModel

    
# ════════════════════════════════════════════════════════════════════════════════
# MODEL LOAD
# ════════════════════════════════════════════════════════════════════════════════
logging.info("Loading faster-whisper 'medium' model (CPU, int8)…")
whisper_model = WhisperModel(
    "medium",
    device       = "cpu",
    compute_type = "int8",
    cpu_threads  = os.cpu_count(),
    num_workers  = 1,
)
logging.info("Whisper model loaded.")



def check_voice_rate_limit():
    allowed, retry_after = _check_rate_limit()

    if not allowed:
        retry_secs = round(retry_after, 1)

        logging.warning(
            f"[rate-limit] IP {request.remote_addr} throttled "
            f"— retry in {retry_secs}s"
        )

        response = jsonify({
            "error": "Too many requests. Please slow down.",
            "retry_after": retry_secs,
        })

        response.status_code = 429
        response.headers["Retry-After"] = str(retry_secs)
        response.headers["X-RateLimit-Limit"] = str(RATE_BURST)

        return response

    return None



def validate_audio_upload():
    if "audio" not in request.files:
        return None, (
            jsonify({
                "error": "No audio file provided (use field name 'audio')."
            }),
            400
        )

    file = request.files["audio"]

    if not file.filename:
        return None, (
            jsonify({"error": "Empty filename."}),
            400
        )

    if not allowed_file(file.filename):
        return None, (
            jsonify({"error": "Unsupported file type."}),
            400
        )

    return file, None



def process_audio_input(file, language):
    t0 = time.perf_counter()

    audio_bytes = file.read()

    if not audio_bytes:
        return None, None, None, (
            jsonify({"error": "Uploaded file is empty."}),
            400
        )

    if len(audio_bytes) > 25 * 1024 * 1024:
        return None, None, None, (
            jsonify({"error": "File exceeds 25 MB limit."}),
            400
        )

    audio_hash = hash_bytes(audio_bytes)
    cache_key = f"{audio_hash}:{language or 'auto'}"

    cached = cache_get(cache_key)

    if cached:
        logging.info(
            f"Cache HIT [{audio_hash[:8]}|lang={language or 'auto'}] "
            f"— {(time.perf_counter() - t0) * 1000:.0f}ms"
        )

        return None, None, None, (jsonify(cached), 200)

    return audio_bytes, cache_key, t0, None



def convert_audio_to_wav(audio_bytes):
    uid = uuid.uuid4().hex

    input_path = os.path.join(
        TEMP_DIR,
        f"input_{uid}"
    )

    wav_path = os.path.join(
        TEMP_DIR,
        f"converted_{uid}.wav"
    )

    with open(input_path, "wb") as fh:
        fh.write(audio_bytes)

    del audio_bytes

    t_ffmpeg = time.perf_counter()

    result = subprocess.run(
        build_ffmpeg_cmd_to_file(
            input_path,
            wav_path
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )

    ffmpeg_ms = (
        time.perf_counter() - t_ffmpeg
    ) * 1000

    logging.info(
        f"FFmpeg done in {ffmpeg_ms:.0f}ms"
    )

    if result.returncode != 0:
        logging.error(
            result.stderr.decode(errors="ignore")
        )
        raise RuntimeError("Audio conversion failed.")

    if not os.path.exists(wav_path):
        raise RuntimeError("WAV file creation failed.")

    return input_path, wav_path, ffmpeg_ms



def transcribe_audio(
    wav_path,
    language,
    filename
):
    transcribe_params = dict(_BASE_ITEMS)
    transcribe_params["language"] = language

    logging.info(
        f"Transcribing | "
        f"lang={'auto' if language is None else language} | "
        f"file={filename}"
    )

    t_whisper = time.perf_counter()

    segments, info = whisper_model.transcribe(
        wav_path,
        **transcribe_params
    )

    text = collect_segments(segments)

    whisper_s = (
        time.perf_counter() - t_whisper
    )

    logging.info(
        f"Whisper {whisper_s:.1f}s | "
        f"detected={info.language} "
        f"({info.language_probability:.0%}) | "
        f"duration={info.duration:.1f}s | "
        f"RTF={whisper_s / max(info.duration, 1):.2f}x"
    )

    return text, info, whisper_s




def build_transcription_response(
    text,
    info,
    language,
    cache_key,
    t0,
    ffmpeg_ms,
    whisper_s
):
    response_body = {
        "text": text,
        "language": info.language,
        "language_probability": round(
            info.language_probability,
            3
        ),
        "language_requested": (
            language or "auto"
        ),
    }

    cache_put(
        cache_key,
        response_body
    )

    total_s = (
        time.perf_counter() - t0
    )

    logging.info(
        f"Total {total_s:.2f}s "
        f"(ffmpeg={ffmpeg_ms:.0f}ms, "
        f"whisper={whisper_s:.1f}s)"
    )

    resp = jsonify(response_body)

    resp.headers[
        "X-Processing-Time"
    ] = f"{total_s:.3f}s"

    return resp