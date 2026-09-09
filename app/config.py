from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    auth_mode: str = "disabled"
    access_gate_enabled: bool = True
    access_max_active_users: int = 7
    access_session_ttl_minutes: int = 60
    database_url: str = "sqlite:///./storage/presentations.db"
    redis_url: str = "redis://redis:6379/0"
    storage_provider: str = "local"
    local_storage_path: Path = Path("storage/files")
    llm_provider: str = "gemini"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str = ""
    # Verified callable by the configured NVIDIA account; strong clean instruction output.
    nvidia_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nvidia_timeout_seconds: float = 120.0
    nvidia_debug_responses: bool = True
    nvidia_slide_by_slide_enabled: bool = True
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_key: str = ""
    gemini_model: str = "gemma-4-26b-a4b-it"
    gemini_timeout_seconds: float = 120.0
    gemini_debug_responses: bool = False
    gemini_max_output_tokens: int = 800
    # Configured from the rate limits shown in Google AI Studio. The gate uses
    # a shared rolling 60-second budget across all local generation jobs.
    gemini_tokens_per_minute: int = 16000
    gemini_requests_per_minute: int = 30
    gemini_queue_max_wait_seconds: float = 120.0
    # Entire decks are FIFO queued before slide-level model requests begin.
    # Keep this at one while a single API key/model is shared by testers.
    generation_max_concurrent_jobs: int = 1
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = ""
    ollama_fallback_enabled: bool = False
    ollama_debug_responses: bool = False
    image_provider: str = "none"  # "openai" enables topic-specific raster visuals
    image_base_url: str = "https://api.openai.com/v1"
    image_api_key: str = ""
    image_model: str = "gpt-image-1"
    max_generated_images_per_deck: int = 3
    file_retention_hours: int = 1
    cleanup_interval_minutes: int = 10
    unsplash_access_key: str = ""
    unsplash_base_url: str = "https://api.unsplash.com"
    max_agent_retries: int = 1
    max_job_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
