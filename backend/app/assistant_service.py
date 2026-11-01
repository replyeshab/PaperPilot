"""Compatibility wrapper around the project's existing Phi + PostgreSQL architecture."""
from __future__ import annotations
from typing import Any

from .config import get_settings
from .documents import list_documents

class AssistantUnavailable(RuntimeError):
    pass

def _extract_answer(result: Any) -> str:
    if isinstance(result, str):
        return result
    content = getattr(result, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(result, dict):
        value = result.get("content") or result.get("answer")
        if isinstance(value, str):
            return value
    text = str(result).strip()
    if not text or text.startswith("RunResponse("):
        raise AssistantUnavailable("The model returned an empty or unsupported response.")
    return text

def ask_assistant(question: str, user_id: str = "web-user", new_conversation: bool = False, document_id: str | None = None) -> tuple[str, str | None]:
    settings = get_settings()
    if not settings.groq_api_key:
        raise AssistantUnavailable("GROQ_API_KEY is missing. Add it to backend/.env and restart the backend.")
    # Keep the original framework and PostgreSQL storage/vector integrations.
    try:
        from phi.assistant import Assistant
        from phi.storage.assistant.postgres import PgAssistantStorage
        from phi.knowledge.pdf import PDFUrlKnowledgeBase
        from phi.vectordb.pgvector import PgVector2
    except ImportError as exc:
        raise AssistantUnavailable(
            "The installed Phidata package does not expose the legacy API used by this project. "
            "Install the project's pinned requirements or migrate the framework imports."
        ) from exc

    model = None
    model_errors = []
    for module_path, constructor_kwargs in (
        ("phi.llm.groq", {"model": settings.groq_model}),
        ("phi.llm.groq", {"id": settings.groq_model}),
        ("phi.model.groq", {"id": settings.groq_model}),
        ("phi.model.groq", {"model": settings.groq_model}),
    ):
        try:
            module = __import__(module_path, fromlist=["Groq"])
            model = module.Groq(**constructor_kwargs)
            break
        except (ImportError, TypeError, AttributeError) as exc:
            model_errors.append(exc)
    if model is None:
        raise AssistantUnavailable("Could not initialise the Groq model with this Phidata version. Verify the pinned framework/model API.") from model_errors[-1]

    docs = list_documents(settings.default_pdf_url)
    if document_id:
        docs = [item for item in docs if item.get("id") == document_id]
        if not docs:
            raise AssistantUnavailable("That document is no longer in your library. Refresh the page and select another document.")
    urls = [item["url"] for item in docs if item.get("url")]
    if not urls:
        raise AssistantUnavailable("Add a PDF source URL before asking questions.")

    try:
        # Keep each selected document in its own vector collection so retrieval does not
        # accidentally mix passages from unrelated PDFs.
        import re
        collection_suffix = re.sub(r"[^a-zA-Z0-9_]", "_", document_id) if document_id else "all_documents"
        collection_name = f"{settings.document_collection}_{collection_suffix}"[:60]
        knowledge_base = PDFUrlKnowledgeBase(
            urls=urls,
            vector_db=PgVector2(collection=collection_name, db_url=settings.database_url),
        )
        # load(recreate=False) should avoid re-creating the index on every question in supported versions.
        # Some legacy versions do not accept this argument, so retain compatibility.
        try:
            knowledge_base.load(recreate=False)
        except TypeError:
            knowledge_base.load()
        storage = PgAssistantStorage(table_name=settings.assistant_table, db_url=settings.database_url)
        run_id = None
        if not new_conversation:
            try:
                run_ids = storage.get_all_run_ids(user_id) or []
                if run_ids:
                    run_id = run_ids[0]
            except Exception:
                run_id = None
        assistant = Assistant(
            run_id=run_id,
            user_id=user_id,
            knowledge_base=knowledge_base,
            storage=storage,
            llm=model,
            show_tool_calls=False,
            search_knowledge=True,
            read_chat_history=True,
        )
        result = assistant.run(question)
        answer = _extract_answer(result)
        return answer, str(getattr(assistant, "run_id", run_id)) if getattr(assistant, "run_id", run_id) else None
    except AssistantUnavailable:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "connection" in message or "postgres" in message or "database" in message:
            raise AssistantUnavailable(
                "Could not connect to PostgreSQL. Start the database and verify DATABASE_URL in backend/.env."
            ) from exc
        raise AssistantUnavailable(f"The assistant could not complete this request: {exc.__class__.__name__}. Check backend logs.") from exc
