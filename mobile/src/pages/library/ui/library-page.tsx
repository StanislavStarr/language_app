import { EmptyState, Screen } from '@/shared/ui';

export function LibraryPage() {
  return (
    <Screen>
      <EmptyState
        title="Библиотека пуста"
        description="Здесь появятся ваши книги. Загрузка книг будет добавлена позже."
      />
    </Screen>
  );
}
