from utils.audio_utils import  MAX_FILE_SIZE_BYTES , MAX_CONCURRENT_JOBS  , MAX_FILE_SIZE_MB  
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import uuid
from flask import jsonify, send_file, after_this_request
from concurrent.futures import TimeoutError as FuturesTimeoutError


def handle_reduce_noise(
    file,
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
):

    valid, err = validate_upload(file)
    if not valid:
        return jsonify({"error": err, "code": "INVALID_FILE"}), 400

    # file size check
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE_BYTES:
        return jsonify({
            "error": f"File exceeds {MAX_FILE_SIZE_MB}MB ({file_size/1024/1024:.1f}MB received).",
            "code": "FILE_TOO_LARGE"
        }), 413
    raw = (preset or DEFAULT_QUALITY).strip().lower()
    resolved = PRESET_ALIAS.get(raw)

    if not resolved:
        return jsonify({
            "error": f"Invalid preset '{raw}'. Use: light, normal, strong.",
            "code": "INVALID_QUALITY"
        }), 400

    profile = QUALITY_PROFILES[resolved]
    logger.info(f"Preset '{raw}' → '{resolved}'")

    ext = os.path.splitext(file.filename)[1].lower() or ".bin"
    uid = str(uuid.uuid4())

    input_path = os.path.join(TEMP_DIR, f"{uid}_input{ext}")
    output_path = os.path.join(TEMP_DIR, f"{uid}_final.wav")

    file.save(input_path)
    logger.info(f"Received: {file.filename} ({file_size/1024:.1f} KB)")
    
    try:
        verify_audio_stream(input_path)
    except RuntimeError as e:
        cleanup_files(input_path)
        return jsonify({"error": str(e), "code": "INVALID_AUDIO_STREAM"}), 400

    try:

        future = executor.submit(process_audio, input_path, output_path, profile)
        future.result(timeout=PIPELINE_TIMEOUT_SECONDS)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Output file missing or empty after processing.")

        @after_this_request
        def cleanup(response):
            delete_file_later(output_path, delay=3.0)
            return response

        stem = os.path.splitext(file.filename)[0]

        return send_file(
            output_path,
            mimetype="audio/wav",
            as_attachment=True,
            download_name=f"crystal_clear_{stem}.wav"
        )

    except FuturesTimeoutError:
        cleanup_files(output_path)
        return jsonify({
            "error": f"Processing timed out after {PIPELINE_TIMEOUT_SECONDS}s.",
            "code": "TIMEOUT"
        }), 504

    except RuntimeError as e:
        cleanup_files(output_path)
        return jsonify({"error": str(e), "code": "PROCESSING_FAILED"}), 500

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        cleanup_files(output_path)
        return jsonify({"error": "Unexpected processing error.", "code": "INTERNAL_ERROR"}), 500

    finally:
        cleanup_files(input_path)