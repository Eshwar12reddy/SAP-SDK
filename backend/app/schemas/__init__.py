from pydantic import BaseModel, Field
class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320); password: str = Field(min_length=8, max_length=128)
class Token(BaseModel): access_token: str; token_type: str = "bearer"
