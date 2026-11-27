import { EmptyState, Screen } from '@/shared/ui';

export function VocabularyPage() {
  return (
    <Screen>
      <EmptyState title="Словарь пуст" description="Здесь появятся сохранённые слова и темы." />
    </Screen>
  );
}
