import cv2
import numpy as np
import gc
from utils.image_utils import decode_image, decode_mask, encode_png
import cv2
import numpy as np
import gc
from flask import Flask, request, jsonify, send_file, url_for



def remove_object_service(image_file, mask_file, MAX_PX, refine_mask, lama_inpaint, log):

    image = decode_image(image_file)
    orig_h, orig_w = image.shape[:2]

    log.info(f"[remove-object] input {orig_w}×{orig_h}")

    # Resolution cap
    scale = 1.0
    if orig_w * orig_h > MAX_PX:
        scale = (MAX_PX / (orig_w * orig_h)) ** 0.5
        nw = int(orig_w * scale)
        nh = int(orig_h * scale)
        image = cv2.resize(image, (nw, nh), cv2.INTER_AREA)
        log.info(f"[remove-object] scaled to {nw}×{nh}")

    img_h, img_w = image.shape[:2]

    mask = decode_mask(mask_file)

    if mask.shape[:2] != (img_h, img_w):
        mask = cv2.resize(mask, (img_w, img_h), cv2.INTER_NEAREST)

    mask = refine_mask(mask)

    white_px = int(np.sum(mask > 127))
    if white_px == 0:
            return jsonify({"error": "Mask is empty — paint over the object first"}), 400
    log.info(f"[remove-object] mask: {white_px} px ({white_px*100//(img_h*img_w)}%)")

    # Inpainting
    result = lama_inpaint(image, mask)

    if scale < 1.0:
        result = cv2.resize(result, (orig_w, orig_h), cv2.INTER_LANCZOS4)

    buf = encode_png(result)
        
        
    del image, mask, result
    gc.collect()

    return buf
    
    
    
    
    
    
    
    
    
    
    
    
    
        
        
        
        
    