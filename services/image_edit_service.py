from models.image_edit_model import (
    get_rebuild_page_filenames , build_pdf_document , save_source_file,
    process_pdf_file , process_image_file , get_saved_pages , rebuild_pages_from_images , 
    save_edited_image , update_page_layers , create_backup_if_needed
 )
from flask import  jsonify, send_file
from config import log
from utils.pdf_utils import ALLOWED_EXT , MAX_FILE_MB 
import os, uuid
from config import TEMP_DIR
from utils.pdf_edit_utils import save_meta



def handle_rebuild_pdf(file_id):
    
    fnames = get_rebuild_page_filenames(file_id)

    if not fnames:

        return jsonify({
            "error": "No pages"
        }), 404

    try:

        out = build_pdf_document(fnames)

        return send_file(
            out,
            download_name=f"edited_{file_id[:8]}.pdf",
            as_attachment=True,
            mimetype="application/pdf"
        )

    except Exception as e:

        log.exception("rebuild_pdf")

        return jsonify({
            "error": str(e)
        }), 500



def validate_uploaded_file(file):

    if not file or not file.filename:
        return {"error": "No file"}, 400

    ext = (
        file.filename.rsplit(".", 1)[-1].lower()
        if "." in file.filename
        else ""
    )

    if ext not in ALLOWED_EXT:
        return {"error": f"'.{ext}' not supported"}, 400

    raw = file.read()

    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        return {"error": "Too large"}, 400

    return {
        "ext": ext,
        "raw": raw
    }, None
    
    
    
    
def handle_upload_file(file):
    
    result, error = validate_uploaded_file(file)

    if error:
        return jsonify(result), error

    ext = result["ext"]
    raw = result["raw"]

    fid = str(uuid.uuid4())

    src_path = save_source_file(
        fid,
        ext,
        raw
    )

    pages = []

    try:

        if ext == "pdf":

            pages = process_pdf_file(
                fid,
                src_path
            )

        else:

            pages = process_image_file(
                fid,
                raw
            )

    except Exception as e:

        log.exception("upload_file")

        return jsonify({
            "error": str(e)
        }), 500

    save_meta(fid, {
        "pages": pages,
        "ext": ext
    })

    return jsonify({
        "file_id": fid,
        "pages": pages
    })
    
    
    
def handle_get_pages(file_id):
    
    pages = get_saved_pages(file_id)

    if pages:
        return jsonify({
            "pages": pages
        })

    rebuilt_pages = rebuild_pages_from_images(file_id)

    if rebuilt_pages is None:

        return jsonify({
            "error": "Session expired"
        }), 404

    return jsonify({
        "pages": rebuilt_pages
    })



def handle_save_page(
    file_id,
    page_index,
    request
):

    img_file = request.files.get("edited_image")

    if not img_file:
        return jsonify({
            "error": "No image"
        }), 400

    img_path = os.path.join(
        TEMP_DIR,
        f"{file_id}_page_{page_index}.png"
    )

    backup_path = os.path.join(
        TEMP_DIR,
        f"{file_id}_page_{page_index}_backup.png"
    )

    create_backup_if_needed(
        img_path,
        backup_path
    )

    try:

        save_edited_image(
            img_file,
            img_path
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

    update_page_layers(
        file_id,
        page_index,
        request.form.get("layers")
    )

    return jsonify({
        "success": True
    })
