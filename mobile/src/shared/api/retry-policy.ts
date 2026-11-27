import { ApiError, NETWORK_ERROR_CODE } from './api-error';

export const RETRY_DELAYS_MS = [2_000, 4_000, 8_000, 16_000, 30_000, 30_000] as const;

const RETRYABLE_STATUSES: readonly number[] = [502, 503, 504];

export function isRetryableError(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }
  return (
    error.code === NETWORK_ERROR_CODE ||
    (error.status !== null && RETRYABLE_STATUSES.includes(error.status))
  );
}

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  return failureCount < RETRY_DELAYS_MS.length && isRetryableError(error);
}

export function retryDelayMs(failureCount: number): number {
  return RETRY_DELAYS_MS[failureCount] ?? RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - 1] ?? 0;
}
