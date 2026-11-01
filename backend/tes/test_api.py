from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_rejects_non_pdf_url():
    response = client.post("/api/documents", json={"url": "https://example.com/not-a-pdf.html"})
    assert response.status_code == 422

def test_chat_rejects_empty_question():
    response = client.post("/api/chat", json={"question": ""})
    assert response.status_code == 422


def test_rejects_non_pdf_upload():
    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 415
