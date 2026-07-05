
import os
import time
from io import BytesIO
from flask import request, jsonify, send_file, g
from models.image_enhancer_model import _active_count

def handle_enhance_image(
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
):
    global _active_count

    rid = g.rid

    with _active_lock:
        if _active_count >= MAX_QUEUE:
            return jsonify({
                "error": "Server busy — retry shortly",
                "request_id": rid
            }), 503
        _active_count += 1

    try:
        if "image" not in request.files:
            return jsonify({
                "error": "No image file provided",
                "request_id": rid
            }), 400

        file = request.files["image"]

        # ---- Parse scale ----
        try:
            scale = int(request.form.get("scale", 2))
        except (ValueError, TypeError):
            return jsonify({
                "error": "scale must be 2, 3, or 4",
                "request_id": rid
            }), 400

        if scale not in VALID_SCALES:
            return jsonify({
                "error": "scale must be 2, 3, or 4",
                "request_id": rid
            }), 400

        # ---- Format & Quality ----
        fmt = request.form.get("format", OUTPUT_FORMAT).lower()
        quality = int(request.form.get("quality", OUTPUT_QUALITY))

        if fmt not in ("png", "webp", "jpeg"):
            fmt = "png"

        raw = file.read()
        if not raw:
            return jsonify({
                "error": "Empty file",
                "request_id": rid
            }), 400

        img = _decode_image(raw)
        if img is None:
            return jsonify({
                "error": "Invalid or corrupted image",
                "request_id": rid
            }), 400

        h, w = img.shape[:2]
        pixels = w * h

        if pixels > MAX_PIXELS:
            return jsonify({
                "error": (
                    f"Image too large ({pixels / 1e6:.1f}MP). "
                    f"Max is {MAX_PIXELS / 1e6:.0f}MP."
                ),
                "request_id": rid,
            }), 400

        log.info("[%s] %dx%d x%d fmt=%s active=%d",
                 rid, w, h, scale, fmt, _active_count)

        # ---- Enhance ----
        try:
            enhanced, method = enhance(img, scale)
        except Exception as exc:
            log.exception("[%s] enhance() error: %s", rid, exc)
            return jsonify({
                "error": "Enhancement failed",
                "request_id": rid
            }), 500

        # ---- Encode ----
        try:
            encoded, mime, ext = _encode_image(enhanced, fmt, quality)
        except Exception as exc:
            log.error("[%s] encode error: %s", rid, exc)
            return jsonify({
                "error": "Encoding failed",
                "request_id": rid
            }), 500

        oh, ow = enhanced.shape[:2]
        elapsed = time.time() - g.t0

        log.info(
            "[%s] done %.2fs | %s | %dx%d -> %dx%d | %s %.1fKB",
            rid, elapsed, method, w, h, ow, oh,
            fmt.upper(), len(encoded) / 1024,
        )

        stem = os.path.splitext(file.filename or "image")[0]

        resp = send_file(
            BytesIO(encoded),
            mimetype=mime,
            as_attachment=False,
            download_name=f"enhanced_{stem}{ext}",
        )

        resp.headers.update({
            "X-Method": method,
            "X-Time": f"{elapsed:.2f}s",
            "X-Output-Size": f"{ow}x{oh}",
            "X-Format": fmt.upper(),
            "X-Request-Id": rid,
        })

        return resp

    finally:
        with _active_lock:
            _active_count -= 1