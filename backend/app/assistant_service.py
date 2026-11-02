
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from typing import Any

from . import repository
from .config import get_settings

logger = logging.getLogger(__name__)


class AssistantUnavailable(RuntimeError):
    """A configuration, dependency or infrastructure problem. Safe to show the user."""


class IngestionError(RuntimeError):
    """The PDF could not be downloaded, parsed, or indexed."""


_DB_HINTS = ("connection", "postgres", "database", "operationalerror", "could not connect")
_EMBEDDING_MODULES = ("fastembed", "openai", "onnxruntime")
_cache_lock = threading.Lock()
_doc_locks: dict[str, threading.Lock] = {}
_knowledge_bases: dict[str, Any] = {}
_model: Any = None
_storage: Any = None
_embedder: Any = None


def _doc_lock(document_id: str) -> threading.Lock:
    with _cache_lock:
        return _doc_locks.setdefault(document_id, threading.Lock())


def _collection_name(document_id: str) -> str:
    settings = get_settings()
    safe = re.sub(r"[^a-z0-9]", "_", document_id.lower())
    return f"{settings.document_collection}_{safe}"[:60]


def _is_database_error(exc: BaseException) -> bool:
    """Return True for actual database connectivity errors, not every SQLAlchemy error."""
    module = type(exc).__module__ or ""
    message = str(exc).lower()
    original = getattr(exc, "orig", None)
    original_module = (type(original).__module__ or "") if original is not None else ""
    return (
        module.startswith("psycopg")
        or original_module.startswith("psycopg")
        or any(hint in message for hint in _DB_HINTS)
    )

def _is_embedding_error(exc: BaseException) -> bool:
    module = type(exc).__module__ or ""
    return (isinstance(exc, ImportError) or module.startswith(_EMBEDDING_MODULES)
            or "could not load model" in str(exc).lower())


def _get_embedder() -> Any:
    global _embedder
    if _embedder is not None:
        return _embedder

    settings = get_settings()
    provider = settings.embedder.lower()
    if provider == "auto":
        provider = "openai" if settings.openai_api_key else "fastembed"

    try:
        if provider == "openai":
            if not settings.openai_api_key:
                raise AssistantUnavailable("EMBEDDER=openai needs OPENAI_API_KEY on the server.")
            from phi.embedder.openai import OpenAIEmbedder

            options: dict[str, Any] = {"api_key": settings.openai_api_key}
            if settings.embedding_model:
                options["model"] = settings.embedding_model
            _embedder = OpenAIEmbedder(**options)

        elif provider == "fastembed":
            from fastembed import TextEmbedding
            from phi.embedder.fastembed import FastEmbedEmbedder
            from pydantic import PrivateAttr

            class SafeFastEmbedEmbedder(FastEmbedEmbedder):
                """Fix Phidata 2.7.10's nested output by requesting one text at a time."""

                _client: Any = PrivateAttr(default=None)

                def get_embedding(self, text: str) -> list[float]:
                    if self._client is None:
                        self._client = TextEmbedding(model_name=self.model)


                    vector = next(self._client.embed([text]))
                    if hasattr(vector, "tolist"):
                        vector = vector.tolist()
                    return [float(value) for value in vector]

            options = (
                {"model": settings.embedding_model}
                if settings.embedding_model
                else {}
            )
            _embedder = SafeFastEmbedEmbedder(**options)

        else:
            raise AssistantUnavailable(
                f"Unknown EMBEDDER '{settings.embedder}'. Use auto, openai or fastembed."
            )
    except ImportError as exc:
        raise AssistantUnavailable(
            f"The {provider} embedder is not installed on the server."
        ) from exc

    return _embedder

def _get_model() -> Any:
    global _model
    settings = get_settings()
    if not settings.groq_api_key:
        raise AssistantUnavailable("GROQ_API_KEY is not configured on the server.")
    if _model is None:
        try:
            from phi.llm.groq import Groq
        except ImportError as exc:
            raise AssistantUnavailable("The Phidata Groq integration is not installed.") from exc
        _model = Groq(model=settings.groq_model, api_key=settings.groq_api_key)
    return _model


def _get_storage() -> Any:
    global _storage
    if _storage is None:
        from phi.storage.assistant.postgres import PgAssistantStorage
        settings = get_settings()
        _storage = PgAssistantStorage(table_name=settings.assistant_table, db_url=settings.database_url)
    return _storage


def _build_knowledge_base(document_id: str, local_path: str | None, url: str | None) -> Any:
    from phi.knowledge.pdf import PDFKnowledgeBase, PDFUrlKnowledgeBase
    from phi.vectordb.pgvector import PgVector2

    settings = get_settings()
    vector_db = PgVector2(collection=_collection_name(document_id), db_url=settings.database_url,
                          embedder=_get_embedder())
    if local_path:
        return PDFKnowledgeBase(path=local_path, vector_db=vector_db)
    return PDFUrlKnowledgeBase(urls=[url], vector_db=vector_db)


def index_document(document_id: str) -> None:
    """Download or parse, embed and store a document once. Raises IngestionError or AssistantUnavailable."""
    with _doc_lock(document_id):
        if document_id in _knowledge_bases:
            return
        document = repository.get_document_with_content(document_id)
        if document is None:
            raise IngestionError("This document no longer exists.")

        temp_path = None
        try:
            if document["source_type"] == "upload":
                handle, temp_path = tempfile.mkstemp(suffix=".pdf")
                with os.fdopen(handle, "wb") as fh:
                    fh.write(document["content"] or b"")
                knowledge_base = _build_knowledge_base(document_id, local_path=temp_path, url=None)
            else:
                knowledge_base = _build_knowledge_base(document_id, local_path=None, url=document["source_label"])
            
            knowledge_base.load(recreate=False)
        except AssistantUnavailable:
            raise
        except Exception as exc:
            if _is_database_error(exc):
                logger.exception("Database error while indexing document %s", document_id)
                raise AssistantUnavailable("The database is unreachable. Please try again shortly.") from exc
            if _is_embedding_error(exc):
                logger.exception("Embedding failed while indexing document %s", document_id)
                raise AssistantUnavailable(
                    "The embedding service failed. Check OPENAI_API_KEY, or the FastEmbed model download on the server."
                ) from exc
            logger.exception("Failed to index document %s", document_id)
            raise IngestionError(
                "This PDF could not be read. Check that the link is public and the file contains "
                "selectable text (scanned images are not supported)."
            ) from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        _knowledge_bases[document_id] = knowledge_base


def forget_document(document_id: str) -> None:
    with _cache_lock:
        _knowledge_bases.pop(document_id, None)


def _collect_answer(output: Any) -> str:
    """Phidata's run() yields text chunks; with stream=False it yields the full answer once.

    Calling run() without stream=False returns a generator, which must never reach the user.
    """
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", item)
        if isinstance(content, str):
            parts.append(content)
    answer = "".join(parts).strip()
    if not answer:
        raise AssistantUnavailable(
            "The language model returned no answer. Check GROQ_API_KEY and the Groq service status, then try again."
        )
    return answer


def _run_once(question: str, document_id: str, user_id: str, run_id: str | None) -> tuple[str, str | None]:
    from phi.assistant import Assistant

    index_document(document_id)
    document_name = repository.get_document_name(document_id)
    if document_name is None:
        raise IngestionError("This document no longer exists.")
    assistant = Assistant(
        run_id=run_id,
        user_id=user_id,
        knowledge_base=_knowledge_bases[document_id],
        storage=_get_storage(),
        llm=_get_model(),
        instructions=[
            f"Answer about the currently selected PDF, {document_name!r}, only.",
            "Use evidence retrieved from this PDF for document-specific claims. Ignore content from any other PDF or conversation.",
            "If this PDF does not contain enough information, say so instead of guessing or using another document.",
        ],
        show_tool_calls=False,
        search_knowledge=True,
      
        add_chat_history_to_messages=True,
        num_history_messages=8,
    )
    answer = _collect_answer(assistant.run(question, stream=False))
    return answer, getattr(assistant, "run_id", None)


def ask_assistant(question: str, document_id: str, user_id: str, run_id: str | None) -> tuple[str, str | None]:
    """Answer a question about one document. Returns (answer, run_id to resume next time)."""
    try:
        return _run_once(question, document_id, user_id, run_id)
    except (AssistantUnavailable, IngestionError):
        raise
    except Exception as exc:
        if run_id:
            
            logger.warning("Could not resume run %s; starting a new one", run_id, exc_info=True)
            try:
                return _run_once(question, document_id, user_id, None)
            except Exception as retry_exc:
                exc = retry_exc
        raise _translate_chat_error(exc) from exc


def _translate_chat_error(exc: Exception) -> AssistantUnavailable:
    if _is_database_error(exc):
        return AssistantUnavailable("The database is unreachable. Please try again shortly.")
    if type(exc).__module__.startswith("groq"):
        return AssistantUnavailable("The language model service is unavailable right now. Please try again shortly.")
    logger.exception("Unexpected error while answering a question")
    return AssistantUnavailable("The assistant could not complete this request. Please try again.")
