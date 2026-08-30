"""
Password hashing (bcrypt via passlib), JWT issuing/verification, refresh-
token generation, and password-strength checks.

Kept as pure functions with no DB or FastAPI imports so they're trivial to
unit test in isolation from routing/database concerns.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from .config import SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Small, deliberately short blocklist of the most common passwords. This is
# not a substitute for a real breach-corpus check (e.g. HaveIBeenPwned's
# k-anonymity API) — it's a cheap first filter that catches the worst
# offenders without a network call or a large bundled wordlist.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789",
    "qwerty123", "letmein1", "welcome1", "admin1234", "iloveyou1",
    "changeme1", "abc12345", "football1", "monkey123", "dragon123",
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str, email: str | None = None) -> list[str]:
    """Returns a list of problems (empty list = acceptable). Kept as simple,
    explainable rules rather than an opaque score — each rule is something
    a user can immediately act on."""
    problems = []
    if len(password) < 8:
        problems.append("Password must be at least 8 characters.")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("This password is too common. Choose something less guessable.")
    if email and password.lower() == email.split("@")[0].lower():
        problems.append("Password must not be the same as your email username.")
    return problems


def _hash_token(raw_token: str) -> str:
    """SHA-256 of an opaque random token — used for both email-verification
    and refresh tokens so the database never holds a usable secret, only
    something the raw token (sent once, over email or in a cookie) can be
    checked against. Not bcrypt: these are high-entropy random tokens, not
    low-entropy user passwords, so a fast, deterministic hash is correct
    here (bcrypt would also work but adds pointless latency for no benefit
    against a 32-byte random secret)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def generate_opaque_token() -> str:
    """Used for email-verification/password-reset tokens and refresh
    tokens alike: a 32-byte URL-safe random string, unguessable and never
    stored raw (see _hash_token)."""
    return secrets.token_urlsafe(32)


hash_token = _hash_token


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_minutes: int | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jose.JWTError on an invalid/expired token — callers decide
    how to turn that into an HTTP response (see deps.get_current_user)."""
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
