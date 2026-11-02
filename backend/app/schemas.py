from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class DocumentResponse(BaseModel):
    id: str
    name: str
    source_type: str
    source: str
    shared: bool
    created_at: datetime
    index_status: str = "ready"


class AddDocumentRequest(BaseModel):
    url: HttpUrl


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_id: str = Field(min_length=1, max_length=100)
    new_conversation: bool = False


class QuotaOut(BaseModel):
    used: int
    limit: int
    remaining: int


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    document_id: str
    quota: QuotaOut


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationResponse(BaseModel):
    conversation_id: str | None
    messages: list[MessageOut]


class HealthResponse(BaseModel):
    status: str
    database: str
    environment: str
