from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.integrations.ai.provider import AIProvider
from app.integrations.dictionary.provider import DictionaryProvider
from app.integrations.nlp.provider import TextAnalyzer
from app.integrations.nlp.spacy_analyzer import SpacyTextAnalyzer
from app.modules.lexicon.service import LexiconProviders
from app.modules.usage.dependencies import get_usage_service
from app.modules.usage.enums import UsageKind
from app.modules.usage.exceptions import UsageLimitExceededError
from fastapi import FastAPI
from tests.fakes.dictionary import FakeDictionaryProvider
from tests.fakes.nlp import FakeTextAnalyzer

type InstallProviders = Callable[..., None]


@pytest.fixture(scope="session")
def spacy_analyzer() -> SpacyTextAnalyzer:
    return SpacyTextAnalyzer()


@pytest.fixture(autouse=True)
def install_providers(app: FastAPI) -> InstallProviders:
    def install(
        *,
        analyzer: TextAnalyzer | None = None,
        dictionary: DictionaryProvider | None = None,
        ai: AIProvider | None = None,
    ) -> None:
        app.state.lexicon_providers = LexiconProviders(
            analyzer or FakeTextAnalyzer(), dictionary or FakeDictionaryProvider(), ai
        )

    install()
    return install


class ExhaustedUsage:
    async def consume(self, _user_id: UUID, kind: UsageKind, _amount: int = 1) -> None:
        raise UsageLimitExceededError(kind, 1, datetime(2026, 1, 2, tzinfo=UTC))


@pytest.fixture
def exhaust_ai_lookups(app: FastAPI) -> Callable[[], None]:
    def exhaust() -> None:
        app.dependency_overrides[get_usage_service] = ExhaustedUsage

    return exhaust
