"""Session cookies that expire, and a login rate limiter."""

import hmac
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

COOKIE = "session"
_signer = URLSafeTimedSerializer(settings.session_secret, salt="session")


def issue_token(username: str) -> str:
    return _signer.dumps(username)


def token_user(token: str | None, max_age: int | None = None) -> str | None:
    if not token:
        return None
    try:
        user = _signer.loads(token, max_age=max_age or settings.session_max_age_s)
    except (BadSignature, SignatureExpired):
        return None
    return user if user == settings.admin_username else None


def check_password(username: str, password: str) -> bool:
    if not settings.admin_password:
        return False
    u = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    p = hmac.compare_digest(password.encode(), settings.admin_password.encode())
    return u and p


class RateLimiter:
    """Sliding one-minute window per key."""

    def __init__(self, per_minute: int, clock=time.monotonic):
        self.per_minute, self.clock = per_minute, clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self.clock()
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True


login_limiter = RateLimiter(settings.login_attempts_per_minute)


def require_user(request: Request) -> str:
    user = token_user(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "not logged in")
    return user
