# Справочник: интеграции — словари, AI, аудио

Этот документ нужен на шагах 29–34 и 38. Здесь собрано всё про внешние сервисы: архитектура
провайдеров, разбор форматов ответов, промпты, обработка ошибок и контроль расходов.

---

## 1. Общий принцип: бизнес-логика не знает про провайдеров

Ключевое архитектурное требование: сервис, который ищет значения слова, не должен содержать ни строки,
специфичной для Яндекса или OpenAI. Иначе замена провайдера превращается в переписывание бизнес-логики,
а тесты начинают требовать интернет.

Схема зависимостей:

```text
LexemeLookupService          EnrichmentService
        │                            │
        ├── DictionaryProvider ◄─────┤        (протокол)
        ├── AIProvider ◄─────────────┤        (протокол)
        └──────────────── AudioProvider ◄─────┘        (протокол)
                    ▲            ▲             ▲
                    │            │             │
        YandexDictionaryProvider  │      WikimediaAudioProvider
        WiktionaryProvider   OpenAIProvider
```

Сервисы зависят от протоколов, реализации внедряются снаружи. Все форматы ответов внешних сервисов
остаются внутри `app/integrations/` и наружу не просачиваются — сервисы получают нормализованные DTO.

Роль AI зафиксирована продуктовым планом и важно её не расширить случайно:

| Задача | Источник |
| --- | --- |
| Перевод | словарь |
| Транскрипция (IPA) | словарь |
| Часть речи | словарь |
| Аудио | Wikimedia Commons |
| Определение (definition) | **AI** |
| Пример (example) | **AI** |
| Значения слова, которого нет в словаре | **AI (fallback)** |
| Значение, которого нет среди словарных | **AI (fallback с учётом source_context)** |

AI не является источником истины для обычных слов. Он дополняет словарь и подстраховывает его.

---

## 2. Нормализованные DTO

Создайте `backend/app/integrations/dictionary/provider.py`:

```python
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class PartOfSpeech(StrEnum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    PREPOSITION = "preposition"
    CONJUNCTION = "conjunction"
    INTERJECTION = "interjection"
    NUMERAL = "numeral"
    PARTICLE = "particle"
    PHRASE = "phrase"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DictionaryTranslation:
    text: str
    synonyms: tuple[str, ...] = ()
    meaning_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DictionaryMeaning:
    part_of_speech: PartOfSpeech
    translations: tuple[DictionaryTranslation, ...]
    definition: str | None = None
    example: str | None = None
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    text: str
    ipa: str | None
    meanings: tuple[DictionaryMeaning, ...]


@dataclass(frozen=True, slots=True)
class DictionaryLookupResult:
    provider_name: str
    entries: tuple[DictionaryEntry, ...] = field(default=())

    @property
    def is_empty(self) -> bool:
        return not self.entries


class DictionaryProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def lookup(self, text: str) -> DictionaryLookupResult: ...
```

`frozen=True, slots=True` делает объекты неизменяемыми и компактными. Неизменяемость здесь по делу:
результат внешнего запроса не должен меняться по пути через слои, иначе источник данных перестаёт быть
понятен. Кортежи вместо списков — по той же причине.

`PartOfSpeech` как закрытый набор — это то, что позволит одинаково обрабатывать `«сущ.»` от Яндекса и
`«Noun»` от Wiktionary. Нормализация к этому перечислению происходит внутри каждого провайдера.

Создайте `backend/app/integrations/errors.py` — общие ошибки интеграций:

```python
class ProviderError(Exception):
    def __init__(self, provider_name: str, message: str) -> None:
        self.provider_name = provider_name
        super().__init__(f"{provider_name}: {message}")


class ProviderTemporaryError(ProviderError):
    pass


class ProviderPermanentError(ProviderError):
    pass


class ProviderResponseInvalidError(ProviderPermanentError):
    pass


class ProviderQuotaExceededError(ProviderError):
    pass
```

Разделение на временные и постоянные ошибки — основа стратегии ретраев. Таймаут и 503 временные,
их имеет смысл повторить. Неверный ключ и 400 постоянные: повторять бессмысленно, надо переходить
к следующему провайдеру или деградировать.

---

## 3. Общий HTTP-клиент

Каждый внешний вызов обязан иметь таймаут, обработку ошибок, логирование и ограниченные ретраи —
это прямое требование раздела 28 правил проекта. Чтобы не повторять это в каждом провайдере, вынесем
в одно место.

Создайте `backend/app/integrations/http_client.py`:

```python
import asyncio
import logging
from typing import Literal

import httpx

from app.integrations.errors import ProviderPermanentError, ProviderTemporaryError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class ProviderHttpClient:
    def __init__(
        self,
        *,
        provider_name: str,
        timeout_seconds: float,
        user_agent: str,
        max_attempts: int = 3,
    ) -> None:
        self._provider_name = provider_name
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._max_attempts = max_attempts

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        expected: Literal["object", "array"] = "object",
    ) -> dict[str, object] | list[object]:
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                payload = await self._perform_request(url, params)
            except ProviderTemporaryError as error:
                last_error = error
                if attempt == self._max_attempts:
                    break
                backoff_seconds = 0.5 * (2 ** (attempt - 1))
                logger.warning(
                    "provider request failed, retrying",
                    extra={
                        "provider": self._provider_name,
                        "attempt": attempt,
                        "backoff_seconds": backoff_seconds,
                    },
                )
                await asyncio.sleep(backoff_seconds)
                continue

            self._ensure_expected_shape(payload, expected)
            return payload

        raise ProviderTemporaryError(
            self._provider_name, f"failed after {self._max_attempts} attempts: {last_error}"
        )

    async def _perform_request(
        self, url: str, params: dict[str, str] | None
    ) -> dict[str, object] | list[object]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers={"User-Agent": self._user_agent, "Accept": "application/json"},
                follow_redirects=True,
            ) as client:
                response = await client.get(url, params=params)
        except httpx.TimeoutException as error:
            raise ProviderTemporaryError(self._provider_name, "request timed out") from error
        except httpx.HTTPError as error:
            raise ProviderTemporaryError(self._provider_name, f"transport error: {error}") from error

        if response.status_code in RETRYABLE_STATUS_CODES:
            raise ProviderTemporaryError(
                self._provider_name, f"retryable status {response.status_code}"
            )

        if response.status_code >= 400:
            raise ProviderPermanentError(
                self._provider_name, f"status {response.status_code}: {response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as error:
            raise ProviderPermanentError(self._provider_name, "response is not json") from error

    def _ensure_expected_shape(
        self, payload: dict[str, object] | list[object], expected: Literal["object", "array"]
    ) -> None:
        if expected == "object" and not isinstance(payload, dict):
            raise ProviderPermanentError(self._provider_name, "expected json object")
        if expected == "array" and not isinstance(payload, list):
            raise ProviderPermanentError(self._provider_name, "expected json array")
```

Задержки между попытками: 0.5с, 1с, 2с. Число попыток ограничено тремя — при недоступном провайдере
мы хотим быстро перейти к следующему, а не держать задачу минутами.

Обрезка `response.text[:200]` в сообщении об ошибке не случайна: провайдер может вернуть HTML-страницу
на десятки килобайт, и в логах это бесполезный шум.

---

## 4. Yandex Dictionary — основной словарь

### Формат запроса

```text
GET https://dictionary.yandex.net/api/v1/dicservice.json/lookup
    ?key=<ключ>
    &lang=en-ru
    &text=bank
    &flags=4
```

Параметр `flags=4` включает фильтр семейных значений. Дополнительно можно передать `ui=ru`, чтобы
названия частей речи приходили по-русски — нам это не нужно, мы всё равно приводим их к своему
перечислению.

### Формат ответа

```json
{
  "head": {},
  "def": [
    {
      "text": "bank",
      "pos": "noun",
      "ts": "bæŋk",
      "tr": [
        {
          "text": "банк",
          "pos": "существительное",
          "syn": [{ "text": "банковский" }],
          "mean": [{ "text": "banking" }],
          "ex": [
            { "text": "central bank", "tr": [{ "text": "центральный банк" }] }
          ]
        },
        { "text": "берег", "pos": "существительное", "mean": [{ "text": "shore" }] }
      ]
    },
    {
      "text": "bank",
      "pos": "verb",
      "ts": "bæŋk",
      "tr": [{ "text": "сложить", "pos": "глагол" }]
    }
  ]
}
```

Что здесь есть и как это ложится на нашу модель данных:

| Поле ответа | Что это | Куда попадает |
| --- | --- | --- |
| `def[]` | группы по части речи | превращаются в набор `Meaning` |
| `def[].ts` | транскрипция без косых скобок | `Lexeme.ipa` |
| `def[].pos` | часть речи | `Meaning.part_of_speech` |
| `def[].tr[]` | варианты перевода | `Translation` |
| `def[].tr[].mean[]` | подсказки смысла по-английски | различение значений при выборе |
| `def[].tr[].syn[]` | синонимы перевода | дополнение перевода |
| `def[].tr[].ex[]` | примеры употребления | резерв, если AI недоступен |

Важное наблюдение, которое влияет на UX: одна запись `def` содержит несколько переводов `tr`, и это
**разные значения** для пользователя. «Банк» и «берег» — то, между чем человек должен выбрать.
Поэтому один элемент `tr` даёт одно `Meaning`, а не один `def`. Иначе пользователю придётся выбирать
между «существительным» и «глаголом», что бесполезно.

Поле `mean` при этом критично: без него «банк» и «берег» выглядят просто как два слова, а с ним
можно показать `берег (shore)`.

### Реализация

Создайте `backend/app/integrations/dictionary/yandex.py`:

```python
import logging
from typing import Final

from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryLookupResult,
    DictionaryMeaning,
    DictionaryTranslation,
    PartOfSpeech,
)
from app.integrations.errors import ProviderPermanentError
from app.integrations.http_client import ProviderHttpClient

logger = logging.getLogger(__name__)

YANDEX_LOOKUP_URL: Final = "https://dictionary.yandex.net/api/v1/dicservice.json/lookup"
FAMILY_FILTER_FLAG: Final = "4"

POS_MAPPING: Final[dict[str, PartOfSpeech]] = {
    "noun": PartOfSpeech.NOUN,
    "verb": PartOfSpeech.VERB,
    "adjective": PartOfSpeech.ADJECTIVE,
    "adverb": PartOfSpeech.ADVERB,
    "pronoun": PartOfSpeech.PRONOUN,
    "preposition": PartOfSpeech.PREPOSITION,
    "conjunction": PartOfSpeech.CONJUNCTION,
    "interjection": PartOfSpeech.INTERJECTION,
    "numeral": PartOfSpeech.NUMERAL,
    "particle": PartOfSpeech.PARTICLE,
    "phrase": PartOfSpeech.PHRASE,
}


class YandexDictionaryProvider:
    def __init__(
        self,
        *,
        api_key: str,
        language_pair: str = "en-ru",
        timeout_seconds: float = 5.0,
        user_agent: str = "english-vocabulary-app/0.1",
    ) -> None:
        self._api_key = api_key
        self._language_pair = language_pair
        self._http = ProviderHttpClient(
            provider_name=self.name,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
        )

    @property
    def name(self) -> str:
        return "yandex_dictionary"

    async def lookup(self, text: str) -> DictionaryLookupResult:
        if not self._api_key:
            raise ProviderPermanentError(self.name, "api key is not configured")

        payload = await self._http.get_json(
            YANDEX_LOOKUP_URL,
            params={
                "key": self._api_key,
                "lang": self._language_pair,
                "text": text,
                "flags": FAMILY_FILTER_FLAG,
            },
        )

        if not isinstance(payload, dict):
            raise ProviderPermanentError(self.name, "expected json object")

        definitions = payload.get("def")
        if not isinstance(definitions, list) or not definitions:
            logger.info("yandex dictionary returned no definitions", extra={"query_text": text})
            return DictionaryLookupResult(provider_name=self.name)

        entry = self._build_entry(text, definitions)
        return DictionaryLookupResult(provider_name=self.name, entries=(entry,))

    def _build_entry(self, text: str, definitions: list[object]) -> DictionaryEntry:
        meanings: list[DictionaryMeaning] = []
        transcription: str | None = None

        for definition in definitions:
            if not isinstance(definition, dict):
                continue

            transcription = transcription or self._read_optional_string(definition.get("ts"))
            part_of_speech = self._map_part_of_speech(definition.get("pos"))

            translations = definition.get("tr")
            if not isinstance(translations, list):
                continue

            for translation in translations:
                meaning = self._build_meaning(part_of_speech, translation)
                if meaning is not None:
                    meanings.append(meaning)

        return DictionaryEntry(text=text, ipa=transcription, meanings=tuple(meanings))

    def _build_meaning(
        self, part_of_speech: PartOfSpeech, translation: object
    ) -> DictionaryMeaning | None:
        if not isinstance(translation, dict):
            return None

        translation_text = self._read_optional_string(translation.get("text"))
        if not translation_text:
            return None

        return DictionaryMeaning(
            part_of_speech=part_of_speech,
            translations=(
                DictionaryTranslation(
                    text=translation_text,
                    synonyms=self._read_text_items(translation.get("syn")),
                    meaning_hints=self._read_text_items(translation.get("mean")),
                ),
            ),
            example=self._read_first_example(translation.get("ex")),
        )

    def _map_part_of_speech(self, raw_pos: object) -> PartOfSpeech:
        if not isinstance(raw_pos, str):
            return PartOfSpeech.UNKNOWN
        return POS_MAPPING.get(raw_pos.strip().lower(), PartOfSpeech.UNKNOWN)

    def _read_optional_string(self, raw_value: object) -> str | None:
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return None

    def _read_text_items(self, raw_items: object) -> tuple[str, ...]:
        if not isinstance(raw_items, list):
            return ()

        collected: list[str] = []
        for item in raw_items:
            if isinstance(item, dict):
                text = self._read_optional_string(item.get("text"))
                if text:
                    collected.append(text)
        return tuple(collected)

    def _read_first_example(self, raw_examples: object) -> str | None:
        examples = self._read_text_items(raw_examples)
        return examples[0] if examples else None
```

Обратите внимание на манеру разбора: каждое поле проверяется на тип, ничего не берётся «на веру».
Это выглядит громоздко по сравнению с `payload["def"][0]["ts"]`, но внешний ответ — недоверенные
данные. Строка `payload["def"][0]["ts"]` упадёт с `KeyError` на слове, у которого нет транскрипции,
и уронит обогащение целой карточки. Здесь же отсутствие поля просто даёт `None`, и карточка
деградирует частично — именно так требует продуктовый план.

Типизация через `object` вместо `Any` — требование правил проекта: тип сужается сразу проверкой
`isinstance`, и mypy это контролирует.

### Ошибки Yandex Dictionary

| Код | Значение | Как реагируем |
| --- | --- | --- |
| 401 | `ERR_KEY_INVALID` | `ProviderPermanentError`, переходим к следующему провайдеру, пишем ошибку в лог |
| 402 | `ERR_KEY_BLOCKED` | то же |
| 403 | превышен дневной лимит запросов | `ProviderPermanentError`, на сегодня провайдер бесполезен |
| 413 | текст слишком длинный | до провайдера доходить не должно — ограничиваем на входе API |
| 501 | направление перевода не поддерживается | постоянная ошибка конфигурации |

Ключ Yandex Dictionary имеет суточный лимит запросов. При работе одного пользователя и кэшировании
в PostgreSQL вы к нему не приблизитесь: повторный поиск того же слова вообще не доходит до провайдера.

### Юридическое требование

Условия использования требуют указывать ссылку на технологию Яндекса. Добавьте на экран профиля
строку «Словарные данные: Yandex.Dictionary» со ссылкой. Это пять минут работы, и вопрос закрыт.

---

## 5. Wiktionary — английские определения

### Зачем второй словарь

Yandex Dictionary даёт перевод, но не даёт англоязычного определения. Определение нужно для этапа
«написание по definition» в занятии. Основной источник определений — AI, но Wiktionary полезен
как бесплатная опора: если определение пришло из словаря, AI-запрос не нужен вовсе, и это прямая
экономия бюджета.

Правило вызова из продуктового плана: **второй провайдер вызывается только если первого не хватило.**
Если у нас уже есть перевод, IPA и определение — Wiktionary не запрашиваем.

### Формат запроса и ответа

```bash
curl -s -H "User-Agent: english-vocabulary-app/0.1 (contact: you@example.com)" \
  "https://en.wiktionary.org/api/rest_v1/page/definition/bank"
```

```json
{
  "en": [
    {
      "partOfSpeech": "Noun",
      "language": "English",
      "definitions": [
        {
          "definition": "An <a href=\"/wiki/institution\">institution</a> where one can place and borrow money.",
          "parsedExamples": [{ "example": "I put my money in the bank." }]
        }
      ]
    }
  ]
}
```

Три особенности, которые надо учесть:

1. ответ сгруппирован по языку — нас интересует только ключ `en`;
2. **определения содержат HTML-разметку** — её нужно вычистить, иначе теги попадут в карточку;
3. первое определение в списке иногда пустое (артефакт разбора вики-разметки) — такие пропускаем.

Заголовок `User-Agent` обязателен: Wikimedia отклоняет запросы без осмысленного идентификатора.
Укажите в нём контакт — это требование их политики использования.

### Реализация

Создайте `backend/app/integrations/dictionary/wiktionary.py`:

```python
import html
import logging
import re
from typing import Final
from urllib.parse import quote

from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryLookupResult,
    DictionaryMeaning,
    PartOfSpeech,
)
from app.integrations.errors import ProviderPermanentError
from app.integrations.http_client import ProviderHttpClient

logger = logging.getLogger(__name__)

WIKTIONARY_DEFINITION_URL: Final = "https://en.wiktionary.org/api/rest_v1/page/definition"
HTML_TAG_PATTERN: Final = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN: Final = re.compile(r"\s+")
MAX_DEFINITIONS_PER_PART_OF_SPEECH: Final = 3

POS_MAPPING: Final[dict[str, PartOfSpeech]] = {
    "noun": PartOfSpeech.NOUN,
    "verb": PartOfSpeech.VERB,
    "adjective": PartOfSpeech.ADJECTIVE,
    "adverb": PartOfSpeech.ADVERB,
    "pronoun": PartOfSpeech.PRONOUN,
    "preposition": PartOfSpeech.PREPOSITION,
    "conjunction": PartOfSpeech.CONJUNCTION,
    "interjection": PartOfSpeech.INTERJECTION,
    "numeral": PartOfSpeech.NUMERAL,
    "particle": PartOfSpeech.PARTICLE,
    "phrase": PartOfSpeech.PHRASE,
    "proverb": PartOfSpeech.PHRASE,
    "idiom": PartOfSpeech.PHRASE,
}


def strip_html_markup(raw_text: str) -> str:
    without_tags = HTML_TAG_PATTERN.sub("", raw_text)
    unescaped = html.unescape(without_tags)
    return WHITESPACE_PATTERN.sub(" ", unescaped).strip()


class WiktionaryProvider:
    def __init__(self, *, timeout_seconds: float = 5.0, user_agent: str) -> None:
        self._http = ProviderHttpClient(
            provider_name=self.name,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_attempts=2,
        )

    @property
    def name(self) -> str:
        return "wiktionary"

    async def lookup(self, text: str) -> DictionaryLookupResult:
        url = f"{WIKTIONARY_DEFINITION_URL}/{quote(text.replace(' ', '_'))}"

        try:
            payload = await self._http.get_json(url)
        except ProviderPermanentError as error:
            logger.info(
                "wiktionary has no article",
                extra={"query_text": text, "reason": str(error)},
            )
            return DictionaryLookupResult(provider_name=self.name)

        if not isinstance(payload, dict):
            return DictionaryLookupResult(provider_name=self.name)

        english_sections = payload.get("en")
        if not isinstance(english_sections, list) or not english_sections:
            return DictionaryLookupResult(provider_name=self.name)

        meanings = self._build_meanings(english_sections)
        if not meanings:
            return DictionaryLookupResult(provider_name=self.name)

        return DictionaryLookupResult(
            provider_name=self.name,
            entries=(DictionaryEntry(text=text, ipa=None, meanings=meanings),),
        )

    def _build_meanings(self, sections: list[object]) -> tuple[DictionaryMeaning, ...]:
        meanings: list[DictionaryMeaning] = []

        for section in sections:
            if not isinstance(section, dict):
                continue

            part_of_speech = self._map_part_of_speech(section.get("partOfSpeech"))
            definitions = section.get("definitions")
            if not isinstance(definitions, list):
                continue

            for definition in definitions[:MAX_DEFINITIONS_PER_PART_OF_SPEECH]:
                meaning = self._build_meaning(part_of_speech, definition)
                if meaning is not None:
                    meanings.append(meaning)

        return tuple(meanings)

    def _build_meaning(
        self, part_of_speech: PartOfSpeech, definition: object
    ) -> DictionaryMeaning | None:
        if not isinstance(definition, dict):
            return None

        raw_definition = definition.get("definition")
        if not isinstance(raw_definition, str):
            return None

        cleaned_definition = strip_html_markup(raw_definition)
        if len(cleaned_definition) < 3:
            return None

        return DictionaryMeaning(
            part_of_speech=part_of_speech,
            translations=(),
            definition=cleaned_definition,
            example=self._read_first_example(definition.get("parsedExamples")),
        )

    def _map_part_of_speech(self, raw_pos: object) -> PartOfSpeech:
        if not isinstance(raw_pos, str):
            return PartOfSpeech.UNKNOWN
        return POS_MAPPING.get(raw_pos.strip().lower(), PartOfSpeech.UNKNOWN)

    def _read_first_example(self, raw_examples: object) -> str | None:
        if not isinstance(raw_examples, list):
            return None

        for item in raw_examples:
            if isinstance(item, dict):
                example = item.get("example")
                if isinstance(example, str):
                    cleaned = strip_html_markup(example)
                    if cleaned:
                        return cleaned
        return None
```

Отсутствие статьи в Wiktionary (404) — это не ошибка, а нормальный результат «ничего не найдено».
Поэтому `ProviderPermanentError` здесь перехватывается и превращается в пустой результат: обогащение
должно продолжиться, а не упасть.

Проверка `len(cleaned_definition) < 3` отбрасывает те самые пустые определения из вики-разметки.

Замена пробелов на подчёркивания в URL нужна для фраз: `look forward to` → `look_forward_to`.
На практике Wiktionary часто не имеет статей для произвольных фраз — это ожидаемо, и определение
для них сгенерирует AI.

---

## 6. Аудио: Wikimedia Commons и конвертация в mp3

### Проблема, которую нельзя пропустить

Файлы произношения на Commons хранятся в формате `.ogg`. **Safari и WKWebView на iOS не
воспроизводят ogg.** Telegram на iPhone использует WKWebView. Если отдать ссылку на ogg напрямую,
аудио будет работать на Android и в десктопном Telegram, но молча не работать на iPhone —
это худший вид бага, потому что он не выдаёт ошибок.

Решение: Celery-задача скачивает ogg, конвертирует в mp3 через `ffmpeg`, сохраняет в локальный том,
а Nginx раздаёт файл по `/media/`. Конвертация одного слова занимает доли секунды, а результат
переиспользуется всеми пользователями.

### Поиск файла на Commons

Файлы произношения следуют соглашению об именах:

```text
File:En-us-bank.ogg      американское произношение
File:En-uk-bank.ogg      британское
File:En-au-bank.ogg      австралийское
File:LL-Q1860 (eng)-Persus-bank.wav    более новый формат Lingua Libre
```

Запрос информации о файле:

```bash
curl -s -H "User-Agent: english-vocabulary-app/0.1 (contact: you@example.com)" \
  "https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|mime&titles=File:En-us-bank.ogg"
```

```json
{
  "query": {
    "pages": {
      "1250051": {
        "title": "File:En-us-bank.ogg",
        "imageinfo": [
          {
            "url": "https://upload.wikimedia.org/wikipedia/commons/4/4d/En-us-bank.ogg",
            "mime": "application/ogg"
          }
        ]
      }
    }
  }
}
```

Если файла нет, страница придёт с ключом `"missing"` и без `imageinfo`. Идентификатор страницы —
произвольное число, поэтому перебираем значения словаря `pages`, а не обращаемся по ключу.

Продуктовый план предусматривает одно audio на карточку в MVP (несколько акцентов — после MVP).
Поэтому пробуем варианты по порядку и берём первый найденный.

### Реализация провайдера

Создайте `backend/app/integrations/audio/provider.py`:

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AudioCandidate:
    source_url: str
    source_name: str
    mime_type: str


class AudioProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def find_pronunciation(self, text: str) -> AudioCandidate | None: ...
```

Создайте `backend/app/integrations/audio/wikimedia.py`:

```python
import logging
from typing import Final

from app.integrations.audio.provider import AudioCandidate
from app.integrations.errors import ProviderError
from app.integrations.http_client import ProviderHttpClient

logger = logging.getLogger(__name__)

COMMONS_API_URL: Final = "https://commons.wikimedia.org/w/api.php"
ACCENT_PREFIXES: Final[tuple[str, ...]] = ("En-us", "En-uk", "En-au")
AUDIO_EXTENSIONS: Final[tuple[str, ...]] = ("ogg", "wav")


class WikimediaAudioProvider:
    def __init__(self, *, timeout_seconds: float = 5.0, user_agent: str) -> None:
        self._http = ProviderHttpClient(
            provider_name=self.name,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_attempts=2,
        )

    @property
    def name(self) -> str:
        return "wikimedia_commons"

    async def find_pronunciation(self, text: str) -> AudioCandidate | None:
        if " " in text.strip():
            return None

        candidate_titles = self._build_candidate_titles(text)

        try:
            return await self._find_first_existing_file(candidate_titles)
        except ProviderError as error:
            logger.info(
                "wikimedia audio lookup failed",
                extra={"query_text": text, "reason": str(error)},
            )
            return None

    def _build_candidate_titles(self, text: str) -> tuple[str, ...]:
        normalized = text.strip().lower()
        return tuple(
            f"File:{prefix}-{normalized}.{extension}"
            for prefix in ACCENT_PREFIXES
            for extension in AUDIO_EXTENSIONS
        )

    async def _find_first_existing_file(
        self, candidate_titles: tuple[str, ...]
    ) -> AudioCandidate | None:
        payload = await self._http.get_json(
            COMMONS_API_URL,
            params={
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "titles": "|".join(candidate_titles),
            },
        )

        if not isinstance(payload, dict):
            return None

        query_section = payload.get("query")
        if not isinstance(query_section, dict):
            return None

        pages = query_section.get("pages")
        if not isinstance(pages, dict):
            return None

        found_by_title = self._collect_found_files(pages)

        for title in candidate_titles:
            candidate = found_by_title.get(title)
            if candidate is not None:
                return candidate
        return None

    def _collect_found_files(self, pages: dict[str, object]) -> dict[str, AudioCandidate]:
        collected: dict[str, AudioCandidate] = {}

        for page in pages.values():
            if not isinstance(page, dict) or "missing" in page:
                continue

            title = page.get("title")
            image_info = page.get("imageinfo")
            if not isinstance(title, str) or not isinstance(image_info, list) or not image_info:
                continue

            first_info = image_info[0]
            if not isinstance(first_info, dict):
                continue

            url = first_info.get("url")
            mime_type = first_info.get("mime")
            if isinstance(url, str) and isinstance(mime_type, str):
                collected[title] = AudioCandidate(
                    source_url=url.split("?")[0],
                    source_name=self.name,
                    mime_type=mime_type,
                )

        return collected
```

Все шесть вариантов имён запрашиваются **одним** запросом через `titles` с разделителем `|` —
Commons API это поддерживает. Шесть последовательных запросов были бы прямым нарушением принципа
«не делать дублирующих внешних вызовов» из раздела 38 правил проекта.

Приоритет сохраняется за счёт того, что мы проходим по `candidate_titles` в исходном порядке, а не
по порядку ответа: американское произношение предпочтительнее британского.

Фразы (со пробелом) сразу отсекаются — записей произношения для них на Commons практически нет,
и запрос будет бесполезным.

Вызов `url.split("?")[0]` убирает параметры аналитики, которые Commons добавляет к ссылке.

### Конвертация и локальное хранение

Создайте `backend/app/integrations/audio/storage.py`:

```python
import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Final

import httpx

from app.integrations.audio.provider import AudioCandidate
from app.integrations.errors import ProviderTemporaryError

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_SECONDS: Final = 30
DOWNLOAD_TIMEOUT_SECONDS: Final = 20
MAX_SOURCE_SIZE_BYTES: Final = 5 * 1024 * 1024


class PronunciationAudioStorage:
    def __init__(self, *, media_root: Path, public_base_url: str, user_agent: str) -> None:
        self._media_root = media_root
        self._public_base_url = public_base_url.rstrip("/")
        self._user_agent = user_agent

    async def store_as_mp3(self, candidate: AudioCandidate, *, lexeme_text: str) -> str:
        file_name = self._build_file_name(candidate, lexeme_text)
        target_path = self._media_root / "pronunciation" / file_name

        if target_path.exists():
            return self._build_public_url(file_name)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        source_bytes = await self._download(candidate.source_url)
        await self._convert_to_mp3(source_bytes, target_path)

        logger.info(
            "pronunciation audio stored",
            extra={"lexeme_text": lexeme_text, "file_name": file_name},
        )
        return self._build_public_url(file_name)

    def _build_file_name(self, candidate: AudioCandidate, lexeme_text: str) -> str:
        digest = hashlib.sha256(candidate.source_url.encode()).hexdigest()[:16]
        safe_text = "".join(char for char in lexeme_text.lower() if char.isalnum())[:32]
        return f"{safe_text or 'audio'}-{digest}.mp3"

    def _build_public_url(self, file_name: str) -> str:
        return f"{self._public_base_url}/pronunciation/{file_name}"

    async def _download(self, url: str) -> bytes:
        try:
            async with httpx.AsyncClient(
                timeout=DOWNLOAD_TIMEOUT_SECONDS,
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ProviderTemporaryError("audio_storage", f"download failed: {error}") from error

        if len(response.content) > MAX_SOURCE_SIZE_BYTES:
            raise ProviderTemporaryError("audio_storage", "source audio is too large")

        return response.content

    async def _convert_to_mp3(self, source_bytes: bytes, target_path: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-b:a",
            "48k",
            "-f",
            "mp3",
            str(target_path),
            "-y",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(input=source_bytes), timeout=FFMPEG_TIMEOUT_SECONDS
            )
        except TimeoutError as error:
            process.kill()
            raise ProviderTemporaryError("audio_storage", "ffmpeg timed out") from error

        if process.returncode != 0:
            target_path.unlink(missing_ok=True)
            raise ProviderTemporaryError(
                "audio_storage", f"ffmpeg failed: {stderr.decode()[:200]}"
            )
```

Разбор решений:

* имя файла — из текста слова плюс хэш исходного URL. Это делает операцию идемпотентной: повторный
  запуск задачи обнаружит существующий файл и не станет конвертировать снова;
* параметры `-ac 1 -ar 24000 -b:a 48k` — моно, 24 кГц, 48 кбит/с. Для произношения одного слова этого
  более чем достаточно, файл получается 5–15 КБ вместо сотни;
* `asyncio.create_subprocess_exec` вместо `subprocess.run` — не блокирует event loop;
* таймаут обязателен: `ffmpeg` на повреждённом файле может ждать ввода бесконечно;
* при ошибке недописанный файл удаляется — иначе следующий запуск сочтёт его готовым;
* ограничение размера источника защищает от скачивания чего-то неожиданно большого.

Проверить конвертацию можно вручную:

```bash
cd infra
docker compose exec celery-worker ffmpeg -version | head -1
docker compose exec celery-worker python -c "
import asyncio
from pathlib import Path
from app.integrations.audio.provider import AudioCandidate
from app.integrations.audio.storage import PronunciationAudioStorage

storage = PronunciationAudioStorage(
    media_root=Path('/app/media'),
    public_base_url='http://localhost:8080/media',
    user_agent='english-vocabulary-app/0.1 (dev)',
)
candidate = AudioCandidate(
    source_url='https://upload.wikimedia.org/wikipedia/commons/4/4d/En-us-bank.ogg',
    source_name='wikimedia_commons',
    mime_type='application/ogg',
)
print(asyncio.run(storage.store_as_mp3(candidate, lexeme_text='bank')))
"
```

Затем откройте полученный URL в браузере — файл должен воспроизводиться:

```bash
curl -sI http://localhost:8080/media/pronunciation/bank-<хэш>.mp3 | head -3
```

---

## 7. AI-провайдер

### Две задачи AI и почему их нельзя путать

| Задача | Когда вызывается | Что получаем |
| --- | --- | --- |
| **Генерация обучающего контента** | при обогащении карточки, если определения/примера нет | `definition` + `example` для конкретного значения и уровня CEFR |
| **Fallback значений** | словари ничего не нашли, или пользователь нажал «Нет нужного значения» | список значений с переводом, определением и примером |

Различие принципиальное с точки зрения кэширования. Первый результат **общий для всех
пользователей** и кэшируется в `MeaningContent` по ключу «значение + уровень + версия промпта».
Второй зависит от личного `source_context` и кэшируется только как обычный `Meaning`, без привязки
к пользователю.

Из этого следует правило, которое легко нарушить случайно: `source_context` — персональные данные,
и он **не должен попадать в общий `MeaningContent`**. Продуктовый план отдельно на это указывает.

### Structured outputs: почему не просто «попроси JSON»

Обычная просьба «верни JSON» даёт валидный JSON в большинстве случаев, но не всегда: модель может
добавить пояснение до или после, обернуть в markdown-блок или переименовать поле. Structured outputs
гарантирует соответствие схеме на уровне API.

Актуальный способ в Python SDK — метод `responses.parse` с Pydantic-моделью в `text_format`.
Результат приходит уже разобранным в `.output_parsed`.

### Модели контента

Создайте `backend/app/integrations/ai/provider.py`:

```python
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from app.integrations.dictionary.provider import PartOfSpeech


class GeneratedMeaningContent(BaseModel):
    definition: str = Field(min_length=10, max_length=200)
    example: str = Field(min_length=5, max_length=200)


class GeneratedMeaning(BaseModel):
    part_of_speech: str
    translation: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=10, max_length=200)
    example: str = Field(min_length=5, max_length=200)


class GeneratedMeaningList(BaseModel):
    meanings: list[GeneratedMeaning] = Field(min_length=1, max_length=3)


@dataclass(frozen=True, slots=True)
class MeaningContentRequest:
    lexeme_text: str
    part_of_speech: PartOfSpeech
    meaning_description: str
    cefr_level: str


@dataclass(frozen=True, slots=True)
class MeaningFallbackRequest:
    lexeme_text: str
    cefr_level: str
    source_context: str | None


@dataclass(frozen=True, slots=True)
class AIUsage:
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class AIResult[T]:
    content: T
    usage: AIUsage


class AIProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate_meaning_content(
        self, request: MeaningContentRequest
    ) -> AIResult[GeneratedMeaningContent]: ...

    async def generate_fallback_meanings(
        self, request: MeaningFallbackRequest
    ) -> AIResult[GeneratedMeaningList]: ...
```

Ограничения длины в схеме Pydantic — это второй слой защиты после structured outputs. Модель может
соблюсти схему, но вернуть определение на 800 символов, которое сломает вёрстку карточки. Валидация
на входе в приложение обязательна для любых данных, сгенерированных AI — раздел 25 правил проекта
формулирует это прямо.

`AIUsage` возвращается вместе с результатом, чтобы писать расход токенов в лог. Без этого вы узнаете
о перерасходе только из счёта.

`AIResult[T]` — generic-класс в современном синтаксисе Python 3.13, без явного `TypeVar`.

### Промпты

Создайте `backend/app/integrations/ai/prompts.py`:

```python
from typing import Final

from app.integrations.ai.provider import MeaningContentRequest, MeaningFallbackRequest

PROMPT_VERSION: Final = "v1"

MEANING_CONTENT_SYSTEM_PROMPT: Final = """
You write learning material for a vocabulary app. The learner's native language is Russian and they
study English.

You will receive an English word or short phrase, its part of speech, a description of the specific
meaning to explain, and the learner's CEFR level.

Produce exactly two things.

definition:
- explain only the given meaning, not other meanings of the word
- write in English
- never use the target word or any form of it inside the definition
- use vocabulary simpler than the target word, appropriate for the given CEFR level
- one sentence, at most 15 words
- no articles like "Definition:" and no quotes

example:
- one natural English sentence that contains the target word or phrase in the given meaning
- the sentence must make the meaning obvious from context
- appropriate for the given CEFR level, at most 12 words
- no rare or technical vocabulary
- do not translate the sentence
""".strip()

MEANING_FALLBACK_SYSTEM_PROMPT: Final = """
You are a bilingual English-Russian lexicographer helping a vocabulary app when dictionaries return
no result.

You will receive an English word or short phrase, the learner's CEFR level, and possibly the sentence
where the learner encountered it.

Return between one and three distinct meanings, ordered by how common they are. If a context sentence
is provided, the meaning that fits that context must be first.

For every meaning provide:
- part_of_speech: one of noun, verb, adjective, adverb, pronoun, preposition, conjunction,
  interjection, numeral, particle, phrase
- translation: the Russian translation of this specific meaning, no explanations in parentheses
- definition: an English explanation of this meaning that never uses the target word itself,
  one sentence, at most 15 words
- example: one natural English sentence containing the target word in this meaning,
  at most 12 words

If the input looks like a misspelling of a common English word, still interpret it as the intended
word and describe that word's meanings.

Never invent meanings that do not exist in real English usage.
""".strip()


def build_meaning_content_user_prompt(request: MeaningContentRequest) -> str:
    return (
        f"word_or_phrase: {request.lexeme_text}\n"
        f"part_of_speech: {request.part_of_speech.value}\n"
        f"meaning_to_explain: {request.meaning_description}\n"
        f"cefr_level: {request.cefr_level}"
    )


def build_meaning_fallback_user_prompt(request: MeaningFallbackRequest) -> str:
    lines = [
        f"word_or_phrase: {request.lexeme_text}",
        f"cefr_level: {request.cefr_level}",
    ]
    if request.source_context:
        lines.append(f"context_sentence: {request.source_context}")
    return "\n".join(lines)
```

Промпты вынесены в отдельный модуль с версией, и это не формальность. `PROMPT_VERSION` входит в ключ
кэша `MeaningContent`. Когда вы улучшите промпт, старый контент **не перегенерируется автоматически** —
так решено в продуктовом плане, потому что иначе одно изменение текста промпта означало бы
перегенерацию всей базы и заметный счёт.

Отдельно обратите внимание на требование «never use the target word inside the definition». Без него
модель охотно выдаёт «to clarify means to make something clear», что делает упражнение «написание по
определению» бессмысленным. Это то правило, которое стоит проверять на первых десяти словах вручную.

### Реализация на OpenAI

Создайте `backend/app/integrations/ai/openai_provider.py`:

```python
import logging
from typing import Final

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from app.integrations.ai.prompts import (
    MEANING_CONTENT_SYSTEM_PROMPT,
    MEANING_FALLBACK_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_meaning_content_user_prompt,
    build_meaning_fallback_user_prompt,
)
from app.integrations.ai.provider import (
    AIResult,
    AIUsage,
    GeneratedMeaningContent,
    GeneratedMeaningList,
    MeaningContentRequest,
    MeaningFallbackRequest,
)
from app.integrations.errors import (
    ProviderPermanentError,
    ProviderQuotaExceededError,
    ProviderResponseInvalidError,
    ProviderTemporaryError,
)

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS: Final = 400


class OpenAIProvider:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ValueError("openai api key is required")
        if not model:
            raise ValueError("openai model is required")

        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=2)

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    async def generate_meaning_content(
        self, request: MeaningContentRequest
    ) -> AIResult[GeneratedMeaningContent]:
        return await self._parse_structured_response(
            system_prompt=MEANING_CONTENT_SYSTEM_PROMPT,
            user_prompt=build_meaning_content_user_prompt(request),
            output_model=GeneratedMeaningContent,
            operation="generate_meaning_content",
        )

    async def generate_fallback_meanings(
        self, request: MeaningFallbackRequest
    ) -> AIResult[GeneratedMeaningList]:
        return await self._parse_structured_response(
            system_prompt=MEANING_FALLBACK_SYSTEM_PROMPT,
            user_prompt=build_meaning_fallback_user_prompt(request),
            output_model=GeneratedMeaningList,
            operation="generate_fallback_meanings",
        )

    async def _parse_structured_response[T: BaseModel](
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[T],
        operation: str,
    ) -> AIResult[T]:
        try:
            response = await self._client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=output_model,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
        except APITimeoutError as error:
            raise ProviderTemporaryError(self.name, "request timed out") from error
        except RateLimitError as error:
            raise ProviderQuotaExceededError(self.name, "rate limit or quota exceeded") from error
        except APIConnectionError as error:
            raise ProviderTemporaryError(self.name, f"connection error: {error}") from error
        except APIStatusError as error:
            if error.status_code in {500, 502, 503, 504}:
                raise ProviderTemporaryError(
                    self.name, f"status {error.status_code}"
                ) from error
            raise ProviderPermanentError(self.name, f"status {error.status_code}") from error

        parsed = response.output_parsed
        if parsed is None:
            raise ProviderResponseInvalidError(self.name, "model returned no structured output")

        try:
            validated = output_model.model_validate(parsed, from_attributes=True)
        except ValidationError as error:
            raise ProviderResponseInvalidError(
                self.name, f"structured output failed validation: {error}"
            ) from error

        usage = self._read_usage(response)
        logger.info(
            "ai generation finished",
            extra={
                "provider": self.name,
                "operation": operation,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        )
        return AIResult(content=validated, usage=usage)

    def _read_usage(self, response: object) -> AIUsage:
        usage_section = getattr(response, "usage", None)
        return AIUsage(
            model=self._model,
            prompt_version=PROMPT_VERSION,
            input_tokens=int(getattr(usage_section, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage_section, "output_tokens", 0) or 0),
        )
```

Разбор важных мест:

* исключения SDK раскладываются по нашим двум категориям. Таймаут и 5xx временные — их повторит
  Celery. Неверный ключ и 400 постоянные — повтор бессмысленен, надо оставить карточку в `PARTIAL`;
* `RateLimitError` выделен отдельно: это сигнал «упёрлись в лимит», и реакция на него — не ретрай,
  а прекращение AI-операций до следующего периода;
* `max_retries=2` внутри клиента плюс ретраи Celery дают в сумме ограниченное число попыток.
  Раздел 29 правил проекта требует именно ограниченности — бесконечные ретраи при исчерпанном
  бюджете сожгут остаток впустую;
* **повторная валидация через `model_validate` не избыточна.** Structured outputs гарантирует
  структуру, но не ограничения `min_length`/`max_length` из наших полей. Модель может вернуть
  определение на 400 символов, формально соответствующее схеме;
* `max_output_tokens` ограничивает стоимость одного вызова сверху.

### Расход и его контроль

Порядок величин для оценки: один вызов генерации definition + example — это примерно 250 токенов
входа и 60 токенов выхода. При стоимости порядка нескольких центов за миллион входных токенов расход
на одно слово измеряется малыми долями цента.

Ключевой множитель — не цена модели, а **сколько раз вы вызываете AI**. Три уровня защиты:

1. **Общий кэш `MeaningContent`.** Контент генерируется для пары «значение + уровень CEFR», а не для
   пользователя. Слово `clarify` в значении «уточнить» на уровне A2 генерируется один раз на всё
   приложение;
2. **Определения из словаря.** Если Wiktionary дал определение, AI для definition не вызывается —
   только для примера, или вообще не вызывается;
3. **Суточный лимит на пользователя** (`AI_DAILY_REQUEST_LIMIT_PER_USER`) — счётчик в Redis, шаг 60.
   Это защита не от пользователя, а от собственной ошибки в коде: цикл, который вызывает генерацию
   в каждой итерации, упрётся в лимит вместо счёта на сто долларов.

Плюс жёсткий месячный лимит в биллинге OpenAI из шага 6 — последняя линия защиты.

Для наблюдения за расходом логируйте токены (это уже делает код выше) и периодически смотрите:

```bash
cd infra
docker compose logs celery-worker | grep '"operation":"generate' | tail -20
```

### Проверка AI-провайдера вживую

```bash
cd infra
docker compose exec backend python -c "
import asyncio
from app.common.settings import get_settings
from app.integrations.ai.openai_provider import OpenAIProvider
from app.integrations.ai.provider import MeaningContentRequest
from app.integrations.dictionary.provider import PartOfSpeech

settings = get_settings()
provider = OpenAIProvider(
    api_key=settings.openai_api_key,
    model=settings.ai_model,
    timeout_seconds=settings.ai_timeout_seconds,
)
request = MeaningContentRequest(
    lexeme_text='bank',
    part_of_speech=PartOfSpeech.NOUN,
    meaning_description='берег (shore, land along a river)',
    cefr_level='A2',
)
result = asyncio.run(provider.generate_meaning_content(request))
print('definition:', result.content.definition)
print('example:', result.content.example)
print('tokens:', result.usage.input_tokens, '/', result.usage.output_tokens)
"
```

Проверьте результат по четырём критериям продуктового плана:

1. определение **не содержит** слово `bank` ни в какой форме;
2. пример **содержит** слово `bank`;
3. речь именно о береге, а не о финансовом учреждении;
4. лексика простая, соответствует A2.

Прогоните так десять разных слов, включая фразу и слово с несколькими значениями. Если правило про
«не использовать целевое слово» нарушается — усильте формулировку в промпте и поднимите
`PROMPT_VERSION`. Это правильный момент для настройки промптов: до того, как в базе появятся сотни
записей.

### Fallback-значения

```bash
docker compose exec backend python -c "
import asyncio
from app.common.settings import get_settings
from app.integrations.ai.openai_provider import OpenAIProvider
from app.integrations.ai.provider import MeaningFallbackRequest

settings = get_settings()
provider = OpenAIProvider(
    api_key=settings.openai_api_key,
    model=settings.ai_model,
    timeout_seconds=settings.ai_timeout_seconds,
)
request = MeaningFallbackRequest(
    lexeme_text='look forward to',
    cefr_level='A2',
    source_context='I look forward to hearing from you.',
)
result = asyncio.run(provider.generate_fallback_meanings(request))
for meaning in result.content.meanings:
    print(meaning.part_of_speech, '|', meaning.translation, '|', meaning.definition)
"
```

Ожидается 1–3 значения, первое из которых соответствует переданному контексту.

---

## 8. Сборка провайдеров: зависимости FastAPI и Celery

Провайдеры создаются в одном месте, чтобы не плодить клиентов по коду.

Создайте `backend/app/integrations/factory.py`:

```python
from functools import lru_cache
from pathlib import Path

from app.common.settings import Settings, get_settings
from app.integrations.ai.openai_provider import OpenAIProvider
from app.integrations.ai.provider import AIProvider
from app.integrations.audio.provider import AudioProvider
from app.integrations.audio.storage import PronunciationAudioStorage
from app.integrations.audio.wikimedia import WikimediaAudioProvider
from app.integrations.dictionary.provider import DictionaryProvider
from app.integrations.dictionary.wiktionary import WiktionaryProvider
from app.integrations.dictionary.yandex import YandexDictionaryProvider


@lru_cache
def get_primary_dictionary_provider() -> DictionaryProvider:
    settings = get_settings()
    return YandexDictionaryProvider(
        api_key=settings.yandex_dictionary_api_key,
        timeout_seconds=settings.yandex_dictionary_timeout_seconds,
        user_agent=settings.wikimedia_user_agent,
    )


@lru_cache
def get_fallback_dictionary_provider() -> DictionaryProvider:
    settings = get_settings()
    return WiktionaryProvider(
        timeout_seconds=settings.wiktionary_timeout_seconds,
        user_agent=settings.wikimedia_user_agent,
    )


@lru_cache
def get_audio_provider() -> AudioProvider:
    settings = get_settings()
    return WikimediaAudioProvider(user_agent=settings.wikimedia_user_agent)


@lru_cache
def get_audio_storage() -> PronunciationAudioStorage:
    settings = get_settings()
    return PronunciationAudioStorage(
        media_root=Path(settings.media_root),
        public_base_url=settings.media_public_base_url,
        user_agent=settings.wikimedia_user_agent,
    )


@lru_cache
def get_ai_provider() -> AIProvider:
    settings: Settings = get_settings()
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )
```

`@lru_cache` даёт по одному экземпляру на процесс. Это безопасно, потому что провайдеры не хранят
состояния между запросами, а `httpx.AsyncClient` создаётся внутри каждого вызова — то есть проблемы
привязки к event loop, описанной в ликбезе, здесь нет.

Использование в FastAPI:

```python
from typing import Annotated

from fastapi import Depends

from app.integrations.dictionary.provider import DictionaryProvider
from app.integrations.factory import get_primary_dictionary_provider

PrimaryDictionary = Annotated[DictionaryProvider, Depends(get_primary_dictionary_provider)]
```

В тестах эти зависимости переопределяются фейковыми реализациями через `app.dependency_overrides` —
см. [10-testing-reference.md](10-testing-reference.md).

---

## 9. Итоговая таблица провайдеров

| Провайдер | Адрес | Ключ | Даёт | Таймаут | Попыток |
| --- | --- | --- | --- | --- | --- |
| Yandex Dictionary | `dictionary.yandex.net/api/v1/dicservice.json/lookup` | нужен, бесплатный | перевод, IPA, часть речи, примеры | 5с | 3 |
| Wiktionary | `en.wiktionary.org/api/rest_v1/page/definition/{word}` | не нужен | англ. определения, примеры | 5с | 2 |
| Wikimedia Commons | `commons.wikimedia.org/w/api.php` | не нужен | ссылка на аудио | 5с | 2 |
| OpenAI | Responses API через SDK | нужен, платный | definition, example, fallback-значения | 30с | 2 + ретраи Celery |

### Чего избегать

| Вариант | Почему не подходит |
| --- | --- |
| `api.dictionaryapi.dev` | На момент написания недоступен (запрос не проходит). Популярен в статьях, но как основа ненадёжен |
| Прямая отдача ogg с Commons | Не воспроизводится на iOS — молчаливый баг |
| Google Translate без официального API | Нарушение условий использования |
| AI как источник перевода и IPA | Продуктовый план требует dictionary-first; AI ошибается в транскрипции |
| Генерация контента на каждого пользователя | Умножает счёт без пользы, ломает идею общего `MeaningContent` |

---

## Что читать дальше

* Реализация pipeline обогащения — [04-week2-vocabulary.md](04-week2-vocabulary.md), шаги 29–38
* Таблицы `Meaning`, `MeaningContent`, `Translation` — [07-database-reference.md](07-database-reference.md)
* Фейковые провайдеры для тестов — [10-testing-reference.md](10-testing-reference.md)
* Проблемы с провайдерами — [11-troubleshooting.md](11-troubleshooting.md)
