"""Staff signup, login, and logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from src.domain.auth import StaffUser
from src.domain.signup_attribution import sanitize_signup_attribution
from src.persistence.auth_service import (
    AuthenticatedSession,
    AuthService,
    InvalidCredentialsError,
    PasswordResetInvalidError,
    SecondFactorInvalidError,
    SecondFactorRequiredError,
    SecurityNotConfiguredError,
    SessionInvalidError,
)

from ..dependencies import get_auth_service, get_current_staff_user
from ..errors import RequestDataError, UnauthorizedError
from ..schemas import (
    ChangePasswordRequest, CurrentPasswordRequest, ForgotPasswordRequest, LoginRequest, PasswordAndTwoFactorRequest, RecoveryCodesResponse,
    ResetPasswordRequest, SecurityAuditEventResponse, SecuritySessionResponse,
    SecurityStatusResponse, SessionResponse, SignupRequest, StaffUserResponse,
    TwoFactorCodeRequest, TwoFactorLoginChallengeResponse, TwoFactorSetupResponse, UpdateStaffProfileRequest,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError()
    return token


def _session_response(session: AuthenticatedSession) -> SessionResponse:
    return SessionResponse(
        token=session.token,
        expires_in_hours=session.expires_at_hours,
        user=StaffUserResponse(
            user_id=session.user.user_id,
            name=session.user.name,
            email=session.user.email,
            business_id=session.user.business_id,
            business_ids=list(session.user.business_ids),
        ),
    )


@router.post("/signup", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    session = auth_service.signup(
        body.email,
        body.password,
        attribution=sanitize_signup_attribution(
            None if body.attribution is None else body.attribution.model_dump()
        ),
    )
    return _session_response(session)


@router.post("/login", response_model=SessionResponse | TwoFactorLoginChallengeResponse)
def login(
    body: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse | TwoFactorLoginChallengeResponse:
    try:
        session = auth_service.login(body.email, body.password)
    except SecondFactorRequiredError as challenge:
        return TwoFactorLoginChallengeResponse(
            challenge_token=challenge.challenge_token,
            expires_in_minutes=challenge.expires_in_minutes,
        )
    return _session_response(session)


@router.post("/login/two-factor", response_model=SessionResponse)
def complete_two_factor_login(
    body: TwoFactorCodeRequest,
    challenge_token: Annotated[str, Header(alias="X-Two-Factor-Challenge")],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    try:
        return _session_response(auth_service.verify_two_factor_login(challenge_token, body.code))
    except SecondFactorInvalidError as exc:
        raise UnauthorizedError("Authenticator code is invalid or expired") from exc


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    # This response is deliberately identical for every well-formed email.
    auth_service.request_password_reset(body.email, request_ip=request.client.host if request.client else None)
    return {"message": "If an account matches that email, a reset link will arrive shortly."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    body: ResetPasswordRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    try:
        auth_service.reset_password(body.token, body.password)
    except (PasswordResetInvalidError, ValueError) as exc:
        raise RequestDataError("This reset link is invalid or has expired") from exc


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
    return StaffUserResponse(
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        business_id=user.business_id,
        business_ids=list(user.business_ids),
    )


@router.patch("/me", response_model=StaffUserResponse)
def update_me(
    body: UpdateStaffProfileRequest,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> StaffUserResponse:
    try:
        updated = auth_service.update_profile(user, body.name)
    except ValueError as exc:
        raise RequestDataError("Enter a valid name") from exc
    return StaffUserResponse(
        user_id=updated.user_id,
        name=updated.name,
        email=updated.email,
        business_id=updated.business_id,
        business_ids=list(updated.business_ids),
    )


@router.get("/security", response_model=SecurityStatusResponse)
def security_status(
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SecurityStatusResponse:
    enabled, remaining = auth_service.security_status(user)
    return SecurityStatusResponse(two_factor_enabled=enabled, recovery_codes_remaining=remaining)


@router.post("/security/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    try:
        auth_service.change_password(user, _bearer_token(authorization), body.current_password, body.new_password)
    except InvalidCredentialsError as exc:
        raise RequestDataError("Current password is incorrect") from exc
    except ValueError as exc:
        raise RequestDataError("Choose a stronger password") from exc


@router.post("/security/two-factor/setup", response_model=TwoFactorSetupResponse)
def begin_two_factor_setup(
    body: CurrentPasswordRequest,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TwoFactorSetupResponse:
    try:
        setup = auth_service.begin_two_factor_setup(user, body.current_password)
    except InvalidCredentialsError as exc:
        raise RequestDataError("Current password is incorrect") from exc
    except SecurityNotConfiguredError as exc:
        raise RequestDataError("Two-factor authentication is not available on this deployment") from exc
    return TwoFactorSetupResponse(secret=setup.secret, provisioning_uri=setup.provisioning_uri, expires_in_minutes=setup.expires_in_minutes)


@router.post("/security/two-factor/confirm", response_model=RecoveryCodesResponse)
def confirm_two_factor_setup(
    body: TwoFactorCodeRequest,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RecoveryCodesResponse:
    try:
        return RecoveryCodesResponse(codes=list(auth_service.confirm_two_factor_setup(user, body.code)))
    except (SecondFactorInvalidError, SecurityNotConfiguredError) as exc:
        raise RequestDataError("Authenticator code is invalid or setup has expired") from exc


@router.post("/security/two-factor/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_two_factor(
    body: PasswordAndTwoFactorRequest,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    try:
        auth_service.disable_two_factor(user, body.current_password, body.code)
    except (InvalidCredentialsError, SecondFactorInvalidError, SecurityNotConfiguredError) as exc:
        raise RequestDataError("Password or authenticator code is incorrect") from exc


@router.post("/security/recovery-codes", response_model=RecoveryCodesResponse)
def regenerate_recovery_codes(
    body: PasswordAndTwoFactorRequest,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RecoveryCodesResponse:
    try:
        return RecoveryCodesResponse(codes=list(auth_service.regenerate_recovery_codes(user, body.current_password, body.code)))
    except (InvalidCredentialsError, SecondFactorInvalidError, SecurityNotConfiguredError) as exc:
        raise RequestDataError("Password or authenticator code is incorrect") from exc


@router.get("/security/sessions", response_model=list[SecuritySessionResponse])
def list_sessions(
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> list[SecuritySessionResponse]:
    return [SecuritySessionResponse(
        session_id=session.session_id, created_at=session.created_at,
        expires_at=session.expires_at, revoked_at=session.revoked_at, current=session.current,
    ) for session in auth_service.list_sessions(user, _bearer_token(authorization))]


@router.delete("/security/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    try:
        auth_service.revoke_session(user, session_id, _bearer_token(authorization))
    except SessionInvalidError as exc:
        raise RequestDataError("That session cannot be revoked") from exc


@router.post("/security/sessions/revoke-others")
def revoke_other_sessions(
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    return {"revoked": auth_service.revoke_other_sessions(user, _bearer_token(authorization))}


@router.get("/security/audit", response_model=list[SecurityAuditEventResponse])
def security_audit(
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[SecurityAuditEventResponse]:
    return [SecurityAuditEventResponse(
        event_id=entry.event_id, event_type=entry.event_type,
        created_at=entry.created_at, metadata=entry.metadata,
    ) for entry in auth_service.list_security_audit(user)]
