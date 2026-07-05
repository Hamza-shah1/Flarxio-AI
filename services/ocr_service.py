from flask import jsonify
from PIL import Image
import pytesseract
from config import TESSERACT_AVAILABLE , log
import  collections
from utils.pdf_colors import rgb_to_hex

def handle_ocr(image_file, TESSERACT_AVAILABLE, log):

    if not TESSERACT_AVAILABLE:
        return jsonify({"error": "Tesseract not available on this server"}), 503

    try:

        img = Image.open(image_file)

        text = pytesseract.image_to_string(
            img,
            lang="eng+osd",
            config="--oem 3 --psm 3"
        )

        return jsonify({
            "text": text.strip()
        })

    except Exception as e:
        log.error(f"[ocr] {e}", exc_info=True)
        return jsonify({"error": str(e)}), 
    
    
#ocr for pdf editing
def sample_bg_color_of_pdf(img_path, x, y, w, h):
    """Sample the lightest (background) color from a region."""
    try:
        pil = Image.open(img_path).convert("RGB")
        pw, ph = pil.size
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(pw, int(x + max(w, 2)))
        y1 = min(ph, int(y + max(h, 2)))
        if x1 <= x0 or y1 <= y0:
            return "#ffffff"
        region = pil.crop((x0, y0, x1, y1))
        pixels = list(region.getdata())
        if not pixels:
            return "#ffffff"
        # Sort by brightness, take 75th percentile (background is usually brightest)
        pixels.sort(key=lambda p: p[0]*299 + p[1]*587 + p[2]*114)
        q = pixels[int(len(pixels) * 0.75)]
        return f"#{q[0]:02x}{q[1]:02x}{q[2]:02x}"
    except Exception as e:
        log.warning(f"sample_bg_color_of_pdf: {e}")
        return "#ffffff"
    
def run_ocr_for_pdf(img_path):
    if not TESSERACT_AVAILABLE:
        return []
    try:
        pil  = Image.open(img_path).convert("RGB")
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT)
        layers = []
        for i in range(len(data.get("text", []))):
            try:
                conf = int(data["conf"][i])
            except Exception:
                conf = -1
            txt = (data["text"][i] or "").strip()
            if not txt or conf <= 40:
                continue
            h_px = max(int(data["height"][i]), 8)
            x    = int(data["left"][i])
            y    = int(data["top"][i])
            w    = max(int(data["width"][i]), 20)
            bg   = sample_bg_color_of_pdf(img_path, x, y, w, h_px)
            layers.append({
                "text":      txt,
                "x":         x, "y": y, "w": w, "h": h_px,
                "fs":        round(max(6.0, min(h_px*0.72, 300.0)), 1),
                "font":      "Arial, Helvetica, sans-serif",
                "color":     "#000000",
                "bold":      False, "italic": False, "underline": False,
                "align":     "left", "opacity": 1.0,
                "bg_color":  bg,
                "source":    "ocr",
                "visible":   False,
                "edited":    False,
            })
        return layers
    except Exception as e:
        log.error(f"run_ocr_for_pdf: {e}")
        return []
    
    

# ── Color sampling (for OCR) ───────────────────────────────────────────────
def sample_bg_color(px, W, H, x1, y1, x2, y2):
    border = []
    bw = 6
    for yy in range(max(0,y1-bw), y1):
        for xx in range(max(0,x1-bw), min(W,x2+bw+1)): border.append(px[xx,yy])
    for yy in range(y2+1, min(H,y2+bw+1)):
        for xx in range(max(0,x1-bw), min(W,x2+bw+1)): border.append(px[xx,yy])
    for xx in range(max(0,x1-bw), x1):
        for yy in range(y1,y2+1): border.append(px[xx,yy])
    for xx in range(x2+1, min(W,x2+bw+1)):
        for yy in range(y1,y2+1): border.append(px[xx,yy])
    if not border: return "#ffffff"
    q=[(r//16*16,g//16*16,b//16*16) for r,g,b in border]
    return rgb_to_hex(collections.Counter(q).most_common(1)[0][0])

def sample_text_color(px, W, H, x1, y1, x2, y2):
    interior=[]
    step=max(1,(x2-x1)//12)
    for yy in range(y1,y2,max(1,(y2-y1)//8)):
        for xx in range(x1,x2,step): interior.append(px[min(xx,W-1),min(yy,H-1)])
    if not interior: return "#000000"
    def lum(c): return 0.299*c[0]+0.587*c[1]+0.114*c[2]
    s=sorted(interior,key=lum); avg=sum(lum(c) for c in interior)/len(interior)
    samp=s[:max(1,len(s)//5)] if avg>128 else s[-max(1,len(s)//5):]
    return rgb_to_hex((int(sum(c[0] for c in samp)/len(samp)),
                       int(sum(c[1] for c in samp)/len(samp)),
                       int(sum(c[2] for c in samp)/len(samp))))
    
def run_ocr_for_image(img_path):
    if not TESSERACT_AVAILABLE: return []
    try:
        pil=Image.open(img_path).convert("RGB"); W,H=pil.size; px=pil.load()
        data=pytesseract.image_to_data(pil,output_type=pytesseract.Output.DICT)
        out=[]
        for i in range(len(data.get("text",[]))):
            txt=(data["text"][i] or "").strip()
            try: conf=int(data["conf"][i])
            except: conf=-1
            if not txt or conf<30: continue
            bx=int(data["left"][i]); by=int(data["top"][i])
            bw=max(int(data["width"][i]),20); bh=max(int(data["height"][i]),8)
            x1=max(0,bx); y1=max(0,by); x2=min(W-1,bx+bw); y2=min(H-1,by+bh)
            out.append({"text":txt,"x":bx,"y":by,"w":bw,"h":bh,
                        "font_size":max(6.0,min(round(bh*0.68,1),300.0)),
                        "font":"Arial","color":sample_text_color(px,W,H,x1,y1,x2,y2),
                        "bold":False,"italic":False,"underline":False,
                        "align":"left","opacity":1.0,"source":"ocr",
                        "bg_color":sample_bg_color(px,W,H,x1,y1,x2,y2),"edited":False})
        log.info(f"OCR: {len(out)} regions"); return out
    except Exception as e: log.error(f"run_ocr_for_image: {e}"); return []
    
    