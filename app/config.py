"""Runtime configuration from environment variables (and .env for local development)."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR.parent / "static"
FONT_DIR = STATIC_DIR / "fonts"

# --- Gemini (auth via GOOGLE_API_KEY, or Vertex AI with GOOGLE_GENAI_USE_VERTEXAI=TRUE)
SPEECH_MODEL = os.getenv("SPEECH_MODEL", "gemini-3.8-flash")
TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "gemini-3.8-flash")
REPORT_MODEL = os.getenv("REPORT_MODEL", "gemini-3.8-flash")
# Tried in order when a model is busy or unavailable
FALLBACK_MODELS = [m.strip() for m in os.getenv("FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",")
                   if m.strip()]

# --- Login: "firebase" (Google sign-in, for production) or "dev" (type a name, for local testing/demos)
AUTH_MODE = os.getenv("AUTH_MODE", "dev").lower()
FIREBASE_WEB_CONFIG = {
    "apiKey": os.getenv("FIREBASE_API_KEY", ""),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
    "appId": os.getenv("FIREBASE_APP_ID", ""),
}

# --- Reviews storage: "sqlite" (local file) or "firestore" (Cloud Run)
STORE = os.getenv("STORE", "sqlite").lower()
SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR.parent / "local.db"))

# --- Maps: optional Google Maps Embed API key (free) for a directions map; without it a location map is shown
MAPS_EMBED_API_KEY = os.getenv("MAPS_EMBED_API_KEY", "")

# --- Limits
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 3000
MAX_COMMENT_CHARS = 600
DAILY_REPORT_LIMIT = int(os.getenv("DAILY_REPORT_LIMIT", "30"))
DAILY_TRANSCRIBE_LIMIT = int(os.getenv("DAILY_TRANSCRIBE_LIMIT", "60"))
