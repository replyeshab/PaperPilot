from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from uuid import uuid4
from pydantic import HttpUrl
from urllib.parse import urlparse

from .assistant_service import AssistantUnavailable, ask_assistant
from .config import get_settings
from .documents import add_document, add_uploaded_document, list_documents, remove_document
from .schemas import AddDocumentRequest, ChatRequest, ChatResponse, DocumentResponse

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", description="PDF question answering with Phi, PostgreSQL and pgvector")
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}

@app.get("/api/documents", response_model=list[DocumentResponse])
def get_documents():
    return list_documents(settings.default_pdf_url)

@app.post("/api/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(payload: AddDocumentRequest):
    url = str(payload.url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Provide a valid HTTP or HTTPS PDF URL.")
    if not parsed.path.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="The source URL must point to a .pdf file.")
    try:
        return add_document(url, settings.default_pdf_url)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not save the document registry.") from exc


@app.post("/api/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...)):
    filename = (file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds the 20 MB upload limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid PDF.")
    stored_name = f"{uuid4().hex}.pdf"
    destination = UPLOAD_DIR / stored_name
    try:
        destination.write_bytes(content)
        internal_url = f"http://127.0.0.1:8000/files/{stored_name}"
        return add_uploaded_document(filename, str(destination), internal_url, settings.default_pdf_url)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save the uploaded PDF.") from exc

@app.get("/files/{filename}", include_in_schema=False)
def serve_uploaded_pdf(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=404, detail="File not found.")
    path = UPLOAD_DIR / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type="application/pdf", filename=safe_name)

@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str):
    if document_id == "default-document":
        raise HTTPException(status_code=400, detail="The default sample document cannot be removed from this demo.")
    if not remove_document(document_id, settings.default_pdf_url):
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": True, "id": document_id}

@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    try:
        answer, run_id = ask_assistant(payload.question.strip(), payload.user_id, payload.new_conversation, payload.document_id)
        return ChatResponse(answer=answer, user_id=payload.user_id, run_id=run_id)
    except AssistantUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected server error. Check backend logs.") from exc
