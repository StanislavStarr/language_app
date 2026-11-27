import { getErrorMessage, toApiError } from '@/shared/api';
import { AppText, ErrorState, Screen } from '@/shared/ui';

type Props = {
  error: Error;
  onRetry: () => void;
};

export function SignInErrorPage({ error, onRetry }: Props) {
  const { code, message } = toApiError(error);

  return (
    <Screen>
      <ErrorState message={getErrorMessage(error)} onRetry={onRetry} />
      {__DEV__ ? (
        <AppText variant="caption" tone="muted">
          {`${code}: ${message}`}
        </AppText>
      ) : null}
    </Screen>
  );
}
