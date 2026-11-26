# English Reader & Vocabulary

Мобильное приложение (Expo / React Native + FastAPI) для изучения английской лексики по своим книгам:
читаешь EPUB/FB2/TXT, нажимаешь на слово — видишь значение в контексте предложения, сохраняешь в
словарь одним тапом, проходишь занятия и задаёшь вопросы по книге (RAG без спойлеров).

> Проект в разработке. Полный README (демо, архитектура, метрики evals, запуск) — задача T6.8.

## Документация

- [Продукт](docs/PRODUCT.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Решения (ADR)](docs/DECISIONS.md)
- [План разработки](docs/plan/README.md)

## Структура

- `backend/` — FastAPI, PostgreSQL (pgvector, FTS), Procrastinate, OpenAI
- `mobile/` — Expo (React Native), TypeScript, Feature-Sliced Design
- `infra/` — локальный Docker Compose, Render Blueprint
- `docs/` — продукт, архитектура, план, отчёты evals
- `CLAUDE.md`, `.claude/` — правила, skills, subagents и hooks для Claude Code

## Данные

Лексические данные — [Wiktionary](https://www.wiktionary.org/) через
[Wiktextract / kaikki.org](https://kaikki.org/), лицензия CC BY-SA.
Демо-книги — общественное достояние.
