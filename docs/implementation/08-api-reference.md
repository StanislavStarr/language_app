# Справочник: REST API

Контракт backend-роутеров и Angular API-слоя. ORM-модели наружу не отдаются — только Pydantic-схемы
(`CollectionCreate`, `CollectionUpdate`, `CollectionResponse`, `VocabularyItemResponse`,
`LexemeLookupRequest`, `LexemeLookupResponse` и остальные из индекса схем в конце).

Все прикладные эндпоинты под `/api/v1`. Служебные `/health` и `/ready` — нет.

У каждого метода: путь, нужна ли авторизация, схемы, JSON, специфичные коды ошибок.

---

## 1. Общие правила

### Базовый URL

```text
https://<host>/api/v1/...
```

Локально backend слушает `http://localhost:8000`. Nginx Mini App проксирует `/api/` на FastAPI.

### Формат

| Правило | Значение |
| --- | --- |
| Тело запроса и ответа | `application/json` |
| Даты | ISO 8601 UTC, например `2026-09-21T15:22:01Z` |
| Идентификаторы пользователя | UUID: `User`, `Collection`, `UserVocabularyItem`, `StudySession` |
| Идентификаторы лексикона | целое число: `Language`, `Lexeme`, `Meaning` |
| Поля JSON | `snake_case` |
| Пустые значения | `null`, не опускать обязательные ключи ответа |
| Списки | обёртка `{ "items": [...], "total": N }` там, где это указано |

Заголовок `X-Correlation-ID` клиент может прислать сам. Если его нет — backend генерирует и
возвращает в ответе. По этому id склеиваются логи Nginx, API и Celery.

### Авторизация

1. Mini App передаёт Telegram `initData` в `POST /api/v1/auth/telegram`.
2. Backend проверяет HMAC-подпись и свежесть `auth_date`.
3. Ответ содержит JWT. Telegram user id **не** является первичным ключом пользователя.
4. Все защищённые запросы несут заголовок:

```http
Authorization: Bearer <access_token>
```

TTL токена — 30 суток (`access_token_ttl_days`). Истёкший или поддельный токен даёт `401`.
Отсутствие заголовка на защищённом эндпоинте — `403`.

Публичные эндпоинты:

* `GET /health`
* `GET /ready`
* `GET /api/v1/languages`
* `POST /api/v1/auth/telegram`

Остальные требуют Bearer-токен.

### Списки и полная карточка

Списочные эндпоинты отдают **краткие сводки**. Полная учебная карточка загружается отдельно:

```text
GET /api/v1/vocabulary/{id}
```

Нельзя подмешивать IPA, аудио, definition и example в список темы — это лишний трафик и лишние
запросы к связанным таблицам.

### «Все слова» — не коллекция

`GET /api/v1/vocabulary` без `collection_id` возвращает весь личный словарь.
Отдельной системной темы «Все слова» нет и создавать её не нужно.

### `source_context`

Это персональные данные владельца: принимаются в lookup и при создании карточки, возвращаются
только владельцу в `GET /vocabulary/{id}`, не пишутся в общий `Meaning` / `MeaningContent`.

### `enrichment_status`

После выбора значения карточка готовится в фоне. Статусы:

| Значение | Смысл | Можно запускать занятие |
| --- | --- | --- |
| `PENDING` | задача ещё не взята воркером | нет |
| `ENRICHING` | воркер работает | нет |
| `READY` | все нужные поля на месте | да |
| `PARTIAL` | часть полей отсутствует, карточка всё же пригодна | да, с деградацией |
| `FAILED` | подготовка не удалась | нет |

Частичная деградация — продуктовое правило: нет аудио или definition, но перевод есть → статус
`PARTIAL`, а не `FAILED`.

### Лимиты (неделя 4)

Контракт кодов `429` действует сразу. Счётчики Redis подключаются на шаге 60.
Пока лимиты не включены, `429` не должен возникать в обычном сценарии.

Планируемые пороги: 60 запросов/мин на пользователя; lookup 20/мин; AI 50 запросов/сутки
на пользователя (`AI_DAILY_REQUEST_LIMIT_PER_USER`); auth 10/мин с IP. Длины: `text` 1–80,
`source_context` и `personal_note` до 500, `name` темы 1–60, `description` до 300, phrase не больше
5 слов. При `429` — заголовок `Retry-After`.

---

## 2. Конверт ошибки

Все прикладные ошибки (после шага 61) имеют одну форму. Фронт читает и `error.message`, и строку
`detail` — второе поле дублирует сообщение, чтобы не ломать код недели 1.

```json
{
  "error": {
    "code": "not_found",
    "message": "Vocabulary item not found",
    "details": []
  },
  "detail": "Vocabulary item not found"
}
```

Ошибка валидации тела:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "Request validation failed",
    "details": [
      {
        "field": "text",
        "message": "String should have at most 80 characters"
      }
    ]
  },
  "detail": "Request validation failed"
}
```

При `429` заголовок `Retry-After` (секунды) обязателен:

```json
{
  "error": {
    "code": "rate_limited",
    "message": "Too many requests",
    "details": []
  },
  "detail": "Too many requests"
}
```

### Коды `error.code`

| `error.code` | HTTP | Когда |
| --- | --- | --- |
| `unauthorized` | 401 | нет/битый/истёкший JWT; невалидный `initData` |
| `forbidden` | 403 | нет заголовка Authorization; чужая сущность; системную тему менять нельзя |
| `not_found` | 404 | сущность не существует **или** принадлежит другому пользователю (не светить чужие id) |
| `conflict` | 409 | дубликат значения в словаре; активная сессия уже есть; повторное complete |
| `validation_failed` | 422 | Pydantic или доменная проверка (языки совпали, мало карточек для занятия) |
| `rate_limited` | 429 | превышен лимит |
| `not_ready` | 503 | `/ready`, если PostgreSQL или Redis недоступны |
| `auth_not_configured` | 503 | нет `TELEGRAM_BOT_TOKEN` |
| `internal_error` | 500 | непредвиденный сбой; в `message` нет стека и секретов |

Чужой UUID чужой темы отдаём как `404`, не `403`: клиент не должен отличать «нет» от «чужое».

У всех **защищённых** эндпоинтов без отдельной пометки возможны `401` / `403` / `429` в этом
конверте. В разделах ниже указаны только специфичные коды (`404`, `409`, `422`, `201`, `204`).

---

## 3. Перечисления контракта

Эти строки — литералы JSON, не внутренние имена Python-enum, хотя значения совпадают.

```text
CefrLevel:            A1 | A2 | B1 | B2 | C1 | C2
LexemeType:           word | phrase
PartOfSpeech:         noun | verb | adjective | adverb | pronoun | preposition
                      | conjunction | interjection | numeral | particle | phrase | unknown
EnrichmentStatus:     PENDING | ENRICHING | READY | PARTIAL | FAILED
MeaningSource:        dictionary | ai | internal
CollectionSystemKey:  irregular_verbs
StudySessionStatus:   in_progress | completed
StudySelectionMode:   random | manual
StudyFlowKind:        word | phrase | irregular_verb
StudyStageType:       introduction | matching | sentence_gap | definition_writing | irregular_forms
```

---

## 4. Сводка эндпоинтов

| Метод | Путь | Auth | Схемы |
| --- | --- | --- | --- |
| GET | `/health` | нет | `HealthResponse` |
| GET | `/ready` | нет | `ReadyResponse` |
| POST | `/api/v1/auth/telegram` | нет | `TelegramAuthRequest` → `AuthTokenResponse` |
| GET | `/api/v1/users/me` | да | `UserResponse` |
| PATCH | `/api/v1/users/me` | да | `UserOnboardingUpdate` → `UserResponse` |
| DELETE | `/api/v1/users/me` | да | пустое тело, `204` |
| GET | `/api/v1/languages` | нет | `LanguageResponse[]` |
| GET | `/api/v1/collections` | да | `CollectionListResponse` |
| POST | `/api/v1/collections` | да | `CollectionCreate` → `CollectionResponse` |
| GET | `/api/v1/collections/{id}` | да | `CollectionResponse` |
| PATCH | `/api/v1/collections/{id}` | да | `CollectionUpdate` → `CollectionResponse` |
| DELETE | `/api/v1/collections/{id}` | да | `204` |
| DELETE | `/api/v1/collections/{id}/items/{item_id}` | да | `204` |
| POST | `/api/v1/lexemes/lookup` | да | `LexemeLookupRequest` → `LexemeLookupResponse` |
| GET | `/api/v1/vocabulary` | да | `VocabularyItemListResponse` |
| POST | `/api/v1/vocabulary` | да | `VocabularyItemCreate` → `VocabularyItemResponse` |
| GET | `/api/v1/vocabulary/{id}` | да | `VocabularyItemResponse` |
| PATCH | `/api/v1/vocabulary/{id}` | да | `VocabularyItemUpdate` → `VocabularyItemResponse` |
| DELETE | `/api/v1/vocabulary/{id}` | да | `204` |
| POST | `/api/v1/study-sessions` | да | `StudySessionCreate` → `StudySessionResponse` |
| GET | `/api/v1/study-sessions/active` | да | `StudySessionResponse` или `204` |
| GET | `/api/v1/study-sessions/{id}` | да | `StudySessionResponse` |
| PATCH | `/api/v1/study-sessions/{id}/progress` | да | `StudySessionProgressUpdate` → `StudySessionResponse` |
| POST | `/api/v1/study-sessions/{id}/complete` | да | `StudySessionResponse` |

Отдельного CRUD для неправильных глаголов нет. Это системная коллекция, см. раздел 12.

---

## 5. Служебные эндпоинты

Они **не** монтируются под `/api/v1`. Их вызывают Docker healthcheck, Nginx и балансировщик, а не
Angular.

### `GET /health`

Авторизация: не нужна.

Проверка «процесс жив». К PostgreSQL и Redis не ходит.

**Схема ответа:** `HealthResponse`

```json
{
  "status": "ok"
}
```

Ошибки: в норме только `200`.

---

### `GET /ready`

Авторизация: не нужна.

Проверка «могу обслуживать трафик»: `SELECT 1` в PostgreSQL и `PING` в Redis.

**Схема ответа:** `ReadyResponse`

Успех:

```json
{
  "status": "ready",
  "checks": {
    "database": true,
    "redis": true
  }
}
```

Не готов — HTTP `503`, тот же JSON со `"status": "not_ready"` и соответствующим `false` в `checks`.
Это не конверт `error`: зонды ждут плоскую структуру.

---

## 6. Auth

### `POST /api/v1/auth/telegram`

Авторизация: не нужна.

Создаёт пользователя при первом входе, находит существующего по `AuthIdentity(provider=telegram)`,
выдаёт JWT приложения.

**Схема запроса:** `TelegramAuthRequest`

Поле `init_data` — сырая query-строка из `Telegram.WebApp.initData`, не JSON пользователя.

```json
{
  "init_data": "query_id=AAE...&user=%7B%22id%22%3A123456789%2C%22first_name%22%3A%22Ann%22%7D&auth_date=1726900000&hash=ab12cd..."
}
```

Ограничение: `min_length=1`, `max_length=4096`.

**Схема ответа:** `AuthTokenResponse`

Первый вход (onboarding ещё не пройден):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3YzllNjY3OS03NDI1LTQwZGUtOTQ0Yi1lMDdmYzFmOTBhZTciLCJpYXQiOjE3MjY5MDAwMDAsImV4cCI6MTcyOTQ5MjAwMH0.signature",
  "token_type": "bearer",
  "user": {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "native_language_id": null,
    "learning_language_id": null,
    "cefr_level": null,
    "onboarding_completed_at": null
  }
}
```

Повторный вход после onboarding возвращает те же поля с заполненными языками, уровнем и
`onboarding_completed_at`. `sub` внутри JWT — UUID пользователя, не Telegram id.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 401 | `unauthorized` | подпись неверна, строка обрезана, `auth_date` старше лимита свежести. Текст **одинаковый** для всех причин: `"Telegram init data is not valid"` |
| 422 | `validation_failed` | пустой `init_data`, длина > 4096 |
| 429 | `rate_limited` | слишком частые попытки с IP |
| 503 | `auth_not_configured` | не задан `TELEGRAM_BOT_TOKEN` |

В `message` нельзя писать «expired» vs «bad hash» — это подсказка для подбора подписи.

---

## 7. Users

### `GET /api/v1/users/me`

Авторизация: да.

**Схема ответа:** `UserResponse`

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "native_language_id": 1,
  "learning_language_id": 2,
  "cefr_level": "A2",
  "onboarding_completed_at": "2026-09-20T11:04:18Z"
}
```

Фронт считает onboarding пройденным, если `onboarding_completed_at !== null`. Специфичных кодов нет.

---

### `PATCH /api/v1/users/me`

Авторизация: да.

Onboarding — атомарная операция: все три поля обязательны. Частично «только уровень» отправить нельзя.

**Схема запроса:** `UserOnboardingUpdate`

```json
{
  "native_language_id": 1,
  "learning_language_id": 2,
  "cefr_level": "A2"
}
```

**Схема ответа:** `UserResponse` — как GET, с заполненными полями. Повторный PATCH меняет языки и
уровень, но **не** переписывает `onboarding_completed_at`.

В MVP реально поддерживается пара Russian → English (`native_language_id` русского,
`learning_language_id` английского). Архитектура это не запрещает, проверка «языки должны
различаться» — доменная, не привязка к кодам `ru`/`en`.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 422 | `validation_failed` | неизвестный `language_id`; родной = изучаемый; `cefr_level` не из enum |

---

### `DELETE /api/v1/users/me`

Авторизация: да.

Удаляет аккаунт и персональные данные: `User`, `AuthIdentity`, `UserVocabularyItem`,
пользовательские `Collection` / `CollectionItem`, `StudySession`, `ProductEvent`.

Общие `Lexeme`, `Meaning`, `Translation`, `MeaningContent`, системные неправильные глаголы
**не** удаляются.

Тело запроса пустое. Ответ: `204 No Content` без JSON.

Повторный запрос с тем же токеном после удаления — `401`. Специфичных кодов кроме этого нет.

---

## 8. Languages

### `GET /api/v1/languages`

Авторизация: не нужна.

Справочник для экрана onboarding. Сейчас две записи, порядок — по `name`.

**Схема элемента:** `LanguageResponse`

```json
[
  {"id": 2, "code": "en", "name": "English"},
  {"id": 1, "code": "ru", "name": "Russian"}
]
```

`id` стабилен только внутри данной базы: фронт выбирает по `code`, не хардкодит числа.

---

## 9. Collections

Тема (`Collection`) принадлежит пользователю, кроме системных (`is_system: true`, `user_id` в БД
пустой). Системные темы видны всем, изменять и удалять их клиент не может.

`system_key` нужен фронту, чтобы найти неправильные глаголы без сравнения имени на русском.

### `GET /api/v1/collections`

Авторизация: да.

Пользовательские темы + системные. «Все слова» в списке **нет**.

**Схема ответа:** `CollectionListResponse`

```json
{
  "items": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "name": "Неправильные глаголы",
      "description": "Базовые неправильные глаголы английского языка",
      "is_system": true,
      "system_key": "irregular_verbs",
      "items_count": 12,
      "created_at": "2026-09-01T00:00:00Z",
      "updated_at": "2026-09-01T00:00:00Z"
    },
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Путешествия",
      "description": "Слова из сериала",
      "is_system": false,
      "system_key": null,
      "items_count": 8,
      "created_at": "2026-09-18T09:11:00Z",
      "updated_at": "2026-09-21T10:02:44Z"
    }
  ],
  "total": 2
}
```

**Схема элемента:** `CollectionResponse`

`items_count` — сколько единиц словаря пользователя сейчас в теме. Для системной темы неправильных
глаголов это размер системного набора, а не персональный словарь. Специфичных кодов нет.

---

### `POST /api/v1/collections`

Авторизация: да.

**Схема запроса:** `CollectionCreate`

```json
{
  "name": "YouTube",
  "description": "Ролики про кулинарию"
}
```

`description` можно опустить или передать `null`. `is_system` клиент **не** присылает.

**Схема ответа:** `CollectionResponse`, HTTP `201`

```json
{
  "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "name": "YouTube",
  "description": "Ролики про кулинарию",
  "is_system": false,
  "system_key": null,
  "items_count": 0,
  "created_at": "2026-09-21T15:40:12Z",
  "updated_at": "2026-09-21T15:40:12Z"
}
```

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 409 | `conflict` | у пользователя уже есть тема с таким `name` (без учёта регистра, после trim) |
| 422 | `validation_failed` | пустое имя, длина, description > 300 |

---

### `GET /api/v1/collections/{id}`

Авторизация: да.

Одна тема без списка слов. Слова темы берутся через `GET /api/v1/vocabulary?collection_id={id}`.
Так список и карточка темы не дублируют контракт словаря.

**Схема ответа:** `CollectionResponse` — тот же JSON, что элемент списка.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 404 | `not_found` | нет такой темы или она чужая |

---

### `PATCH /api/v1/collections/{id}`

Авторизация: да.

**Схема запроса:** `CollectionUpdate`

Все поля опциональны, передаются только изменяемые.

```json
{
  "name": "Travel",
  "description": null
}
```

`description: null` очищает описание. Отсутствие ключа описание не трогает.

**Схема ответа:** `CollectionResponse`

Системную тему менять нельзя.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 403 | `forbidden` | `is_system = true` |
| 404 | `not_found` | |
| 409 | `conflict` | имя пересекается с другой темой пользователя |
| 422 | `validation_failed` | пустое имя, сверх лимита длины |

---

### `DELETE /api/v1/collections/{id}`

Авторизация: да.

Удаляет тему и связи `CollectionItem`. Сами `UserVocabularyItem` остаются в «Всех словах».

Ответ: `204 No Content`.

Системную тему удалить нельзя — `403` с тем же `error.code: forbidden`. Иначе `404`, если темы нет.

---

### `DELETE /api/v1/collections/{id}/items/{item_id}`

Авторизация: да.

Снимает карточку с темы, не удаляя её из личного словаря.

`id` — UUID коллекции, `item_id` — UUID `UserVocabularyItem`.

Ответ: `204 No Content`.

Повторное удаление уже снятой связи — `404`.

Из системной темы неправильных глаголов персональные карточки так не снимаются: набор общий.
Запрос к системной теме даёт `403`.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 403 | `forbidden` | системная тема |
| 404 | `not_found` | нет темы, нет карточки, карточка не в этой теме |

Чтобы удалить слово из словаря целиком — `DELETE /api/v1/vocabulary/{id}`.

---

## 10. Lexeme lookup

Один эндпоинт закрывает три действия: первый поиск, «Показать ещё», «Нет нужного значения».

Отдельный `POST /lexemes/lookup/more` **не** вводим: это тот же поиск с другим смещением, а два
почти одинаковых контракта разъедутся. Пагинация — поле `offset` в теле, не query: у POST query
легко потерять в клиенте, а `text` и `source_context` и так в JSON.

AI fallback — флаг `use_ai_fallback` на том же запросе, а не отдельный URL. Pipeline один,
меняется только последний шаг. Фронт обязан сначала показать словарные значения и вызвать fallback
только по кнопке пользователя.

### `POST /api/v1/lexemes/lookup`

Авторизация: да.

**Схема запроса:** `LexemeLookupRequest`

```json
{
  "text": "bank",
  "source_context": "He sat on the bank of the river.",
  "offset": 0,
  "use_ai_fallback": false
}
```

| Поле | Тип | Правила |
| --- | --- | --- |
| `text` | string | обязательно, 1–80 символов, trim на сервере |
| `source_context` | string \| null | до 500 символов; для fallback желателен |
| `offset` | int | по умолчанию `0`, шаг страницы всегда `3`, `offset >= 0` |
| `use_ai_fallback` | bool | по умолчанию `false` |

Нормализация `text` (регистр, пробелы) выполняется на сервере. Клиент шлёт как ввёл пользователь.

**Схема ответа:** `LexemeLookupResponse`

Первая страница словарных значений:

```json
{
  "text": "bank",
  "normalized_text": "bank",
  "lexeme_type": "word",
  "typo_suggestion": null,
  "offset": 0,
  "limit": 3,
  "has_more": true,
  "used_ai_fallback": false,
  "meanings": [
    {
      "meaning_id": 101,
      "lexeme_id": 50,
      "part_of_speech": "noun",
      "translation": "берег",
      "source": "dictionary",
      "ipa": "bæŋk"
    },
    {
      "meaning_id": 102,
      "lexeme_id": 50,
      "part_of_speech": "noun",
      "translation": "банк",
      "source": "dictionary",
      "ipa": "bæŋk"
    },
    {
      "meaning_id": 103,
      "lexeme_id": 50,
      "part_of_speech": "verb",
      "translation": "полагаться",
      "source": "dictionary",
      "ipa": "bæŋk"
    }
  ]
}
```

**Схема элемента значения:** `LookupMeaningResponse`

Definition и example в lookup **не** входят: их готовит enrichment после выбора `meaning_id`.
На экране выбора достаточно перевода, части речи и транскрипции, если она уже известна.

#### «Показать ещё»

Тот же `text` и `source_context`, `offset: 3`, `use_ai_fallback: false`.

```json
{
  "text": "bank",
  "source_context": "He sat on the bank of the river.",
  "offset": 3,
  "use_ai_fallback": false
}
```

Ответ — тот же `LexemeLookupResponse`: `offset: 3`, до трёх следующих `meanings`, `has_more: false`,
если страница последняя. Пустая страница (`offset` за пределами) — `meanings: []`, HTTP `200`.

#### Опечатка

Сервер не подменяет ввод сам. Если `pg_trgm` нашёл близкую лексемму, заполняется
`typo_suggestion`, а `meanings` относятся к **введённому** тексту (часто пустые).

```json
{
  "text": "clarfy",
  "normalized_text": "clarfy",
  "lexeme_type": "word",
  "typo_suggestion": "clarify",
  "offset": 0,
  "limit": 3,
  "has_more": false,
  "used_ai_fallback": false,
  "meanings": []
}
```

Фронт показывает «Возможно, вы имели в виду clarify?» и при согласии повторяет lookup с
`text: "clarify"`.

#### Phrase

`lexeme_type: "phrase"`, если после нормализации 2–5 слов. Иначе `"word"`. JSON тот же, что у word:
`part_of_speech` обычно `"phrase"`, `ipa` часто `null`.

#### AI fallback: «Нет нужного значения»

```json
{
  "text": "bank",
  "source_context": "He sat on the bank of the river.",
  "offset": 0,
  "use_ai_fallback": true
}
```

При `use_ai_fallback: true` поле `offset` игнорируется (всегда первая и единственная страница
AI-результата). `source_context` уходит в провайдер, в общий кэш `MeaningContent` **не** пишется.

Ответ создаёт (или переиспользует) `Meaning` со `source: ai`, чтобы фронт мог сразу вызвать
`POST /vocabulary` с `meaning_id`.

```json
{
  "text": "bank",
  "normalized_text": "bank",
  "lexeme_type": "word",
  "typo_suggestion": null,
  "offset": 0,
  "limit": 3,
  "has_more": false,
  "used_ai_fallback": true,
  "meanings": [
    {
      "meaning_id": 501,
      "lexeme_id": 50,
      "part_of_speech": "noun",
      "translation": "берег реки",
      "source": "ai",
      "ipa": null
    }
  ]
}
```

Если AI не смог разобрать ввод — `200` с пустым `meanings`, не `404`. Пустой результат — валидный
исход поиска, пользователь остаётся на том же экране.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 422 | `validation_failed` | длина, phrase > 5 слов, отрицательный offset |
| 429 | `rate_limited` | общий lookup-лимит или суточный AI-лимит. Для AI `message`: `"Daily AI lookup limit exceeded"` |

---

## 11. Vocabulary

Единица словаря — `UserVocabularyItem`. Уникальность: пара `user_id + meaning_id`.
Одно значение нельзя добавить дважды; разные значения одной лексемы (`bank` берег / банк) — можно.

### `GET /api/v1/vocabulary`

Авторизация: да.

Краткие сводки для списка темы и экрана «Все слова».

**Query-параметры**

| Параметр | Тип | Смысл |
| --- | --- | --- |
| `collection_id` | UUID, опционально | фильтр по теме; без параметра — все слова пользователя |
| `offset` | int, по умолчанию 0 | |
| `limit` | int, по умолчанию 50, максимум 100 | |

**Схема ответа:** `VocabularyItemListResponse`

«Все слова»:

```json
{
  "items": [
    {
      "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "text": "bank",
      "translation": "берег",
      "lexeme_type": "word",
      "enrichment_status": "READY"
    },
    {
      "id": "1c1a7e2a-0d4f-4c3a-9f11-2a6b8c0d1e2f",
      "text": "look forward to",
      "translation": "с нетерпением ждать",
      "lexeme_type": "phrase",
      "enrichment_status": "ENRICHING"
    }
  ],
  "total": 2
}
```

**Схема элемента списка:** `VocabularyItemSummaryResponse`

Поля списка по продукту: текст, перевод, тип, статус. IPA/аудио/заметки сюда не входят.

Фильтр по теме: `?collection_id={uuid}`. Для `irregular_verbs` список в том же формате сводки.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 404 | `not_found` | `collection_id` не существует или чужой |
| 422 | `validation_failed` | `limit` вне диапазона |

---

### `POST /api/v1/vocabulary`

Авторизация: да.

Пользователь уже выбрал `meaning_id` на экране lookup.

**Схема запроса:** `VocabularyItemCreate`

```json
{
  "meaning_id": 101,
  "collection_ids": [
    "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
  ],
  "source_context": "He sat on the bank of the river."
}
```

| Поле | Правила |
| --- | --- |
| `meaning_id` | обязателен, должен существовать |
| `collection_ids` | массив UUID, может быть пустым (слово только в «Всех словах») |
| `source_context` | опционально, до 500 символов |

Системные id в `collection_ids` запрещены — `422`. Неправильные глаголы не добавляют вручную.

После создания сразу ставится Celery-задача enrichment. Ответ не ждёт готовности карточки.

**Схема ответа:** `VocabularyItemResponse`, HTTP `201`. Те же ключи, что у GET ниже:
`enrichment_status: "PENDING"`, `audio_url` / `definition` / `example` / `personal_note` равны `null`.
Вложенные темы — `VocabularyItemCollectionRef` (`id`, `name`), не полный `CollectionResponse`.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 404 | `not_found` | нет `meaning_id`; нет одной из тем (или чужая) |
| 409 | `conflict` | это значение уже есть у пользователя |
| 422 | `validation_failed` | системная тема в `collection_ids`; слишком длинный context |

Повтор с тем же `meaning_id` — `409`, enrichment заново не ставится. Клиент показывает, что слово уже сохранено.

---

### `GET /api/v1/vocabulary/{id}`

Авторизация: да.

Полная карточка владельца. Фронт дергает её по клику в списке и может опрашивать, пока статус
`PENDING` / `ENRICHING` (интервал — на клиенте, отдельного websocket нет).

**Схема ответа:** `VocabularyItemResponse`

Готовая карточка:

```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "meaning_id": 101,
  "text": "bank",
  "normalized_text": "bank",
  "lexeme_type": "word",
  "part_of_speech": "noun",
  "translation": "берег",
  "ipa": "bæŋk",
  "audio_url": "https://cdn.example.local/audio/bank.mp3",
  "definition": "the land along the side of a river",
  "example": "We sat on the bank of the river.",
  "source_context": "He sat on the bank of the river.",
  "personal_note": "встретил в сериале, не путать с банком",
  "enrichment_status": "READY",
  "study_count": 2,
  "last_studied_at": "2026-09-21T18:00:00Z",
  "collections": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Путешествия"
    }
  ],
  "created_at": "2026-09-21T16:01:09Z",
  "updated_at": "2026-09-21T16:07:44Z"
}
```

Частичная деградация (`PARTIAL`) — тот же `VocabularyItemResponse`, но часть из `audio_url` /
`definition` / `example` равна `null`. Карточка годится для занятия.
`FAILED` — нет даже `translation`. Это редкость.

Специфичный код GET: `404`, если карточки нет или она чужая.

---

### `PATCH /api/v1/vocabulary/{id}`

Авторизация: да.

В MVP меняется только личная заметка. Перевод, IPA и темы этим методом не правятся.

**Схема запроса:** `VocabularyItemUpdate`

```json
{
  "personal_note": "запомнить как берег возле воды"
}
```

`personal_note: null` очищает заметку.

**Схема ответа:** `VocabularyItemResponse` (полная карточка после изменения).

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 404 | `not_found` | |
| 422 | `validation_failed` | длина > 500 |

---

### `DELETE /api/v1/vocabulary/{id}`

Авторизация: да.

Удаляет карточку из словаря и из всех пользовательских тем. Общий `Meaning` остаётся.

Ответ: `204 No Content`. Специфичный код: `404`.

---

## 12. Неправильные глаголы

Отдельного `/api/v1/irregular-verbs` нет: системная коллекция `is_system: true`,
`system_key: "irregular_verbs"`. Она уже есть в `GET /collections`; занятие стартует тем же
`POST /study-sessions`. Отличие только в payload: `flow_kind: "irregular_verb"` и этап
`irregular_forms`. Сидинг набора — шаг 48, не API клиента.

Системные глаголы не обязаны быть `UserVocabularyItem`. `PATCH`/`DELETE` системной темы — `403`.

---

## 13. Study sessions

Backend отдаёт готовые упражнения в `stages`: фронт не собирает matching и не вырезает пропуски.
Проверку (строгая, 3 попытки) считает клиент, поэтому правильные ответы входят в payload.

В занятие попадают только `READY` и `PARTIAL`. Одновременно одна сессия `in_progress`.
Маршрут `/study-sessions/active` регистрируйте раньше `/study-sessions/{id}`.

---

### `POST /api/v1/study-sessions`

Авторизация: да.

**Схема запроса:** `StudySessionCreate`

Случайный набор из темы, 10 слов:

```json
{
  "collection_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "size": 10,
  "mode": "random"
}
```

Ручной выбор (`item_ids`.length === `size`):

```json
{
  "collection_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "size": 2,
  "mode": "manual",
  "item_ids": [
    "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "6a6e2f7f-5c9e-418f-9e66-7f1a3b5c6274"
  ]
}
```

`collection_id: null` — занятие по всем словам. Системные неправильные глаголы — `collection_id`
темы с `system_key: "irregular_verbs"`.

| Поле | Правила |
| --- | --- |
| `collection_id` | UUID темы или `null` (= все слова) |
| `size` | 1–50; пресеты UI: 5, 10, 15, custom |
| `mode` | `random` или `manual` |
| `item_ids` | обязателен при `manual`, длина должна равняться `size`; при `random` не передаётся |

Отбор `random`: сначала единицы с `study_count = 0`, недостающее добирается из уже изучавшихся.

Если готовых карточек меньше `size` — сессия создаётся на доступном количестве, в ответе фактический
`size`. Если готовых ноль — `422`.

**Схема ответа:** `StudySessionResponse`, HTTP `201`. Тело такое же, как у GET: со `stages`.
Пример полного payload — ниже в GET.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 404 | `not_found` | нет темы / нет одного из `item_ids` |
| 409 | `conflict` | уже есть `in_progress`; в теле полезно вернуть id |
| 422 | `validation_failed` | `manual` без `item_ids`; id не из темы; карточка не READY/PARTIAL; size вне диапазона; ноль кандидатов |

Пример 409 — фронт должен уйти в восстановление:

```json
{
  "error": {
    "code": "conflict",
    "message": "An unfinished study session already exists",
    "details": [
      {
        "field": "session_id",
        "message": "550e8400-e29b-41d4-a716-446655440000"
      }
    ]
  },
  "detail": "An unfinished study session already exists"
}
```

---

### `GET /api/v1/study-sessions/active`

Авторизация: да.

Нужен, чтобы после закрытия Telegram продолжить занятие (шаг 57).

Если сессия `in_progress` есть — `200` и полный `StudySessionResponse`.
Если нет — `204 No Content` без тела. Не используйте `404`: «нет активного занятия» — норма,
а не ошибка. Других специфичных кодов нет.

---

### `GET /api/v1/study-sessions/{id}`

Авторизация: да.

Возвращает сессию вместе с упражнениями и курсором прогресса.

**Схема ответа:** `StudySessionResponse`

#### Flow обычного слова (`flow_kind: "word"`)

Этапы: `introduction` → `matching` → `sentence_gap` → `definition_writing`.

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress",
  "collection_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "mode": "random",
  "size": 2,
  "flow_kind": "word",
  "current_stage": "introduction",
  "current_item_index": 0,
  "started_at": "2026-09-21T19:00:00Z",
  "completed_at": null,
  "items": [
    {"position": 0, "vocabulary_item_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d", "text": "bank", "lexeme_type": "word"},
    {"position": 1, "vocabulary_item_id": "6a6e2f7f-5c9e-418f-9e66-7f1a3b5c6274", "text": "clarify", "lexeme_type": "word"}
  ],
  "stages": [
    {
      "type": "introduction",
      "items": [
        {
          "vocabulary_item_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
          "text": "bank",
          "ipa": "bæŋk",
          "audio_url": "https://cdn.example.local/audio/bank.mp3",
          "translation": "берег",
          "definition": "the land along the side of a river",
          "example": "We sat on the bank of the river."
        },
        {
          "vocabulary_item_id": "6a6e2f7f-5c9e-418f-9e66-7f1a3b5c6274",
          "text": "clarify",
          "ipa": "ˈklær.ɪ.faɪ",
          "audio_url": "https://cdn.example.local/audio/clarify.mp3",
          "translation": "прояснить",
          "definition": "to make something easier to understand",
          "example": "Could you clarify what you mean?"
        }
      ]
    },
    {
      "type": "matching",
      "left": [
        {"id": "m-l-0", "vocabulary_item_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d", "text": "bank"},
        {"id": "m-l-1", "vocabulary_item_id": "6a6e2f7f-5c9e-418f-9e66-7f1a3b5c6274", "text": "clarify"}
      ],
      "right": [
        {"id": "m-r-1", "vocabulary_item_id": "6a6e2f7f-5c9e-418f-9e66-7f1a3b5c6274", "text": "прояснить"},
        {"id": "m-r-0", "vocabulary_item_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d", "text": "берег"}
      ]
    },
    {
      "type": "sentence_gap",
      "word_bank": ["bank", "clarify"],
      "prompts": [
        {
          "vocabulary_item_id": "6a6e2f7f-5c9e-418f-9e66-7f1a3b5c6274",
          "sentence_with_gap": "Could you _____ what you mean?",
          "answer": "clarify"
        }
      ]
    },
    {
      "type": "definition_writing",
      "word_bank": ["bank", "clarify"],
      "prompts": [
        {
          "vocabulary_item_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
          "definition": "the land along the side of a river",
          "answer": "bank"
        }
      ]
    }
  ]
}
```

`word_bank` на этапах 3–4 не сокращается после верных ответов. Правый ряд matching перемешан на
сервере один раз. В реальной сессии на `sentence_gap` и `definition_writing` по одному prompt
на каждую единицу; в примере выше массив укорочен.

Перевод на этапе знакомства фронт показывает размытым; API отдаёт его открытым текстом.

Если у `PARTIAL`-карточки нет `example`, prompt всё равно есть с `"skipped": true`,
`"sentence_with_gap": null`, `"answer"` заполнен. Фронт не показывает эту единицу и не считает ошибку.

#### Flow phrase (`flow_kind: "phrase"`)

Этапа `sentence_gap` в массиве `stages` **нет**: карточка → matching → написание по definition.

```json
{
  "id": "661f9511-f3ac-52e5-b827-557766551111",
  "status": "in_progress",
  "collection_id": null,
  "mode": "manual",
  "size": 1,
  "flow_kind": "phrase",
  "current_stage": "matching",
  "current_item_index": 0,
  "started_at": "2026-09-21T19:10:00Z",
  "completed_at": null,
  "items": [
    {
      "position": 0,
      "vocabulary_item_id": "1c1a7e2a-0d4f-4c3a-9f11-2a6b8c0d1e2f",
      "text": "look forward to",
      "lexeme_type": "phrase"
    }
  ],
  "stages": [
    {
      "type": "introduction",
      "items": [
        {
          "vocabulary_item_id": "1c1a7e2a-0d4f-4c3a-9f11-2a6b8c0d1e2f",
          "text": "look forward to",
          "ipa": null,
          "audio_url": null,
          "translation": "с нетерпением ждать",
          "definition": "to feel happy and excited about something that is going to happen",
          "example": "I look forward to meeting you."
        }
      ]
    },
    {
      "type": "matching",
      "left": [
        {
          "id": "m-l-0",
          "vocabulary_item_id": "1c1a7e2a-0d4f-4c3a-9f11-2a6b8c0d1e2f",
          "text": "look forward to"
        }
      ],
      "right": [
        {
          "id": "m-r-0",
          "vocabulary_item_id": "1c1a7e2a-0d4f-4c3a-9f11-2a6b8c0d1e2f",
          "text": "с нетерпением ждать"
        }
      ]
    },
    {
      "type": "definition_writing",
      "word_bank": ["look forward to"],
      "prompts": [
        {
          "vocabulary_item_id": "1c1a7e2a-0d4f-4c3a-9f11-2a6b8c0d1e2f",
          "definition": "to feel happy and excited about something that is going to happen",
          "answer": "look forward to"
        }
      ]
    }
  ]
}
```

Смешанный набор word+phrase в одном занятии: `flow_kind` берётся по **составу пачки**. Если есть
хотя бы одно обычное слово — `word`, и phrase-единицы на `sentence_gap` получают `skipped: true`.
Если пачка из одних фраз — `phrase`. Так фронт не ветвит логику на каждую карточку сверх флага
`skipped`.

#### Flow неправильных глаголов (`flow_kind: "irregular_verb"`)

Этапы: `introduction` → `irregular_forms`. Matching, gap и definition **не** используются.

```json
{
  "id": "7720a622-04bd-63f6-c938-668877662222",
  "status": "in_progress",
  "collection_id": "11111111-1111-4111-8111-111111111111",
  "mode": "random",
  "size": 1,
  "flow_kind": "irregular_verb",
  "current_stage": "introduction",
  "current_item_index": 0,
  "started_at": "2026-09-21T19:20:00Z",
  "completed_at": null,
  "items": [
    {
      "position": 0,
      "vocabulary_item_id": null,
      "irregular_verb_id": 3,
      "text": "go",
      "lexeme_type": "word"
    }
  ],
  "stages": [
    {
      "type": "introduction",
      "items": [
        {
          "irregular_verb_id": 3,
          "base": "go",
          "past_simple": "went",
          "past_participle": "gone",
          "translation": "идти",
          "base_audio_url": "https://cdn.example.local/audio/go.mp3",
          "past_audio_url": "https://cdn.example.local/audio/went.mp3",
          "participle_audio_url": "https://cdn.example.local/audio/gone.mp3"
        }
      ]
    },
    {
      "type": "irregular_forms",
      "prompts": [
        {
          "irregular_verb_id": 3,
          "prompt_kind": "full_forms",
          "stem": "go",
          "expected_past_simple": "went",
          "expected_past_participle": "gone"
        },
        {
          "irregular_verb_id": 3,
          "prompt_kind": "past_simple_of",
          "stem": "go",
          "expected_past_simple": "went",
          "expected_past_participle": null
        },
        {
          "irregular_verb_id": 3,
          "prompt_kind": "past_participle_of",
          "stem": "go",
          "expected_past_simple": null,
          "expected_past_participle": "gone"
        }
      ]
    }
  ]
}
```

`prompt_kind`:

* `full_forms` — UI «go → ? → ?»;
* `past_simple_of` — «Past Simple of go»;
* `past_participle_of` — «Past Participle of go».

`vocabulary_item_id` у системных глаголов может быть `null`: это не личный словарь.
Прогресс всё равно идёт по `current_stage` + `current_item_index` / индексу prompt.
Специфичный код GET сессии: `404`.

---

### `PATCH /api/v1/study-sessions/{id}/progress`

Авторизация: да.

Сохраняет курсор, чтобы после перезапуска Mini App открыть тот же этап и ту же единицу.
Попытки и правильность ответа живут на клиенте; на сервер достаточно курсора. Опционально можно
прислать счётчик попыток текущей единицы — тогда восстановление покажет «осталось 2 попытки».

**Схема запроса:** `StudySessionProgressUpdate`

```json
{
  "current_stage": "sentence_gap",
  "current_item_index": 1,
  "current_attempts": 2
}
```

`current_stage` — значение `StudyStageType` из **фактического** `stages` этой сессии
(для phrase нельзя прислать `sentence_gap`).

`current_item_index` — индекс внутри текущего этапа (слово на introduction / prompt на gap).
`0`-based.

**Схема ответа:** `StudySessionResponse` с обновлённым курсором, `stages` те же.

Нельзя двигать `completed` сессию.

| HTTP | `error.code` | Когда |
| --- | --- | --- |
| 404 | `not_found` | |
| 409 | `conflict` | сессия уже `completed` |
| 422 | `validation_failed` | этап не из flow; индекс вне диапазона |

---

### `POST /api/v1/study-sessions/{id}/complete`

Авторизация: да.

Тело пустое. Помечает сессию `completed`, ставит `completed_at`, увеличивает `study_count` и
`last_studied_at` у всех `UserVocabularyItem` занятия (для системных глаголов счётчик личного
словаря не трогается).

Сложные слова и ошибки **не** блокируют завершение. Баллов в MVP нет.

**Схема ответа:** `StudySessionResponse`. `status` становится `completed`, заполняется
`completed_at`. `stages` после complete можно отдать пустыми: занятие больше не воспроизводится.
GET по id остаётся `200`.

Повторный complete — `409`. Иначе `404`.

---

## 14. Индекс Pydantic-схем

Имена копируются в `schemas.py` и во frontend-интерфейсы один в один. Этапы сессии — union по `type`.

```text
HealthResponse, ReadyResponse, ErrorResponse, ErrorDetail
TelegramAuthRequest, AuthTokenResponse, UserResponse, UserOnboardingUpdate, LanguageResponse
CollectionCreate, CollectionUpdate, CollectionResponse, CollectionListResponse
LexemeLookupRequest, LexemeLookupResponse, LookupMeaningResponse
VocabularyItemCreate, VocabularyItemUpdate, VocabularyItemSummaryResponse
VocabularyItemListResponse, VocabularyItemResponse, VocabularyItemCollectionRef
StudySessionCreate, StudySessionProgressUpdate, StudySessionResponse, StudySessionItemRef
StudyStageIntroduction, StudyStageMatching, StudyStageSentenceGap
StudyStageDefinitionWriting, StudyStageIrregularForms
```

---

## Что читать дальше

* Реализация лексикона, lookup, тем и enrichment — [04-week2-vocabulary.md](04-week2-vocabulary.md)
* Учебные сессии, этапы, неправильные глаголы — [05-week3-study.md](05-week3-study.md)
* Словари, AI и аудио за этим контрактом — [09-integrations-reference.md](09-integrations-reference.md)
