from pydantic import BaseModel, Field
class ChatRequest(BaseModel): conversation_id: int | None = None; message: str = Field(min_length=1, max_length=12000); response_language: str | None = Field(default=None, max_length=40)
class EditMessageRequest(BaseModel): message_index: int = Field(ge=0); message: str = Field(min_length=1, max_length=12000); response_language: str | None = Field(default=None, max_length=40)
class RegenerateRequest(BaseModel): response_language: str | None = Field(default=None, max_length=40)
class ChatResponse(BaseModel): conversation_id: int; answer: str
