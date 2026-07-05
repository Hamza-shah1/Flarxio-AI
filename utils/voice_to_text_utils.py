 # 50MB
from config import RATE_BURST , RATE_RPS
import time
from flask import request
import threading
from collections import OrderedDict
import hashlib


class _TokenBucket:
    __slots__ = ("tokens", "last_refill", "lock")

    def __init__(self) -> None:
        self.tokens:      float = float(RATE_BURST)
        self.last_refill: float = time.monotonic()
        self.lock                = threading.Lock()

    def consume(self) -> tuple[bool, float]:
        """
        Returns (allowed: bool, retry_after_seconds: float).
        retry_after_seconds is 0.0 when allowed.
        """
        now = time.monotonic()
        with self.lock:
            elapsed       = now - self.last_refill
            self.tokens   = min(RATE_BURST, self.tokens + elapsed * RATE_RPS)
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True, 0.0
            # How long until 1 token refills?
            wait = (1.0 - self.tokens) / RATE_RPS
            return False, wait


class _RateLimiterStore:
    """Thread-safe registry of per-IP buckets with LRU eviction."""

    _EVICT_CAPACITY = 4096

    def __init__(self) -> None:
        self._buckets: OrderedDict[str, _TokenBucket] = OrderedDict()
        self._lock = threading.Lock()

    def get_bucket(self, ip: str) -> _TokenBucket:
        with self._lock:
            if ip in self._buckets:
                self._buckets.move_to_end(ip)
                return self._buckets[ip]
            bucket = _TokenBucket()
            self._buckets[ip] = bucket
            if len(self._buckets) > self._EVICT_CAPACITY:
                self._buckets.popitem(last=False)
            return bucket





# ════════════════════════════════════════════════════════════════════════════════
# LRU TRANSCRIPTION CACHE
# ════════════════════════════════════════════════════════════════════════════════
CACHE_CAPACITY = 50
_transcription_cache: OrderedDict[str, dict] = OrderedDict()
_cache_lock = threading.Lock()        # protect cache under threaded=True




def cache_get(key: str) -> dict | None:
    with _cache_lock:
        if key not in _transcription_cache:
            return None
        _transcription_cache.move_to_end(key)
        return _transcription_cache[key]


def cache_put(key: str, value: dict) -> None:
    with _cache_lock:
        if key in _transcription_cache:
            _transcription_cache.move_to_end(key)
        _transcription_cache[key] = value
        if len(_transcription_cache) > CACHE_CAPACITY:
            _transcription_cache.popitem(last=False)

# ════════════════════════════════════════════════════════════════════════════════
# HASHING
# ════════════════════════════════════════════════════════════════════════════════
def hash_bytes(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()



# ════════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════════
_ALLOWED_EXT_SET: frozenset[str] = frozenset({
    # Common audio formats
    "mp3",
    "wav",
    "ogg",
    "webm",
    "m4a",
    "flac",
    "aac",
    "aiff",

    # Mobile phone recordings
    "3gp",      # Older Android recordings
    "amr",      # Android voice recorder
    "caf",      # iPhone recordings (sometimes)
    "mp4",      # Audio-only MP4 recordings
    "opus",     # Modern voice recording format

    # Additional formats
    "wma",
    "mka",
    "oga"
})


def allowed_file(filename: str) -> bool:
    dot = filename.rfind(".")
    return dot != -1 and filename[dot + 1:].lower() in _ALLOWED_EXT_SET