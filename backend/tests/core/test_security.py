from datetime import timedelta
from uuid import uuid4

import pytest
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    decode_access_token,
    hash_device_secret,
    issue_access_token,
    verify_device_secret,
)

SIGNING_KEY = "k" * 32


def test_verify_device_secret_accepts_matching_secret() -> None:
    assert verify_device_secret("secret", hash_device_secret("secret"))


def test_verify_device_secret_rejects_other_secret() -> None:
    assert not verify_device_secret("other", hash_device_secret("secret"))


def test_access_token_round_trips_user_id() -> None:
    user_id = uuid4()

    token = issue_access_token(user_id, SIGNING_KEY, timedelta(days=1))

    assert decode_access_token(token, SIGNING_KEY) == user_id


def test_expired_access_token_is_rejected() -> None:
    token = issue_access_token(uuid4(), SIGNING_KEY, timedelta(seconds=-1))

    with pytest.raises(TokenExpiredError):
        decode_access_token(token, SIGNING_KEY)


def test_access_token_signed_with_other_key_is_rejected() -> None:
    token = issue_access_token(uuid4(), "x" * 32, timedelta(days=1))

    with pytest.raises(TokenInvalidError):
        decode_access_token(token, SIGNING_KEY)


def test_malformed_access_token_is_rejected() -> None:
    with pytest.raises(TokenInvalidError):
        decode_access_token("not-a-token", SIGNING_KEY)
