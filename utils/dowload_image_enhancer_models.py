
import urllib.request
import os
from config import MODEL_DIR


FSRCNN_URLS = {
    2: "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x2.pb",
    3: "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x3.pb",
    4: "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x4.pb",
}
LAPSRN_URLS = {
    2: "https://github.com/fannymonori/TF-LapSRN/raw/master/export/LapSRN_x2.pb",
    4: "https://github.com/fannymonori/TF-LapSRN/raw/master/export/LapSRN_x4.pb",
}

import logging

log = logging.getLogger(__name__)

def _download_model(url: str, filename: str) -> str | None:
    path = os.path.join(MODEL_DIR, filename)
    if os.path.exists(path):
        return path
    log.info("Downloading %s ...", filename)
    try:
        urllib.request.urlretrieve(url, path)
        log.info("Downloaded %s", filename)
        return path
    except Exception as exc:
        log.error("Download failed %s: %s", filename, exc)
        if os.path.exists(path):
            os.remove(path)
        return None