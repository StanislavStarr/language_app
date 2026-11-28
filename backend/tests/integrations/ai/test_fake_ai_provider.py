import pytest
from app.integrations.ai.provider import (
    AIUnavailableError,
    GenerateFallbackMeaningsRequest,
    SelectSenseRequest,
)
from app.integrations.ai.schemas.fallback_meanings import FallbackMeaningsOutput
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput

from tests.fakes.fake_ai_provider import FAKE_MODEL, FakeAIProvider

REQUEST = SelectSenseRequest("bank", "A sentence.", ())


async def test_fake_returns_the_configured_value_and_records_calls() -> None:
    output = SenseSelectionOutput(
        selected_meaning_id=None, contextual_translation=None, confidence=0
    )
    fake = FakeAIProvider(sense=output)

    result = await fake.select_sense(REQUEST)

    assert result.value == output
    assert result.model == FAKE_MODEL
    assert fake.calls == [("select_sense", REQUEST)]


async def test_fake_can_simulate_a_provider_failure() -> None:
    fake = FakeAIProvider(error=AIUnavailableError("down"))

    with pytest.raises(AIUnavailableError):
        await fake.generate_fallback_meanings(GenerateFallbackMeaningsRequest("x", None))
    assert [name for name, _ in fake.calls] == ["generate_fallback_meanings"]


async def test_fake_refuses_calls_it_was_not_configured_for() -> None:
    fake = FakeAIProvider(fallback=FallbackMeaningsOutput(found=False, meanings=[]))

    with pytest.raises(AssertionError, match="select_sense"):
        await fake.select_sense(REQUEST)
