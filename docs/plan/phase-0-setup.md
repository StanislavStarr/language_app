# Фаза 0 — Подготовка (~4 ч)

**Результат:** репозиторий очищен от Angular/Telegram/Yandex, локальный Postgres поднимается
одной командой, аккаунты и ключи готовы.

---

### T0.1 — Очистка репозитория                                  ~1 ч   [x]

**Цель:** в репозитории не осталось следов прежнего стека.
**Контекст:** DECISIONS.md ADR-001, ADR-004, ADR-012.
**Сделать:**
- удалить `frontend/`, `bot/`, `docs/implementation/`, `english_vocabulary_app_plan.md`
  (история остаётся в git);
- удалить корневой `.env.example`; создать `backend/.env.example` и `mobile/.env.example`
  с переменными из ARCHITECTURE.md (без значений);
- **человек вручную** переносит `OPENAI_API_KEY` из корневого `.env` в `backend/.env` и удаляет
  корневой `.env` (агент не читает `.env`);
- обновить `.gitignore`: убрать `.angular/`; добавить `.expo/`, `mobile/android/`, `mobile/ios/`,
  `*.apk`, `*.aab`, `backend/evals/.cache/`, `data/`; оставить `.env`, `.env.*`, `!.env.example`;
- `.editorconfig`: добавить `*.{tsx,js,mjs}` к отступу 2;
- `README.md` — короткая версия (что это, ссылки на docs, как запустить — заполняется в T6.8).

**Приёмка:** `git status` показывает только ожидаемые изменения; в репозитории нет упоминаний
Angular, Celery, Redis, Yandex, Telegram (кроме docs/DECISIONS.md).
**Не делать:** не создавать код приложений.

> Итог: выполнено при подготовке плана, кроме ручного шага с `.env`: перенести `OPENAI_API_KEY`
> из корневого `.env` в `backend/.env` и удалить корневой `.env`. Статус поменять на `[x]` после этого.

### T0.2 — Аккаунты и ключи (человек)                           ~1 ч   []

- [x] OpenAI: API-ключ проекта, **лимит расходов** в настройках (например, $10/мес).
- [x] Expo: аккаунт; организация для проекта (Create Organization) — понадобится iPhone-тестировщикам.
- [x] Expo Go установлен на телефоне.
- [x] GitHub: репозиторий, Actions включены.
- [ ] Neon и Render — можно отложить до T6.5.

### T0.3 — Локальная инфраструктура и Makefile                  ~2 ч   [x]

**Цель:** `make up` поднимает Postgres с pgvector; общие команды проекта в одном месте.
**Контекст:** ARCHITECTURE.md §12.
**Сделать:**
- `infra/docker-compose.yml`: сервис `postgres` на образе `pgvector/pgvector:pg17`, volume,
  healthcheck, порт 5432; вторая база `vocabulary_test` для тестов (init-скрипт);
- корневой `Makefile` с целями: `up`, `down`, `db-reset`, `backend-dev`, `backend-check`
  (ruff check, ruff format --check, mypy, pytest), `backend-fix` (ruff format, ruff check --fix),
  `migrate`, `migration name=...`, `mobile-dev`, `mobile-check` (tsc, eslint, steiger, jest),
  `api-types` (экспорт OpenAPI + генерация TS);
  цели, для которых ещё нет кода, допустимо добавить в T1.1/T1.7.

**Приёмка:** `make up` → `docker compose ps` показывает healthy postgres; `psql` видит обе базы.

> Итог: добавлены `infra/docker-compose.yml` (pgvector:pg17, healthcheck, init-скрипт для `vocabulary_test`; user/password/db — `vocabulary`) и корневой `Makefile`. Цели backend/mobile/api-types пока не работают — кода ещё нет (T1.1/T1.7); `api-types` ожидает `backend/scripts/export_openapi.py`.
