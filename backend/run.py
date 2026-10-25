"""Start the Scribe API: `python run.py` (from the backend folder).

Environment: SCRIBE_HOST (default 127.0.0.1), SCRIBE_PORT (default 5000);
everything else is in app/config.py / .env.example.
"""
import os
from pathlib import Path


def _load_dotenv():
    """Minimal .env loader (KEY=VALUE lines) so no extra package is needed.
    Values already present in the environment win."""
    env = Path(__file__).resolve().parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

from app import create_app  # noqa: E402  (config reads env at import time)

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("SCRIBE_HOST", "127.0.0.1")
    port = int(os.environ.get("SCRIBE_PORT", "5000"))
    # threaded=True so the UI can poll status while a job runs; the reloader
    # is off because it would start a second process and load models twice.
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
