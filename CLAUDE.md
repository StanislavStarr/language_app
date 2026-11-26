# CLAUDE.md — English Reader & Vocabulary

Mobile app for learning English vocabulary from real books: read your own EPUB/FB2/TXT, tap a word,
get its meaning in context, save it, study it, ask questions about the book (RAG).

- Product: `docs/PRODUCT.md` · Architecture: `docs/ARCHITECTURE.md` · Decisions: `docs/DECISIONS.md`
- Plan and tasks: `docs/plan/README.md` → `docs/plan/phase-*.md`
- Backend rules: `backend/CLAUDE.md` · Mobile rules: `mobile/CLAUDE.md`

Read the relevant doc sections before changing anything non-trivial. Docs are the source of truth;
if the code must diverge, stop and propose a doc change first.

## Stack (fixed — do not change without an ADR)

- `backend/`: Python 3.13, uv, FastAPI, Pydantic v2, SQLAlchemy 2 async + psycopg 3, Alembic,
  PostgreSQL 17 (pgvector, pg_trgm, FTS), Procrastinate (Postgres job queue), spaCy, OpenAI SDK.
- `mobile/`: Expo (Expo Go compatible only), React Native, TypeScript strict, Expo Router,
  Feature-Sliced Design, TanStack Query, Zustand, openapi-fetch.
- No Redis, no Celery, no Telegram, no Angular, no microservices, no GraphQL.

## Commands

```bash
make up                 # local Postgres (pgvector) in Docker
make backend-dev        # FastAPI with reload on :8000
make backend-check      # ruff check + ruff format --check + mypy + pytest
make backend-fix        # ruff format + ruff check --fix
make migrate            # alembic upgrade head
make migration name=add_book_chunk   # autogenerate a migration (review it!)
make mobile-dev         # expo start
make mobile-check       # tsc + eslint + steiger + jest
make api-types          # export OpenAPI from backend and regenerate mobile/src/shared/api/schema.d.ts
uv run python -m evals run <suite>   # (in backend/) AI evals — real API calls, costs money
```

A task is not done until the relevant `*-check` target is green.

## How to work on a task

1. Use `/run-task <ID>` (skill `run-task`). It defines the full loop: read → plan → implement →
   check → review → update the plan file.
2. One task per session. Do not start the next task on your own.
3. Stay inside the task's scope. Ideas outside scope go to `docs/backlog.md`.
4. Before finishing: run the self-review checklist below and the `code-reviewer` subagent.
5. Never commit or push unless the human asked for it in this session.

## Engineering principles (apply to both backend and mobile)

- **KISS.** The simplest design that keeps responsibilities separated. No speculative abstractions,
  no generic frameworks, no base classes "for the future".
- **YAGNI.** Build what the current task needs. No unused parameters, flags, layers or files.
- **DRY — for knowledge, not for lines.** One source of truth for every business rule, constant,
  limit, error code and API type. Two similar-looking pieces of code that represent different
  domain rules may stay separate. Rule of three before extracting a shared abstraction.
- **SOLID, pragmatically:**
  - *Single responsibility* — one reason to change per module, class, component, hook.
  - *Open/closed* — new AI features, parsers, dictionary sources are added as new implementations
    of an existing Protocol/interface, not by growing `if` chains.
  - *Liskov* — fakes (`FakeAIProvider`, …) must honour the same contract as real implementations.
  - *Interface segregation* — small Protocols per capability (`AIProvider`, `EmbeddingProvider`,
    `DictionaryProvider`), not one god-interface.
  - *Dependency inversion* — services depend on Protocols; concrete integrations are wired in
    dependencies/composition root, never imported inside domain logic.
- **Explicit over clever.** Clear names in domain language, small functions, early returns,
  no hidden side effects, no magic strings (use enums/literal unions).
- **Strict typing everywhere.** No `Any` / `any`, no unsafe casts. `# type: ignore[<code>]` /
  `@ts-expect-error` only for a third-party typing gap, isolated in the integration layer.
- **No comments in code.** Intent is expressed by names, small functions and types. No explanatory
  comments, no docstrings, no TODO/FIXME, no commented-out code. Exceptions: directives a tool
  strictly requires (`# noqa: <rule>` / `eslint-disable-next-line <rule>` with the specific rule,
  pragmas, license headers). Decisions that need explaining go to `docs/DECISIONS.md`.
- **Validate at boundaries.** HTTP input, files, external API responses and **every LLM output**
  are untrusted and validated before use.
- **Security and privacy.** Secrets only from env. Never read `.env` files. Never log tokens,
  secrets, book text, user context sentences or notes. User data never goes into shared tables.

## Domain language (use exactly these names)

Lexeme, LexemeForm, Meaning, Translation, MeaningContent, SenseSelection, UserVocabularyItem,
Collection, Book, BookChapter, BookParagraph, BookChunk, ReadingProgress, BookQuestion,
StudySession, StudySessionItem, IrregularVerb, Enrichment, Lookup, AIProvider, EmbeddingProvider,
DictionaryProvider. Statuses and codes are defined in `docs/ARCHITECTURE.md` — reuse them.

## Self-review checklist (before saying "done")

- Correct module/layer? (router/service/repository; FSD layer and slice)
- Any duplicated business rule, constant or type?
- Anything doing too much (file > ~250 lines, function > ~40 lines, component with several responsibilities)?
- Types strict, no `Any`/`any`, no unsafe casts?
- Errors: domain error codes, mapped at the boundary, shown to the user?
- External input and LLM output validated?
- Transactions explicit; jobs deferred after commit; jobs idempotent?
- N+1 queries, unbounded queries, unnecessary re-renders?
- Tests for the behaviour added; `*-check` green?
- Docs/plan updated if behaviour or decisions changed? Nothing unrelated changed?

## Git

Conventional commits with task id: `feat(books): EPUB parser with zip-bomb guard [T3.2]`.
Small focused commits. Never commit `.env`, data dumps (`data/`), APK/AAB, generated caches.
