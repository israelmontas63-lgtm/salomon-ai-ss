"""
Configuración central del proyecto Salomón AI.
Todas las rutas y variables de entorno se definen aquí.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data"
MEMORIA_DIR = DATA_DIR / "memoria_chroma"
SESIONES_DB = DATA_DIR / "sesiones.db"
AGENTE_BACKUP_DIR = DATA_DIR / "agente_backups"

# ── Google Gemini ──────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash").strip()
GEMINI_MAX_TURNOS = int(os.getenv("GEMINI_MAX_TURNOS", "20"))
GEMINI_MODELOS_RESPALDO = [
    m.strip()
    for m in os.getenv(
        "GEMINI_MODELOS_RESPALDO",
        "gemini-2.0-flash-lite,gemini-2.0-flash",
    ).split(",")
    if m.strip()
]

# ── OpenWeatherMap ─────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

# ── TTS — ElevenLabs (motor principal) ─────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_MODEL_ID = os.getenv(
    "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
).strip()
# Perfil juvenil / enérgico (más expresivo = stability más baja)
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.32"))
ELEVENLABS_SIMILARITY = float(os.getenv("ELEVENLABS_SIMILARITY", "0.82"))
ELEVENLABS_STYLE = float(os.getenv("ELEVENLABS_STYLE", "0.55"))

# Compatibilidad (ya no se usan como motor principal)
TTS_RATE = int(os.getenv("TTS_RATE", "185"))
TTS_VOLUME = float(os.getenv("TTS_VOLUME", "0.95"))
TTS_ASYNC = os.getenv("TTS_ASYNC", "false").strip().lower() in ("1", "true", "yes", "on")

# ── OpenAI (proveedor alternativo) ───────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()

# ── Groq (OpenAI-compatible, gratis sin tarjeta) ───────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

# ── Cognición ──────────────────────────────────────────────────────────────
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
AGENTE_AUTONOMO_HABILITADO = os.getenv("AGENTE_AUTONOMO", "false").strip().lower() in (
    "1", "true", "yes", "on",
)
AGENTE_MAX_ARCHIVOS = int(os.getenv("AGENTE_MAX_ARCHIVOS", "4"))
AGENTE_MAX_BYTES = int(os.getenv("AGENTE_MAX_BYTES", "80000"))

# ── Seguridad API ───────────────────────────────────────────────────────────
SALOMON_API_KEY = os.getenv("SALOMON_API_KEY", "").strip()
SALOMON_ADMIN_KEY = os.getenv("SALOMON_ADMIN_KEY", "").strip()
SEGURIDAD_HABILITADA = os.getenv("SEGURIDAD_HABILITADA", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# ── Proveedor LLM ──────────────────────────────────────────────────────────
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "gemini").strip().lower()

# ── Fallback LLM ───────────────────────────────────────────────────────────
LLM_FALLBACK = os.getenv("LLM_FALLBACK", "true").strip().lower() in (
    "1", "true", "yes", "on",
)
LLM_LOCAL_FALLBACK = os.getenv("LLM_LOCAL_FALLBACK", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# ── Búsqueda web (Tavily preferido; DDG/noticias como respaldo) ────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
BUSQUEDA_WEB_AUTO = os.getenv("BUSQUEDA_WEB_AUTO", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ── Colsub Media — Multi-Model Routing (Pro/Ultra) ─────────────────────────
MEDIA_CALIDAD_FORZADA = os.getenv("MEDIA_CALIDAD_FORZADA", "pro_ultra").strip()
MEDIA_FORZAR_PRO = os.getenv("MEDIA_FORZAR_PRO", "true").strip().lower() in (
    "1", "true", "yes", "on",
)
MEDIA_PREFER_IMAGEN = os.getenv("MEDIA_PREFER_IMAGEN", "flux").strip().lower()
MEDIA_PREFER_VIDEO = os.getenv("MEDIA_PREFER_VIDEO", "runway").strip().lower()
FLUX_API_KEY = os.getenv("FLUX_API_KEY", "").strip()
FLUX_API_URL = os.getenv("FLUX_API_URL", "").strip()
FLUX_MODEL = os.getenv("FLUX_MODEL", "flux-1-pro").strip()
MIDJOURNEY_API_KEY = os.getenv("MIDJOURNEY_API_KEY", "").strip()
MIDJOURNEY_API_URL = os.getenv("MIDJOURNEY_API_URL", "").strip()
RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY", "").strip()
RUNWAY_API_URL = os.getenv("RUNWAY_API_URL", "").strip()
RUNWAY_MODEL = os.getenv("RUNWAY_MODEL", "gen3a_alpha").strip()
RUNWAY_MODEL_PRO = os.getenv("RUNWAY_MODEL_PRO", "gen3a_alpha").strip()
KLING_API_KEY = os.getenv("KLING_API_KEY", "").strip()
KLING_API_URL = os.getenv("KLING_API_URL", "").strip()
KLING_MODEL = os.getenv("KLING_MODEL", "kling-v1-pro").strip()
KREA_API_KEY = os.getenv("KREA_API_KEY", "").strip()
KREA_API_URL = os.getenv("KREA_API_URL", "").strip()

# ── Colsub (orquesta on-demand 1–40 agentes) ───────────────────────────────
COLSUB_MAX_AGENTES = int(os.getenv("COLSUB_MAX_AGENTES", "40"))
COLSUB_MAX_WORKERS = int(os.getenv("COLSUB_MAX_WORKERS", "8"))
COLSUB_CPU_CRITICO = float(os.getenv("COLSUB_CPU_CRITICO", "85"))
COLSUB_RAM_CRITICO = float(os.getenv("COLSUB_RAM_CRITICO", "88"))

# ── Caché conectores ───────────────────────────────────────────────────────
CACHE_TTL_SEGUNDOS = int(os.getenv("CACHE_TTL_SEGUNDOS", "900"))

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

# ── Aprendizaje async ──────────────────────────────────────────────────────
APRENDIZAJE_ASYNC = os.getenv("APRENDIZAJE_ASYNC", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# ── Function-calling (Fase 2 OS) ───────────────────────────────────────────
FUNCTION_CALLING_HABILITADO = os.getenv("FUNCTION_CALLING_HABILITADO", "true").strip().lower() in (
    "1", "true", "yes", "on",
)
FUNCTION_CALLING_SIEMPRE = os.getenv("FUNCTION_CALLING_SIEMPRE", "false").strip().lower() in (
    "1", "true", "yes", "on",
)
FUNCTION_CALLING_MAX_ITER = int(os.getenv("FUNCTION_CALLING_MAX_ITER", "3"))

# ── VDCP — Visión Dinámica de Campo Profundo ───────────────────────────────
VDCP_MAX_FOVEAS = int(os.getenv("VDCP_MAX_FOVEAS", "12"))
VDCP_OCR_ENGINE = os.getenv("VDCP_OCR_ENGINE", "").strip().lower()  # paddle|tesseract|easyocr|gemini
VDCP_YOLO_WEIGHTS = os.getenv(
    "VDCP_YOLO_WEIGHTS",
    str(DATA_DIR / "models" / "vdcp" / "yolov8n.pt"),
).strip()
VDCP_YOLO_CONF = float(os.getenv("VDCP_YOLO_CONF", "0.25"))
VDCP_USAR_GEMINI = os.getenv("VDCP_USAR_GEMINI", "false").strip().lower() in (
    "1", "true", "yes", "on",
)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

# ── Túnel móvil (localtunnel) ──────────────────────────────────────────────
COLSUB_PORT = int(os.getenv("COLSUB_PORT", "8000"))
COLSUB_HOST = os.getenv("COLSUB_HOST", "0.0.0.0").strip() or "0.0.0.0"
TUNEL_HABILITADO = os.getenv("TUNEL_HABILITADO", "true").strip().lower() in (
    "1", "true", "yes", "on",
)
TUNEL_AUTO = os.getenv("TUNEL_AUTO", "true").strip().lower() in (
    "1", "true", "yes", "on",
)
TUNEL_SUBDOMAIN = os.getenv("TUNEL_SUBDOMAIN", "salomon-ai").strip()
