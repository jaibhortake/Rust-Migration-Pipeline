import os
from pathlib import Path

# Settings must be valid before app modules import them.
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-secret-0123456789abcdef")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ["LLM_CACHE"] = "false"
os.environ["MIGRATOR_DB"] = ":memory:"

import pytest  # noqa: E402

from app import db  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture(autouse=True)
def memory_db():
    db._conn = None
    db.connect(":memory:")
    yield
    db._conn = None


def load_dir(name: str) -> dict[str, str]:
    d = SAMPLES / "projects" / name
    return {str(p.relative_to(d)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in d.rglob("*") if p.is_file()}
