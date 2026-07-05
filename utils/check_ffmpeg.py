import subprocess
from utils.handler import logger

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg",  "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10)
        subprocess.run(["ffprobe", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10)
        logger.info("FFmpeg and FFprobe detected.")
    except FileNotFoundError:
        raise EnvironmentError("FFmpeg is not installed or not in PATH.")
    except subprocess.TimeoutExpired:
        raise EnvironmentError("FFmpeg version check timed out.")
    except subprocess.CalledProcessError as e:
        raise EnvironmentError(f"FFmpeg check failed: {e}")