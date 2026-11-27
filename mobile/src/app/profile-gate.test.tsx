import { QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { userKeys } from '@/entities/user';
import { createQueryClient } from '@/shared/api';

import { ProfileGate } from './profile-gate';

const initialMetrics = {
  frame: { x: 0, y: 0, width: 320, height: 640 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

const USER = {
  id: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001',
  native_language_id: 1,
  learning_language_id: 2,
  cefr_level: 'A1',
  answer_language: 'en_simple',
  onboarding_completed_at: null,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const cleanups: (() => void)[] = [];

async function renderGate() {
  const queryClient = createQueryClient();
  const { unmount } = await render(
    <SafeAreaProvider initialMetrics={initialMetrics}>
      <QueryClientProvider client={queryClient}>
        <ProfileGate>
          <Text>Содержимое</Text>
        </ProfileGate>
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
  cleanups.push(() => {
    unmount();
    queryClient.clear();
  });
}

describe('ProfileGate', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    cleanups.splice(0).forEach((cleanup) => {
      cleanup();
    });
  });

  it('shows the loading state while the profile loads', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => new Promise<Response>(() => undefined));

    await renderGate();

    expect(screen.getByText('Загрузка…')).toBeOnTheScreen();
    expect(screen.queryByText('Содержимое')).not.toBeOnTheScreen();
  });

  it('renders the content once the profile is loaded', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(jsonResponse(200, USER)));

    await renderGate();

    expect(await screen.findByText('Содержимое')).toBeOnTheScreen();
  });

  it('shows a retryable error when the profile cannot be loaded', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() =>
        Promise.resolve(jsonResponse(500, { error: { code: 'internal_error', message: 'x' } })),
      )
      .mockImplementation(() => Promise.resolve(jsonResponse(200, USER)));
    await renderGate();

    expect(await screen.findByText('Ошибка на сервере. Попробуйте позже.')).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole('button', { name: 'Повторить' }));

    expect(await screen.findByText('Содержимое')).toBeOnTheScreen();
  });

  it('keeps the app mounted when a background refresh of a loaded profile fails', async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(userKeys.me(), USER);
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() =>
        Promise.resolve(jsonResponse(500, { error: { code: 'internal_error', message: 'x' } })),
      );
    const { unmount } = await render(
      <SafeAreaProvider initialMetrics={initialMetrics}>
        <QueryClientProvider client={queryClient}>
          <ProfileGate>
            <Text>Содержимое</Text>
          </ProfileGate>
        </QueryClientProvider>
      </SafeAreaProvider>,
    );
    cleanups.push(() => {
      unmount();
      queryClient.clear();
    });

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: userKeys.me() });
    });

    expect(screen.getByText('Содержимое')).toBeOnTheScreen();
    expect(screen.queryByText('Ошибка на сервере. Попробуйте позже.')).not.toBeOnTheScreen();
  });
});
