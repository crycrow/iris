from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import create_access_token, token_hash, verify_password
from app.common.models import User, Session as LoginSession, SystemSetting
from app.common.permissions import bearer, get_current_user
from app.common.schemas import LoginIn, LoginOut, UserOut, Ok
from app.common.services.access_log import audit

router = APIRouter(prefix="/api/auth", tags=["Вход и сессии"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.login == body.login.strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Неверный логин или пароль")
    if user.is_blocked:
        raise HTTPException(403, "Учётная запись заблокирована")
    value = db.scalar(
        select(SystemSetting.setting_value).where(
            SystemSetting.setting_key == "token_minutes"
        )
    )
    token, expires = create_access_token(user.user_id, int(value or 480))
    db.add(
        LoginSession(
            user_id=user.user_id, token_hash=token_hash(token), expires_at=expires
        )
    )
    db.commit()
    audit(user.user_id, "login", "sessions")
    return LoginOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout", response_model=Ok)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        delete(LoginSession).where(
            LoginSession.token_hash == token_hash(credentials.credentials)
        )
    )
    db.commit()
    audit(user.user_id, "logout", "sessions")
    return Ok()
