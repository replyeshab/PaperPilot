from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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


def _document_out(row: dict) -> DocumentResponse:
    return DocumentResponse(
        id=row["id"], name=row["name"], source_type=row["source_type"], source=row["source_label"],
        shared=row["owner_id"] is None, created_at=row["created_at"],
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

    existing = repository.find_visible_url(user["id"], url)
    if existing:
        return _document_out(existing)  # already in the library: no charge

    quota.reserve()
    row = repository.add_document(user["id"], repository.display_name(url), "url", url, None)
    _index_or_rollback(row["id"], user["id"])
    return _document_out(repository.get_document(row["id"], user["id"]))


@router.post("/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), user: dict = Depends(current_user)) -> DocumentResponse:
    original = (file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1] or "document.pdf"
    if not original.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")

    limit = get_settings().max_upload_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {get_settings().max_upload_mb} MB upload limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid PDF.")

    quota.reserve()
    row = repository.add_document(user["id"], repository.display_name(original), "upload", original, content)
    await run_in_threadpool(_index_or_rollback, row["id"], user["id"])
    return _document_out(repository.get_document(row["id"], user["id"]))


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user: dict = Depends(current_user)) -> dict:
    if document_id == DEFAULT_DOCUMENT_ID:
        raise HTTPException(status_code=400, detail="The sample document cannot be removed.")
    if not repository.delete_document(document_id, user["id"]):
        raise HTTPException(status_code=404, detail="Document not found.")
    forget_document(document_id)
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
