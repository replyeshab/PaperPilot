"""Request dependencies: authentication, login throttling and the shared quota."""
import threading
import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import repository
from .config import get_settings
from .security import hash_token

_bearer = HTTPBearer(auto_error=False)


def ensure_ready() -> None:
    repository.ensure_schema()


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _: None = Depends(ensure_ready),
) -> tuple[dict, str]:
    """Returns (user, token_hash). Raises 401 when the token is missing, unknown or expired."""
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                 detail="Please sign in to continue.",
                                 headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    token_hash = hash_token(credentials.credentials)
    user = repository.get_user_for_session(token_hash)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Your session has expired. Please sign in again.",
                            headers={"WWW-Authenticate": "Bearer"})
    return user, token_hash


def current_user(session: tuple[dict, str] = Depends(current_session)) -> dict:
    return session[0]


def client_ip(request: Request) -> str:
    """Render and most proxies append the real client address, so the last X-Forwarded-For entry is trustworthy.
    The first entry is supplied by the client and can be forged."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class LoginThrottle:
    """Counts failed sign-ins per IP and per email. In-memory, so it is per server instance."""

    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self._window
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]
        return self._failures[key]

    def blocked(self, ip: str, email: str) -> bool:
        with self._lock:
            return len(self._recent(f"ip:{ip}")) >= self._max or len(self._recent(f"email:{email}")) >= self._max

    def record_failure(self, ip: str, email: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures[f"ip:{ip}"].append(now)
            self._failures[f"email:{email}"].append(now)

    def record_success(self, email: str) -> None:
        with self._lock:
            self._failures.pop(f"email:{email}", None)


_throttle: LoginThrottle | None = None


def login_throttle() -> LoginThrottle:
    global _throttle
    if _throttle is None:
        settings = get_settings()
        _throttle = LoginThrottle(settings.login_max_failures, settings.login_window_seconds)
    return _throttle
