import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

from app.services import PipelineError

load_dotenv()


@dataclass(frozen=True)
class Settings:
    groq_api_key: Optional[str]
    groq_model: str
    allowed_origins: tuple
    max_upload_mb: int
    database_url: str
    upload_dir: str
    rate_limit_per_min: int


@lru_cache
def get_settings() -> Settings:
    origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        allowed_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./auditor.db"),
        upload_dir=os.getenv("UPLOAD_DIR", "uploads"),
        rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "5")),
    )


def require_groq_key() -> str:
    """Lazy key check: only raises when an LLM call is actually needed."""
    key = get_settings().groq_api_key
    if not key or key == "your_groq_api_key_here":
        raise PipelineError("The server is not configured with a Groq API key.")
    return key


@lru_cache
def get_async_groq():
    # pyrefly: ignore [missing-import]
    from groq import AsyncGroq

    return AsyncGroq(api_key=require_groq_key())