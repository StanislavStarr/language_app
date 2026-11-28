from collections.abc import Mapping

from app.integrations.dictionary.provider import DictionaryEntry, DictionaryError, normalize_lookup


class FakeDictionaryProvider:
    def __init__(
        self,
        entries: Mapping[str, DictionaryEntry] | None = None,
        error: DictionaryError | None = None,
    ) -> None:
        self._entries = dict(entries or {})
        self._error = error
        self.lookups: list[str] = []

    async def lookup(self, word: str) -> DictionaryEntry | None:
        query = normalize_lookup(word)
        if query is None:
            return None
        self.lookups.append(query)
        if self._error is not None:
            raise self._error
        return self._entries.get(query)
