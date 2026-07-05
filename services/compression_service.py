from utils.helpers import validate_compression_request , get_settings
from utils.handler import process_file
from io import BytesIO
import uuid
import zipfile
from config import TEMP_DIR
import logging
import os
import subprocess
from flask import jsonify, send_file


# ----------------- Compression Service ---------
def handle_compression(request):
    try:
        files, error = validate_compression_request(request)
        if error:
            return error

        level = request.form.get('level', 'medium').lower()
        settings = get_settings(level)

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                if not file.filename:
                    continue

                process_file(file, settings, zipf)

        zip_buffer.seek(0)

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            download_name="compressed_files.zip",
            as_attachment=True
        )

    except Exception as e:
        logging.error(f"Compression crash: {e}")
        return jsonify({"error": "Compression failed"}), 500
    
    
    