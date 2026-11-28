import pytest
from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryMeaning,
    DictionaryUnavailableError,
)

from tests.fakes.dictionary import FakeDictionaryProvider

ENTRY = DictionaryEntry("bank", None, None, (DictionaryMeaning("noun", "A bank.", None),))


async def test_fake_returns_known_entries_and_none_for_unknown_words() -> None:
    fake = FakeDictionaryProvider({"bank": ENTRY})

    assert await fake.lookup(" bank ") == ENTRY
    assert await fake.lookup("zzz") is None
    assert fake.lookups == ["bank", "zzz"]


@pytest.mark.parametrize("word", ["", "..", "a/b", "w" * 101])
async def test_fake_applies_the_same_lookup_rules_as_the_real_provider(word: str) -> None:
    fake = FakeDictionaryProvider({"bank": ENTRY})

    assert await fake.lookup(word) is None
    assert fake.lookups == []


async def test_fake_can_simulate_a_provider_failure() -> None:
    fake = FakeDictionaryProvider(error=DictionaryUnavailableError("down"))

    with pytest.raises(DictionaryUnavailableError):
        await fake.lookup("bank")
