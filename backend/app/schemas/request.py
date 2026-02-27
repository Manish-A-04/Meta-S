from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailTriageRequest(BaseModel):
    subject: str | None = None
    body: str = Field(..., min_length=1)
    force_reflection: bool = False
    max_reflections: int = Field(default=2, ge=0, le=2)


class AddDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
