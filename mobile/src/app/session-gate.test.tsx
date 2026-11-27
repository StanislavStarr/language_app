import { QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { hideAsync } from 'expo-splash-screen';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useSessionStore } from '@/entities/session';
import { createQueryClient } from '@/shared/api';

import { SessionGate } from './session-gate';

const initialMetrics = {
  frame: { x: 0, y: 0, width: 320, height: 640 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function renderGate() {
  await render(
    <SafeAreaProvider initialMetrics={initialMetrics}>
      <QueryClientProvider client={createQueryClient()}>
        <SessionGate>
          <Text>Приложение</Text>
        </SessionGate>
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

describe('SessionGate', () => {
  beforeEach(() => {
    useSessionStore.setState({ accessToken: null });
    jest.mocked(hideAsync).mockClear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('shows the app and hides the splash once the device is signed in', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(jsonResponse(200, { access_token: 'token-1' })));

    await renderGate();

    expect(await screen.findByText('Приложение')).toBeOnTheScreen();
    expect(hideAsync).toHaveBeenCalled();
  });

  it('keeps the splash while the first attempt is still running', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => new Promise<Response>(() => undefined));

    await renderGate();

    expect(screen.getByText('Подключаемся к серверу…')).toBeOnTheScreen();
    expect(screen.queryByText('Приложение')).not.toBeOnTheScreen();
    expect(hideAsync).not.toHaveBeenCalled();
  });

  it('reveals the loading state with the splash hidden when the server does not answer', async () => {
    jest.useFakeTimers();
    jest.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Network request failed'));

    await renderGate();
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0);
    });

    expect(hideAsync).toHaveBeenCalled();
    expect(screen.getByText('Подключаемся к серверу…')).toBeOnTheScreen();
  });

  it('shows a retryable error screen when sign-in is refused', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() =>
        Promise.resolve(
          jsonResponse(401, { error: { code: 'invalid_device_credentials', message: 'x' } }),
        ),
      )
      .mockImplementation(() => Promise.resolve(jsonResponse(200, { access_token: 'token-2' })));
    await renderGate();

    expect(await screen.findByText('Не удалось войти на этом устройстве.')).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole('button', { name: 'Повторить' }));

    await waitFor(() => {
      expect(screen.getByText('Приложение')).toBeOnTheScreen();
    });
  });
});
