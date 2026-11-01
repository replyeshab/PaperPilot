"""One shared budget for paid calls (questions and document additions), across all users."""
from fastapi import HTTPException, status

from . import repository
from .config import get_settings
from .schemas import QuotaOut


def status_snapshot() -> QuotaOut:
    limit = get_settings().request_limit
    used = min(repository.quota_used(), limit)
    return QuotaOut(used=used, limit=limit, remaining=limit - used)


def reserve() -> None:
    limit = get_settings().request_limit
    if not repository.reserve_request(limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"The shared request limit of {limit} has been reached, so questions and uploads are paused. "
                   "You can still read your past conversations.",
        )


def release() -> None:
    repository.release_request()
