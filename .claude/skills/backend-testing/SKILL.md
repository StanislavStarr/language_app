---
name: backend-testing
description: Write pytest tests for the FastAPI backend — API, service, repository, job and parser tests on real PostgreSQL with fakes for AI/embeddings/dictionary. Use when adding or changing backend behaviour or fixing a bug.
---

# Backend tests

## Layout

```text
backend/tests/
├── conftest.py              # db engine, per-test transaction, app + AsyncClient, auth helper, fakes
├── factories.py             # async helpers: create_user(), create_lexeme(), create_book(...)
├── fakes/                   # FakeAIProvider, FakeEmbeddingProvider, FakeDictionaryProvider, FrozenClock
├── fixtures/                # books (epub/fb2/txt), wiktextract jsonl samples, http responses
└── modules/<module>/test_<unit>.py
```

## What to test at which level

| Code | Test style |
| --- | --- |
| Pure functions (normalize, tokenize, chunker, RRF, parsers, validators) | plain unit tests, parametrized |
| Repository | real DB, assert returned rows and query behaviour (filters, ordering, limits) |
| Service | real DB + fakes for integrations; assert DB state, returned value, raised domain error, deferred jobs |
| Router/API | `AsyncClient`; assert status, response JSON shape, error `code`; auth required |
| Jobs | call the task function with the in-memory Procrastinate connector or call the service directly |
| AI output validation | parametrized good/bad model outputs against Pydantic schemas |

## Conventions

- Test names state behaviour: `test_lookup_returns_lemma_for_irregular_form`,
  `test_question_never_cites_chunks_after_reading_position`.
- Arrange–Act–Assert blocks separated by a blank line; one behaviour per test.
- Use `pytest.mark.parametrize` for input tables instead of loops.
- Factories set only what the test cares about; everything else gets valid defaults.
- Fakes are configured per test (`fake_ai.select_sense_result = ...`) and record calls
  (`assert fake_ai.calls["select_sense"] == 1`) — used to prove caching.
- Time: inject a clock where behaviour depends on dates (daily limits, token expiry).
- HTTP clients: `respx` routes; assert timeouts/404/garbage handling.
- No network, no real OpenAI, no sleeping. A test that needs `sleep` is a design problem.
- Every user-scoped endpoint gets an access test: another user's resource → 404.

## Example

```python
async def test_add_word_twice_returns_conflict_with_existing_id(
    client: AsyncClient, auth_headers: dict[str, str], meaning: Meaning
) -> None:
    payload = {"meaning_id": meaning.id, "collection_ids": [], "source": {"type": "manual"}}
    first = await client.post("/api/v1/vocabulary", json=payload, headers=auth_headers)

    second = await client.post("/api/v1/vocabulary", json=payload, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_in_vocabulary"
    assert second.json()["error"]["details"]["item_id"] == first.json()["id"]
```

## Before finishing

- `make backend-check` green.
- New behaviour covered at the cheapest level that proves it; bug fixes have a regression test.
