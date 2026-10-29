import base64
import hashlib
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
API_KEY_ENCRYPTION_PREFIX = "fernet:v1:"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_source_preview_token(user_id: str, source_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode = {
        "sub": user_id,
        "source_id": source_id,
        "typ": "source_preview",
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def decode_source_preview_token(token: str, source_id: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != "source_preview":
        return None
    if payload.get("source_id") != source_id:
        return None
    return payload.get("sub")


def encrypt_api_key(key: str) -> str:
    return API_KEY_ENCRYPTION_PREFIX + _api_key_cipher().encrypt(key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    if encrypted.startswith(API_KEY_ENCRYPTION_PREFIX):
        token = encrypted.removeprefix(API_KEY_ENCRYPTION_PREFIX)
        try:
            return _api_key_cipher().decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Invalid encrypted API key") from exc

    return base64.b64decode(encrypted.encode()).decode()


def mask_api_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _api_key_cipher() -> Fernet:
    secret = settings.api_key_encryption_secret or settings.secret_key
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
