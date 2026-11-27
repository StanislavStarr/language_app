import { AppText } from './app-text';
import { CenteredState } from './centered-state';

type Props = {
  title: string;
  description?: string;
};

export function EmptyState({ title, description }: Props) {
  return (
    <CenteredState>
      <AppText variant="title">{title}</AppText>
      {description ? <AppText tone="muted">{description}</AppText> : null}
    </CenteredState>
  );
}
