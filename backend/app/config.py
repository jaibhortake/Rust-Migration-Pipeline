from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2"
    admin_username: str = "admin"
    admin_password: str = ""
    session_secret: str = "change-me-in-env"

    max_compile_attempts: int = 4
    max_verify_attempts: int = 3
    run_timeout_s: int = 20
    build_timeout_s: int = 180
    max_output_bytes: int = 1_000_000


settings = Settings()
