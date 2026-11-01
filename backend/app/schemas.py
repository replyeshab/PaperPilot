from pydantic import BaseModel, Field, HttpUrl

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    user_id: str = Field(default="web-user", min_length=1, max_length=100)
    new_conversation: bool = False
    document_id: str | None = None

class ChatResponse(BaseModel):
    answer: str
    user_id: str
    run_id: str | None = None

class AddDocumentRequest(BaseModel):
    url: HttpUrl

class DocumentResponse(BaseModel):
    id: str
    name: str
    url: str
    status: str = "configured"
