import pytest

from app import routers_chat, routers_library
from app.assistant_service import AssistantUnavailable, IngestionError


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def ask(question, document_id, user_id, run_id):
        calls.append({"question": question, "run_id": run_id})
        return f"answer {len(calls)}", f"run-{len(calls)}"

    monkeypatch.setattr(routers_chat, "ask_assistant", ask)
    monkeypatch.setattr(routers_library, "index_document", lambda document_id: None)
    return calls


def test_chat_saves_history_and_resumes_the_run(client, signed_up, fake_llm):
    headers, _ = signed_up()
    first = client.post("/api/chat", json={"question": "What is in Pad Thai?", "document_id": "default-document"}, headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert body["answer"] == "answer 1" and body["quota"]["used"] == 1

    second = client.post("/api/chat", json={"question": "And tom yum?", "document_id": "default-document"}, headers=headers)
    assert second.json()["conversation_id"] == body["conversation_id"]
    assert fake_llm[1]["run_id"] == "run-1"  # resumed the same run

    history = client.get("/api/documents/default-document/conversation", headers=headers).json()
    assert history["conversation_id"] == body["conversation_id"]
    assert [m["role"] for m in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert history["messages"][0]["content"] == "What is in Pad Thai?"


def test_new_conversation_starts_fresh_and_history_is_kept(client, signed_up, fake_llm):
    headers, _ = signed_up()
    first = client.post("/api/chat", json={"question": "one", "document_id": "default-document"}, headers=headers).json()
    fresh = client.post("/api/chat", json={"question": "two", "document_id": "default-document", "new_conversation": True}, headers=headers).json()
    assert fresh["conversation_id"] != first["conversation_id"]
    assert fake_llm[1]["run_id"] is None
    latest = client.get("/api/documents/default-document/conversation", headers=headers).json()
    assert latest["conversation_id"] == fresh["conversation_id"]


def test_conversations_are_private(client, signed_up, fake_llm):
    alice, _ = signed_up("alice2@example.com")
    bob, _ = signed_up("bob2@example.com")
    client.post("/api/chat", json={"question": "secret", "document_id": "default-document"}, headers=alice)
    bob_view = client.get("/api/documents/default-document/conversation", headers=bob).json()
    assert bob_view["messages"] == []


def test_shared_quota_caps_all_users_together(client, signed_up, fake_llm, monkeypatch):
    monkeypatch.setenv("REQUEST_LIMIT", "2")
    from app.config import get_settings
    get_settings.cache_clear()
    alice, _ = signed_up("q1@example.com")
    bob, _ = signed_up("q2@example.com")

    assert client.post("/api/chat", json={"question": "a", "document_id": "default-document"}, headers=alice).status_code == 200
    assert client.post("/api/chat", json={"question": "b", "document_id": "default-document"}, headers=bob).status_code == 200
    blocked = client.post("/api/chat", json={"question": "c", "document_id": "default-document"}, headers=alice)
    assert blocked.status_code == 429
    assert "shared request limit of 2" in blocked.json()["detail"]
    assert client.get("/api/quota", headers=bob).json() == {"used": 2, "limit": 2, "remaining": 0}
    assert len(fake_llm) == 2  # the blocked request never reached the model
    get_settings.cache_clear()


def test_failed_question_gives_the_request_back(client, signed_up, monkeypatch):
    def failing(question, document_id, user_id, run_id):
        raise AssistantUnavailable("The language model service is unavailable right now.")
    monkeypatch.setattr(routers_chat, "ask_assistant", failing)
    headers, _ = signed_up()
    response = client.post("/api/chat", json={"question": "hello", "document_id": "default-document"}, headers=headers)
    assert response.status_code == 503
    assert client.get("/api/quota", headers=headers).json()["used"] == 0
    assert client.get("/api/documents/default-document/conversation", headers=headers).json()["messages"] == []


def test_ingestion_failure_on_chat_is_reported_as_422(client, signed_up, monkeypatch):
    def unreadable(question, document_id, user_id, run_id):
        raise IngestionError("This PDF could not be read.")
    monkeypatch.setattr(routers_chat, "ask_assistant", unreadable)
    headers, _ = signed_up()
    assert client.post("/api/chat", json={"question": "hi", "document_id": "default-document"}, headers=headers).status_code == 422
