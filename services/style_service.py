import cv2
import numpy as np

def get_bbox(data, H, W):
    
    x = max(0, int(data.get("x", 0)))
    y = max(0, int(data.get("y", 0)))

    w = max(1, int(data.get("w", 10)))
    h = max(1, int(data.get("h", 10)))

    x1 = max(0, x)
    y1 = max(0, y)

    x2 = min(W, x + w)
    y2 = min(H, y + h)

    return x1, y1, x2, y2, w, h



def analyze_background(img, x1, y1, x2, y2):
    
    H, W = img.shape[:2]

    bpad = 10

    bx1 = max(0, x1 - bpad)
    by1 = max(0, y1 - bpad)

    bx2 = min(W, x2 + bpad)
    by2 = min(H, y2 + bpad)

    border_crop = img[by1:by2, bx1:bx2].copy()

    inner_mask = np.zeros(
        border_crop.shape[:2],
        dtype=bool
    )

    iy1_r = y1 - by1
    iy2_r = iy1_r + (y2 - y1)

    ix1_r = x1 - bx1
    ix2_r = ix1_r + (x2 - x1)

    inner_mask[
        max(0, iy1_r):iy2_r,
        max(0, ix1_r):ix2_r
    ] = True

    border_px = border_crop[
        ~inner_mask
    ].reshape(-1, 3)

    if len(border_px) > 0:

        bg_bgr = np.median(
            border_px,
            axis=0
        )

        bg_hex = "#{:02x}{:02x}{:02x}".format(
            int(bg_bgr[2]),
            int(bg_bgr[1]),
            int(bg_bgr[0])
        )

        bg_lum = (
            0.2126 * bg_bgr[2]
            + 0.7152 * bg_bgr[1]
            + 0.0722 * bg_bgr[0]
        )

    else:

        bg_hex = "#ffffff"
        bg_lum = 255

    return bg_hex, bg_lum



def analyze_text_region(
    roi,
    bg_lum
):

    txt_hex = "#000000"

    is_bold = False

    if roi.size <= 0:
        return txt_hex, is_bold

    gray = cv2.cvtColor(
        roi,
        cv2.COLOR_BGR2GRAY
    )

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    if bg_lum > 128:
        text_mask = binary == 0
    else:
        text_mask = binary == 255

    text_px = roi[text_mask]

    if len(text_px) > 10:

        txt_bgr = np.median(
            text_px,
            axis=0
        )

        txt_hex = "#{:02x}{:02x}{:02x}".format(
            int(txt_bgr[2]),
            int(txt_bgr[1]),
            int(txt_bgr[0])
        )

        text_img = (
            text_mask.astype(np.uint8)
        ) * 255

        k = np.ones((3, 3), np.uint8)

        eroded = cv2.erode(
            text_img,
            k,
            iterations=1
        )

        survival = eroded.sum() / max(
            text_img.sum(),
            1
        )

        is_bold = bool(survival > 0.28)

    return txt_hex, is_bold


def process_style_analysis(data, img):
    
    H, W = img.shape[:2]

    x1, y1, x2, y2, w, h = get_bbox(
        data,
        H,
        W
    )

    bg_hex, bg_lum = analyze_background(
        img,
        x1,
        y1,
        x2,
        y2
    )

    roi = img[y1:y2, x1:x2]

    txt_hex, is_bold = analyze_text_region(
        roi,
        bg_lum
    )

    fs = max(8, round(h * 0.70))

    return {
        "bg_color": bg_hex,
        "text_color": txt_hex,
        "fs": fs,
        "bold": is_bold,
        "italic": False,
    }