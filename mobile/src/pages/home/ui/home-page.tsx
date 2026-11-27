import { AppText, Screen } from '@/shared/ui';

export function HomePage() {
  return (
    <Screen>
      <AppText variant="title">English Reader</AppText>
      <AppText tone="muted">Читайте книги и учите слова в контексте.</AppText>
    </Screen>
  );
}
