from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from cookfully.api.dependencies.auth import get_auth_service, require_browser_owner
from cookfully.application.auth import AuthService
from cookfully.infrastructure.config import Settings, get_settings
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
def create_session(
    payload: LoginRequest,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    issued = auth.login(payload.email, payload.password)
    response.set_cookie(
        "cookfully_session",
        issued.session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        expires=issued.expires_at,
        path="/",
    )
    response.set_cookie(
        "cookfully_csrf",
        issued.csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        expires=issued.expires_at,
        path="/",
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> None:
    session_token = request.cookies.get("cookfully_session")
    if session_token:
        auth.logout(session_token)
    response.delete_cookie("cookfully_session", path="/")
    response.delete_cookie("cookfully_csrf", path="/")
