import ipaddress
import logging
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from . import quota, repository
from .assistant_service import AssistantUnavailable, IngestionError, forget_document, index_document
from .config import get_settings
from .db import DEFAULT_DOCUMENT_ID, get_engine
from .deps import ensure_ready, current_user
from .schemas import (AddDocumentRequest, ConversationResponse, DocumentResponse, HealthResponse, MessageOut,
                      QuotaOut)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
_index_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paperpilot-pdf-index")
_index_lock = threading.Lock()
_indexing_ids: set[str] = set()


def _points_to_internal_address(host: str) -> bool:
    """True when a URL host is, or resolves to, a loopback, private, link-local or otherwise non-public address.

    The server downloads PDF links itself, so without this check a user could make it fetch internal
    services (for example a cloud metadata endpoint) by submitting a link that ends in .pdf.
    If the name cannot be resolved here we let the downloader fail on its own.
    """
    try:
        candidates = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            candidates = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)]
        except (socket.gaierror, ValueError, UnicodeError):
            return False
    return any(not address.is_global for address in candidates)


def _document_out(row: dict) -> DocumentResponse:
    return DocumentResponse(
        id=row["id"], name=row["name"], source_type=row["source_type"], source=row["source_label"],
        shared=row["owner_id"] is None, created_at=row["created_at"], index_status=row.get("index_status", "ready"),
        index_error=row.get("index_error"),
    )


def _index_or_rollback(document_id: str, owner_id: str) -> None:
    """Index a freshly added document. On failure, remove it and give the request back."""
    try:
        index_document(document_id)
    except IngestionError as exc:
        repository.delete_document(document_id, owner_id)
        quota.release()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AssistantUnavailable as exc:
        repository.delete_document(document_id, owner_id)
        quota.release()
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _index_uploaded_pdf(document_id: str) -> None:
    try:
        index_document(document_id)
        repository.set_document_index_status(document_id, "ready")
    except Exception as exc:
        logger.exception("Background indexing failed for document %s", document_id)
        try:
            message = str(exc) if isinstance(exc, (IngestionError, AssistantUnavailable)) else (
                "PaperPilot could not index this PDF. Check the server logs and try again."
            )
            repository.set_document_index_status(document_id, "error", message[:500])
        except Exception:
            logger.exception("Could not save indexing failure for document %s", document_id)
        try:
            quota.release()
        except Exception:
            logger.exception("Could not refund the upload quota for document %s", document_id)
    finally:
        with _index_lock:
            _indexing_ids.discard(document_id)


def _schedule_pdf_indexing(document_id: str):
    with _index_lock:
        if document_id in _indexing_ids:
            return None
        _indexing_ids.add(document_id)
    try:
        return _index_executor.submit(_index_uploaded_pdf, document_id)
    except Exception:
        with _index_lock:
            _indexing_ids.discard(document_id)
        raise


def _queue_pdf_indexing(document_id: str) -> None:
    # FastAPI sends the upload response before running this task. Waiting here
    # keeps the single indexing worker serial without holding up the user.
    future = _schedule_pdf_indexing(document_id)
    if future is not None:
        future.result()


def resume_pending_uploads() -> None:
    """Resume uploads that were still being indexed when the API process restarted."""
    for document_id in repository.list_indexing_uploads():
        _schedule_pdf_indexing(document_id)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unreachable"
    return HealthResponse(status="ok" if database == "ok" else "degraded", database=database,
                          environment=get_settings().environment)


@router.get("/quota", response_model=QuotaOut)
def get_quota(_: dict = Depends(current_user)) -> QuotaOut:
    return quota.status_snapshot()


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(user: dict = Depends(current_user)) -> list[DocumentResponse]:
    return [_document_out(row) for row in repository.list_documents(user["id"])]


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def add_document(payload: AddDocumentRequest, user: dict = Depends(current_user)) -> DocumentResponse:
    url = str(payload.url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Provide a valid HTTP or HTTPS PDF URL.")
    if not parsed.path.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="The source URL must point to a .pdf file.")

    if _points_to_internal_address(parsed.hostname or ""):
        raise HTTPException(status_code=422, detail="That link points to a private or internal address. Use a public PDF link.")

    existing = repository.find_visible_url(user["id"], url)
    if existing:
        return _document_out(existing)  # already in the library: no charge

    quota.reserve()
    try:
        row = repository.add_document(user["id"], repository.display_name(url), "url", url, None)
    except Exception:
        quota.release()  # the budget unit was taken but nothing was stored
        raise
    _index_or_rollback(row["id"], user["id"])
    return _document_out(repository.get_document(row["id"], user["id"]))


@router.post("/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                          user: dict = Depends(current_user)) -> DocumentResponse:
    original = (file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1] or "document.pdf"
    if not original.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")

    limit = get_settings().max_upload_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {get_settings().max_upload_mb} MB upload limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid PDF.")

    await run_in_threadpool(quota.reserve)
    try:
        row = await run_in_threadpool(
            repository.add_document, user["id"], repository.display_name(original), "upload", original, content,
            index_status="indexing")
    except Exception:
        await run_in_threadpool(quota.release)
        raise
    background_tasks.add_task(_queue_pdf_indexing, row["id"])
    return _document_out(row)


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user: dict = Depends(current_user)) -> dict:
    if document_id == DEFAULT_DOCUMENT_ID:
        raise HTTPException(status_code=400, detail="The sample document cannot be removed.")
    run_ids = repository.list_run_ids(document_id)
    if not repository.delete_document(document_id, user["id"]):
        raise HTTPException(status_code=404, detail="Document not found.")
    forget_document(document_id, run_ids)
    return {"deleted": True, "id": document_id}


@router.get("/documents/{document_id}/conversation", response_model=ConversationResponse)
def get_conversation(document_id: str, user: dict = Depends(current_user)) -> ConversationResponse:
    if repository.get_document(document_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    conversation = repository.latest_conversation(user["id"], document_id)
    if conversation is None:
        return ConversationResponse(conversation_id=None, messages=[])
    rows = repository.list_messages(conversation["id"])
    return ConversationResponse(
        conversation_id=conversation["id"],
        messages=[MessageOut(id=r["id"], role=r["role"], content=r["content"], created_at=r["created_at"]) for r in rows],
    )
