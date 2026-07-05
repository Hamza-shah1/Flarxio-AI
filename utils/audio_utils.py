MAX_FILE_SIZE_MB         = 50
MAX_FILE_SIZE_BYTES      = MAX_FILE_SIZE_MB * 1024 * 1024
FFMPEG_TIMEOUT_SECONDS   = 120
PIPELINE_TIMEOUT_SECONDS = 300
MAX_CONCURRENT_JOBS      = 4

ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
    ".aac",
    ".m4a",
    ".webm",
    ".opus",
    ".wma",

    # Mobile recordings
    ".amr",    # Android Voice Recorder
    ".3gp",    # Older Android recordings
    ".caf",    # iPhone recordings
    ".mp4",    # Audio-only MP4 files
    ".aiff",
    ".oga",
    ".mka"
}

ALLOWED_MIMETYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",

    "audio/mpeg",
    "audio/mp3",

    "audio/ogg",
    "audio/flac",

    "audio/aac",
    "audio/x-aac",

    "audio/mp4",
    "audio/x-m4a",

    "audio/webm",
    "audio/opus",

    "audio/x-ms-wma",

    # Mobile-specific formats
    "audio/amr",
    "audio/amr-wb",
    "audio/3gpp",
    "audio/3gpp2",
    "audio/x-caf",
    "audio/aiff",
    "audio/x-aiff",

    # Sometimes browsers/devices send generic MIME types
    "application/octet-stream",
}