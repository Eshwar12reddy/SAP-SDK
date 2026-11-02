from pydantic import BaseModel, Field


class MemoryUpdate(BaseModel):
    memory_text: str = Field(min_length=1, max_length=600)


class MemoryPreferenceUpdate(BaseModel):
    enabled: bool
