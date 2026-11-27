import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { ApiError, createQueryClient, NETWORK_ERROR_CODE } from '@/shared/api';

import { useIsServerWaking } from './use-is-server-waking';

const networkError = new ApiError(NETWORK_ERROR_CODE, 'offline', null, null);
const badRequest = new ApiError('validation_error', 'invalid', 422, null);

async function setup() {
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const { result } = await renderHook(() => useIsServerWaking(), { wrapper });
  return { queryClient, result };
}

describe('useIsServerWaking', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('is false when nothing is loading', async () => {
    const { result } = await setup();

    expect(result.current).toBe(false);
  });

  it('is true while a failed request is being retried and false after it succeeds', async () => {
    const { queryClient, result } = await setup();
    const queryFn = jest
      .fn<Promise<string>, []>()
      .mockRejectedValueOnce(networkError)
      .mockResolvedValueOnce('ok');

    let pending: Promise<string> | undefined;
    await act(async () => {
      pending = queryClient.fetchQuery({ queryKey: ['wake'], queryFn });
      await jest.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toBe(true);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(2_000);
    });

    await expect(pending).resolves.toBe('ok');
    expect(result.current).toBe(false);
  });

  it('is false for errors that are not retried', async () => {
    const { queryClient, result } = await setup();
    const queryFn = jest.fn<Promise<string>, []>().mockRejectedValue(badRequest);

    await act(async () => {
      await queryClient.fetchQuery({ queryKey: ['invalid'], queryFn }).catch(() => undefined);
    });

    expect(result.current).toBe(false);
    expect(queryFn).toHaveBeenCalledTimes(1);
  });
});
