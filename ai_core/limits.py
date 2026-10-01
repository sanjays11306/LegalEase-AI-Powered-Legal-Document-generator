"""Cost protection: input-size limits, a per-minute burst limiter and daily quotas.

Why it lives here and not only in the API route: the Streamlit UI can call generate_document() directly
(when the API is not running), so a limit placed only on POST /api/generate could be walked around.
Both entry points call check_and_consume() before spending Gemini tokens.

Environment (all optional):
  LEGALEASE_BURST_LIMIT         calls per user per minute          (default 5)
  LEGALEASE_DAILY_LIMIT         generations per user per day       (default 20)
  LEGALEASE_DAILY_REVIEW_LIMIT  AI reviews per user per day        (default 40)
  LEGALEASE_GLOBAL_DAILY_LIMIT  generations per day, all users     (default 500)  <- your spending cap
  LEGALEASE_GLOBAL_REVIEW_LIMIT AI reviews per day, all users      (default 1000)
The day rolls over at midnight India time (IST).
"""
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from .storage import connect

IST = timezone(timedelta(hours=5, minutes=30))
MAX_FIELD_CHARS = 4000      # any single form field
MAX_TOTAL_CHARS = 20000     # all form fields together
MAX_DOCUMENT_CHARS = 60000  # a document sent for AI review


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _seconds_to_midnight() -> int:
    now = datetime.now(IST)
    return int((now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1) - now).total_seconds())


# ------------------------------------------------------------------ input size
def check_input_size(details: dict | None, *extra: str) -> None:
    """Raise ValueError if the request is large enough to be abuse (each call is billed per token)."""
    values = [str(v) for v in (details or {}).values()] + [str(e) for e in extra]
    if any(len(v) > MAX_FIELD_CHARS for v in values):
        raise ValueError(f"A field is longer than {MAX_FIELD_CHARS:,} characters. Please shorten it.")
    if sum(len(v) for v in values) > MAX_TOTAL_CHARS:
        raise ValueError(f"The details are longer than {MAX_TOTAL_CHARS:,} characters in total. Please shorten them.")


# ------------------------------------------------------------------ burst limiter (in memory)
class BurstLimiter:
    """Sliding window: at most `max_calls` per `window` seconds for each key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, max_calls: int, window: float = 60.0) -> int:
        """Record a call. Returns 0 if allowed, otherwise the seconds to wait."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= window:
                q.popleft()
            if max_calls and len(q) >= max_calls:
                return max(1, int(window - (now - q[0])) + 1)
            q.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


burst = BurstLimiter()


# ------------------------------------------------------------------ daily quota (SQLite, survives restarts)
def _consume(owner: str, kind: str, limit: int) -> bool:
    """Atomically add 1 to today's counter unless it already reached `limit` (0 = unlimited)."""
    day = _today()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            row = con.execute("SELECT count FROM usage WHERE owner=? AND day=? AND kind=?", (owner, day, kind)).fetchone()
            used = row["count"] if row else 0
            if limit and used >= limit:
                con.execute("ROLLBACK")
                return False
            con.execute("INSERT INTO usage (owner, day, kind, count) VALUES (?,?,?,1) "
                        "ON CONFLICT(owner, day, kind) DO UPDATE SET count = count + 1", (owner, day, kind))
            con.execute("COMMIT")
            return True
        except Exception:
            con.execute("ROLLBACK")
            raise


def usage_today(owner: str, kind: str = "generate") -> int:
    with connect() as con:
        row = con.execute("SELECT count FROM usage WHERE owner=? AND day=? AND kind=?", (owner, _today(), kind)).fetchone()
    return row["count"] if row else 0


def daily_limit(kind: str = "generate") -> int:
    return _int_env("LEGALEASE_DAILY_REVIEW_LIMIT", 40) if kind == "review" else _int_env("LEGALEASE_DAILY_LIMIT", 20)


def check_and_consume(owner: str, kind: str = "generate") -> None:
    """Call once before every billable Gemini request. Raises RateLimitExceeded with a user-friendly message."""
    wait = burst.hit(f"{owner}:{kind}", _int_env("LEGALEASE_BURST_LIMIT", 5))
    if wait:
        raise RateLimitExceeded(f"Too many requests - please wait about {wait} seconds and try again.", wait)
    if not _consume(owner, kind, daily_limit(kind)):
        what = "AI reviews" if kind == "review" else "AI-drafted documents"
        raise RateLimitExceeded(f"You have reached today's limit of {daily_limit(kind)} {what}. "
                                "It resets at midnight (IST).", _seconds_to_midnight())
    global_limit = _int_env("LEGALEASE_GLOBAL_REVIEW_LIMIT", 1000) if kind == "review" else _int_env("LEGALEASE_GLOBAL_DAILY_LIMIT", 500)
    if not _consume("*", kind, global_limit):
        raise RateLimitExceeded("The service has reached its daily capacity. Please try again tomorrow.", _seconds_to_midnight())
