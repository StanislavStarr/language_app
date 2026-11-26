# mobile/CLAUDE.md — Expo / React Native / FSD rules

Applies to everything under `mobile/`. Root `CLAUDE.md` principles apply too.
Architecture: `docs/ARCHITECTURE.md` §3 (Mobile), §6.5–§6.7, §7.

## Hard constraint: Expo Go compatibility

The app must run in **Expo Go** (no paid Apple account, see `docs/DECISIONS.md` ADR-002).

- Install native-related packages only with `npx expo install <pkg>` and only if the package is part
  of the Expo SDK or bundled in Expo Go (reanimated, gesture-handler, flash-list, svg, async-storage…).
- No config plugins that need prebuild, no `expo-dev-client`, no custom native modules,
  no `react-native-mmkv`, no share extensions/widgets.
- If a task seems to need such a package — stop and propose an alternative or a backlog item.

## Feature-Sliced Design

```text
mobile/
├── app/                 # Expo Router routes ONLY (thin files)
│   ├── _layout.tsx
│   ├── (tabs)/library.tsx …
│   └── books/[bookId]/read.tsx …
└── src/
    ├── app/             # providers, root layout pieces, global styles/theme setup
    ├── pages/           # full screens composed from widgets/features
    ├── widgets/         # large self-contained UI blocks (reader-view, word-lookup-sheet, study-matching)
    ├── features/        # user actions with business value (upload-book, add-word-to-vocabulary, ask-book)
    ├── entities/        # business entities (book, lexeme, vocabulary-item, collection, study-session, session)
    └── shared/          # api client + generated schema, ui kit, theme, config, generic lib
```

### Import rules (enforced by `steiger` and ESLint)

- A layer imports only from layers **below** it: `app → pages → widgets → features → entities → shared`.
- Slices on the same layer do not import each other. If an entity genuinely references another,
  use the FSD cross-import notation `entities/<a>/@x/<b>.ts` and keep it minimal.
- Import a slice **only through its public API** `index.ts`: `import { BookCard } from '@/entities/book'`.
  Never deep-import `@/entities/book/ui/book-card`.
- `shared` has no business logic and no knowledge of entities.
- Route files in `mobile/app/` contain no logic: read params, render a page from `@/pages/...`.

### Slice segments

```text
<slice>/
├── ui/        # components
├── model/     # Zustand stores, hooks with state, selectors, types of the slice
├── api/       # query keys, useQuery/useMutation hooks, request functions (via shared/api client)
├── lib/       # pure functions (tokenizer, reducers, answer checking) — the most tested code
├── config/    # constants, copy texts reused within the slice
└── index.ts   # public API: export only what other layers need
```

Create only the segments the slice needs.

## Naming

- Files and folders: `kebab-case` (`word-lookup-sheet.tsx`, `use-add-word.ts`, `tokenize-paragraph.ts`).
- Components `PascalCase`, hooks `useCamelCase`, stores `useXxxStore`, types `PascalCase`,
  constants `UPPER_SNAKE_CASE`. One exported component per file; file name matches it.
- Domain names from root `CLAUDE.md`. No `utils.ts`, `helpers.ts`, `types.ts` dumping grounds.

## Components

- Function components with typed props (`type Props = {...}`); no default exports except route files
  (Expo Router requires them).
- A component renders and delegates. Data fetching, mutations and orchestration live in hooks
  (`api/`, `model/`), pure logic in `lib/`.
- Split when a component has more than one responsibility or exceeds ~200 lines.
- Every async screen handles **loading, error, empty, success** using shared `LoadingState`,
  `ErrorState`, `EmptyState`.
- Accessibility: `accessibilityRole`/`accessibilityLabel` on interactive elements, touch targets ≥ 44 pt
  (`hitSlop` when needed).
- UI copy is Russian. Error texts come from one map: `shared/api/error-messages.ts` (by error code).

## State

- **Server state = TanStack Query only.** Never copy server data into Zustand or `useState`.
- Query keys are defined once per entity in `api/query-keys.ts` and reused for invalidation.
- Mutations live in `features/*/api`; on success invalidate precise keys (e.g. `vocabularyKeys.forms()`).
- **Client state = Zustand** for cross-screen UI state (study session progress, phrase selection,
  reader settings). Local `useState` for state of one component.
- Complex state transitions are pure reducers in `lib/` (e.g. `study-session-reducer.ts`), the store
  only wires them.
- Persisted client settings: Zustand `persist` + AsyncStorage. Credentials only in `expo-secure-store`.

## API layer

- All HTTP goes through `shared/api/client.ts` (`openapi-fetch` typed by generated `schema.d.ts`).
- Never hand-write request/response types that exist in `schema.d.ts`; derive them:
  `type BookResponse = components['schemas']['BookResponse']`.
- After any backend contract change run `make api-types` (skill `mobile-api-sync`).
- Components never build URLs or call `fetch`.
- Errors are normalized to `ApiError` in the client; UI branches on `error.code`, never on message text.

## Styling

- `StyleSheet.create` at the bottom of the component file; values from theme tokens
  (`shared/ui/theme`: colors, spacing, radii, typography). No magic numbers or hex colors in components.
- No inline style objects in JSX except values that are truly dynamic (then memoize).
- Light/dark theme through `useTheme()`; never read `Appearance` directly in components.

## Performance

- Long lists: `FlashList` with stable `keyExtractor` and `estimatedItemSize` where needed.
- Reader: paragraph components are memoized by paragraph id + highlight version; word press handlers
  are stable (`useCallback` with ids, not closures per token).
- Avoid creating objects/functions in render that are passed to memoized children.
- No polling faster than 3 s; stop polling when status is terminal.

## TypeScript

- `strict: true`, `noUncheckedIndexedAccess: true`. No `any`, no `as` casts except `as const`;
  narrow `unknown` with type guards or zod.
- Literal unions/discriminated unions for statuses and stages, exhaustive `switch` with `never` check.
- Path alias `@/` → `src/`.

## Testing (skill `mobile-testing`)

- `jest-expo` + `@testing-library/react-native`. Test files next to the code: `tokenize-paragraph.test.ts`.
- Must be tested: everything in `lib/` (tokenizer, phrase selection, study reducer, answer check,
  error mapping), and key interactive widgets (lookup sheet states, study stages).
- Query by role/text like a user; no snapshot tests of whole screens.
- Mock the network at the API-client boundary; mock Expo native modules in `jest.setup.ts`.
