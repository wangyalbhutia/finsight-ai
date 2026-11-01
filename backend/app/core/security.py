import hashlib, secrets, hmac
from datetime import datetime, timedelta, timezone
import jwt
from .config import settings

# Prefer passlib bcrypt, fallback to pbkdf2_hmac (reliable on py3.12 without bcrypt build issues)
try:
    from passlib.context import CryptContext
    _ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    def hash_password(pw: str) -> str:
        # bcrypt truncates at 72 bytes
        return _ctx.hash(pw[:72])
    def verify_password(pw: str, hashed: str) -> bool:
        if hashed.startswith("pbkdf2$"):
            return _verify_pbkdf2(pw, hashed)
        try:
            return _ctx.verify(pw[:72], hashed)
        except Exception:
            return False
except Exception:
    def hash_password(pw: str) -> str:
        return _hash_pbkdf2(pw)
    def verify_password(pw: str, hashed: str) -> bool:
        return _verify_pbkdf2(pw, hashed)

def _hash_pbkdf2(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 260000)
    return f"pbkdf2${salt}${dk.hex()}"

def _verify_pbkdf2(pw: str, hashed: str) -> bool:
    try:
        _, salt, hexdk = hashed.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 260000)
        return hmac.compare_digest(dk.hex(), hexdk)
    except Exception:
        return False

# If passlib present but bcrypt backend broken, the above hash may fail at runtime; wrap:
_orig_hash = hash_password
def hash_password_safe(pw: str) -> str:
    try:
        return _orig_hash(pw)
    except Exception:
        return _hash_pbkdf2(pw)
hash_password = hash_password_safe

def create_access_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    jti = secrets.token_hex(16)
    return jwt.encode({"sub": str(user_id), "exp": exp, "type": "access", "jti": jti}, settings.secret_key, algorithm=settings.algorithm)

def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def decode_token(token: str):
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
