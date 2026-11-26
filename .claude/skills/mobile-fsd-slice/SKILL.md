---
name: mobile-fsd-slice
description: Create or extend a Feature-Sliced Design slice (entity, feature, widget, page) and its Expo Router route in the Expo app. Use for any new screen, UI block, user action or entity on mobile.
---

# FSD slice in the Expo app

Rules: `mobile/CLAUDE.md`. Expo Go compatibility is mandatory.

## 1. Pick the layer

| What it is | Layer | Example |
| --- | --- | --- |
| Business noun: data shape, query hooks, small UI to display it | `entities` | `entities/book` (BookCard, useBookQuery, tokenize-paragraph) |
| User action that changes something / has business value | `features` | `features/add-word-to-vocabulary`, `features/upload-book` |
| Large self-contained block composed of entities/features | `widgets` | `widgets/reader-view`, `widgets/word-lookup-sheet` |
| Full screen | `pages` | `pages/reader` |
| Navigation | `mobile/app/` route file | `app/books/[bookId]/read.tsx` |
| Generic, no business meaning | `shared` | `shared/ui/button`, `shared/api/client` |

If unsure between feature and entity: does it *do* something the user asked for (feature) or
*represent* something (entity)?

## 2. Create the slice

```text
src/features/add-word-to-vocabulary/
├── api/use-add-word.ts
├── model/use-add-word-form.ts
├── ui/add-word-button.tsx
├── ui/collection-picker.tsx
└── index.ts
```

`index.ts` exports only the public surface:

```ts
export { AddWordButton } from './ui/add-word-button';
export { useAddWord } from './api/use-add-word';
```

## 3. Templates

Entity query hook (`entities/book/api/`):

```ts
import { useQuery } from '@tanstack/react-query';

import { apiClient, unwrap } from '@/shared/api';

import { bookKeys } from './query-keys';

export function useBookQuery(bookId: string) {
  return useQuery({
    queryKey: bookKeys.detail(bookId),
    queryFn: async () =>
      unwrap(await apiClient.GET('/api/v1/books/{book_id}', { params: { path: { book_id: bookId } } })),
  });
}
```

Query keys (`entities/book/api/query-keys.ts`):

```ts
export const bookKeys = {
  all: ['books'] as const,
  list: () => [...bookKeys.all, 'list'] as const,
  detail: (bookId: string) => [...bookKeys.all, 'detail', bookId] as const,
  chapter: (bookId: string, chapterIndex: number) =>
    [...bookKeys.detail(bookId), 'chapter', chapterIndex] as const,
};
```

Feature mutation (`features/add-word-to-vocabulary/api/use-add-word.ts`):

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { vocabularyKeys } from '@/entities/vocabulary-item';
import { apiClient, unwrap, type ApiSchemas } from '@/shared/api';

type AddWordPayload = ApiSchemas['VocabularyItemCreate'];

export function useAddWord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AddWordPayload) =>
      unwrap(await apiClient.POST('/api/v1/vocabulary', { body: payload })),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: vocabularyKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: vocabularyKeys.forms() }),
      ]),
  });
}
```

Presentational component:

```tsx
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText, useTheme, spacing, radii } from '@/shared/ui';

import type { BookSummary } from '../model/types';

type Props = {
  book: BookSummary;
  onPress: (bookId: string) => void;
};

export function BookCard({ book, onPress }: Props) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={book.title}
      onPress={() => onPress(book.id)}
      style={[styles.card, { backgroundColor: theme.colors.surface }]}
    >
      <AppText variant="title">{book.title}</AppText>
      {book.author ? <AppText variant="caption">{book.author}</AppText> : null}
      <View style={styles.progress} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { padding: spacing.md, borderRadius: radii.md, gap: spacing.xs },
  progress: { height: 4, borderRadius: radii.sm },
});
```

Page + route:

```tsx
// src/pages/reader/ui/reader-page.tsx — composes widgets, handles loading/error/empty
export function ReaderPage({ bookId }: { bookId: string }) { /* ... */ }

// app/books/[bookId]/read.tsx — route file, no logic
import { useLocalSearchParams } from 'expo-router';

import { ReaderPage } from '@/pages/reader';

export default function ReadRoute() {
  const { bookId } = useLocalSearchParams<{ bookId: string }>();
  return <ReaderPage bookId={bookId} />;
}
```

(The `// ...` lines above are documentation for this skill only — real code has no comments.)

## 4. Checks

- `npm run lint:fsd` (steiger) and `npm run lint` pass — no cross-slice or upward imports,
  no deep imports.
- Loading / error / empty states exist for async UI.
- Pure logic moved to `lib/` with tests (skill `mobile-testing`).
- New dependency? Installed via `npx expo install` and confirmed to work in Expo Go.
