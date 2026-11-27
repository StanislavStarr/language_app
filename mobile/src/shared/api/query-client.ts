import { QueryClient } from '@tanstack/react-query';

import { retryDelayMs, shouldRetryQuery } from './retry-policy';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetryQuery, retryDelay: retryDelayMs },
      mutations: { retry: false },
    },
  });
}
