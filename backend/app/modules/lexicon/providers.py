import httpx
import structlog

from app.core.config import Settings
from app.integrations.ai.openai_provider import OpenAIProvider
from app.integrations.ai.provider import AIProvider, AIProviderError
from app.integrations.dictionary.free_dictionary import FreeDictionaryProvider
from app.integrations.nlp.spacy_analyzer import SpacyTextAnalyzer
from app.modules.lexicon.service import LexiconProviders

logger = structlog.get_logger()


def build_ai_provider(settings: Settings) -> AIProvider | None:
    try:
        return OpenAIProvider.from_settings(settings)
    except AIProviderError:
        logger.warning("ai_not_configured")
        return None


def build_lexicon_providers(settings: Settings, http_client: httpx.AsyncClient) -> LexiconProviders:
    return LexiconProviders(
        analyzer=SpacyTextAnalyzer(),
        dictionary=FreeDictionaryProvider(http_client),
        ai=build_ai_provider(settings),
    )
