import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        algo, salt_hex, digest_hex = hashed.split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(
    subject: str,
    role: str,
    *,
    scope: str = "iccc",
    minutes: int | None = None,
) -> str:
    settings = get_settings()
    ttl = minutes if minutes is not None else settings.access_token_expire_minutes
    if scope == "field":
        ttl = minutes if minutes is not None else settings.field_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    payload = {
        "sub": subject,
        "role": role,
        "scope": scope,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": os.urandom(8).hex(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("invalid token") from exc
