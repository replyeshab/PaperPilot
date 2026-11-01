"""Database schema and engine. Tables are created idempotently on first use."""
from functools import lru_cache

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, LargeBinary, MetaData, String, Table, Text,
                        create_engine, text)

from .config import get_settings

metadata = MetaData()
DEFAULT_DOCUMENT_ID = "default-document"

users = Table(
    "users", metadata,
    Column("id", String(36), primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

sessions = Table(
    "sessions", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

documents = Table(
    "documents", metadata,
    Column("id", String(36), primary_key=True),
    # NULL owner means a shared document (the sample PDF) visible to everyone.
    Column("owner_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True),
    Column("name", String(200), nullable=False),
    Column("source_type", String(20), nullable=False),  # "url" or "upload"
    Column("source_label", Text, nullable=False),        # the URL, or the original file name
    Column("content", LargeBinary, nullable=True),       # uploaded PDF bytes
    Column("created_at", DateTime(timezone=True), nullable=False),
)

conversations = Table(
    "conversations", metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("document_id", String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("run_id", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

messages = Table(
    "messages", metadata,
    Column("id", String(36), primary_key=True),
    Column("conversation_id", String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("role", String(10), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# One row holding the shared request counter for all users.
request_quota = Table(
    "request_quota", metadata,
    Column("key", String(50), primary_key=True),
    Column("used", Integer, nullable=False, default=0),
)


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def create_schema(connection) -> None:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    metadata.create_all(connection)
