from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from . import repository
from .config import get_settings
from .deps import client_ip, current_session, current_user, ensure_ready, login_throttle
from .schemas import AuthResponse, LoginRequest, SignupRequest, UserOut
from .security import hash_password, hash_token, is_valid_email, new_session_token, normalize_email, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_session(user: dict) -> AuthResponse:
    token = new_session_token()
    repository.create_session(user["id"], hash_token(token), get_settings().session_ttl_days)
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"]))


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, _: None = Depends(ensure_ready)) -> AuthResponse:
    email = normalize_email(payload.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    try:
        user = repository.create_user(email, hash_password(payload.password))
    except repository.EmailTaken as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Try signing in.") from exc
    return _issue_session(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, _: None = Depends(ensure_ready)) -> AuthResponse:
    email = normalize_email(payload.email)
    ip = client_ip(request)
    throttle = login_throttle()
    if throttle.blocked(ip, email):
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again in a few minutes.")
    user = repository.get_user_by_email(email)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        throttle.record_failure(ip, email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    throttle.record_success(email)
    return _issue_session(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: tuple[dict, str] = Depends(current_session)) -> Response:
    repository.delete_session(session[1])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)) -> UserOut:
    return UserOut(id=user["id"], email=user["email"])
