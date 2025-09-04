import os

import tiktoken

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
os.environ.setdefault("WEBHOOK_VERIFY_TOKEN", "test")
os.environ.setdefault("WH_TOKEN", "test")
os.environ.setdefault("WH_PHONE_ID", "1")
os.environ.setdefault("X_ADMIN_TOKEN", "test")

from api.ai import count_tokens
from api.config import settings


def test_count_tokens_growth() -> None:
    assert tiktoken is not None
    small = count_tokens("abc", settings.OPENAI_MODEL)
    large = count_tokens("a" * 1000, settings.OPENAI_MODEL)
    assert isinstance(small, int) and small >= 1
    assert small < large
