---
name: llm-feature
description: Build or change an AI/LLM feature in the backend — provider Protocol method, versioned prompt, structured output schema with validation, caching, usage limits, fakes and an eval suite with before/after reports. Use for sense selection, meaning content, translations, fallback meanings, book Q&A, embeddings, or any prompt/model/retrieval change.
---

# LLM feature

Architecture: `docs/ARCHITECTURE.md` §9 (AI layer, evals). Decision: `docs/DECISIONS.md` ADR-008.

## Anatomy of a feature

```text
app/integrations/ai/
├── provider.py                    # AIProvider Protocol: one method per feature + request/response DTOs
├── openai_provider.py             # implementation (Responses API, structured outputs)
├── prompts/<feature>.py           # PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt(request)
├── schemas/<feature>.py           # Pydantic output model with limits and validators
└── dependencies.py                # get_ai_provider()
tests/fakes/fake_ai_provider.py    # deterministic fake, records calls
backend/evals/datasets/<feature>.jsonl
backend/evals/suites/<feature>.py
docs/evals/<feature>-<YYYY-MM-DD>.md
```

## Steps

1. **Contract.** Add a Protocol method with typed request DTO and `AIResult[<OutputModel>]` return.
2. **Output schema.** Pydantic model with:
   - length limits on every string (protects UI);
   - closed sets as `Literal`/`StrEnum`;
   - domain validators (e.g. definition must not contain the target word or its forms; cited ids
     must be a subset of provided ids — validated in the service when it needs request context).
3. **Prompt module.** `PROMPT_VERSION = "<feature>-v1"`; system prompt with explicit rules,
   output fields described, failure behaviour defined ("if no meaning fits, return null");
   user prompt built from the request DTO with labelled fields. No user secrets, no unrelated data.
4. **Implementation.** `client.responses.parse(model=settings.ai_model_<…>, input=[…], text_format=OutputModel)`;
   timeout from settings; retries only on connection errors/429/5xx; map SDK errors to
   `AIUnavailableError`/`AIProviderError`; log feature, model, prompt version, tokens, latency.
   Never log prompt contents with user text.
5. **Service integration.** The domain service:
   - checks usage limits before calling (`usage.consume`);
   - checks cache first (shared cache tables keyed by ids + hashes + `PROMPT_VERSION`);
   - validates output against request context; on invalid output — one retry, then degrade
     gracefully (feature-specific fallback), never crash the request;
   - stores provider/model/prompt_version with cached results.
6. **Fake.** Extend `FakeAIProvider`: configurable result per test, call counter.
7. **Tests.** Schema validation (good/bad outputs), service behaviour with fake (cache hit, limit,
   invalid output handling).
8. **Eval suite.** Dataset JSONL (≥ 30 cases for a new feature, include hard and negative cases),
   suite computing metrics from `docs/ARCHITECTURE.md` §9, report in `docs/evals/`.
   Run: `cd backend && uv run python -m evals run <feature>` (`--limit 10` for a quick check).
9. **Docs.** Update the feature table in `docs/ARCHITECTURE.md` §9 if anything changed.

## Changing an existing prompt, model or retrieval parameter

1. Run the suite on the current version → baseline report (if not recent).
2. Bump `PROMPT_VERSION` (never edit a version in place: caches are keyed by it).
3. Run the suite again → new report. Use the `eval-analyst` subagent to compare and explain failures.
4. Keep the change only if the target metric improves and no guard metric regresses
   (e.g. spoiler leaks must stay 0). Put the before/after numbers in the commit message.

## Dataset line examples

```json
{"id": "bank-river", "word": "bank", "sentence": "They had a picnic on the bank of the river.", "expected_gloss_contains": "side of a river"}
{"id": "qa-spoiler-1", "book": "pride-and-prejudice", "reading_position": 420, "question": "Who does Elizabeth marry?", "answerable": false, "gold_positions": []}
```

## Cost hygiene

- Use the cheapest model that meets the metric; model ids only in settings.
- Embeddings: `dimensions=512`, batches of 64.
- Evals in CI: never. Print the approximate cost of each run in the report.
