import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { useSessionStore } from '@/entities/session';
import { createQueryClient } from '@/shared/api';

import { useDeviceSignIn } from './use-device-sign-in';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const REFUSED = jsonResponse(401, { error: { code: 'invalid_device_credentials', message: 'x' } });

async function setup() {
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useDeviceSignIn(), { wrapper });
}

describe('useDeviceSignIn', () => {
  beforeEach(() => {
    useSessionStore.setState({ accessToken: null });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('becomes ready once the device is signed in', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(jsonResponse(200, { access_token: 'token-1' })));

    const { result } = await setup();

    await waitFor(() => {
      expect(result.current.status).toBe('ready');
    });
    expect(useSessionStore.getState().accessToken).toBe('token-1');
  });

  it('reports a refused sign-in as an error without retrying', async () => {
    const fetchSpy = jest
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(REFUSED.clone()));

    const { result } = await setup();

    await waitFor(() => {
      expect(result.current.status).toBe('error');
    });
    expect(result.current.error).toMatchObject({ code: 'invalid_device_credentials' });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('signs in again when the user retries', async () => {
    const fetchSpy = jest
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => Promise.resolve(REFUSED.clone()))
      .mockImplementation(() => Promise.resolve(jsonResponse(200, { access_token: 'token-2' })));
    const { result } = await setup();
    await waitFor(() => {
      expect(result.current.status).toBe('error');
    });

    result.current.retry();

    await waitFor(() => {
      expect(result.current.status).toBe('ready');
    });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
