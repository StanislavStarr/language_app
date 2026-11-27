import { QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ApiError, createQueryClient, NETWORK_ERROR_CODE } from '@/shared/api';

import { ServerWakeBanner } from './server-wake-banner';

const BANNER_TEXT = 'Сервер просыпается… Это может занять около минуты.';
const initialMetrics = {
  frame: { x: 0, y: 0, width: 320, height: 640 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

describe('ServerWakeBanner', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('is shown while a request is retried and hidden once it succeeds', async () => {
    const queryClient = createQueryClient();
    await render(
      <SafeAreaProvider initialMetrics={initialMetrics}>
        <QueryClientProvider client={queryClient}>
          <ServerWakeBanner />
        </QueryClientProvider>
      </SafeAreaProvider>,
    );
    expect(screen.queryByText(BANNER_TEXT)).not.toBeOnTheScreen();
    const queryFn = jest
      .fn<Promise<string>, []>()
      .mockRejectedValueOnce(new ApiError(NETWORK_ERROR_CODE, 'offline', null, null))
      .mockResolvedValueOnce('ok');

    await act(async () => {
      void queryClient.fetchQuery({ queryKey: ['wake'], queryFn });
      await jest.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText(BANNER_TEXT)).toBeOnTheScreen();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(2_000);
    });
    expect(screen.queryByText(BANNER_TEXT)).not.toBeOnTheScreen();
  });
});
