"""Application configuration, read from environment variables.

Every setting has a sensible local-development default, so the app runs
without a .env file. See .env.example for the full list.
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Storage
    DATABASE_PATH = os.environ.get(
        "SCRIBE_DATABASE_PATH", str(BACKEND_DIR / "instance" / "scribe.db")
    )

    # Uploads: plain-text transcripts only, read into memory, never executed
    # or written to disk under the user's filename.
    MAX_UPLOAD_MB = float(os.environ.get("SCRIBE_MAX_UPLOAD_MB", "2"))
    MAX_CONTENT_LENGTH = int(MAX_UPLOAD_MB * 1024 * 1024) + 64 * 1024  # form overhead
    MIN_TRANSCRIPT_WORDS = int(os.environ.get("SCRIBE_MIN_TRANSCRIPT_WORDS", "20"))

    # Models (identical to the notebook)
    SUMMARIZER_MODEL = os.environ.get("SCRIBE_SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-12-6")
    EMBEDDING_MODEL = os.environ.get(
        "SCRIBE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    SPACY_MODEL = os.environ.get("SCRIBE_SPACY_MODEL", "en_core_web_sm")

    # "auto" uses CUDA when available, else CPU.
    DEVICE = os.environ.get("SCRIBE_DEVICE", "auto")

    # Load models at startup instead of on first use.
    PRELOAD_MODELS = _bool("SCRIBE_PRELOAD_MODELS", False)

    # Semantic search: results below this cosine similarity are not shown.
    SEMANTIC_MIN_SCORE = float(os.environ.get("SCRIBE_SEMANTIC_MIN_SCORE", "0.25"))

    # CORS for the Vite dev server.
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            "SCRIBE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]

    # Run analysis jobs in a background thread (True) or inline (tests).
    ASYNC_ANALYSIS = _bool("SCRIBE_ASYNC_ANALYSIS", True)
