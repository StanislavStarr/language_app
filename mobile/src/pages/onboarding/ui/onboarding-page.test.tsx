import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { isOnboardingCompleted, userKeys, type UserProfile } from '@/entities/user';
import { createQueryClient } from '@/shared/api';

import { OnboardingPage } from './onboarding-page';

const USER: UserProfile = {
  id: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001',
  native_language_id: 1,
  learning_language_id: 2,
  cefr_level: 'A1',
  answer_language: 'en_simple',
  onboarding_completed_at: null,
};

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

const cleanups: (() => void)[] = [];

async function renderOnboarding() {
  const queryClient = createQueryClient();
  queryClient.setQueryData(userKeys.me(), USER);
  const { unmount } = await render(
    <SafeAreaProvider initialMetrics={initialMetrics}>
      <QueryClientProvider client={queryClient}>
        <OnboardingPage />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
  cleanups.push(() => {
    unmount();
    queryClient.clear();
  });
  return queryClient;
}

describe('OnboardingPage', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    cleanups.splice(0).forEach((cleanup) => {
      cleanup();
    });
  });

  it('explains the fixed languages, the device binding and the OpenAI processing', async () => {
    await renderOnboarding();

    expect(screen.getByText('Родной язык: русский')).toBeOnTheScreen();
    expect(screen.getByText('Изучаемый язык: английский')).toBeOnTheScreen();
    expect(screen.getByText(/привязаны к этому устройству/)).toBeOnTheScreen();
    expect(screen.getByText(/обрабатываются сервисом OpenAI/)).toBeOnTheScreen();
  });

  it('starts with the profile values of the user selected', async () => {
    await renderOnboarding();

    expect(screen.getByRole('radio', { name: 'A1 — Начальный' })).toBeSelected();
    expect(screen.getByRole('radio', { name: 'Простой английский' })).toBeSelected();
  });

  it('sends the chosen level and answer language and completes onboarding', async () => {
    const bodies: unknown[] = [];
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const request = new Request(input);
      const body: unknown = JSON.parse(await request.clone().text());
      bodies.push(body);
      return jsonResponse(200, {
        ...USER,
        cefr_level: 'B2',
        answer_language: 'ru',
        onboarding_completed_at: '2026-11-27T10:00:00Z',
      });
    });
    const queryClient = await renderOnboarding();

    await fireEvent.press(screen.getByRole('radio', { name: 'B2 — Выше среднего' }));
    await fireEvent.press(screen.getByRole('radio', { name: 'Русский' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Начать' }));

    await waitFor(() => {
      expect(bodies).toEqual([
        { cefr_level: 'B2', answer_language: 'ru', complete_onboarding: true },
      ]);
    });
    await waitFor(() => {
      const cached = queryClient.getQueryData<UserProfile>(userKeys.me());
      expect(cached !== undefined && isOnboardingCompleted(cached)).toBe(true);
    });
  });

  it('shows a Russian error when saving fails and stays on the form', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() =>
        Promise.resolve(jsonResponse(422, { error: { code: 'validation_error', message: 'x' } })),
      );
    await renderOnboarding();

    await fireEvent.press(screen.getByRole('button', { name: 'Начать' }));

    expect(await screen.findByText('Проверьте введённые данные.')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: 'Начать' })).toBeOnTheScreen();
  });
});
