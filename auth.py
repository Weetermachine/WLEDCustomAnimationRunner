"""Password hashing + session helpers (stdlib only).

The plaintext password is never stored: only a per-user random salt and a
PBKDF2-HMAC-SHA256 hash live in SQLite. Sessions are opaque random tokens
stored server-side so they can be revoked.
"""
import hashlib
import hmac
import secrets
import time

ITERATIONS = 200_000
SESSION_TTL = 30 * 24 * 3600  # 30 days
COOKIE_NAME = "wled_session"


def hash_password(password, salt=None):
    """Return (salt_hex, hash_hex)."""
    if salt is None:
        salt_bytes = secrets.token_bytes(16)
    elif isinstance(salt, str):
        salt_bytes = bytes.fromhex(salt)
    else:
        salt_bytes = salt
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, ITERATIONS)
    return salt_bytes.hex(), dk.hex()


def verify_password(password, salt_hex, hash_hex):
    _, candidate = hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, hash_hex)


def new_session_token():
    return secrets.token_urlsafe(32)


def session_expiry():
    return time.time() + SESSION_TTL
