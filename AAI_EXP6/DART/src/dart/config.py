from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    repository_root: str
    artifacts_dir: Path
    test_timeout_seconds: int
    max_test_output_chars: int


def get_settings() -> Settings:
    artifacts = Path(os.getenv("ARTIFACTS_DIR", str(PROJECT_ROOT / "artifacts"))).expanduser()
    if not artifacts.is_absolute():
        artifacts = (PROJECT_ROOT / artifacts).resolve()
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        repository_root=os.getenv("REPOSITORY_ROOT", str(PROJECT_ROOT / "sample_data" / "demo_repository")),
        artifacts_dir=artifacts,
        test_timeout_seconds=int(os.getenv("TEST_TIMEOUT_SECONDS", "120")),
        max_test_output_chars=int(os.getenv("MAX_TEST_OUTPUT_CHARS", "12000")),
    )
