"""Application configuration (env-driven)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Copy `.env.example` to `.env` to configure."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM provider: "auto" (use Groq when key present, else fallback), "groq", "fallback"
    llm_provider: str = "auto"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_timeout_seconds: float = 15.0
    llm_temperature: float = 0.7

    # Speech AI (all free): Whisper STT via Groq, neural TTS via edge-tts
    # (falls back to gTTS when Microsoft's endpoint is unreachable).
    whisper_model: str = "whisper-large-v3"
    tts_voice_en: str = "en-IN-SwaraNeural"
    tts_voice_hi: str = "hi-IN-SwaraNeural"
    tts_cache_seconds: int = 86400 * 7  # 7 days

    # Agent identity
    agent_name: str = "Meera"
    agent_role: str = "Divyasree property consultant"

    # Demo
    max_session_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


def llm_provider_active(settings: Settings | None = None) -> str:
    """Resolve which provider is actually active."""
    settings = settings or get_settings()
    if settings.llm_provider == "groq":
        return "groq"
    if settings.llm_provider == "fallback":
        return "fallback"
    return "groq" if settings.groq_api_key else "fallback"
