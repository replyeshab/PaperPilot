from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from . import quota, repository
from .assistant_service import AssistantUnavailable, IngestionError, ask_assistant
from .deps import current_user
from .schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api")


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: dict = Depends(current_user)) -> ChatResponse:
    document = repository.get_document(payload.document_id, user["id"])
    if document is None:
        raise HTTPException(status_code=404, detail="That document is no longer in your library. Pick another one.")

    conversation = None if payload.new_conversation else repository.latest_conversation(user["id"], document["id"])
    run_id = conversation["run_id"] if conversation else None
    if conversation is None:
        conversation_id = repository.create_conversation(user["id"], document["id"])
    else:
        conversation_id = conversation["id"]

    question = payload.question.strip()
    quota.reserve()
    try:
        answer, new_run_id = await run_in_threadpool(ask_assistant, question, document["id"], user["id"], run_id)
    except IngestionError as exc:
        quota.release()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AssistantUnavailable as exc:
        quota.release()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        quota.release()
        raise

    repository.add_messages(conversation_id, [("user", question), ("assistant", answer)])
    repository.set_conversation_run(conversation_id, new_run_id)
    return ChatResponse(answer=answer, conversation_id=conversation_id, document_id=document["id"],
                        quota=quota.status_snapshot())
