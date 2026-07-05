from flask import jsonify, Request
from utils.image_types import ALLOWED_FORMATS
from utils.helpers import process_single_image, process_multiple_images
from utils.converters import (
    b64_to_cv2,
    cv2_to_b64
)
import cv2
import numpy as np

def handle_image_conversion(request: Request):

    if "images" not in request.files:
        return jsonify({"error": "No images uploaded"}), 400

    files = request.files.getlist("images")
    target_format = request.form.get("format", "").lower()

    if target_format not in ALLOWED_FORMATS:
        return jsonify({"error": "Unsupported format"}), 400
    # SINGLE IMAGE
    if len(files) == 1:
        return process_single_image(files[0], target_format)

    return process_multiple_images(files, target_format)
  
  

def decode_request_image(img_b64):
    
    if not img_b64:
        return None

    return b64_to_cv2(img_b64)


def get_inpaint_params(data, H, W):
    
    x = max(0, int(data.get("x", 0)))
    y = max(0, int(data.get("y", 0)))

    w = max(1, int(data.get("w", 10)))
    h = max(1, int(data.get("h", 10)))

    pad = int(data.get("pad", 4))
    rad = int(data.get("radius", 5))

    x1 = max(0, x - pad)
    y1 = max(0, y - pad)

    x2 = min(W, x + w + pad)
    y2 = min(H, y + h + pad)

    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "radius": rad,
    }
    
def build_inpaint_mask(H, W, x1, y1, x2, y2):
    
    mask = np.zeros((H, W), dtype=np.uint8)

    mask[y1:y2, x1:x2] = 255

    return mask


def apply_telea_inpaint(img, mask, radius):
    
    return cv2.inpaint(
        img,
        mask,
        radius,
        cv2.INPAINT_TELEA
    )
    
    
def get_average_bg_color(result, x1, y1, x2, y2):
    
    region = result[y1:y2, x1:x2]

    avg_bgr = (
        region.mean(axis=(0, 1))
        if region.size > 0
        else [255, 255, 255]
    )

    return "#{:02x}{:02x}{:02x}".format(
        int(avg_bgr[2]),
        int(avg_bgr[1]),
        int(avg_bgr[0])
    )

def process_inpaint(data):
    
    img_b64 = data.get("image")

    img = decode_request_image(img_b64)

    if img is None:
        return {
            "error": "Cannot decode image"
        }, 400

    H, W = img.shape[:2]

    params = get_inpaint_params(data, H, W)

    mask = build_inpaint_mask(
        H,
        W,
        params["x1"],
        params["y1"],
        params["x2"],
        params["y2"],
    )

    result = apply_telea_inpaint(
        img,
        mask,
        params["radius"]
    )

    bg_hex = get_average_bg_color(
        result,
        params["x1"],
        params["y1"],
        params["x2"],
        params["y2"],
    )

    out_b64 = cv2_to_b64(result)

    if out_b64 is None:
        return {
            "error": "Encode failed"
        }, 500

    return {
        "image": out_b64,
        "bg_color": bg_hex,
    }, 200