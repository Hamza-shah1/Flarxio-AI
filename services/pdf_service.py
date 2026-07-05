import os
import json
import shutil
import fitz
import uuid, json, re
from io import BytesIO
from PIL import Image
from flask import jsonify, send_file , abort
from config import TEMP_DIR
from services.ocr_service import run_ocr_for_pdf
from utils.pdf_edit_utils import save_meta , load_meta , numeric_sort_key , validate_pdf_upload
from models.pdf_edit_model import (
    process_pdf_image_page , save_pdf_source_file , process_pdf_pages,
    update_pdf_page_layers , save_pdf_page_image , create_pdf_backup_if_needed
    , build_pdf_only_document , get_pdf_page_paths , get_pdf_only_page_filenames 
    , get_pdf_rebuild_scale , restore_backup_page , cleanup_temp_files , get_restore_paths
)


def safe_file_id(fid):
    return bool(re.fullmatch(r"[a-f0-9\-]{36}", fid))





def handle_pdf_upload(
    file,
    allowed_ext,
    max_mb,
    log,
):

    result, error = validate_pdf_upload(
        file,
        allowed_ext,
        max_mb,
    )

    if error:
        return jsonify(result), error

    ext = result["ext"]
    raw = result["raw"]

    fid = str(uuid.uuid4())

    src_path = save_pdf_source_file(
        fid,
        ext,
        raw,
    )

    try:

        if ext == "pdf":

            pages = process_pdf_pages(
                fid,
                src_path,
                log,
            )

        else:

            pages = process_pdf_image_page(
                fid,
                raw,
            )

        save_meta(fid, {
            "pages": pages,
            "ext": ext,
        })

        return jsonify({
            "file_id": fid,
            "pages": pages,
        })

    except Exception as e:

        log.exception(
            "pdf_upload_file error"
        )

        return jsonify({
            "error":
                f"Processing failed: {e}"
        }), 500
        
        
        

def get_temp_file_response(filename):
    
    if ".." in filename or "/" in filename or "\\" in filename:
        return None, 400

    path = os.path.join(
        TEMP_DIR,
        os.path.basename(filename)
    )

    if not os.path.exists(path):
        return None, 404

    resp = send_file(path)

    resp.headers["Cache-Control"] = \
        "no-cache, no-store, must-revalidate"

    resp.headers["Pragma"] = "no-cache"

    resp.headers["Expires"] = "0"

    return resp, 200



def build_pages_only_pdf_response(file_id):
    
    meta = load_meta(file_id)

    if meta and "pages" in meta:
        return {"pages": meta["pages"]}, 200

    fnames = sorted(
        [
            f for f in os.listdir(TEMP_DIR)
            if (
                f.startswith(file_id + "_page_")
                and f.endswith(".png")
                and "_backup" not in f
            )
        ],
        key=numeric_sort_key,
    )

    if not fnames:
        return {
            "error": "Session expired"
        }, 404

    pages = []

    for fname in fnames:

        img_path = os.path.join(
            TEMP_DIR,
            fname
        )

        layers = run_ocr_for_pdf(img_path)

        try:
            pil = Image.open(img_path)
            w, h = pil.size

        except Exception:
            w, h = 0, 0

        pages.append({
            "img": f"/temp/{fname}",   
            "layers": layers,
            "width": w,
            "height": h,
            "scale": 1.0,
        })

    return {"pages": pages}, 200




def handle_cleanup(file_id):

    removed = cleanup_temp_files(
        file_id
    )

    return jsonify({
        "removed": removed
    })


def handle_restore_page(
    file_id,
    page_index
):

    backup_path, page_path = get_restore_paths(
        file_id,
        page_index
    )

    restored = restore_backup_page(
        backup_path,
        page_path
    )

    if not restored:

        return jsonify({
            "error": "No backup"
        }), 404

    return jsonify({
        "success": True
    })
    
    

def handle_rebuild_pdf_only(file_id):

    fnames = get_pdf_only_page_filenames(file_id)

    if not fnames:

        return jsonify({
            "error": "No pages found"
        }), 404

    try:

        scale = get_pdf_rebuild_scale(
            file_id
        )

        pdf_bytes = build_pdf_only_document(
            fnames,
            scale
        )

        return send_file(
            BytesIO(pdf_bytes),
            download_name=f"edited_{file_id[:8]}.pdf",
            as_attachment=True,
            mimetype="application/pdf"
        )

    except Exception as e:

        log.exception("rebuild_pdf_only")

        return jsonify({
            "error": str(e)
        }), 500
        
        
def handle_save_page_only_pdf(
    file_id,
    page_index,
    request
):

    img_file = request.files.get("edited_image")

    if not img_file:

        return jsonify({
            "error": "No image data"
        }), 400

    img_path, backup_path = get_pdf_page_paths(
        file_id,
        page_index
    )

    create_pdf_backup_if_needed(
        img_path,
        backup_path
    )

    try:

        save_pdf_page_image(
            img_file,
            img_path
        )

    except Exception as e:

        return jsonify({
            "error": f"Could not save: {e}"
        }), 500

    update_pdf_page_layers(
        file_id,
        page_index,
        request.form.get("layers")
    )

    return jsonify({
        "success": True
    })