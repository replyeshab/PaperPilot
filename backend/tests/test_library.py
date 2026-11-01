from app import routers_library
from app.assistant_service import IngestionError

PDF = b"%PDF-1.4\n% minimal test document\n%%EOF"


def test_default_sample_is_visible_but_not_deletable(client, signed_up):
    headers, _ = signed_up()
    docs = client.get("/api/documents", headers=headers).json()
    assert docs[0]["id"] == "default-document" and docs[0]["shared"] is True
    assert client.delete("/api/documents/default-document", headers=headers).status_code == 400


def test_documents_are_private_to_their_owner(client, signed_up, monkeypatch):
    monkeypatch.setattr(routers_library, "index_document", lambda document_id: None)
    alice, _ = signed_up("alice@example.com")
    bob, _ = signed_up("bob@example.com")

    created = client.post("/api/documents", json={"url": "https://example.com/alice-notes.pdf"}, headers=alice)
    assert created.status_code == 201
    doc_id = created.json()["id"]

    bob_docs = [d["id"] for d in client.get("/api/documents", headers=bob).json()]
    assert doc_id not in bob_docs
    assert client.get(f"/api/documents/{doc_id}/conversation", headers=bob).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 200


def test_upload_rejects_wrong_type_and_fake_pdf(client, signed_up, monkeypatch):
    monkeypatch.setattr(routers_library, "index_document", lambda document_id: None)
    headers, _ = signed_up()
    assert client.post("/api/documents/upload", files={"file": ("a.txt", b"hi", "text/plain")}, headers=headers).status_code == 415
    assert client.post("/api/documents/upload", files={"file": ("a.pdf", b"not a pdf", "application/pdf")}, headers=headers).status_code == 415
    ok = client.post("/api/documents/upload", files={"file": ("notes.pdf", PDF, "application/pdf")}, headers=headers)
    assert ok.status_code == 201 and ok.json()["source_type"] == "upload"


def test_unreadable_pdf_is_rolled_back_and_not_charged(client, signed_up, monkeypatch):
    def broken(document_id):
        raise IngestionError("This PDF could not be read.")
    monkeypatch.setattr(routers_library, "index_document", broken)
    headers, _ = signed_up()
    response = client.post("/api/documents", json={"url": "https://example.com/bad.pdf"}, headers=headers)
    assert response.status_code == 422
    assert client.get("/api/quota", headers=headers).json()["used"] == 0
    assert all(d["source"] != "https://example.com/bad.pdf" for d in client.get("/api/documents", headers=headers).json())
