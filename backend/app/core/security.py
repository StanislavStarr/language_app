import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

JWT_ALGORITHM = "HS256"


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


def hash_device_secret(device_secret: str) -> str:
    return hashlib.sha256(device_secret.encode()).hexdigest()


def verify_device_secret(device_secret: str, secret_hash: str) -> bool:
    return hmac.compare_digest(hash_device_secret(device_secret), secret_hash)


def issue_access_token(user_id: UUID, signing_key: str, ttl: timedelta) -> str:
    issued_at = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": issued_at, "exp": issued_at + ttl}
    return jwt.encode(claims, signing_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, signing_key: str) -> UUID:
    try:
        claims = jwt.decode(
            token, signing_key, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp"]}
        )
        return UUID(claims["sub"])
    except jwt.ExpiredSignatureError as error:
        raise TokenExpiredError from error
    except (jwt.InvalidTokenError, ValueError) as error:
        raise TokenInvalidError from error
