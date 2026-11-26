# backend/CLAUDE.md — Python / FastAPI rules

Applies to everything under `backend/`. Root `CLAUDE.md` principles (KISS, DRY, SOLID, YAGNI,
no comments, strict typing) apply too. Architecture: `docs/ARCHITECTURE.md` §4–§13.

## Style: PEP 8 enforced by tools

- `ruff format` is the formatter, `ruff check` the linter (rule set in `pyproject.toml`), line length 100.
  Never hand-format against ruff; never disable a rule globally to make code pass.
- `mypy --strict` must pass. Python 3.13 syntax: `list[str]`, `X | None`, `type` aliases,
  PEP 695 generics (`class AIResult[T]: ...`).
- Naming (PEP 8): modules/functions/variables `snake_case`; classes `PascalCase`; constants
  `UPPER_SNAKE_CASE`; private helpers `_leading_underscore`. Names describe business behaviour:
  `find_meanings_by_lexeme`, `defer_enrichment`, `select_sense` — not `process`, `handle`, `do_work`,
  `get_data`, `utils`, `helpers`, `manager`.
- Imports: absolute (`from app.modules.lexicon.service import LookupService`), sorted by ruff,
  no wildcard imports, no imports inside functions except to break a proven cycle.
- `pathlib` over `os.path`; f-strings; `enum.StrEnum` for closed sets of values stored in DB/API.
- Immutable DTOs: `@dataclass(frozen=True, slots=True)` for internal data, Pydantic models for
  validated boundaries.

## Module layout

```text
app/modules/<module>/
├── router.py        # HTTP only
├── schemas.py       # Pydantic request/response models (API contract)
├── models.py        # SQLAlchemy models
├── repository.py    # SQL only
├── service.py       # use cases; split into services/<use_case>.py when it grows
├── exceptions.py    # domain errors (subclasses of AppError)
├── dependencies.py  # FastAPI Depends factories wiring service ← repository ← integrations
└── jobs.py          # Procrastinate tasks (thin)
```

Create only the files a module actually needs. No empty layers, no placeholder files.

### Dependency direction (never reversed)

```text
router → service → repository → models
           ↓
     integrations (via Protocol)
jobs → service
```

- A module uses another module **only through its service** (or a small public function).
  Never import another module's repository or models to bypass its rules.
- `core/` holds infrastructure without business meaning (config, db, security, logging, errors,
  jobs app, rate limit). Domain logic never goes into `core/`.
- `integrations/` holds external systems (OpenAI, Free Dictionary, spaCy). Provider-specific
  formats never leak out: integrations return normalized DTOs.

## Layer rules

### Router (`router.py`)
- Parse input (Pydantic), call one service method, return a response schema. Nothing else.
- No SQL, no business rules, no provider calls, no `try/except` for domain errors (global handler maps them).
- Declare `response_model`, status codes, and `responses` for documented error codes.
- Auth via `CurrentUser = Annotated[User, Depends(get_current_user)]`.

### Service (`service.py`) — the service layer
- Owns use cases and **transaction boundaries**: one public method = one use case = one transaction.
  The service receives `AsyncSession`, calls repositories, then `await session.commit()` at the end
  of the use case. Repositories never commit.
- Defers background jobs **after** commit.
- Raises domain exceptions (`BookNotReady`, `UsageLimitExceeded`), never `HTTPException`.
- Independent of FastAPI: no `Request`, `Response`, `Depends` inside services.
- Depends on Protocols for integrations, injected in `__init__`; no module-level singletons
  except immutable settings.
- Keep methods short; extract private methods with domain names; split a service by use case when
  it exceeds ~250 lines.

### Repository (`repository.py`)
- SQLAlchemy 2.x `select()` style only; returns models or DTOs; never HTTP or domain errors
  (return `None`, let the service decide).
- No business decisions (no "if user is premium…"); only queries and persistence.
- Prevent N+1 with explicit `selectinload`/joins; every list query is paginated or bounded.
- Raw SQL (`text()`) only where SQLAlchemy is unclear (hybrid search, RRF), with bound parameters.

### Schemas (`schemas.py`)
- Separate models per intent: `CollectionCreate`, `CollectionUpdate`, `CollectionResponse`.
  Never expose ORM models as API responses.
- Field constraints mirror product limits (`Field(max_length=80)`); limits come from one place
  (`app/core/config.py` or module constants), not repeated literals.
- Discriminated unions for polymorphic inputs (`LookupRequest = Annotated[ManualLookup | BookLookup, Field(discriminator="source")]`).

### Models (`models.py`)
- `DeclarativeBase`, `Mapped[...]`, `mapped_column()`; nullability matches the domain.
- Invariants enforced by the DB: FKs with explicit `ondelete`, unique constraints, check constraints.
- Naming convention for constraints is set on `Base.metadata` — do not name constraints manually.

### Errors
- `AppError(code: str, message: str, status_code: int, details: dict | None)` in `core/errors.py`;
  each module defines subclasses with a stable `code` (snake_case). The list of codes lives in
  `docs/ARCHITECTURE.md` and is mirrored in the mobile error-message map.
- Unknown exceptions → `internal_error`, logged with request id, no internals in the response.

## Integrations and AI

- Every external capability is a `Protocol` in `integrations/<area>/provider.py` plus one real
  implementation and one fake for tests. Business code imports the Protocol only.
- Every external call: explicit timeout, bounded retries (only on network errors/429/5xx),
  structured log with provider, operation, latency, outcome.
- AI features follow skill `llm-feature`: versioned prompt module, Pydantic output schema with
  length limits and domain validators, cache where reusable, eval dataset, `docs/evals` report.
- Model names only from settings. Never hard-code a model id.
- Shared tables (`meaning_content`, `sense_selection`, `translation`) never contain user text;
  user context is hashed (`sha256`) before being used as a cache key.

## Background jobs (Procrastinate)

- Tasks live in `modules/<module>/jobs.py`, are `async`, receive only ids/primitive args, and
  call a service method. No business logic in task functions.
- Idempotent: re-running a task must not duplicate rows or regress a status.
- Bounded retries with exponential backoff; final failure sets a domain status (`failed`) with an error code.
- Concurrency on shared resources via `pg_advisory_xact_lock` + unique constraints, never in-process locks.

## Database migrations (skill `backend-migration`)

- Every schema change = new Alembic revision. Never edit an applied revision.
- Autogenerate, then **read and fix** the script (extensions, generated columns, HNSW/GIN indexes,
  enum types, data migrations are not autogenerated correctly).
- `downgrade()` implemented unless impossible (then say why in the PR description).
- Test: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`.

## Files and untrusted input

- Book files: check size before reading fully, verify signature, parse with `defusedxml`,
  limit total decompressed EPUB size, never write archive paths to disk.
- CPU-bound work (spaCy, parsing) runs via `asyncio.to_thread` inside jobs, never blocks the event loop
  of a request handler longer than ~50 ms.

## Logging

- `structlog` with `request_id`; event names in `snake_case` (`book_parsed`, `ai_call_failed`).
- Log ids and counts, never content: no tokens, secrets, book text, contexts, notes, questions.
- No `print()`.

## Testing (skill `backend-testing`)

- `pytest` + `pytest-asyncio`; tests mirror the app tree: `tests/modules/<module>/test_<unit>.py`.
- Real PostgreSQL for repository/service/API tests (transaction rolled back per test).
  No SQLite substitutes.
- Fakes for AI, embeddings, dictionary, time. No real network in tests (`respx` for HTTP clients).
- Test observable behaviour: API responses, DB state, raised domain errors. Not private methods.
- Every bug fix in non-trivial logic gets a regression test.
- Factories as plain async helper functions in `tests/factories.py`; no fixture mega-files.

## Dependencies

Add a package only when the standard library and existing deps cannot do it reasonably.
`uv add <pkg>` (or `uv add --dev`). Check maintenance status and licence. Never pin by hand-editing `uv.lock`.
