"""Centralized, environment-driven configuration.

All tunables live here so the rest of the codebase never reads ``os.getenv``
directly. This keeps configuration auditable and makes the app safe to expose
on the public internet (every limit has a hard server-side ceiling).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` on missing/invalid."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    """Read a boolean env var (``1/true/yes/on``), falling back to ``default``."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _clean(value: str) -> str:
    return (value or "").strip()


class Config:
    # --- Runtime ---
    APP_ENV = _clean(os.getenv("APP_ENV", "production")).lower()
    IS_PRODUCTION = APP_ENV == "production"
    DEBUG = APP_ENV in ("dev", "development", "debug")
    HOST = _clean(os.getenv("HOST", "0.0.0.0"))
    PORT = _int("PORT", 8000)
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")
    CORS_ALLOWED_ORIGINS = _clean(os.getenv("CORS_ALLOWED_ORIGINS", "*"))

    # --- GitHub ---
    GITHUB_TOKEN = _clean(os.getenv("GITHUB_TOKEN", "")) or None

    # --- Hard request ceilings (defend a public endpoint) ---
    MAX_SEARCH_SIZE = _int("MAX_SEARCH_SIZE", 100)
    MAX_RESULTS = _int("MAX_RESULTS", 50)
    MAX_REPOS_PER_USER = _int("MAX_REPOS_PER_USER", 20)
    SCRAPER_MAX_WORKERS = max(1, _int("SCRAPER_MAX_WORKERS", 8))
    # Achievements are only on the profile HTML page (no API), so we scrape them
    # for the shortlist only. Disable to skip the extra HTML requests entirely.
    FETCH_ACHIEVEMENTS = _bool("FETCH_ACHIEVEMENTS", True)

    # --- Rate limiting ---
    RATELIMIT_STORAGE_URI = _clean(os.getenv("RATELIMIT_STORAGE_URI", "memory://"))
    RATELIMIT_DEFAULT = _clean(os.getenv("RATELIMIT_DEFAULT", "60 per minute"))
    RATELIMIT_SEARCH = _clean(os.getenv("RATELIMIT_SEARCH", "10 per minute"))

    # --- LLM ---
    LLM_PROVIDER = _clean(os.getenv("LLM_PROVIDER", "none")).lower()
    LLM_EVAL_TOP_K = _int("LLM_EVAL_TOP_K", 12)
    # Parallel LLM eval calls. Keep low on token-per-minute-limited tiers (e.g.
    # Groq free = 8000 TPM) so a burst of evals doesn't trip 429 rate limits.
    LLM_MAX_CONCURRENCY = max(1, _int("LLM_MAX_CONCURRENCY", 2))
    # SDK-level retries; the client honors the provider's Retry-After header, so
    # a few retries let calls recover from transient per-minute rate limits.
    LLM_MAX_RETRIES = max(0, _int("LLM_MAX_RETRIES", 5))
    # Output-token ceiling for a single evaluation (input+output count toward TPM).
    LLM_EVAL_MAX_TOKENS = _int("LLM_EVAL_MAX_TOKENS", 500)
    OPENAI_API_KEY = _clean(os.getenv("OPENAI_API_KEY", "")) or None
    OPENAI_MODEL = _clean(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    OPENAI_BASE_URL = _clean(os.getenv("OPENAI_BASE_URL", "")) or None
    # Groq (OpenAI-compatible API; serves gpt-oss and other open models).
    GROQ_API_KEY = _clean(os.getenv("GROQ_API_KEY", "")) or None
    GROQ_MODEL = _clean(os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    GROQ_BASE_URL = _clean(os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    # gpt-oss is a reasoning model; keep reasoning terse so JSON isn't truncated.
    GROQ_REASONING_EFFORT = _clean(os.getenv("GROQ_REASONING_EFFORT", "low")).lower() or None
    AWS_REGION = _clean(os.getenv("AWS_REGION", "us-east-1"))
    BEDROCK_MODEL_ID = _clean(
        os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    )

    @classmethod
    def clamp_search_size(cls, value, default=None) -> int:
        """Clamp a requested search size into ``[1, MAX_SEARCH_SIZE]``."""
        return _clamp(value, 1, cls.MAX_SEARCH_SIZE, default or 100)

    @classmethod
    def clamp_max_results(cls, value, default=None) -> int:
        """Clamp a requested result count into ``[1, MAX_RESULTS]``."""
        return _clamp(value, 1, cls.MAX_RESULTS, default or 10)


def _clamp(value, low: int, high: int, default: int) -> int:
    """Safely parse ``value`` to int and clamp into ``[low, high]``."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


config = Config()
