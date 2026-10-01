"""Shared test setup: every test run gets its own empty database and no real credentials or tight limits."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB", str(tmp_path / "test.db"))
    for k in ("LEGALEASE_USERS", "LEGALEASE_API_KEYS", "LEGALEASE_REQUIRE_LOGIN", "LEGALEASE_API_URL",
              "LEGALEASE_DAILY_LIMIT", "LEGALEASE_DAILY_REVIEW_LIMIT", "LEGALEASE_GLOBAL_DAILY_LIMIT",
              "LEGALEASE_GLOBAL_REVIEW_LIMIT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LEGALEASE_BURST_LIMIT", "1000")
    from ai_core.limits import burst
    burst.reset()
