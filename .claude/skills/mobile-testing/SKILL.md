---
name: mobile-testing
description: Write Jest tests for the Expo app — pure lib functions (tokenizer, phrase selection, study reducer, answer checking, error mapping) and React Native components with Testing Library. Use when adding or changing mobile logic or interactive UI.
---

# Mobile tests

Stack: `jest-expo` preset, `@testing-library/react-native`, user-centric queries.

## Priorities

1. **`lib/` pure functions — exhaustive.** These hold the risky logic:
   `tokenize-paragraph`, `select-phrase`, `study-session-reducer`, `check-answer`,
   `to-api-error`, `compute-highlights`. Use `it.each` tables with edge cases.
2. **Interactive widgets — behaviour.** Lookup sheet states, study stages, upload states:
   render with props/mocked hooks, act like a user, assert visible result and dispatched actions.
3. **Screens — only critical states** (loading/error/empty) when the logic is non-trivial.

No snapshot tests of whole screens.

## Conventions

- Test file next to the source: `tokenize-paragraph.test.ts`, `word-lookup-sheet.test.tsx`.
- Queries: `getByRole`, `getByText`, `getByLabelText`; `testID` only when nothing user-visible fits.
- Events: `userEvent` from Testing Library (`await user.press(...)`, `await user.type(...)`).
- Wrap components needing data in a test `QueryClientProvider` with retries off
  (`src/shared/lib/test/render-with-providers.tsx`).
- Mock the network at the boundary: mock `apiClient` methods or the slice's `api` hooks; never hit the real backend.
- Native modules (`expo-secure-store`, `expo-audio`, `expo-document-picker`) are mocked in `jest.setup.ts`.
- Deterministic: no timers without `jest.useFakeTimers()`, no random without a seed.

## Example — reducer

```ts
import { createInitialState, studySessionReducer } from './study-session-reducer';

const items = [wordItem('clarify'), wordItem('avoid'), phraseItem('look forward to')];

it('reveals the answer and moves on after the third wrong attempt', () => {
  let state = createInitialState(items, 'sentence');

  for (const answer of ['clarity', 'clarifi', 'clear']) {
    state = studySessionReducer(state, { type: 'answer_submitted', answer });
  }

  expect(state.revealedAnswer).toBe('clarify');
  state = studySessionReducer(state, { type: 'continue_pressed' });
  expect(state.currentItemIndex).toBe(1);
});

it('skips the sentence stage for phrases', () => {
  const state = createInitialState([phraseItem('look forward to')], 'matching');

  const next = studySessionReducer(state, { type: 'stage_completed' });

  expect(next.stage).toBe('definition');
});
```

## Before finishing

`make mobile-check` green (typecheck, lint, steiger, jest).
