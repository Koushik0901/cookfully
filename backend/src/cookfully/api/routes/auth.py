from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from cookfully.api.dependencies.auth import (
    BrowserPrincipal,
    get_auth_service,
    require_browser_owner,
    require_browser_session,
)
from cookfully.application.auth import AuthService, SessionRead
from cookfully.infrastructure.config import Settings, get_settings
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)


class SessionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    client_label: str | None = Field(alias="clientLabel")
    created_at: datetime = Field(alias="createdAt")
    last_seen_at: datetime = Field(alias="lastSeenAt")
    is_current: bool = Field(alias="isCurrent")


class SessionListResponse(BaseModel):
    sessions: list[SessionItem]


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(alias="currentPassword", min_length=1, max_length=1024)
    new_password: str = Field(alias="newPassword", min_length=12, max_length=1024)


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
def create_session(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    issued = auth.login(
        payload.email, payload.password, user_agent=request.headers.get("user-agent")
    )
    response.set_cookie(
        "cookfully_session",
        issued.session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        expires=issued.expires_at,
        path="/",
    )
    response.set_cookie(
        "cookfully_csrf",
        issued.csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
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


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    principal: Annotated[BrowserPrincipal, Depends(require_browser_session)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionListResponse:
    sessions: tuple[SessionRead, ...] = auth.list_sessions(
        principal.owner.id, principal.session_id_hash
    )
    return SessionListResponse(
        sessions=[
            SessionItem(
                id=item.id,
                client_label=item.client_label,
                created_at=item.created_at,
                last_seen_at=item.last_seen_at,
                is_current=item.is_current,
            )
            for item in sessions
        ]
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: UUID,
    response: Response,
    principal: Annotated[BrowserPrincipal, Depends(require_browser_session)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth.revoke_session(principal.owner.id, session_id)
    if session_id == principal.session_id:
        response.delete_cookie("cookfully_session", path="/")
        response.delete_cookie("cookfully_csrf", path="/")


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    principal: Annotated[BrowserPrincipal, Depends(require_browser_session)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth.change_password(
        principal.owner.id,
        payload.current_password,
        payload.new_password,
        principal.session_id_hash,
    )
