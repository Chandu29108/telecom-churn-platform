"""
Registration and login.

Registration has two distinct paths, and they are NOT interchangeable:

1. `organization_name` doesn't match any existing org -> a brand-new org is
   created and the registering user becomes its "owner". Single-step,
   self-serve, no invite needed — there's no existing tenant boundary to
   protect yet.
2. `organization_name` DOES match an existing org -> registration is
   REJECTED unless a valid `invite_token` is supplied (minted by that org's
   owner via POST /api/auth/invites). Every org's analysis runs, customer
   risk scores, and SHAP explanations are scoped by org_id — so admitting
   someone to an org by nothing more than them typing its name would let
   anyone who knows (or guesses) a company's name read that company's data.
   That used to be exactly how this endpoint worked; it no longer is.
"""
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..models_db import User, Organization, Invite, EmailToken, RefreshToken
from ..schemas import (
    UserCreate, UserOut, Token, InviteCreate, InviteOut, MessageResponse,
    VerifyEmailRequest, ResendVerificationRequest, ForgotPasswordRequest,
    ResetPasswordRequest,
)
from ..security import (
    hash_password, verify_password, create_access_token,
    generate_opaque_token, hash_token, validate_password_strength,
)
from ..deps import get_current_user, require_owner
from ..config import (
    RATE_LIMIT_AUTH, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
    REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME, COOKIE_SAMESITE, COOKIE_SECURE,
    EMAIL_VERIFICATION_EXPIRE_HOURS, PASSWORD_RESET_EXPIRE_MINUTES,
    PERSONAL_MAX_SEATS, PERSONAL_MAX_UPLOAD_ROWS,
)
from ..email.factory import send_verification_email, send_password_reset_email
from ..audit import log_event

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("churn_platform.auth")
limiter = Limiter(key_func=get_remote_address)

# Generic anti-enumeration responses — same message whether or not the
# email exists, so /resend-verification and /forgot-password never reveal
# which accounts are registered (audit report, Part 6, finding #4).
_GENERIC_VERIFICATION_MESSAGE = (
    "If an account with that email exists and isn't verified yet, "
    "a new verification link has been sent."
)
_GENERIC_RESET_MESSAGE = (
    "If an account with that email exists, a password reset link has been sent."
)


def _issue_refresh_token(db: Session, user: User, request: Request) -> str:
    """Creates and persists a new refresh token, returns the RAW token
    (only the hash is stored — see security.hash_token)."""
    raw = generate_opaque_token()
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("user-agent") if request else None,
        ip_address=request.client.host if request and request.client else None,
    )
    db.add(record)
    db.commit()
    return raw


def _set_refresh_cookie(response: Response, raw_token: str) -> str:
    """Sets the refresh cookie and a paired CSRF cookie, and returns the
    raw CSRF token so the caller can also put it in the JSON response
    body. The frontend never reads the CSRF cookie directly (it can't —
    frontend and backend are different origins); it stores the token
    from the response body in memory and echoes it back as a header on
    /refresh and /logout. The cookie's only job is to prove the request
    carries our session; the header proves it was built by JS that
    actually received our response (which a cross-site attacker's page
    cannot do, since CORS blocks it from reading our responses)."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/api/auth",  # only ever sent to auth endpoints, not the whole API
    )
    csrf_raw = generate_opaque_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_raw,
        httponly=True,  # frontend never reads this directly, only the JSON body copy
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/api/auth",
    )
    return csrf_raw


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/api/auth")


def _verify_csrf(request: Request) -> None:
    """Double-submit check for the two endpoints that authenticate purely
    off the refresh cookie (refresh, logout): the caller must echo the
    CSRF cookie's value back as a header. A cross-site attacker's page
    can make the browser send the refresh cookie automatically, but it
    cannot know this value (it was only ever delivered in a JSON response
    body our CORS policy keeps that attacker's page from reading)."""
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_value or not header_value or cookie_value != header_value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token.")


def _create_org_with_unique_name(db: Session, base_name: str, **kwargs) -> Organization:
    """Organization.name has a unique constraint. Auto-generated personal
    workspace names ("Jane Doe's Workspace") can collide across different
    users with the same display name — handled here by retrying with a
    short random suffix rather than surfacing a confusing IntegrityError,
    or forcing personal-account users to pick a unique name for something
    they never see as an identifier."""
    for attempt in range(3):
        name = base_name if attempt == 0 else f"{base_name} ({secrets.token_hex(3)})"
        org = Organization(name=name, **kwargs)
        db.add(org)
        try:
            db.commit()
        except Exception:
            db.rollback()
            continue
        db.refresh(org)
        return org
    raise HTTPException(500, "Could not create workspace. Please try again.")


def _resolve_registration_org(db: Session, payload: UserCreate):
    """Returns (org, invite_or_None, role) for the three registration
    paths: joining via invite, a new personal (single-seat) workspace, or
    a new/named multi-seat organization. Split out of register() itself
    so each path's rules are easy to read in isolation."""
    if payload.invite_token:
        # An invite always identifies its org directly by id — no need to
        # also match on organization_name, and a personal workspace can
        # never be the target since invites are only ever minted by
        # require_owner on an "organization"-type org (see create_invite).
        invite = db.query(Invite).filter(Invite.token == payload.invite_token).first()
        if invite is None:
            raise HTTPException(400, "Invalid invite link.")
        if invite.used_at is not None:
            raise HTTPException(400, "This invite link has already been used.")
        if invite.expires_at < datetime.utcnow():
            raise HTTPException(400, "This invite link has expired. Ask an owner for a new one.")
        org = db.query(Organization).filter(Organization.id == invite.org_id).first()
        if org is None:
            raise HTTPException(400, "Invalid invite link.")
        return org, invite, invite.role

    if payload.account_type == "personal":
        workspace_name = payload.organization_name or f"{payload.full_name}'s Workspace"
        org = _create_org_with_unique_name(
            db, workspace_name, account_type="personal",
            max_seats=PERSONAL_MAX_SEATS, max_upload_rows=PERSONAL_MAX_UPLOAD_ROWS,
        )
        return org, None, "owner"

    # account_type == "organization", no invite: create-or-conflict by name.
    if not payload.organization_name or not payload.organization_name.strip():
        raise HTTPException(400, "Organization name is required.")
    existing = db.query(Organization).filter(Organization.name == payload.organization_name).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An organization with this name already exists. Ask an "
            "owner there to send you an invite link, then register "
            "again with that link.",
        )
    org = Organization(name=payload.organization_name, account_type="organization")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org, None, "owner"


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT_AUTH)
def register(
    request: Request,
    response: Response,
    payload: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == payload.email).first():
        # Deliberately NOT genericized here (unlike resend/forgot-password
        # below): the caller just typed this exact email into a form
        # they're actively submitting, so confirming it's taken is normal
        # UX, not an enumeration leak in the same sense as a background
        # "does this account exist" probe. See audit report finding #4 for
        # the nuance.
        raise HTTPException(400, "An account with this email already exists.")

    strength_problems = validate_password_strength(payload.password, payload.email)
    if strength_problems:
        raise HTTPException(400, " ".join(strength_problems))

    org, invite, role = _resolve_registration_org(db, payload)

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        org_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if invite is not None:
        invite.used_at = datetime.utcnow()
        invite.used_by = user.id
        db.commit()

    logger.info(
        "auth.register user_id=%s org_id=%s new_org=%s via_invite=%s",
        user.id, org.id, invite is None and role == "owner", invite is not None,
    )
    log_event(
        db, request, "account.created", user_id=user.id, org_id=org.id,
        resource_type="user", resource_id=user.id,
        metadata={"via_invite": invite is not None},
    )

    verification_raw = generate_opaque_token()
    db.add(EmailToken(
        user_id=user.id,
        token_hash=hash_token(verification_raw),
        purpose="verify_email",
        expires_at=datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS),
    ))
    db.commit()
    # Sent after the response is on its way out — registration itself
    # should never be slow or fail because an email provider is down.
    background_tasks.add_task(send_verification_email, user.email, verification_raw)
    log_event(db, request, "auth.verification_sent", user_id=user.id, org_id=org.id)

    token = create_access_token({"sub": str(user.id), "org_id": user.org_id})
    refresh_raw = _issue_refresh_token(db, user, request)
    csrf_token = _set_refresh_cookie(response, refresh_raw)
    return Token(access_token=token, csrf_token=csrf_token)


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT_AUTH)
def create_invite(
    request: Request,
    payload: InviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Owner-only. Mints a single-use join link for the caller's own org.
    There is no email delivery configured yet, so the token/link is
    returned directly for the owner to share through whatever channel they
    already use — email sending is an external-service dependency (an
    SMTP/SES/SendGrid account) that hasn't been set up in this project."""
    if current_user.org.account_type == "personal":
        raise HTTPException(
            400,
            "Personal accounts are single-seat and don't support team "
            "invites. Create an Organization account to add teammates.",
        )
    invite = Invite(
        token=secrets.token_urlsafe(32),
        org_id=current_user.org_id,
        role="member",
        created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=payload.expires_hours),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    logger.info("auth.invite_created org_id=%s created_by=%s", invite.org_id, current_user.id)

    return InviteOut(
        id=invite.id, token=invite.token, org_id=invite.org_id,
        role=invite.role, expires_at=invite.expires_at.isoformat(), used=False,
    )


@router.get("/invites", response_model=list[InviteOut])
def list_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Owner-only. Pending + past invites for the caller's own org."""
    invites = (
        db.query(Invite)
        .filter(Invite.org_id == current_user.org_id)
        .order_by(Invite.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        InviteOut(
            id=i.id, token=i.token, org_id=i.org_id, role=i.role,
            expires_at=i.expires_at.isoformat(), used=i.used_at is not None,
        )
        for i in invites
    ]


@router.post("/login", response_model=Token)
@limiter.limit(RATE_LIMIT_AUTH)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # OAuth2PasswordRequestForm's "username" field carries the email —
    # this keeps the endpoint compatible with FastAPI's built-in /docs
    # "Authorize" button, which expects that field name.
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        log_event(
            db, request, "auth.login_failed", success=False,
            metadata={"email_attempted": form_data.username},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    log_event(db, request, "auth.login", user_id=user.id, org_id=user.org_id)
    token = create_access_token({"sub": str(user.id), "org_id": user.org_id})
    refresh_raw = _issue_refresh_token(db, user, request)
    csrf_token = _set_refresh_cookie(response, refresh_raw)
    return Token(access_token=token, csrf_token=csrf_token)


@router.post("/refresh", response_model=Token, dependencies=[Depends(_verify_csrf)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """Exchanges the httpOnly refresh cookie for a new short-lived access
    token, rotating the refresh token in the process. This is what makes
    a 15-minute access token invisible to the user under normal use —
    the frontend calls this silently on load and on 401.

    Rotation + reuse detection: each refresh token is single-use. If a
    token that's already been rotated out (replaced_by_hash is set) is
    presented again, that's either a bug or a stolen cookie being replayed
    — either way, every refresh token for that user is revoked so a
    compromised cookie can't keep minting new sessions indefinitely.
    """
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token provided.")

    token_hash = hash_token(raw)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if record is None or record.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or expired.")

    if record.revoked_at is not None:
        # Reuse of an already-rotated/revoked token — treat as compromise.
        db.query(RefreshToken).filter(
            RefreshToken.user_id == record.user_id, RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": datetime.utcnow()})
        db.commit()
        log_event(
            db, request, "auth.refresh_reuse_detected", user_id=record.user_id,
            success=False,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or expired.")

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or expired.")

    new_raw = _issue_refresh_token(db, user, request)
    record.revoked_at = datetime.utcnow()
    record.replaced_by_hash = hash_token(new_raw)
    db.commit()
    csrf_token = _set_refresh_cookie(response, new_raw)

    token = create_access_token({"sub": str(user.id), "org_id": user.org_id})
    return Token(access_token=token, csrf_token=csrf_token)


@router.post("/logout", response_model=MessageResponse, dependencies=[Depends(_verify_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
        record = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw)).first()
        if record and record.revoked_at is None:
            record.revoked_at = datetime.utcnow()
            db.commit()
            log_event(db, request, "auth.logout", user_id=record.user_id)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out.")


@router.post("/verify-email", response_model=MessageResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def verify_email(request: Request, payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.token)
    record = (
        db.query(EmailToken)
        .filter(EmailToken.token_hash == token_hash, EmailToken.purpose == "verify_email")
        .first()
    )
    if record is None or record.used_at is not None or record.expires_at < datetime.utcnow():
        raise HTTPException(400, "This verification link is invalid or has expired.")

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(400, "This verification link is invalid or has expired.")

    user.is_verified = 1
    record.used_at = datetime.utcnow()
    db.commit()
    log_event(db, request, "auth.email_verified", user_id=user.id, org_id=user.org_id)
    return MessageResponse(message="Email verified. You're all set.")


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and not user.is_verified:
        # Invalidate any previously-issued, still-unused verification
        # tokens so only the newest link works.
        db.query(EmailToken).filter(
            EmailToken.user_id == user.id, EmailToken.purpose == "verify_email",
            EmailToken.used_at.is_(None),
        ).update({"used_at": datetime.utcnow()})
        raw = generate_opaque_token()
        db.add(EmailToken(
            user_id=user.id, token_hash=hash_token(raw), purpose="verify_email",
            expires_at=datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS),
        ))
        db.commit()
        background_tasks.add_task(send_verification_email, user.email, raw)
        log_event(db, request, "auth.verification_resent", user_id=user.id, org_id=user.org_id)
    # Same generic response whether or not the account exists / is already
    # verified — see _GENERIC_VERIFICATION_MESSAGE.
    return MessageResponse(message=_GENERIC_VERIFICATION_MESSAGE)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None:
        db.query(EmailToken).filter(
            EmailToken.user_id == user.id, EmailToken.purpose == "reset_password",
            EmailToken.used_at.is_(None),
        ).update({"used_at": datetime.utcnow()})
        raw = generate_opaque_token()
        db.add(EmailToken(
            user_id=user.id, token_hash=hash_token(raw), purpose="reset_password",
            expires_at=datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
        ))
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, raw)
        log_event(db, request, "auth.password_reset_requested", user_id=user.id, org_id=user.org_id)
    return MessageResponse(message=_GENERIC_RESET_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.token)
    record = (
        db.query(EmailToken)
        .filter(EmailToken.token_hash == token_hash, EmailToken.purpose == "reset_password")
        .first()
    )
    if record is None or record.used_at is not None or record.expires_at < datetime.utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired.")

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(400, "This reset link is invalid or has expired.")

    strength_problems = validate_password_strength(payload.new_password, user.email)
    if strength_problems:
        raise HTTPException(400, " ".join(strength_problems))

    user.hashed_password = hash_password(payload.new_password)
    record.used_at = datetime.utcnow()
    # Invalidate every existing session — a password reset should mean
    # every previously-issued refresh token (e.g. from a device that had
    # the compromised password) stops working, not just the current one.
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": datetime.utcnow()})
    db.commit()
    log_event(db, request, "auth.password_reset_completed", user_id=user.id, org_id=user.org_id)
    return MessageResponse(message="Password updated. Please log in again.")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
