import os
import time
import threading
import logging
from config import TEMP_DIR

# Cleanup settings
TEMP_FILE_LIFETIME = 5 * 60      # 5 minutes (seconds)
CLEANUP_INTERVAL = 60            # Check every 1 minute

def cleanup_temp_folder():
    """Delete files and empty folders older than 5 minutes."""
    while True:
        try:
            now = time.time()

            if os.path.exists(TEMP_DIR):
                for root, dirs, files in os.walk(TEMP_DIR, topdown=False):

                    # Delete old files
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            if now - os.path.getmtime(file_path) > TEMP_FILE_LIFETIME:
                                os.remove(file_path)
                                logging.info(f"Deleted temp file: {file_path}")
                        except Exception as e:
                            logging.error(f"Could not delete {file_path}: {e}")

                    # Delete empty directories
                    for directory in dirs:
                        dir_path = os.path.join(root, directory)
                        try:
                            if not os.listdir(dir_path):
                                os.rmdir(dir_path)
                                logging.info(f"Removed empty folder: {dir_path}")
                        except Exception:
                            pass

        except Exception as e:
            logging.error(f"Temp cleanup error: {e}")

        # Wait before next cleanup
        time.sleep(CLEANUP_INTERVAL)


def start_temp_cleanup():
    """Start the cleanup thread."""
    thread = threading.Thread(target=cleanup_temp_folder, daemon=True)
    thread.start()