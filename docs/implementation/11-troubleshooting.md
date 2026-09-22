# Справочник проблем

Этот файл открывают в момент, когда что-то не работает. Поэтому он организован не по темам, а по
симптомам: найдите строку, похожую на то, что видите в терминале или в консоли браузера, и идите
по цепочке «симптом — причина — решение».

Правило, которое экономит больше всего времени: **сначала сузьте слой, потом чините**. Приложение
состоит из семи контейнеров и трёх внешних провайдеров, и почти всегда первые две минуты диагностики
отвечают на вопрос «где именно ломается», после чего исправление занимает минуты.

## Оглавление

1. [Базовая диагностика](#1-базовая-диагностика)
2. [Окружение и установка](#2-окружение-и-установка)
3. [Docker Compose](#3-docker-compose)
4. [PostgreSQL и SQLAlchemy](#4-postgresql-и-sqlalchemy)
5. [Alembic](#5-alembic)
6. [Celery](#6-celery)
7. [Аутентификация Telegram](#7-аутентификация-telegram)
8. [Telegram Mini App и бот](#8-telegram-mini-app-и-бот)
9. [Angular](#9-angular)
10. [Внешние провайдеры](#10-внешние-провайдеры)
11. [Nginx и деплой](#11-nginx-и-деплой)
12. [Экстренные процедуры](#12-экстренные-процедуры)

---

## 1. Базовая диагностика

### Порядок сужения проблемы

Запрос из Mini App проходит путь: Telegram WebView → туннель → `nginx` (порт 8080) → `frontend`
или `backend` → `postgres` / `redis` → Celery-worker → внешний провайдер. Проверяйте слои от внешнего
к внутреннему и остановитесь на первом, который отвечает неправильно.

| Вопрос | Команда | Что значит плохой ответ |
| --- | --- | --- |
| Контейнеры живы? | `docker compose ps` | статус `Restarting` или `Exited` — идите в раздел 3 |
| Процесс backend жив? | `curl -s http://localhost:8080/health` | нет ответа — nginx или backend лежит, раздел 11 |
| Зависимости доступны? | `curl -s http://localhost:8080/ready` | `"database": false` — раздел 4, `"redis": false` — раздел 3 |
| API отвечает? | `curl -s http://localhost:8080/api/v1/languages` | 502 — раздел 11, 500 — смотрите логи backend |
| Фон работает? | `docker compose logs --tail=50 celery-worker` | нет строки `ready` — раздел 6 |

### Команды, которые нужны всегда

Все команды `docker compose` запускаются из папки `infra`, потому что там лежит
`infra/docker-compose.yml`.

```bash
cd infra
docker compose ps
docker compose logs --tail=100 backend
docker compose logs -f celery-worker
docker compose logs --since=10m nginx
```

Логи backend и worker — построчный JSON, поэтому фильтровать их удобно обычным поиском по ключам:

```bash
docker compose logs --no-color --tail=500 backend | grep '"level":"ERROR"'
docker compose logs --no-color --tail=500 celery-worker | grep '"message":"enrichment'
```

### Поиск по correlation_id

Каждый HTTP-запрос получает `correlation_id`, он же уходит в заголовок ответа `X-Correlation-ID` и в
JSON-логи Nginx. Это единственный надёжный способ связать запись фронта, API и фоновой задачи.

```bash
curl -si -H "X-Correlation-ID: debug-001" http://localhost:8080/api/v1/languages | grep -i correlation
docker compose logs --no-color backend nginx celery-worker | grep debug-001
```

Если идентификатор не задан клиентом, возьмите его из заголовка ответа в панели Network браузера и
ищите по нему.

### Прямой доступ к PostgreSQL и Redis

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\dt"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "select count(*) from users;"
```

```bash
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli -n 1 keys '*'
docker compose exec redis redis-cli -n 1 llen celery
docker compose exec redis redis-cli -n 0 keys 'enrichment:*'
```

Номера баз фиксированы: `0` — кэш и локи приложения, `1` — брокер Celery, `2` — результаты задач.

### Заход внутрь контейнера

```bash
docker compose exec backend bash
docker compose exec backend python -c "from app.common.settings import get_settings; print(get_settings().postgres_host)"
docker compose exec backend env | sort
```

Последняя команда отвечает на самый частый вопрос диагностики: «а какие переменные реально видит
процесс». Она же сразу показывает, подхватился ли `.env`.

---

## 2. Окружение и установка

### Angular CLI отказывается работать на Node 22.13.1

**Симптом.** При `ng new frontend` или `npm install -g @angular/cli@22`:

```text
Node.js version v22.13.1 detected.
The Angular CLI requires a minimum Node.js version of ^22.22.3 || ^24.15.0 || >=26.0.0.
npm warn EBADENGINE Unsupported engine
```

**Причина.** Angular CLI 22.1.7 объявляет диапазон `^22.22.3 || ^24.15.0 || >=26.0.0`. Версия 22.13.1
формально из ветки 22, но ниже минимума — установка либо прерывается, либо проходит и даёт
непредсказуемые сборки.

**Решение.** Обновите Node по [00-prerequisites.md](00-prerequisites.md), шаг 1:

```bash
brew upgrade node
node --version
```

Если нужны несколько версий одновременно:

```bash
nvm install 24
nvm alias default 24
nvm use 24
node --version
ng version
```

После смены версии Node удалите и переустановите зависимости фронта, иначе останутся бинарники,
собранные под старую версию:

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Прочие проблемы установки

| Симптом | Причина | Решение |
| --- | --- | --- |
| `zsh: command not found: uv` | установщик положил бинарь в `~/.local/bin`, его нет в `PATH` | перезапустить терминал; проверить `echo $PATH`, при необходимости добавить `export PATH="$HOME/.local/bin:$PATH"` в `~/.zshrc` |
| `FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'` локально | `ffmpeg` не установлен на macOS | `brew install ffmpeg`, затем `ffmpeg -version` |
| Та же ошибка внутри контейнера | собран старый образ backend, без `ffmpeg` | `docker compose build --no-cache backend && docker compose up -d backend` |
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | Docker Desktop не запущен | запустить Docker Desktop, дождаться зелёного индикатора, проверить `docker run --rm hello-world` |
| `uv sync` падает на `No solution found` | конфликт версий в `pyproject.toml` | `uv lock --upgrade`, при отсутствии результата — откатить последнюю добавленную зависимость |
| `ng version` показывает Angular 17 | глобально установлен старый CLI | `npm uninstall -g @angular/cli && npm install -g @angular/cli@22` |

### Порт занят другим процессом

**Симптом.** При `docker compose up`:

```text
Error response from daemon: Ports are not available: exposing port TCP 0.0.0.0:5432 -> 0.0.0.0:0:
listen tcp 0.0.0.0:5432: bind: address already in use
```

или при локальном запуске uvicorn: `[Errno 48] Address already in use`.

**Причина.** На хосте уже слушает другой процесс: системный PostgreSQL из Homebrew, второй экземпляр
compose, забытый `uv run uvicorn`, `npm start` с прошлого раза.

**Решение.** Найдите владельца порта и решите, кого выключать:

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
lsof -nP -iTCP:6379 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

```bash
kill <PID>
kill -9 <PID>
```

| Порт | Кто занимает чаще всего | Как выключить правильно |
| --- | --- | --- |
| 5432 | системный PostgreSQL из Homebrew | `brew services stop postgresql@17` |
| 6379 | системный Redis из Homebrew | `brew services stop redis` |
| 8000 | локальный `uv run uvicorn` из другого терминала | завершить процесс в его терминале |
| 8080 | другой проект на Docker | `docker ps` и остановить лишний контейнер |
| 4200 | забытый `npm start` | завершить процесс |

Если порт занимает контейнер из другого проекта:

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'
docker stop <container>
```

---

## 3. Docker Compose

### Контейнер перезапускается в цикле

**Симптом.** `docker compose ps` показывает `Restarting (1) 5 seconds ago`, приложение недоступно.

**Причина.** Процесс падает при старте, а `restart: unless-stopped` поднимает его снова. Настоящая
причина — в первых строках лога, которые уезжают вверх.

**Решение.** Читайте логи именно этого сервиса и с начала:

```bash
docker compose logs --tail=80 backend
docker compose logs --tail=80 celery-worker
docker compose logs --tail=80 telegram-bot
```

Типовые причины по тексту ошибки:

| В логе | Причина | Решение |
| --- | --- | --- |
| `pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings secret_key Field required` | нет обязательной переменной окружения | заполнить `.env`, см. раздел про `env_file` ниже |
| `ModuleNotFoundError: No module named 'app.enrichment.tasks'` | модуль указан в `include` Celery, но файла нет | создать `backend/app/enrichment/tasks.py` и `__init__.py` |
| `socket.gaierror: [Errno -2] Name or service not known` | обращение к `postgres` из процесса вне сети compose | раздел 4 |
| `aiogram.utils.token.TokenValidationError` | битый `TELEGRAM_BOT_TOKEN` | раздел 8 |

Чтобы отладить старт без перезапусков, временно запустите сервис в переднем плане:

```bash
docker compose up backend
```

### Переменные окружения не подхватились

**Симптом.** При запуске compose появляются предупреждения:

```text
WARN[0000] The "POSTGRES_DB" variable is not set. Defaulting to a blank string.
WARN[0000] The "POSTGRES_PASSWORD" variable is not set. Defaulting to a blank string.
```

а затем postgres падает с `Database is uninitialized and superuser password is not specified`.

**Причина.** Подстановка `${POSTGRES_DB}` в `docker-compose.yml` берёт значения из файла `.env`
**рядом с compose-файлом**, то есть из `infra/.env`. Наш `.env` лежит в корне репозитория. Директива
`env_file: ../.env` работает корректно — она про переменные внутри контейнера, но не про подстановку
в самом YAML.

**Решение.** Запускайте compose с явным указанием файла:

```bash
cd infra
docker compose --env-file ../.env up -d
```

Чтобы не повторять флаг, создайте симлинк один раз:

```bash
ln -s ../.env infra/.env
```

Проверка того, что реально увидит Docker после подстановки:

```bash
docker compose --env-file ../.env config | grep -A4 'POSTGRES_'
```

Проверка того, что видит процесс внутри контейнера:

```bash
docker compose exec backend env | grep -E 'POSTGRES|REDIS|OPENAI|TELEGRAM'
```

### Изменения в коде не применяются

| Что изменили | Почему не применилось | Что сделать |
| --- | --- | --- |
| файл в `backend/app/` | обычно применяется само через `--reload` | `docker compose logs backend`, убедиться в строке `Reloading...` |
| файл в `backend/app/`, но для worker | у `celery-worker` нет автоперезагрузки | `docker compose restart celery-worker` |
| `pyproject.toml`, новая зависимость | зависимости ставятся на этапе сборки образа | `docker compose build backend celery-worker && docker compose up -d` |
| `Dockerfile` | образ не пересобирается автоматически | `docker compose up -d --build` |
| `infra/nginx/nginx.conf` | конфиг смонтирован, но nginx его не перечитал | `docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload` |
| код фронта | статика вшита в образ `frontend` | `docker compose build frontend && docker compose up -d frontend` |
| `.env` | переменные читаются при старте контейнера | `docker compose --env-file ../.env up -d` |

Полная пересборка без кэша, когда есть подозрение на «залипший» слой:

```bash
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

### Volume с устаревшими данными PostgreSQL

**Симптом.** После смены `POSTGRES_PASSWORD` или `POSTGRES_USER` в `.env`:

```text
FATAL: password authentication failed for user "vocabulary"
```

**Причина.** Переменные `POSTGRES_*` применяются только при **первой** инициализации кластера.
Том `postgres-data` уже создан со старым паролем, и новые значения игнорируются.

**Решение локально** — пересоздать том (данные будут потеряны, см. раздел 12):

```bash
docker compose down -v
docker compose --env-file ../.env up -d postgres
```

**Решение без потери данных** — сменить пароль внутри работающей БД:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary \
  -c "alter user vocabulary with password 'новый_пароль';"
```

### depends_on и healthcheck

**Симптом.** Backend падает сразу после `docker compose up` с
`ConnectionRefusedError` или `asyncpg.exceptions.CannotConnectNowError`, а при повторном запуске
всё работает.

**Причина.** `depends_on` без условия ждёт только запуска контейнера, а не готовности сервиса.
PostgreSQL стартует несколько секунд.

**Решение.** В `infra/docker-compose.yml` для `backend` и `celery-worker` уже указано
`condition: service_healthy`. Проверьте, что healthcheck действительно проходит:

```bash
docker compose ps
docker inspect --format '{{json .State.Health}}' $(docker compose ps -q postgres) | python3 -m json.tool
```

Если статус `unhealthy`, смотрите вывод самой проверки — чаще всего `pg_isready` не проходит,
потому что переменные `POSTGRES_USER`/`POSTGRES_DB` пустые, то есть проблема на самом деле из
предыдущего пункта.

При `no space left on device` во время сборки помогает `docker system df` и `docker system prune -f`.
Вариант `docker system prune -a --volumes` удаляет и тома, включая `postgres-data`, — без
необходимости его не запускайте.

---

## 4. PostgreSQL и SQLAlchemy

### Не удаётся подключиться к базе

**Симптом.** При запуске `alembic` или `uvicorn` с хоста:

```text
socket.gaierror: [Errno 8] nodename nor servname provided, or not known
sqlalchemy.exc.InterfaceError: [Errno 61] Connection refused
```

**Причина.** `POSTGRES_HOST=postgres` — это имя сервиса в сети Docker Compose. С macOS такого хоста
нет, снаружи база доступна как `localhost:5432` (порт проброшен в compose).

**Решение.**

| Откуда запускаете | Значение `POSTGRES_HOST` | Команда |
| --- | --- | --- |
| контейнер `backend`, `celery-worker` | `postgres` | задано в `docker-compose.yml` |
| терминал macOS, `uv run ...` | `localhost` | `POSTGRES_HOST=localhost uv run alembic upgrade head` |
| `docker compose exec backend ...` | `postgres` | ничего не меняем |

Быстрая проверка доступности с хоста и изнутри сети:

```bash
docker compose exec postgres pg_isready -U vocabulary -d vocabulary
psql "postgresql://vocabulary:<пароль>@localhost:5432/vocabulary" -c "select 1;"
```

### MissingGreenlet

**Симптом.**

```text
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here. Was IO attempted in an unexpected place?
```

**Причина.** Код обратился к данным, для получения которых нужен неявный SQL-запрос: к ленивой связи
(`lexeme.meanings`) или к полю объекта, «протухшего» после `commit()`. В асинхронном режиме неявный
запрос выполнить невозможно.

**Решение.** Загружайте связи явно там, где строится запрос:

```python
from sqlalchemy.orm import selectinload

statement = (
    select(Lexeme)
    .where(Lexeme.id == lexeme_id)
    .options(selectinload(Lexeme.meanings).selectinload(Meaning.translations))
)
```

Для объектов после коммита проверьте, что фабрика сессий создана с `expire_on_commit=False` — в
`app/common/database.py` и в `app/common/task_runtime.py` это уже так. Если ошибка возникает именно
после `commit()` в новом коде, вы, скорее всего, создали свою сессию без этого параметра.

Рецепты загрузки связей под каждую таблицу — в [07-database-reference.md](07-database-reference.md).

### Данные не сохраняются

**Симптом.** Эндпоинт возвращает 200, объект в ответе есть, но в таблице записи нет.

**Причина.** Зависимость `get_db_session` сознательно не делает `commit()` — она только откатывает
транзакцию при исключении. Коммит — ответственность сервиса.

**Решение.** В сервисе после всех операций должен быть ровно один `await session.commit()`.
Репозиторий делает только `flush()`, когда нужен сгенерированный id.

Проверка, что дело именно в этом:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary \
  -c "select id, created_at from users order by created_at desc limit 5;"
```

### Исчерпан пул соединений

**Симптом.**

```text
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 5 reached,
connection timed out, timeout 30.00
```

**Причина.** Сессии не закрываются (создание сессии вне `async with`), либо долгие операции держат
соединение: внешний HTTP-запрос выполняется, пока сессия открыта.

**Решение.**

1. Убедитесь, что все сессии создаются через `get_db_session` или `task_db_session`, а не вручную.
2. В сервисах обогащения выносите вызовы провайдеров за пределы открытой транзакции: сначала сходили
   в сеть, потом открыли сессию и записали результат.
3. Посмотрите, сколько соединений реально открыто:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select state, count(*) from pg_stat_activity where datname = 'vocabulary' group by state;
"
```

Если соединений много и они в состоянии `idle in transaction` — где-то забыт коммит или откат.

### N+1 запросов

**Симптом.** Список из 20 слов открывается секунду и дольше, в логах PostgreSQL десятки однотипных
`SELECT`.

**Решение.** Временно включите вывод SQL в `create_engine()` (`echo=True`), перезапустите backend,
выполните один запрос к списку и посчитайте строки `SELECT`. Если их количество растёт вместе с
числом элементов — добавьте `selectinload` на нужные связи или соберите агрегаты одним запросом.
Не забудьте вернуть `echo=False`.

### Прочие ошибки SQLAlchemy

| Симптом | Причина | Решение |
| --- | --- | --- |
| `IntegrityError: duplicate key value violates unique constraint "uq_auth_identities_provider_external"` | одновременные первые входы одного пользователя | обрабатывается в `TelegramAuthService._create_user_handling_race`; если возникло в другом месте — повторите чтение после `rollback()` |
| `DetachedInstanceError: Instance <User> is not bound to a Session` | ORM-объект используется после закрытия сессии | передавайте примитивы (id, строки), а не объекты, между слоями и в Celery |
| `TypeError: can't subtract offset-naive and offset-aware datetimes` | смешаны naive и aware даты | везде `datetime.now(UTC)`, колонки `DateTime(timezone=True)` |
| `InvalidTextRepresentation: invalid input value for enum cefr_level: "a2"` | в БД пишется значение не из enum | использовать `CefrLevel`, а не строковый литерал |
| `asyncpg.exceptions.UndefinedFunctionError: function similarity(...) does not exist` | не включено расширение `pg_trgm` | применить первую миграцию: `POSTGRES_HOST=localhost uv run alembic upgrade head` |

---

## 5. Alembic

### Autogenerate не видит новую таблицу

**Симптом.** После создания модели:

```text
INFO  [alembic.env] No changes in schema detected.
```

или, что хуже, сгенерирован `op.drop_table(...)` для уже существующей таблицы.

**Причина.** Alembic строит `target_metadata` из `Base.metadata`, а туда попадают только импортированные
модули. Забытый импорт в `app/common/models_registry.py` означает, что таблицы для Alembic не существует.

**Решение.** Добавьте импорт модели в `models_registry.py` и проверьте, что метаданные её видят:

```bash
cd backend
uv run python -c "
from app.common.models_registry import Base
print(sorted(Base.metadata.tables))
"
```

Если таблицы нет в выводе — миграция и не будет её содержать, чинить надо импорт, а не миграцию.

### type already exists

**Симптом.** При повторном `alembic upgrade head` после `downgrade`:

```text
sqlalchemy.exc.ProgrammingError: (asyncpg.exceptions.DuplicateObjectError)
type "cefr_level" already exists
```

**Причина.** `op.drop_table()` удаляет таблицу, но не удаляет созданный PostgreSQL-тип enum.
Autogenerate почти никогда не дописывает это в `downgrade()`.

**Решение.** В `downgrade()` каждой миграции с enum должны быть явные строки:

```python
def downgrade() -> None:
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS cefr_level")
```

Если тип уже завис в базе, удалите его руками и повторите upgrade:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\dT+"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "drop type if exists cefr_level;"
```

### Две головы ревизий

**Симптом.**

```text
alembic.util.exc.CommandError: Multiple head revisions are present for given argument 'head';
please specify a specific target revision
```

**Причина.** Две ветки создали миграции от одного `down_revision` — обычно после слияния веток.

**Решение.** Посмотрите головы и объедините их:

```bash
cd backend
POSTGRES_HOST=localhost uv run alembic heads
POSTGRES_HOST=localhost uv run alembic history --verbose | head -40
POSTGRES_HOST=localhost uv run alembic merge -m "merge heads" <rev1> <rev2>
POSTGRES_HOST=localhost uv run alembic upgrade head
```

Если вторая миграция ещё не применялась ни у кого, чище другой путь: поправьте в ней `down_revision`
так, чтобы она шла следом за первой, и цепочка снова станет линейной. Уже применённые на других
машинах или в production миграции так править нельзя — только `merge`.

### Миграция падает на чистой базе

**Симптом.** Локально всё применяется, а CI падает на шаге `Migrations apply cleanly`, либо новый
разработчик не может поднять проект.

**Причина.** Миграция опирается на состояние, которое у вас возникло вручную: созданное расширение,
уже существующая колонка, вставленные данные.

**Решение.** Проверяйте каждую миграцию на пустой базе перед коммитом:

```bash
cd infra
docker compose down -v
docker compose --env-file ../.env up -d postgres
cd ../backend
POSTGRES_HOST=localhost uv run alembic upgrade head
POSTGRES_HOST=localhost uv run alembic downgrade base
POSTGRES_HOST=localhost uv run alembic upgrade head
```

### Прочие ошибки Alembic

| Симптом | Причина | Решение |
| --- | --- | --- |
| `Can't locate revision identified by 'abc123'` | в таблице `alembic_version` номер ревизии, которой нет в текущей ветке | вернуться на нужную ветку кода либо `alembic downgrade base` на пустой локальной БД |
| `Target database is not up to date` при `--autogenerate` | есть неприменённые миграции | `alembic upgrade head`, затем генерировать |
| `KeyError: 'secret_key'` при запуске alembic | `env.py` создаёт `Settings`, а переменных нет | запускать из `backend/`, где читается `../.env`, либо задать переменные явно |
| Миграция «не видит» изменение длины `String(80)` → `String(120)` | выключено сравнение типов | в `env.py` уже стоит `compare_type=True`; при отсутствии — добавить |
| Нужен откат одной ревизии | — | `POSTGRES_HOST=localhost uv run alembic downgrade -1` |
| Нужно понять, что применено | — | `POSTGRES_HOST=localhost uv run alembic current -v` |

---

## 6. Celery

### Worker не видит задачу

**Симптом.** В логах worker:

```text
KeyError: 'enrichment.enrich_vocabulary_item'
Received unregistered task of type 'enrichment.enrich_vocabulary_item'.
The message has been ignored and discarded.
```

**Причина.** Модуль с задачей не указан в `include` объекта Celery, либо worker запущен до появления
файла, либо имя задачи в `@celery_app.task(name=...)` отличается от того, что вызывает API.

**Решение.** Посмотрите фактический список зарегистрированных задач:

```bash
docker compose exec celery-worker \
  celery -A app.common.celery_app:celery_app inspect registered
```

Если задачи нет в списке — проверьте `include=["app.enrichment.tasks"]` в
`app/common/celery_app.py` и перезапустите worker:

```bash
docker compose restart celery-worker
```

### Задача висит в очереди

**Симптом.** `result.get(timeout=20)` падает по таймауту, карточка остаётся в статусе `PENDING`.

**Причина.** Worker не запущен, упал, либо API и worker смотрят в разные базы Redis.

**Решение.** Проверьте по шагам:

```bash
docker compose ps celery-worker
docker compose exec celery-worker celery -A app.common.celery_app:celery_app inspect ping
docker compose exec celery-worker celery -A app.common.celery_app:celery_app inspect active
docker compose exec redis redis-cli -n 1 llen celery
```

Ненулевая длина очереди при живом worker означает, что все процессы заняты долгими задачами:
`--concurrency=2`, а `worker_prefetch_multiplier=1`. Смотрите `inspect active`, чтобы понять, на чём
они стоят. Если задача зависла на внешнем провайдере, сработает `task_soft_time_limit` через 150
секунд.

Сбросить очередь целиком (только локально, задачи будут потеряны):

```bash
docker compose exec celery-worker celery -A app.common.celery_app:celery_app purge -f
```

### Ошибки event loop

**Симптом.**

```text
RuntimeError: Event loop is closed
RuntimeError: Task <...> got Future <...> attached to a different loop
asyncpg.exceptions.InterfaceError: cannot perform operation: another operation is in progress
```

**Причина.** Внутри задачи используется объект, созданный в другом event loop: общий `engine` из
`app/common/database.py`, глобальный `httpx.AsyncClient` или Redis-клиент уровня модуля. `asyncio.run`
создаёт новый loop на каждый вызов задачи и закрывает его в конце.

**Решение.** Вся работа задачи идёт через `app/common/task_runtime.py`, который создаёт свой engine на
время выполнения:

```python
@celery_app.task(name="enrichment.enrich_vocabulary_item", bind=True, max_retries=3)
def enrich_vocabulary_item(self, vocabulary_item_id: str) -> None:
    run_async_task(lambda: run_enrichment(UUID(vocabulary_item_id)))
```

HTTP-клиенты создавайте внутри корутины (`async with httpx.AsyncClient(...)`), а не на уровне модуля.
Если импортировали `from app.common.database import session_factory` в коде задачи — это и есть
источник ошибки.

### Задача выполняется дважды

**Симптом.** В логах два запуска одного `enrichment`, в счётчике AI-запросов двойной расход.

**Причина.** Это штатное поведение брокера: `task_acks_late=True` возвращает сообщение в очередь при
падении или перезапуске worker. Гарантии «ровно один раз» не существует.

**Решение.** Задача должна быть идемпотентной, и в проекте для этого два механизма:

1. unique constraint на `(meaning_id, cefr_level, prompt_version)` в `MeaningContent` — повторная
   генерация упадёт на уровне БД, и это правильно;
2. Redis-лок `SET NX EX` на время генерации.

Проверить, что лок реально ставится:

```bash
docker compose exec redis redis-cli -n 0 keys 'enrichment:*'
docker compose exec redis redis-cli -n 0 ttl <ключ>
```

Зависший лок после аварийного завершения worker исчезнет сам по TTL. Если ждать нельзя:

```bash
docker compose exec redis redis-cli -n 0 del <ключ>
```

### Ретраи не заканчиваются

**Симптом.** Одна и та же задача повторяется десятки раз, логи забиты одинаковыми ошибками.

**Причина.** `self.retry()` вызывается без ограничения, либо исключение поднимается до того, как
счётчик попыток успевает сработать.

**Решение.** У задачи обязателен `max_retries`, задержка растёт, а после исчерпания попыток карточка
переводится в `PARTIAL` или `FAILED` — но остаётся пригодной к использованию:

```python
try:
    ...
except ProviderTemporaryError as error:
    if self.request.retries >= self.max_retries:
        run_async_task(lambda: mark_enrichment_failed(item_id))
        return
    raise self.retry(exc=error, countdown=2 ** self.request.retries * 10)
```

Найти зависшие карточки:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select enrichment_status, count(*) from user_vocabulary_items group by enrichment_status;
"
```

### Ошибка сериализации аргументов

**Симптом.**

```text
kombu.exceptions.EncodeError: Object of type UUID is not JSON serializable
kombu.exceptions.EncodeError: Object of type UserVocabularyItem is not JSON serializable
```

**Причина.** В `delay()` передан ORM-объект или `UUID`. Сериализатор — `json`, и это осознанное
решение: `pickle` позволял бы передать что угодно, но это дыра в безопасности и источник
рассинхронизации между версиями кода.

**Решение.** Передавайте только примитивы, а объект загружайте внутри задачи:

```python
enrich_vocabulary_item.delay(str(item.id))
```

### Как заглянуть в очередь

```bash
docker compose exec redis redis-cli -n 1 keys '*'
docker compose exec redis redis-cli -n 1 llen celery
docker compose exec redis redis-cli -n 1 lrange celery 0 0
docker compose exec redis redis-cli -n 2 keys 'celery-task-meta-*'
```

---

## 7. Аутентификация Telegram

### Подпись initData не сходится

**Симптом.** `POST /api/v1/auth/telegram` возвращает 401 и `{"detail":"Telegram init data is not valid"}`.
Наружу причина не раскрывается сознательно — точную причину ищите в логах backend.

```bash
docker compose logs --tail=100 backend | grep -i telegram
```

| Причина | Как проявляется | Решение |
| --- | --- | --- |
| `hash` не удалён из полей до построения data check string | подпись не сходится никогда, даже для валидных данных | `fields.pop("hash")` строго до формирования строки |
| Ключи не отсортированы | подпись сходится случайно и непредсказуемо | `"\n".join(f"{key}={fields[key]}" for key in sorted(fields))` |
| Неверный токен бота | все запросы отклоняются, включая первый | сверить `TELEGRAM_BOT_TOKEN` через `getMe` |
| Пробел, перевод строки или кавычки в токене в `.env` | то же самое | в `.env` значение пишется без кавычек и без пробелов вокруг `=` |
| Секрет считается неправильно | подпись не сходится | секрет ровно `HMAC-SHA256(key=b"WebAppData", msg=токен)`, а не наоборот |
| Строка уже была URL-декодирована на фронте | подпись не сходится для пользователей с эмодзи в имени | передавайте `window.Telegram.WebApp.initData` как есть, без преобразований |

Проверка токена:

```bash
curl -s "https://api.telegram.org/bot<ТОКЕН>/getMe" | python3 -m json.tool
```

Проверка того, что именно приехало в backend, без раскрытия секретов в логах: сгенерируйте заведомо
валидную строку тем же кодом, что в тестах, и сравните поведение.

```bash
cd backend
uv run python -c "
import sys; sys.path.insert(0, 'tests')
from test_telegram_auth import build_init_data
print(build_init_data(bot_token='<ТОКЕН>'))
"
uv run pytest tests/test_telegram_auth.py -v
```

Если тесты зелёные, а реальный Mini App получает 401 — проблема не в алгоритме, а в токене или в
самой строке `initData`.

### initData пустой

**Симптом.** Фронт показывает «Не удалось войти», в Network нет запроса `POST /auth/telegram`.

**Причина.** `window.Telegram.WebApp.initData` пуст: приложение открыто не из Telegram, открыто по
обычной ссылке, либо не подключён `telegram-web-app.js`.

**Решение.** Проверьте в консоли WebView:

```javascript
window.Telegram?.WebApp?.initData?.length
window.Telegram?.WebApp?.version
```

Ноль или `undefined` означает: открывайте через кнопку бота с `web_app=WebAppInfo(...)` или через
Menu Button в BotFather. Пустой `initData` вне Telegram — это ожидаемое поведение, и приложение
специально показывает понятный экран, а не белую страницу.

### auth_date устарел

**Симптом.** В логах `TelegramInitDataExpired: init data is too old`, при том что Mini App только что
открыли.

**Причина.** Либо `TELEGRAM_AUTH_MAX_AGE_SECONDS` выставлен слишком маленьким, либо часы разъехались:
время внутри виртуальной машины Docker после сна ноутбука может отстать на минуты.

**Решение.**

```bash
date -u
docker compose exec backend date -u
```

Если время отличается — перезапустите Docker Desktop. Значение по умолчанию `86400` менять не нужно;
в production его имеет смысл уменьшить, но не до секунд.

### 401 на защищённых эндпоинтах

| Симптом | Причина | Решение |
| --- | --- | --- |
| 403 `Not authenticated` | нет заголовка `Authorization` | проверить, что `authInterceptor` подключён в `provideHttpClient(withInterceptors([authInterceptor]))` |
| 401 `Invalid access token` сразу после смены `.env` | изменился `SECRET_KEY`, все ранее выпущенные JWT недействительны | это ожидаемо: очистить токен на клиенте и войти заново |
| 401 `Invalid access token` через месяц | истёк `ACCESS_TOKEN_TTL_DAYS` | клиент сам получит новый через `initData`; если нет — проверить логику восстановления сессии |
| 401 `User no longer exists` | пользователь удалён (шаг 59), а токен остался в `localStorage` | проверка намеренная, клиент должен очистить токен и пройти аутентификацию заново |

Очистить токен вручную в консоли WebView или браузера:

```javascript
localStorage.removeItem('vocabulary.accessToken');
location.reload();
```

Проверить содержимое токена без секрета:

```bash
cd backend
uv run python -c "
import jwt, sys
print(jwt.decode(sys.argv[1], options={'verify_signature': False}))
" "<токен>"
```

---

## 8. Telegram Mini App и бот

### Белый экран при открытии Mini App

**Причина и решение** зависят от того, что в консоли. Откройте отладку: в Telegram Desktop это
правый клик по окну Mini App и `Inspect`, на Android — включённый режим разработчика в клиенте.

| В консоли | Причина | Решение |
| --- | --- | --- |
| `Failed to load resource: main-*.js 404` | неверный `base href` или путь сборки в `frontend/Dockerfile` | проверить `ls dist/` и строку `COPY --from=build /app/dist/frontend/browser` |
| `Mixed Content: The page at 'https://...' was loaded over HTTPS, but requested 'http://localhost:8000'` | собрана dev-конфигурация с абсолютным `apiBaseUrl` | собирать с `--configuration=production`, где `apiBaseUrl` равен `/api/v1` |
| `blocked by CORS policy` | `MINI_APP_URL` не совпадает с текущим адресом туннеля | обновить `.env` и перезапустить backend |
| ничего, пустая консоль | приложение не смонтировалось, упал `main.ts` | проверить `docker compose logs frontend` и что образ пересобран после изменений |

### Кнопка открывает браузер вместо Mini App

**Причина.** В сообщении бота использована обычная ссылка или `InlineKeyboardButton(url=...)`.
Mini App открывается только кнопкой с `web_app=WebAppInfo(url=...)` либо через Menu Button,
настроенную как Web App.

**Решение.** В `bot/app/main.py` клавиатура строится через `WebAppInfo`. В BotFather путь:
`/mybots` → бот → `Bot Settings` → `Menu Button` → `Configure menu button`, и там указывается URL
Mini App, а не произвольная ссылка.

### Адрес туннеля сменился

**Симптом.** Вчера работало, сегодня кнопка ведёт на «страницу не найдена» или запросы блокируются
по CORS.

**Причина.** `cloudflared tunnel --url http://localhost:8080` выдаёт новый адрес при каждом запуске.

**Решение.** Пройдите цепочку целиком, пропуск любого шага ломает вход:

```bash
cloudflared tunnel --url http://localhost:8080
```

1. скопировать новый адрес вида `https://random-words-1234.trycloudflare.com`;
2. вписать его в `MINI_APP_URL` в `.env`;
3. `docker compose --env-file ../.env restart telegram-bot backend`;
4. обновить адрес в BotFather (`Menu Button`);
5. в Telegram закрыть Mini App полностью и открыть заново.

### TelegramConflictError

**Симптом.** В логах бота:

```text
TelegramConflictError: Telegram server says - Conflict: terminated by other getUpdates request;
make sure that only one bot instance is running
```

**Причина.** Long polling ведут две копии бота: контейнер `telegram-bot` и локальный `uv run`, либо
две машины с одним токеном. Telegram отдаёт обновления только одному потребителю.

**Решение.**

```bash
docker compose ps telegram-bot
ps aux | grep -i "app.main" | grep -v grep
```

Оставьте одну копию. Если ранее для бота настраивали webhook, его нужно снять — webhook и polling
несовместимы:

```bash
curl -s "https://api.telegram.org/bot<ТОКЕН>/getWebhookInfo" | python3 -m json.tool
curl -s "https://api.telegram.org/bot<ТОКЕН>/deleteWebhook"
```

### Тема оформления не применяется

**Симптом.** Внутри Telegram в тёмной теме приложение остаётся белым.

**Причина.** Не загружен `telegram-web-app.js`, не вызван `ready()`, либо в стилях используются
жёсткие цвета вместо токенов.

**Решение.** Скрипт `https://telegram.org/js/telegram-web-app.js` должен быть в `<head>` файла
`index.html` до загрузки приложения, `TelegramWebAppBridge.markReady()` вызывается в `App.ngOnInit`,
а цвета берутся так: `var(--tg-theme-bg-color, #ffffff)`. Проверка в консоли WebView:

```javascript
getComputedStyle(document.documentElement).getPropertyValue('--tg-theme-bg-color');
```

Пустая строка означает, что переменные Telegram не приехали, то есть приложение открыто вне клиента.

### iOS увеличивает страницу при фокусе на поле

**Симптом.** На iPhone при касании `input` или `select` страница «прыгает» и увеличивается.

**Причина.** Safari и WebView Telegram автоматически масштабируют страницу, если размер шрифта поля
меньше 16px.

**Решение.** Всем интерактивным полям ставьте `font-size: 16px` в SCSS компонента. Отключать
масштабирование через `maximum-scale=1` в `<meta name="viewport">` не нужно: это ломает доступность,
а проблему решает один размер шрифта.

### В Telegram открывается старая версия

**Симптом.** Изменения на фронте видны в браузере по адресу туннеля, но не в Mini App.

**Решение.** WebView кэширует агрессивно. По возрастанию радикальности: закрыть Mini App свайпом
вниз и открыть заново; в Telegram на iOS — `Settings` → `Data and Storage` → `Storage Usage` →
`Clear Cache`; на Desktop — правый клик по окну Mini App → `Reload`. Со стороны сервера убедитесь,
что `index.html` не кэшируется (раздел 11).

---

## 9. Angular

### Быстрая таблица

| Симптом | Причина | Решение |
| --- | --- | --- |
| Шаблон не обновляется после изменения данных | состояние в обычном поле класса; при zoneless и OnPush перерисовку вызывает только изменение сигнала | перенести состояние в `signal()`, производное — в `computed()` |
| `TypeError: item.text is not a function` или в шаблоне пусто | сигнал не вызван: `item.text` вместо `item().text` | добавить `()` |
| Массив изменился, экран нет | мутация через `push` | `items.update((current) => [...current, added])` |
| Запрос не уходит, в Network пусто | `Observable` ленив и без подписки не выполняется | `subscribe()`, `firstValueFrom()` или `resource()` |
| `NullInjectorError: No provider for VocabularyApi` | у сервиса нет `@Injectable({ providedIn: 'root' })` или `inject()` вызван вне контекста внедрения | добавить `providedIn: 'root'`; `inject()` вызывать в поле класса, не в методе |
| Список мигает, поле ввода теряет фокус | `@for` без стабильного `track` | `track item.id`, никогда не `track $index` для изменяемых списков |
| `*ngIf` не работает | синтаксис из старых версий Angular | `@if`, `@for`, `@switch` |
| Стили не применяются | селектор пытается дотянуться до элемента внутри дочернего компонента | стилизовать внутри самого дочернего компонента |
| `ng test` или сборка падает с ошибкой про Node | версия Node ниже требуемой CLI | раздел 2 |

### Ошибки strictTemplates

**Симптом.** Сборка падает на шаблоне:

```text
error NG9: Type 'string | null' is not assignable to type 'string'.
error NG8002: Can't bind to 'item' since it isn't a known property of 'app-word-card'.
```

**Причина.** `strictTemplates: true` проверяет типы в HTML. Первая ошибка — передача возможного
`null` во вход, ожидающий `string`. Вторая — компонент не импортирован в `imports` родителя.

**Решение.** Для первой: сузьте тип до передачи, например через `@if (item(); as loaded)`, либо
объявите вход как `input<string | null>(null)`. Для второй: добавьте компонент в `imports` массива
декоратора родителя — в standalone-компонентах шаблон видит только явно импортированное. Подавлять
такие ошибки через `as any` запрещено правилами проекта.

### 404 при перезагрузке страницы

**Симптом.** Прямое обращение к `https://<адрес>/onboarding` даёт 404, хотя переход внутри приложения
работает.

**Причина.** Файла `/onboarding` на диске нет, маршрутизацию выполняет Angular в браузере.

**Решение.** Раздача статики должна отдавать `index.html` для любого неизвестного пути. В
`frontend/Dockerfile` за это отвечает `try_files $uri $uri/ /index.html;`. Проверка:

```bash
curl -sI http://localhost:8080/onboarding | head -1
docker compose exec frontend cat /etc/nginx/conf.d/default.conf
```

### CORS

**Симптом.** В консоли:

```text
Access to fetch at 'https://api.example.com/api/v1/languages' from origin
'https://random-words-1234.trycloudflare.com' has been blocked by CORS policy
```

**Причина.** При `APP_ENV != local` backend разрешает единственный источник — значение `MINI_APP_URL`.
Адрес туннеля сменился, а переменная осталась старой.

**Решение.** Обновить `MINI_APP_URL` и перезапустить backend. В production правильная схема —
относительный `apiBaseUrl` (`/api/v1`) и общий Nginx, при котором CORS вообще не возникает; если вы
видите CORS на production, значит собралась dev-конфигурация фронта.

### Полезные проверки фронта

```bash
cd frontend
npx tsc --noEmit
npm run build -- --configuration=production
npm test -- --watch=false
```

---

## 10. Внешние провайдеры

Протоколы, DTO и реализации описаны в [09-integrations-reference.md](09-integrations-reference.md).
Здесь только диагностика отказов.

### Yandex Dictionary

```bash
curl -s "https://dictionary.yandex.net/api/v1/dicservice.json/getLangs?key=<КЛЮЧ>" | python3 -m json.tool
curl -s "https://dictionary.yandex.net/api/v1/dicservice.json/lookup?key=<КЛЮЧ>&lang=en-ru&text=bank" | python3 -m json.tool
```

| Код или ответ | Значение | Решение |
| --- | --- | --- |
| 401 `ERR_KEY_INVALID` | ключ неверный | проверить `YANDEX_DICTIONARY_API_KEY`, скопирован ли он целиком |
| 402 `ERR_KEY_BLOCKED` | ключ заблокирован | получить новый ключ на странице сервиса |
| 403 `ERR_DAILY_REQ_LIMIT_EXCEEDED` | исчерпан суточный лимит | дождаться сброса; проверить, нет ли цикла запросов без кэширования |
| 501 `ERR_LANG_NOT_SUPPORTED` | неверное направление перевода | направление всегда `en-ru` |
| 200, но `{"def": []}` | слова нет в словаре — обычно для фраз и редких форм | это не ошибка: сервис переходит к Wiktionary, затем к AI |

Пустой ответ на фразу — штатный сценарий. Yandex Dictionary работает со словарными формами, а фразы
целиком он не знает.

### Wiktionary

```bash
curl -s -H "User-Agent: english-vocabulary-app/0.1 (contact: you@example.com)" \
  "https://en.wiktionary.org/api/rest_v1/page/definition/clarify" | head -c 400
```

| Симптом | Причина | Решение |
| --- | --- | --- |
| 403 без тела | не передан `User-Agent` | Wikimedia требует осмысленный `User-Agent`; значение берётся из `WIKIMEDIA_USER_AGENT` |
| 404 | страницы для этой формы нет | попробовать нормализованную словарную форму; при неудаче — отдать генерацию AI |
| 429 | слишком частые запросы | уважать ретраи с задержкой, не опрашивать в цикле |
| Ответ есть, но нужного языка нет | в ответе несколько языков по коду | брать секцию `en`, остальные игнорировать |

### Аудио с Wikimedia Commons

| Симптом | Причина | Решение |
| --- | --- | --- |
| Файл не найден | произношения для слова нет; шаблон имени `File:En-us-{word}.ogg` покрывает не всё | карточка переходит в `PARTIAL`, это допустимая частичная деградация |
| Звук не воспроизводится на iPhone | исходник в формате `ogg`, WebView iOS его не поддерживает | обязательна конвертация в mp3 через `ffmpeg` в Celery-задаче |
| `ffmpeg` не найден в контейнере | образ собран без пакета | `docker compose build --no-cache backend celery-worker` |
| Файл сконвертирован, но не открывается по ссылке | не отдаётся `/media` | раздел 11 |

Проверки:

```bash
docker compose exec celery-worker ffmpeg -version | head -1
docker compose exec celery-worker ls -la /app/media | head
curl -sI http://localhost:8080/media/<файл>.mp3 | head -3
```

Отдельно: `api.dictionaryapi.dev` на момент написания плана недоступен. Если вы нашли пример решения
через него — это тупик, не тратьте время.

### OpenAI

| Симптом | Причина | Решение |
| --- | --- | --- |
| `AuthenticationError: Incorrect API key provided` | неверный или отозванный ключ | проверить `OPENAI_API_KEY`, создать новый ключ |
| `RateLimitError: insufficient_quota` | закончился баланс или сработал месячный лимит | пополнить баланс либо поднять лимит в Billing |
| `RateLimitError` с `Retry-After` | превышена частота запросов | ретрай с экспоненциальной задержкой, не более трёх попыток |
| `APITimeoutError` | модель отвечает дольше `AI_TIMEOUT_SECONDS` | таймаут 30 секунд достаточен для коротких карточек; при регулярных таймаутах уменьшить объём промпта |
| `NotFoundError: The model ... does not exist` | значение `AI_MODEL` устарело | взять актуальное имя из списка моделей; имя модели живёт только в переменной окружения |
| `.output_parsed is None` | модель отказалась отвечать либо ответ неполный | проверить `response.status` и `response.incomplete_details`; при отказе — не сохранять контент, оставить `PARTIAL` |
| `ValidationError` при разборе ответа | вернулся JSON, не соответствующий схеме | использовать `client.responses.parse(..., text_format=PydanticModel)`, а не ручной разбор строки; валидировать до записи в БД |

Проверка ключа и модели:

```bash
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; print([m['id'] for m in json.load(sys.stdin)['data']][:10])"
```

### Неожиданно большой расход бюджета

**Симптом.** Счёт растёт быстрее ожидаемого при одном-двух пользователях.

**Причина.** Контент генерируется повторно для одного и того же значения: не сработал кэш
`MeaningContent`, либо задача выполняется многократно из-за ретраев.

**Решение.** Проверьте, что дубли не создаются:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select meaning_id, cefr_level, prompt_version, count(*)
from meaning_contents
group by 1, 2, 3
having count(*) > 1;
"
```

Пустой результат означает, что unique constraint работает. Дальше смотрите число запусков задачи в
логах worker по `correlation_id` и проверьте суточный лимит `AI_DAILY_REQUEST_LIMIT_PER_USER`.
Жёсткий месячный лимит в Billing на стороне OpenAI — обязательная страховка, он ставится на шаге 6.

---

## 11. Nginx и деплой

### 502 Bad Gateway

**Симптом.** Браузер показывает 502, в логах nginx:

```text
connect() failed (111: Connection refused) while connecting to upstream,
upstream: "http://172.18.0.4:8000/api/v1/languages"
```

**Причина.** Контейнер `backend` не запущен, упал при старте или слушает не тот порт.

**Решение.**

```bash
docker compose ps backend
docker compose logs --tail=50 backend
docker compose exec nginx wget -qO- http://backend:8000/health
```

Если последняя команда не отвечает — проблема в backend (раздел 3), а не в Nginx. Если отвечает,
проверьте конфиг и перечитайте его:

```bash
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

### 413 Request Entity Too Large

**Причина.** `client_max_body_size 1m` в `infra/nginx/nginx.conf`. Для нашего API это правильное
ограничение: все запросы измеряются килобайтами.

**Решение.** Если 413 появился — почти наверняка в запрос попало что-то лишнее (например,
`source_context` без ограничения длины). Сначала проверьте лимиты полей в Pydantic-схемах и только
при реальной необходимости поднимайте значение в конфиге, после чего перечитайте конфиг Nginx.

### /media не отдаётся

**Симптом.** Ссылка на аудио даёт 404, хотя файл сгенерирован.

| Проверка | Команда | Что должно быть |
| --- | --- | --- |
| Файл создан worker | `docker compose exec celery-worker ls /app/media` | файл присутствует |
| Том виден Nginx | `docker compose exec nginx ls /srv/media` | тот же файл |
| Путь в конфиге | `location /media/ { alias /srv/media/; }` | слеши на конце обязательны в обеих частях |
| Публичный адрес | `echo $MEDIA_PUBLIC_BASE_URL` | совпадает с адресом, по которому открывается приложение |

Если файл есть у worker, но не виден Nginx — сервисы подключены к разным томам, сверьте секцию
`volumes` в `infra/docker-compose.yml`: у `celery-worker` это `media-data:/app/media`, у `nginx` —
`media-data:/srv/media:ro`.

### HTTPS и сертификат

| Симптом | Причина | Решение |
| --- | --- | --- |
| Telegram не открывает Mini App, показывает ошибку загрузки | адрес не HTTPS либо сертификат самоподписанный | Telegram требует валидный сертификат: туннель `cloudflared` локально, Let's Encrypt на VPS |
| `curl: (60) SSL certificate problem` | сертификат не выпущен или истёк | перевыпустить сертификат, проверить автообновление |
| Приложение открывается, но запросы к API блокируются | часть ресурсов по HTTP на HTTPS-странице | все URL относительные, `apiBaseUrl` равен `/api/v1` в production-конфигурации |

### Отдаётся старая статика

**Симптом.** После деплоя пользователи видят старую версию фронта.

**Причина.** Статика вшита в образ `frontend`, а браузер и WebView кэшируют `index.html`.

**Решение.** Пересоберите образ и убедитесь, что `index.html` не кэшируется, тогда как файлы с хэшем
в имени кэшировать можно и нужно:

```bash
docker compose build frontend
docker compose up -d frontend
curl -sI http://localhost:8080/index.html | grep -i cache
```

Если заголовка нет, добавьте в конфиг раздачи статики отдельную локацию для `index.html` с
`Cache-Control: no-store`, оставив долгий кэш для `*.js` и `*.css`.

---

## 12. Экстренные процедуры

### Полностью пересоздать локальную базу

Применяется, когда миграции разъехались или данные испорчены экспериментами. Локальные данные будут
потеряны — это нормально, они восстанавливаются миграциями и сидами.

```bash
cd infra
docker compose down -v
docker compose --env-file ../.env up -d postgres redis
cd ../backend
POSTGRES_HOST=localhost uv run alembic upgrade head
cd ../infra
docker compose --env-file ../.env up -d
docker compose exec postgres psql -U vocabulary -d vocabulary -c "select * from languages;"
```

Если нужно снести только базу, сохранив Redis, остановите `postgres`, удалите его том
(`docker volume ls` покажет точное имя, оно начинается с имени проекта `vocabulary-app`) и поднимите
сервис заново.

### Резервная копия и восстановление

Снятие копии:

```bash
docker compose exec -T postgres pg_dump -U vocabulary -d vocabulary -Fc \
  > backups/vocabulary-$(date +%Y%m%d-%H%M).dump
```

Восстановление в пустую базу:

```bash
docker compose exec -T postgres pg_restore -U vocabulary -d vocabulary --clean --if-exists \
  < backups/vocabulary-20260921-1830.dump
```

Проверка после восстановления:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select (select count(*) from users) as users,
       (select count(*) from languages) as languages;
"
cd ../backend
POSTGRES_HOST=localhost uv run alembic current
```

Резервная копия, которую ни разу не восстанавливали, не является резервной копией. Проверьте
восстановление на локальной машине до того, как оно понадобится на production.

### Откат деплоя

Порядок важен: сначала возвращается код, и только потом, если это действительно необходимо,
откатывается схема БД.

```bash
git log --oneline -10
git checkout <последний рабочий тег или коммит>
docker compose -f docker-compose.prod.yml --env-file ../.env up -d --build
curl -s https://<домен>/ready | python3 -m json.tool
```

Схему откатывайте только если новая миграция несовместима со старым кодом:

```bash
docker compose exec backend alembic downgrade -1
```

Миграция, удаляющая колонку с данными, необратима по содержимому даже при корректном `downgrade`.
Перед таким откатом обязательно снимите дамп.

### Секрет попал в git

Действуйте в этом порядке, потому что отзыв ключа защищает немедленно, а чистка истории занимает
время и без отзыва бесполезна.

1. **Отозвать** скомпрометированное значение:

| Секрет | Как отозвать |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/mybots` → бот → `API Token` → `Revoke current token` |
| `OPENAI_API_KEY` | platform.openai.com → API keys → удалить ключ, создать новый |
| `YANDEX_DICTIONARY_API_KEY` | кабинет сервиса: удалить ключ и получить новый |
| `POSTGRES_PASSWORD` | `alter user vocabulary with password '...';` и обновление `.env` |
| `SECRET_KEY` | сгенерировать новый: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |

Смена `SECRET_KEY` делает недействительными все выпущенные JWT. Пользователи просто войдут заново
через `initData` — потери данных нет.

2. **Прописать новые значения** в `.env` и перезапустить:

```bash
cd infra
docker compose --env-file ../.env up -d --force-recreate backend celery-worker telegram-bot
```

3. **Вычистить историю**. Если утечка только в последнем незапушенном коммите — достаточно
`git reset`. Если коммит уже в удалённом репозитории, историю придётся переписать:

```bash
brew install git-filter-repo
git filter-repo --path .env --invert-paths
git push --force --all
git push --force --tags
```

4. **Закрыть повторение**:

```bash
git check-ignore -v .env
git log --all --full-history -- .env
```

Первая команда должна подтвердить, что файл игнорируется, вторая — что в истории его больше нет.
Помните: после force-push старые копии остаются у всех, кто уже клонировал репозиторий, поэтому
отзыв ключей из пункта 1 обязателен в любом случае.

---

## Если ничего из перечисленного не подошло

1. Соберите факты: точный текст ошибки, `docker compose ps`, последние сто строк логов нужного
   сервиса, `correlation_id` конкретного запроса.
2. Проверьте, воспроизводится ли проблема на чистом состоянии (`docker compose down -v` и полный
   подъём). Если нет — дело в накопленных данных, а не в коде.
3. Сузьте до слоя вызовом напрямую: `curl` к backend мимо Nginx (порт 8000), вызов сервиса через
   `docker compose exec backend python -c ...` мимо Celery, запрос к провайдеру через `curl` мимо
   приложения. Как выглядит правильное поведение каждого шага, описано в разделах «Проверка»
   файла [03-week1-foundation.md](03-week1-foundation.md).

Когда проблема оказалась нетривиальной, добавьте регрессионный тест — этого требует раздел 36 правил
проекта, и это единственный способ не встретить ту же ошибку через месяц.
