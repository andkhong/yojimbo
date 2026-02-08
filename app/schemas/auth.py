from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    department_id: int | None = None
    role: str

    model_config = {"from_attributes": True}
