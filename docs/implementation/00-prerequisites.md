# Этап 0 — Подготовка окружения (шаги 1–6)

Цель этапа: на машине стоят нужные версии инструментов, есть пустой репозиторий с правильной
структурой, и получены все три внешних ключа. Без этого первая неделя будет постоянно спотыкаться.

Ориентировочное время: 2–3 часа, из них большая часть — ожидание писем и регистраций.

---

## Шаг 1. Привести версии инструментов в порядок

### Цель

Установленные версии совпадают с теми, под которые написан план.

### Что уже есть на машине (проверено)

| Инструмент | Установлено | Нужно | Действие |
| --- | --- | --- | --- |
| Python | 3.13.4 | 3.13.x | ничего |
| Docker | 27.4.0 | 24+ | ничего |
| Homebrew | 4.6.16 | любой свежий | ничего |
| npm | 11.6.0 | 10+ | ничего |
| **Node.js** | **22.13.1** | **^22.22.3 или ^24.15.0** | **обновить** |

Про Node важно: Angular CLI 22.1.7 объявляет в `engines` диапазон `^22.22.3 || ^24.15.0 || >=26.0.0`.
На 22.13.1 команда `ng new` либо откажется работать, либо выдаст предупреждение и непредсказуемое
поведение сборки. Это не формальность — обновите до начала работы.

### Действия

Проверьте текущее состояние:

```bash
python3 --version
node --version
npm --version
docker --version
docker compose version
```

Обновите Node. Если Node установлен через Homebrew:

```bash
brew update
brew upgrade node
node --version
```

Если вы хотите держать несколько версий Node (пригодится, когда Angular обновится), используйте
менеджер версий — это более удобный путь:

```bash
brew install nvm
mkdir -p ~/.nvm
```

Затем добавьте в `~/.zshrc`:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"
```

Перезапустите терминал и установите Node 24 LTS:

```bash
nvm install 24
nvm alias default 24
node --version
```

Установите `ffmpeg` — он понадобится на шаге 32 для конвертации аудио. Локально он нужен, чтобы
отлаживать задачу вне Docker:

```bash
brew install ffmpeg
ffmpeg -version | head -1
```

Убедитесь, что Docker Desktop запущен и умеет собирать образы:

```bash
docker run --rm hello-world
```

### Проверка

```bash
node --version    # v22.22.3+ или v24.15.0+
python3 --version # 3.13.x
ffmpeg -version | head -1
docker compose version
```

---

## Шаг 2. Установить `uv` и Angular CLI

### Цель

Готовы инструменты создания проектов: `uv` для Python, `ng` для Angular.

### Что такое `uv` и почему не pip

`uv` — менеджер пакетов и виртуальных окружений для Python от авторов линтера `ruff`. Он делает то же,
что `pip` + `venv` + `pip-tools`, но на порядок быстрее и с одним lock-файлом. Практическая разница
для вас: зависимости описываются в `pyproject.toml` (а не в разрозненных `requirements.txt`),
а `uv.lock` фиксирует точные версии, поэтому сборка в Docker и на CI воспроизводима.

Команды, которые вы будете использовать чаще всего:

| Команда | Что делает |
| --- | --- |
| `uv sync` | создаёт `.venv` и устанавливает всё из `pyproject.toml` по `uv.lock` |
| `uv add fastapi` | добавляет зависимость в `pyproject.toml` и ставит её |
| `uv add --dev pytest` | то же, но в группу для разработки |
| `uv run uvicorn app.main:app` | запускает команду внутри окружения, без `source .venv/bin/activate` |
| `uv lock --upgrade` | обновляет lock-файл |

### Действия

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Перезапустите терминал и проверьте:

```bash
uv --version
```

Установите Angular CLI глобально:

```bash
npm install -g @angular/cli@22
ng version
```

Команда `ng version` должна показать Angular CLI 22.x. Если она ругается на версию Node — вернитесь
к шагу 1.

### Проверка

```bash
uv --version
ng version
```

---

## Шаг 3. Создать репозиторий и структуру monorepo

### Цель

В проекте есть git-репозиторий, структура папок из продуктового плана и корневые служебные файлы.

### Действия

Перейдите в папку проекта и инициализируйте репозиторий. Документ с планом уже лежит здесь, он станет
первым коммитом:

```bash
cd /Users/stas/Desktop/Portfolio/language_app
git init
git branch -M main
```

Создайте структуру:

```bash
mkdir -p backend/app backend/tests
mkdir -p frontend
mkdir -p bot/app
mkdir -p infra/nginx infra/scripts
mkdir -p docs
mkdir -p .github/workflows
```

Создайте корневой `.gitignore`:

```gitignore
.DS_Store
.env
.env.*
!.env.example

.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage

node_modules/
dist/
.angular/
coverage/

media/
postgres-data/
backups/
*.log
```

Создайте `.editorconfig`, чтобы отступы не разъезжались между Python и TypeScript:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.{py}]
indent_style = space
indent_size = 4

[*.{ts,html,scss,json,yml,yaml}]
indent_style = space
indent_size = 2

[*.md]
trim_trailing_whitespace = false
```

Создайте черновой `README.md` в корне — подробный напишете на шаге 70:

```markdown
# English Vocabulary App

Telegram Mini App для изучения английских слов и выражений.

Документация: [`docs/implementation/README.md`](docs/implementation/README.md)

## Структура

- `backend/` — FastAPI, PostgreSQL, Celery
- `frontend/` — Angular Mini App
- `bot/` — Telegram-бот (точка входа в Mini App)
- `infra/` — Docker Compose, Nginx, скрипты
- `docs/` — архитектура, API, модель данных
```

Сделайте первый коммит:

```bash
git add -A
git commit -m "chore: initialize monorepo structure"
```

### Проверка

```bash
git log --oneline
tree -L 2 -a -I '.git'
```

Структура должна выглядеть так:

```text
.
├── .editorconfig
├── .github/workflows
├── .gitignore
├── README.md
├── backend/{app,tests}
├── bot/app
├── docs/implementation
├── english_vocabulary_app_plan.md
├── frontend
└── infra/{nginx,scripts}
```

### Коммит

`chore: initialize monorepo structure`

---

## Шаг 4. Создать Telegram-бота и получить токен

### Цель

Есть бот, его токен и понимание, где настраивается Mini App.

### Действия

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather).
2. Отправьте `/newbot`.
3. Укажите отображаемое имя, например `English Vocabulary`.
4. Укажите username — он должен заканчиваться на `bot`, например `my_english_vocab_bot`.
5. BotFather пришлёт токен вида `1234567890:AAH...`. Это секрет: он даёт полный контроль над ботом.
   Не коммитьте его и не пересылайте.

Узнайте свой Telegram user ID — он понадобится как `ADMIN_TELEGRAM_IDS`. Напишите боту
[@userinfobot](https://t.me/userinfobot), он ответит числовым id.

Mini App пока не настраиваем: для него нужен публичный HTTPS-адрес, который появится на шаге 23.
Просто запомните путь: `/mybots` → ваш бот → `Bot Settings` → `Menu Button` / `Web App`.

### Проверка

Токен работает, если запрос возвращает информацию о боте:

```bash
curl -s "https://api.telegram.org/bot<ВАШ_ТОКЕН>/getMe"
```

Ответ должен содержать `"ok":true` и username вашего бота.

---

## Шаг 5. Получить ключ Yandex Dictionary

### Цель

Есть бесплатный ключ основного словарного провайдера.

### Почему именно этот словарь

Для пары «английский → русский» Yandex Dictionary закрывает сразу три поля карточки одним запросом:
перевод, часть речи и транскрипцию. Альтернативы либо дают только англо-английские определения,
либо требуют работы с дампами. Ограничение: это не источник английских определений — их берём из
Wiktionary и AI.

Юридический момент: условия использования требуют указывать ссылку на технологию Яндекса в интерфейсе.
Добавьте строку «Словарные данные: Yandex.Dictionary» на экран профиля (шаг 22 или позже) — это
несколько минут работы и снимает вопрос.

### Действия

1. Откройте [yandex.com/dev/dictionary](https://yandex.com/dev/dictionary).
2. Прочитайте условия использования.
3. Нажмите «Get a free API key» и авторизуйтесь в аккаунте Яндекса.
4. Скопируйте ключ вида `dict.1.1.2019...`.

### Проверка

Запрос списка направлений перевода должен вернуть массив, включающий `en-ru`:

```bash
curl -s "https://dictionary.yandex.net/api/v1/dicservice.json/getLangs?key=<ВАШ_КЛЮЧ>"
```

Пробный поиск слова:

```bash
curl -s "https://dictionary.yandex.net/api/v1/dicservice.json/lookup?key=<ВАШ_КЛЮЧ>&lang=en-ru&text=bank"
```

В ответе вы увидите структуру с полями `pos`, `ts` (транскрипция) и вложенными переводами `tr`.
Разбор этой структуры — в [09-integrations-reference.md](09-integrations-reference.md).

Если вернулся код `401` — ключ неверный, `402` — ключ заблокирован.

---

## Шаг 6. Получить ключ OpenAI и собрать `.env`

### Цель

Есть ключ AI-провайдера с ограниченным бюджетом, и все секреты собраны в одном игнорируемом файле.

### Действия

1. Зарегистрируйтесь на [platform.openai.com](https://platform.openai.com).
2. Пополните баланс минимально — для MVP при одном пользователе и кэшировании хватает нескольких
   долларов.
3. В разделе Billing → Limits поставьте жёсткий месячный лимит, например 5 USD. Это защита от ошибки
   в коде, которая начнёт генерировать в цикле.
4. В разделе API keys создайте ключ и сразу скопируйте — повторно его не покажут.
5. В разделе Models посмотрите список доступных моделей и выберите самую дешёвую с поддержкой
   structured outputs (семейство `mini`). Имя модели мы нигде не хардкодим, оно живёт в переменной
   окружения `AI_MODEL`, потому что модельный ряд меняется каждые несколько месяцев.

### Файлы

Создайте `.env.example` в корне — это **шаблон без секретов**, он коммитится и служит документацией:

```bash
APP_ENV=local
APP_DEBUG=true
API_BASE_PATH=/api/v1
SECRET_KEY=change-me-to-a-long-random-string
ACCESS_TOKEN_TTL_DAYS=30

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=vocabulary
POSTGRES_USER=vocabulary
POSTGRES_PASSWORD=change-me

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

TELEGRAM_BOT_TOKEN=
TELEGRAM_AUTH_MAX_AGE_SECONDS=86400
ADMIN_TELEGRAM_IDS=
MINI_APP_URL=

YANDEX_DICTIONARY_API_KEY=
YANDEX_DICTIONARY_TIMEOUT_SECONDS=5

WIKTIONARY_TIMEOUT_SECONDS=5
WIKIMEDIA_USER_AGENT=english-vocabulary-app/0.1 (contact: you@example.com)

OPENAI_API_KEY=
AI_MODEL=
AI_TIMEOUT_SECONDS=30
AI_PROMPT_VERSION=v1
AI_DAILY_REQUEST_LIMIT_PER_USER=50

MEDIA_ROOT=/app/media
MEDIA_PUBLIC_BASE_URL=http://localhost:8080/media
```

Скопируйте его в реальный `.env` и заполните настоящими значениями:

```bash
cp .env.example .env
```

Сгенерируйте `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Впишите в `.env`: `SECRET_KEY`, `POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_IDS`,
`YANDEX_DICTIONARY_API_KEY`, `OPENAI_API_KEY`, `AI_MODEL`.

### Проверка

`.env` не попадает в git:

```bash
git status --short
git check-ignore -v .env
```

Вторая команда должна ответить, что файл игнорируется правилом из `.gitignore`. Если `.env` виден в
`git status` — немедленно поправьте `.gitignore`, иначе секреты уйдут в историю репозитория.

### Коммит

```bash
git add .env.example
git commit -m "chore: add environment variables template"
```

---

## Итог этапа 0

- [ ] Node обновлён, `ng version` работает
- [ ] `uv` установлен
- [ ] `ffmpeg` установлен
- [ ] Репозиторий создан, структура папок на месте
- [ ] Токен бота получен и проверен через `getMe`
- [ ] Ключ Yandex Dictionary получен и проверен через `getLangs`
- [ ] Ключ OpenAI получен, месячный лимит выставлен
- [ ] `.env` заполнен и не отслеживается git

Перед неделей 1 прочитайте [01-primer-python-backend.md](01-primer-python-backend.md) —
это сэкономит время на всех последующих шагах.

Дальше: [03-week1-foundation.md](03-week1-foundation.md), шаг 7.
