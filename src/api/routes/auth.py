"""Staff signup, login, and logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from src.domain.auth import StaffUser
from src.persistence.auth_service import AuthenticatedSession, AuthService

from ..dependencies import get_auth_service, get_current_staff_user
from ..schemas import LoginRequest, SessionResponse, SignupRequest, StaffUserResponse


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _session_response(session: AuthenticatedSession) -> SessionResponse:
    return SessionResponse(
        token=session.token,
        expires_in_hours=session.expires_at_hours,
        user=StaffUserResponse(
            user_id=session.user.user_id,
            email=session.user.email,
            business_id=session.user.business_id,
        ),
    )


@router.post("/signup", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    session = auth_service.signup(body.email, body.password)
    return _session_response(session)


@router.post("/login", response_model=SessionResponse)
def login(
    body: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    session = auth_service.login(body.email, body.password)
    return _session_response(session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            auth_service.logout(token)


@router.get("/me", response_model=StaffUserResponse)
def me(user: Annotated[StaffUser, Depends(get_current_staff_user)]) -> StaffUserResponse:
    return StaffUserResponse(user_id=user.user_id, email=user.email, business_id=user.business_id)
