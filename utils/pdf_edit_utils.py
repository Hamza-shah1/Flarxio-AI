from config import TEMP_DIR , log
import os, json, re
import logging


def meta_path(fid):
    return os.path.join(TEMP_DIR, f"{fid}_meta.json")

def numeric_sort_key(fname):
    m = re.search(r"_page_(\d+)", fname)
    return int(m.group(1)) if m else 0




def load_meta(fid):
    p = meta_path(fid)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"load_meta {fid}: {e}")
    return {}

def save_meta(fid, data):
    try:
        with open(meta_path(fid), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f"save_meta {fid}: {e}")
        
        

def validate_pdf_upload(file, allowed_ext, max_mb):
    
    if not file or not file.filename:
        return {"error": "No file uploaded"}, 400

    ext = (
        file.filename.rsplit(".", 1)[-1].lower()
        if "." in file.filename
        else ""
    )

    if ext not in allowed_ext:
        return {"error": f"Unsupported: .{ext}"}, 400

    raw = file.read()

    if len(raw) > max_mb * 1024 * 1024:
        return {
            "error": f"File too large (max {max_mb}MB)"
        }, 400

    return {
        "ext": ext,
        "raw": raw,
    }, None
