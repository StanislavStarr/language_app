import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_production_requires_custom_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_accepts_custom_jwt_secret() -> None:
    settings = Settings(app_env="production", jwt_secret="p" * 40)

    assert settings.jwt_secret.get_secret_value() == "p" * 40


def test_short_jwt_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "short")

    with pytest.raises(ValidationError):
        Settings()
