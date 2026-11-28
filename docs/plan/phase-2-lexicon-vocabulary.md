# Фаза 2 — Лексикон и личный словарь (~30 ч)

**Результат:** слово или выражение добавляется вручную: значения из Wiktionary, рекомендация по
контексту, AI fallback, опечатки; карточка готовится в фоне; темы работают; есть первые отчёты evals.

---

## Backend

### T2.1 — Разведка: данные Wiktextract                          ~3 ч   [x]

**Цель:** решения по импорту основаны на цифрах, а не на догадках.
**Контекст:** ARCHITECTURE.md §6.1; DECISIONS ADR-004.
**Сделать:**
- скачать английский JSONL с kaikki.org в `data/` (вне git);
- скрипт-исследование `backend/scripts/explore_wiktextract.py`: по топ-N частотных слов
  (`wordfreq`, `top_n_list("en", N)`) посчитать: долю найденных лемм, долю с IPA, с mp3, долю
  значений с русским переводом, среднее число значений, наличие форм (`forms`, `form_of`),
  число фраз (`pos = phrase`/`phrasal verb`/idioms), ожидаемый размер таблиц для N = 30k/60k/100k;
- отчёт `docs/spikes/lexicon-coverage.md` с таблицей и рекомендацией N и фильтров.

**Приёмка:** отчёт есть, рекомендация обоснована цифрами; в ARCHITECTURE.md §6.1 обновлены
параметры, если они меняются.
**Не делать:** не писать модели и импорт.

> Итог: скрипт `explore_wiktextract.py` (потоково читает `.jsonl` и `.jsonl.gz`, 2 минуты на «сырой» дамп) и отчёт `docs/spikes/lexicon-coverage.md`. Главная находка: общий дамп kaikki (3,4 ГБ) теряет большую часть русских переводов, поэтому источником импорта выбран «сырой» дамп `raw-wiktextract-data.jsonl.gz` (3 ГБ). Рекомендация: N = 60 000 (≈ 50 МБ), фразы с словами из топ-30k (≈ 28 тысяч, ≈ 11 МБ), перевод есть у ≈ 56% лемм, остальное переводит AI. ARCHITECTURE §6.1 обновлён; `wordfreq` добавлен в dev-зависимости.

### T2.2 — Модели лексикона                                      ~3 ч   [x]

**Контекст:** ARCHITECTURE.md §5.2; skill `backend-migration`.
**Сделать:** модели `lexeme`, `lexeme_form`, `meaning`, `translation`, `meaning_content`,
`sense_selection`, `irregular_verb` (только таблица) + миграция с индексами (GIN trgm);
enum'ы для `type`, `source`, `part_of_speech`, `cefr_level`, статусов; репозитории модуля `lexicon`:
поиск лексемы по кандидатам, значения с переводами (без N+1), похожие лексемы по trgm.
**Тесты:** репозитории на реальной БД: поиск по форме, порядок значений, trgm-подсказка.

> Итог: модуль `lexicon` — модели 7 таблиц (§5.2), миграция `0005` (GIN trigram на `lexeme.normalized_text`, индексы форм, значений и `sense_selection.selected_meaning_id`), перечисления, `LexemeRepository` (`find_by_candidates` с приоритетом кандидатов, `list_meanings` с переводами без N+1, `find_similar` по `pg_trgm`), 30 тестов на реальной БД. Отличия: `CefrLevel` перенесён в `languages`; добавлен общий помощник `string_enum` (используется в users, auth, usage, lexicon); `Lexeme.forms/meanings` не созданы (нет потребителя). Известное ограничение: порог trigram 0,45 пропускает перестановки в коротких словах — в `docs/backlog.md` для задачи lookup. `find_by_candidates` может вернуть одну лексему дважды (по тексту и по форме), сервис должен убрать дубли.

### T2.3 — Импорт лексикона                                      ~4 ч   [ ]

**Контекст:** отчёт T2.1; ARCHITECTURE.md §6.1.
**Сделать:** `backend/scripts/import_lexicon.py` (CLI: `--source`, `--top-n`, `--batch-size`,
`--dry-run`): потоковое чтение JSONL, фильтры, маппинг в модели, upsert батчами, идемпотентность,
итоговый отчёт (сколько лемм/форм/значений/переводов, размер таблиц).
**Приёмка:** импорт в локальную БД за разумное время (< 15 мин); повторный запуск не меняет
количество строк; выборочно: `go/went`, `bank` (несколько значений с переводами), `look forward to`.
**Тесты:** маппинг на фикстуре из ~20 строк JSONL (включая слово без перевода, форму, фразу, мусорную запись).

### T2.4 — NLP: нормализация и лемматизация                       ~3 ч   [ ]

**Контекст:** ARCHITECTURE.md §6.2 шаги 2–3; DECISIONS ADR-011.
**Сделать:** `integrations/nlp/`: `normalize_text`, `split_sentences(text) -> list[Span]`,
`lemma_candidates(sentence, char_start, char_end) -> list[LemmaCandidate(lemma, pos)]`;
загрузка `en_core_web_sm` один раз (ленивая, потокобезопасная), модель — зависимость
в `pyproject.toml`; синхронные вызовы spaCy выполняются через `asyncio.to_thread`.
**Тесты:** went→go, running→run, books→book, saw (глагол/существительное по контексту),
типографский апостроф, фраза из нескольких токенов, границы предложений с сокращениями (Mr., Dr.).

### T2.5 — Free Dictionary fallback                              ~2 ч   [ ]

**Сделать:** `integrations/dictionary/`: протокол `DictionaryProvider`, реализация
`FreeDictionaryProvider` (httpx, таймаут 5 с, 404 → `None`, нормализованный DTO: IPA, audio, значения).
**Тесты:** respx-фикстуры: успешный ответ, 404, таймаут, мусорный JSON.

### T2.6 — AI-слой                                               ~4 ч   [ ]

**Контекст:** ARCHITECTURE.md §9; skill `llm-feature`; DECISIONS ADR-008.
**Сделать:**
- `integrations/ai/provider.py`: `AIProvider` Protocol; DTO запросов; `AIResult[T]` с usage;
- `integrations/ai/openai_provider.py`: Responses API (`responses.parse`), таймауты, ретраи,
  маппинг ошибок в `AIProviderError`/`AIUnavailableError`, лог вызова (фича, модель, версия
  промпта, токены, латентность);
- промпты с версиями (`integrations/ai/prompts/`): `select_sense`, `generate_meaning_content`,
  `translate_meanings`, `generate_fallback_meanings`;
- Pydantic-схемы ответов с ограничениями длины и доменной валидацией (определение не содержит
  целевое слово и его формы; пример содержит; `selected_meaning_id` ∈ переданных или `null`);
- `FakeAIProvider` для тестов; `scripts/ai_smoke.py` — ручная проверка каждого метода на реальном API.

**Приёмка:** smoke-скрипт возвращает валидные ответы для `bank` в двух контекстах.
**Тесты:** валидация схем на хороших и плохих ответах; маппинг ошибок SDK.

### T2.7 — Lookup                                                ~4 ч   [ ]

**Контекст:** ARCHITECTURE.md §6.2; PRODUCT.md §6.4.
**Сделать:** `LookupService` и эндпоинты `POST /lexemes/lookup` (вариант `manual`; схема —
discriminated union, вариант `book` добавляется в T3.5), `GET /lexemes/{id}/meanings?offset=`,
`POST /lexemes/{id}/ai-meanings`; typo-подсказка; выбор значения с кэшем `sense_selection`;
списание `ai_lookup`; при исчерпании лимита — ответ без AI-шагов и флаг `ai_limited: true`.
**Тесты:** каждая ветка пайплайна с fake-провайдерами: найдено в БД, найдено по форме, Free
Dictionary, AI fallback, опечатка, кэш выбора значения (второй вызов не идёт в AI), лимит.

### T2.8 — Словарь и темы                                        ~4 ч   [ ]

**Контекст:** ARCHITECTURE.md §5.3, §6.3, §7.
**Сделать:** модули `vocabulary` и `collections`: модели, миграция, эндпоинты из §7;
`POST /vocabulary` (вариант `manual`) — транзакция + `defer` задачи после commit; дубликат →
409 `already_in_vocabulary` с id существующего; список с курсором и фильтрами; карточка с
`meaning_content`, переводом, источником и темами одним запросом (без N+1);
`GET /vocabulary/forms`.
**Тесты:** создание и дубликат; удаление из темы и из словаря; пагинация; формы включают
неправильные формы; чужой пользователь не видит чужие данные (404).

### T2.9 — Подготовка карточки (enrichment)                      ~3 ч   [ ]

**Контекст:** ARCHITECTURE.md §6.3.
**Сделать:** модуль `enrichment`: сервис + задача `enrich_vocabulary_item`; перевод при отсутствии;
`meaning_content` с `pg_advisory_xact_lock`; статусы `ready`/`partial`/`failed`; ретраи.
**Тесты:** готовая карточка; частичная (AI упал на определении); повторный запуск идемпотентен;
два элемента с одним значением → один вызов генерации.

### T2.10 — Каркас evals и первые наборы                          ~3 ч   [ ]

**Контекст:** ARCHITECTURE.md §9 (Evals); skill `llm-feature`; subagent `eval-analyst`.
**Сделать:** пакет `backend/evals/` (раннер, отчёт в markdown, judge); наборы
`sense_selection.jsonl` (40 кейсов: многозначные слова в разных контекстах, включая «ни одно
значение не подходит») и `meaning_content.jsonl` (30 значений × 2 уровня); правила-проверки
и judge для `meaning_content`; базовые отчёты в `docs/evals/`.
**Приёмка:** `uv run python -m evals run sense_selection` печатает метрики и пишет отчёт; есть
два отчёта.

## Mobile

### T2.11 — Сущности словаря                                     ~3 ч   [ ]

**Сделать:** `entities/lexeme`, `entities/vocabulary-item`, `entities/collection`: типы на основе
`schema.d.ts`, query keys, хуки запросов, UI-компоненты (`WordRow`, `EnrichmentStatusBadge`,
`MeaningOption`, `AudioButton` на `expo-audio`).
**Тесты:** `EnrichmentStatusBadge` по статусам; `AudioButton` без URL не рендерится.

### T2.12 — Вкладка «Словарь»                                    ~4 ч   [ ]

**Сделать:** `pages/vocabulary-home` («Все слова», «Неправильные глаголы» — заглушка, темы,
«Создать тему»), `pages/collection` (список слов со статусами, опрос каждые 3 с, пока есть
`pending`/`enriching`), `pages/word-card` (полная карточка, заметка, темы, удаление);
`features/manage-collection` (создать/переименовать/удалить с подтверждением).
**Приёмка:** на телефоне видно, как карточка переходит в «Готова».

### T2.13 — Добавление слова вручную                             ~4 ч   [ ]

**Контекст:** PRODUCT.md §6.4.
**Сделать:** `features/lookup-word` + `pages/add-word`: ввод (zod-валидация длины и числа слов),
контекст, выбор тем → результат lookup: рекомендованное значение сверху с переводом под контекст,
3 значения + «Показать ещё», «Нет нужного значения» → AI, подсказка опечатки, «Уже в словаре» →
переход к карточке; после добавления — «Добавить ещё» / «Открыть словарь»; сообщения по кодам
ошибок (`usage_limit_exceeded` и т. п.).
**Тесты:** валидация формы; отрисовка рекомендации; обработка `already_in_vocabulary`.
