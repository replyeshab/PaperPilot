import pytest

from app import assistant_service as svc
from app.assistant_service import AssistantUnavailable


def test_collect_answer_joins_streamed_chunks():
    assert svc._collect_answer(iter(["Pad Thai ", "uses tamarind."])) == "Pad Thai uses tamarind."


def test_collect_answer_accepts_response_objects():
    class Chunk:
        def __init__(self, content):
            self.content = content
    assert svc._collect_answer([Chunk("Hello")]) == "Hello"


def test_collect_answer_rejects_empty_output():
    with pytest.raises(AssistantUnavailable):
        svc._collect_answer(iter(["   "]))


def test_collection_names_are_safe_and_short():
    name = svc._collection_name("ABC-123_xyz.with spaces" + "x" * 80)
    assert name == name.lower()
    assert all(ch.isalnum() or ch == "_" for ch in name)
    assert len(name) <= 60


def test_missing_groq_key_is_reported_clearly(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    monkeypatch.setattr(svc, "_model", None)
    with pytest.raises(AssistantUnavailable, match="GROQ_API_KEY"):
        svc._get_model()
    get_settings.cache_clear()
