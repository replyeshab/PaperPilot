"""Small persistent registry for PDF URLs configured through the UI.

Phi's PDFUrlKnowledgeBase + PgVector2 remain responsible for ingestion and vector storage.
The registry only remembers which source URLs the user has configured.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "documents.json"
DEFAULT_URL = "https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf"

def _name(url: str) -> str:
    parsed = urlparse(url)
    last = parsed.path.rsplit("/", 1)[-1]
    name = re.sub(r"[-_]+", " ", last.rsplit(".", 1)[0] if "." in last else last).strip()
    return name or parsed.netloc or "PDF document"

def list_documents(default_url: str = DEFAULT_URL) -> list[dict]:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        rows = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            rows = []
    except (OSError, json.JSONDecodeError):
        rows = []
    if not rows:
        rows = [{"id": "default-document", "name": _name(default_url), "url": default_url, "status": "configured"}]
        save_documents(rows)
    return rows

def save_documents(rows: list[dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

def add_document(url: str, default_url: str = DEFAULT_URL) -> dict:
    rows = list_documents(default_url)
    for row in rows:
        if row.get("url") == url:
            return row
    row = {"id": str(uuid4()), "name": _name(url), "url": url, "status": "configured"}
    rows.append(row)
    save_documents(rows)
    return row

def add_uploaded_document(filename: str, stored_path: str, internal_url: str, default_url: str = DEFAULT_URL) -> dict:
    rows = list_documents(default_url)
    row = {"id": str(uuid4()), "name": _name(filename), "url": internal_url,
           "status": "configured", "local_path": stored_path, "source_type": "upload"}
    rows.append(row)
    save_documents(rows)
    return row

def remove_document(document_id: str, default_url: str = DEFAULT_URL) -> bool:
    rows = list_documents(default_url)
    removed = [row for row in rows if row.get("id") == document_id]
    updated = [row for row in rows if row.get("id") != document_id]
    if len(updated) == len(rows):
        return False
    for row in removed:
        local_path = row.get("local_path")
        if local_path:
            try:
                Path(local_path).unlink(missing_ok=True)
            except OSError:
                pass
    save_documents(updated)
    return True
