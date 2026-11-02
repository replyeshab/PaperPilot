"""All database access. Routes and services call these functions instead of writing SQL."""
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .db import (DEFAULT_DOCUMENT_ID, conversations, create_schema, documents, get_engine, messages,
                 request_quota, sessions, users)

logger = logging.getLogger(__name__)
QUOTA_KEY = "requests"
_schema_ready = False
_schema_lock = threading.Lock()


class EmailTaken(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


def display_name(raw: str) -> str:
    """'my-research_paper.pdf' or a URL path becomes 'my research paper'."""
    path = urlparse(raw).path if raw.startswith(("http://", "https://")) else raw
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[-_]+", " ", stem).strip()[:120] or "PDF document"


def ensure_schema() -> None:
    """Create tables, the vector extension, the quota row and the shared sample document once."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        settings = get_settings()
        with get_engine().begin() as connection:
            create_schema(connection)
            connection.execute(
                pg_insert(request_quota).values(key=QUOTA_KEY, used=0).on_conflict_do_nothing()
            )
            connection.execute(
                pg_insert(documents).values(
                    id=DEFAULT_DOCUMENT_ID,
                    owner_id=None,
                    name=display_name(settings.default_pdf_url),
                    source_type="url",
                    source_label=settings.default_pdf_url,
                    content=None,
                    created_at=now(),
                ).on_conflict_do_nothing()
            )
        _schema_ready = True


# ---- users and sessions ------------------------------------------------------

def create_user(email: str, password_hash: str) -> dict:
    user = {"id": new_id(), "email": email, "password_hash": password_hash, "created_at": now()}
    try:
        with get_engine().begin() as connection:
            connection.execute(insert(users).values(**user))
    except IntegrityError as exc:
        raise EmailTaken() from exc
    return user


def get_user_by_email(email: str) -> dict | None:
    with get_engine().connect() as connection:
        row = connection.execute(select(users).where(users.c.email == email)).mappings().first()
    return dict(row) if row else None


def create_session(user_id: str, token_hash: str, ttl_days: int) -> None:
    created = now()
    with get_engine().begin() as connection:
        connection.execute(insert(sessions).values(
            token_hash=token_hash, user_id=user_id, created_at=created,
            expires_at=created + timedelta(days=ttl_days),
        ))


def get_user_for_session(token_hash: str) -> dict | None:
    query = (
        select(users.c.id, users.c.email)
        .join(sessions, sessions.c.user_id == users.c.id)
        .where(sessions.c.token_hash == token_hash, sessions.c.expires_at > now())
    )
    with get_engine().connect() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def delete_session(token_hash: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.token_hash == token_hash))


# ---- documents ----------------------------------------------------------------

_DOCUMENT_COLUMNS = (documents.c.id, documents.c.name, documents.c.source_type, documents.c.source_label,
                     documents.c.owner_id, documents.c.index_status, documents.c.created_at)


def _visible_to(user_id: str):
    return (documents.c.owner_id.is_(None)) | (documents.c.owner_id == user_id)


def list_documents(user_id: str) -> list[dict]:
    query = (select(*_DOCUMENT_COLUMNS).where(_visible_to(user_id))
             .order_by(documents.c.owner_id.is_(None).desc(), documents.c.created_at.desc()))
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def list_indexing_uploads() -> list[str]:
    query = select(documents.c.id).where(
        documents.c.source_type == "upload", documents.c.index_status == "indexing")
    with get_engine().connect() as connection:
        return list(connection.execute(query).scalars())


def set_document_index_status(document_id: str, index_status: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(update(documents).where(documents.c.id == document_id)
                           .values(index_status=index_status))


def get_document(document_id: str, user_id: str) -> dict | None:
    query = select(*_DOCUMENT_COLUMNS).where(documents.c.id == document_id, _visible_to(user_id))
    with get_engine().connect() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def get_document_name(document_id: str) -> str | None:
    with get_engine().connect() as connection:
        return connection.execute(select(documents.c.name).where(documents.c.id == document_id)).scalar_one_or_none()


def get_document_with_content(document_id: str) -> dict | None:
    """Used only by the indexing code, which needs the uploaded bytes."""
    with get_engine().connect() as connection:
        row = connection.execute(select(documents).where(documents.c.id == document_id)).mappings().first()
    return dict(row) if row else None


def find_visible_url(user_id: str, url: str) -> dict | None:
    query = select(*_DOCUMENT_COLUMNS).where(
        documents.c.source_type == "url", documents.c.source_label == url, _visible_to(user_id))
    with get_engine().connect() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def add_document(owner_id: str, name: str, source_type: str, source_label: str,
                 content: bytes | None, index_status: str = "ready") -> dict:
    row = {"id": new_id(), "owner_id": owner_id, "name": name, "source_type": source_type,
           "source_label": source_label, "content": content, "index_status": index_status, "created_at": now()}
    with get_engine().begin() as connection:
        connection.execute(insert(documents).values(**row))
    return {k: v for k, v in row.items() if k != "content"}


def delete_document(document_id: str, owner_id: str) -> bool:
    """Only the owner can delete, so the shared sample document is never removed."""
    with get_engine().begin() as connection:
        result = connection.execute(delete(documents).where(
            documents.c.id == document_id, documents.c.owner_id == owner_id))
    return result.rowcount == 1


# ---- conversations and messages -------------------------------------------------

def create_conversation(user_id: str, document_id: str) -> str:
    conversation_id = new_id()
    with get_engine().begin() as connection:
        connection.execute(insert(conversations).values(
            id=conversation_id, user_id=user_id, document_id=document_id, run_id=None, created_at=now()))
    return conversation_id


def latest_conversation(user_id: str, document_id: str) -> dict | None:
    query = (select(conversations).where(conversations.c.user_id == user_id,
                                         conversations.c.document_id == document_id)
             .order_by(conversations.c.created_at.desc()).limit(1))
    with get_engine().connect() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def set_conversation_run(conversation_id: str, run_id: str | None) -> None:
    with get_engine().begin() as connection:
        connection.execute(update(conversations).where(conversations.c.id == conversation_id)
                           .values(run_id=run_id))


def add_messages(conversation_id: str, pairs: list[tuple[str, str]]) -> list[dict]:
    rows = [{"id": new_id(), "conversation_id": conversation_id, "role": role, "content": content, "created_at": now()}
            for role, content in pairs]
    with get_engine().begin() as connection:
        connection.execute(insert(messages), rows)
    return rows


def list_messages(conversation_id: str) -> list[dict]:
    query = select(messages).where(messages.c.conversation_id == conversation_id).order_by(messages.c.created_at)
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


# ---- shared request quota --------------------------------------------------------

def quota_used() -> int:
    with get_engine().connect() as connection:
        return connection.execute(select(request_quota.c.used).where(request_quota.c.key == QUOTA_KEY)).scalar_one()


def reserve_request(limit: int) -> bool:
    """Atomically take one unit of the shared budget. The WHERE clause makes this race-free."""
    statement = (update(request_quota)
                 .where(request_quota.c.key == QUOTA_KEY, request_quota.c.used < limit)
                 .values(used=request_quota.c.used + 1))
    with get_engine().begin() as connection:
        return connection.execute(statement).rowcount == 1


def release_request() -> None:
    """Give a unit back when the request failed before producing an answer."""
    statement = (update(request_quota).where(request_quota.c.key == QUOTA_KEY, request_quota.c.used > 0)
                 .values(used=request_quota.c.used - 1))
    with get_engine().begin() as connection:
        connection.execute(statement)
