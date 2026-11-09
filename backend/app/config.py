from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECRET = "change-me-in-env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2"
    cheap_llm: str = "ollama"  # "ollama": short jobs (test inputs) use the local model; "groq": everything hosted
    cheap_timeout_s: int = 150
    llm_cache: bool = True  # identical prompts reuse the stored answer (saves quota during benchmarks)

    # Auth
    admin_username: str = "admin"
    admin_password: str = ""
    session_secret: str = DEFAULT_SECRET
    session_max_age_s: int = 12 * 3600
    cookie_secure: bool = False  # set true when served over HTTPS
    login_attempts_per_minute: int = 5

    # Sandbox: "docker" (isolated, default) or "local" (runs on the host; development only)
    sandbox: str = "docker"
    sandbox_image: str = "rust-migrator-sandbox:2"
    sandbox_memory: str = "1536m"
    sandbox_cpus: str = "2"
    sandbox_pids: int = 256

    # Limits
    max_concurrent_jobs: int = 2
    max_upload_bytes: int = 1_000_000
    max_files: int = 60
    max_file_chars: int = 100_000
    run_timeout_s: int = 20
    build_timeout_s: int = 300
    max_output_bytes: int = 1_000_000

    # Pipeline budgets
    # Benchmark switches, comma separated: contract, targeting, minimize, repair, unit (turn a feature off)
    ablate: str = ""
    unit_tests: bool = True  # function-level verification after the program-level check passes
    parallel_translate: int = 3  # modules translated at the same time (LLM calls only)
    max_module_fix_attempts: int = 3
    max_verify_attempts: int = 4
    coverage_target: float = 0.95
    max_tests: int = 40
    exploration_runs: int = 80
    targeted_rounds: int = 2

    def off(self, feature: str) -> bool:
        return feature in {x.strip() for x in self.ablate.split(",")}


settings = Settings()


def config_problems(s: Settings = settings) -> list[str]:
    """Settings that make the app unsafe to start."""
    problems = []
    if not s.admin_password:
        problems.append("ADMIN_PASSWORD is empty")
    if s.session_secret == DEFAULT_SECRET or len(s.session_secret) < 16:
        problems.append("SESSION_SECRET must be set to a random string of at least 16 characters")
    if s.sandbox not in ("docker", "local"):
        problems.append("SANDBOX must be 'docker' or 'local'")
    return problems
