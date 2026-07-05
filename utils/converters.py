import base64 , collections
import cv2
import numpy as np

def b64_to_cv2(b64):
    raw = base64.b64decode(b64.split(",")[-1])
    arr = np.frombuffer(raw, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def cv2_to_b64(img):
    ok, enc = cv2.imencode(".png", img)
    if not ok: return None
    return "data:image/png;base64," + base64.b64encode(enc.tobytes()).decode()
