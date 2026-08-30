"""
Shared FastAPI dependencies. `get_current_user` is what every tenant-scoped
router (analysis, prediction, copilot) depends on — it's the single choke
point that turns a bearer token into a User row, and every query downstream
filters by `current_user.org_id` so one org's uploads/models are never
visible to another.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from .database import get_db
from .security import decode_access_token
from .models_db import User

# tokenUrl is only used to populate FastAPI's /docs "Authorize" button —
# the actual login endpoint lives in routers/auth.py.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


def require_owner(current_user: User = Depends(get_current_user)) -> User:
    """Gate for org-management actions (currently: generating invite
    links). Anyone can be a `member`, but only the org's `owner` can grow
    its membership — otherwise any member could mint invites and the
    invite system wouldn't actually be a stronger boundary than the old
    join-by-name behaviour it replaces."""
    if current_user.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an organization owner can do this.",
        )
    return current_user


def require_verified(current_user: User = Depends(get_current_user)) -> User:
    """Gate for actions that create new data (currently: starting an
    analysis). Deliberately narrower than blocking login entirely — an
    unverified user can still sign in, see past results, and manage their
    account, but can't kick off new work until they've confirmed they own
    the email address. The 403's detail string is matched explicitly on
    the frontend (see api.js) to show a "verify your email" prompt rather
    than a generic error."""
    if not current_user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Please verify your email address before running an analysis.",
        )
    return current_user
