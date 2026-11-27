import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { userKeys, type UserProfile } from '@/entities/user';
import { createQueryClient } from '@/shared/api';

import { ProfilePage } from './profile-page';

const USER: UserProfile = {
  id: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001',
  native_language_id: 1,
  learning_language_id: 2,
  cefr_level: 'A2',
  answer_language: 'en_simple',
  onboarding_completed_at: '2026-11-27T10:00:00Z',
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

async function renderProfile() {
  const queryClient = createQueryClient();
  queryClient.setQueryData(userKeys.me(), USER);
  const { unmount } = await render(
    <SafeAreaProvider initialMetrics={initialMetrics}>
      <QueryClientProvider client={queryClient}>
        <ProfilePage />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
  cleanups.push(() => {
    unmount();
    queryClient.clear();
  });
}

describe('ProfilePage', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    cleanups.splice(0).forEach((cleanup) => {
      cleanup();
    });
  });

  it('shows the saved level and answer language', async () => {
    await renderProfile();

    expect(screen.getByRole('radio', { name: 'A2 — Элементарный' })).toBeSelected();
    expect(screen.getByRole('radio', { name: 'Простой английский' })).toBeSelected();
  });

  it('saves a new level on the server as soon as it is chosen', async () => {
    const bodies: unknown[] = [];
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const request = new Request(input);
      const body: unknown = JSON.parse(await request.clone().text());
      bodies.push(body);
      return jsonResponse(200, { ...USER, cefr_level: 'B1' });
    });
    await renderProfile();

    await fireEvent.press(screen.getByRole('radio', { name: 'B1 — Средний' }));

    expect(
      await screen.findByRole('radio', { name: 'B1 — Средний', selected: true }),
    ).toBeOnTheScreen();
    expect(bodies).toEqual([{ cefr_level: 'B1' }]);
  });

  it('saves a new answer language without touching the level', async () => {
    const bodies: unknown[] = [];
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const request = new Request(input);
      const body: unknown = JSON.parse(await request.clone().text());
      bodies.push(body);
      return jsonResponse(200, { ...USER, answer_language: 'ru' });
    });
    await renderProfile();

    await fireEvent.press(screen.getByRole('radio', { name: 'Русский' }));

    expect(await screen.findByRole('radio', { name: 'Русский', selected: true })).toBeOnTheScreen();
    expect(bodies).toEqual([{ answer_language: 'ru' }]);
  });

  it('keeps the old value and shows an error when saving fails', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() =>
        Promise.resolve(jsonResponse(429, { error: { code: 'rate_limited', message: 'x' } })),
      );
    await renderProfile();

    await fireEvent.press(screen.getByRole('radio', { name: 'B1 — Средний' }));

    expect(await screen.findByText('Слишком много запросов. Подождите немного.')).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'A2 — Элементарный' })).toBeSelected();
  });
});
