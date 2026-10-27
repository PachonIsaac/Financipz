from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import CurrentUser, get_current_user

router = APIRouter(tags=["users"])


class MeResponse(BaseModel):
    id: str
    email: str | None


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """The authenticated user."""
    return user
