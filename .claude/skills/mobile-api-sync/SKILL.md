---
name: mobile-api-sync
description: Regenerate mobile TypeScript API types from the FastAPI OpenAPI schema and update the affected query hooks and error-message map. Use after any backend endpoint, schema or error code change, or when the mobile app needs a new endpoint.
---

# Sync API contract to mobile

Source of truth: FastAPI OpenAPI. Decision: `docs/DECISIONS.md` ADR-010.

## Steps

1. Backend change is done and `make backend-check` is green.
2. `make api-types`, which runs:
   ```bash
   cd backend && uv run python -m scripts.export_openapi > openapi.json
   cd ../mobile && npx openapi-typescript ../backend/openapi.json -o src/shared/api/schema.d.ts
   ```
3. `npm run typecheck` in `mobile/` — every compile error is a place that must follow the new contract.
   Fix usages; do not loosen types.
4. Derive types, never duplicate:
   ```ts
   import type { components } from '@/shared/api/schema';
   export type ApiSchemas = components['schemas'];
   type LookupResponse = ApiSchemas['LookupResponse'];
   ```
5. New error codes → add Russian texts to `src/shared/api/error-messages.ts`. The test
   `error-messages.test.ts` fails if a code documented in the backend registry has no text.
6. New endpoint → query/mutation hook in the owning slice's `api/` segment + query keys.
7. Commit `backend/openapi.json` and `schema.d.ts` together with the change (CI checks they match).

## Rules

- `schema.d.ts` is generated — never edit it by hand.
- Request bodies are typed from the schema (`ApiSchemas['VocabularyItemCreate']`), including
  discriminated unions (`source: { type: 'book', ... }`).
- Multipart upload (`POST /books`) uses `FormData` with `bodySerializer` in openapi-fetch; the
  response is still typed from the schema.
