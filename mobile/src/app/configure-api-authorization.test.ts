import { useSessionStore } from '@/entities/session';
import { apiClient, ApiError, unwrap } from '@/shared/api';

import { configureApiAuthorization } from './configure-api-authorization';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('configureApiAuthorization', () => {
  beforeEach(() => {
    configureApiAuthorization();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('signs in again on 401 and retries the request with the new token', async () => {
    useSessionStore.setState({ accessToken: 'old' });
    const calls: string[] = [];
    jest.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const request = new Request(input);
      const { pathname } = new URL(request.url);
      calls.push(`${request.method} ${pathname} ${request.headers.get('Authorization') ?? '-'}`);
      if (pathname === '/api/v1/auth/device') {
        return Promise.resolve(jsonResponse(200, { access_token: 'new' }));
      }
      const authorized = request.headers.get('Authorization') === 'Bearer new';
      return Promise.resolve(
        authorized
          ? jsonResponse(200, { id: 'user-1' })
          : jsonResponse(401, { error: { code: 'token_expired', message: 'x' } }),
      );
    });

    const result = await apiClient.GET('/api/v1/users/me');

    expect(result.response.status).toBe(200);
    expect(useSessionStore.getState().accessToken).toBe('new');
    expect(calls).toEqual([
      'GET /api/v1/users/me Bearer old',
      'POST /api/v1/auth/device -',
      'GET /api/v1/users/me Bearer new',
    ]);
  });

  it('signs in only once for concurrent unauthorized requests', async () => {
    useSessionStore.setState({ accessToken: 'old' });
    let signIns = 0;
    jest.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const request = new Request(input);
      if (new URL(request.url).pathname === '/api/v1/auth/device') {
        signIns += 1;
        return Promise.resolve(jsonResponse(200, { access_token: 'new' }));
      }
      const authorized = request.headers.get('Authorization') === 'Bearer new';
      return Promise.resolve(
        authorized
          ? jsonResponse(200, { id: 'user-1' })
          : jsonResponse(401, { error: { code: 'token_expired', message: 'x' } }),
      );
    });

    const results = await Promise.all([
      apiClient.GET('/api/v1/users/me'),
      apiClient.GET('/api/v1/users/me'),
    ]);

    expect(results.map((result) => result.response.status)).toEqual([200, 200]);
    expect(signIns).toBe(1);
  });

  it('surfaces a refused re-sign-in as an ApiError without retrying forever', async () => {
    useSessionStore.setState({ accessToken: 'old' });
    const fetchSpy = jest.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const { pathname } = new URL(new Request(input).url);
      return Promise.resolve(
        pathname === '/api/v1/auth/device'
          ? jsonResponse(401, { error: { code: 'invalid_device_credentials', message: 'x' } })
          : jsonResponse(401, { error: { code: 'token_expired', message: 'x' } }),
      );
    });

    const failure = await unwrap(apiClient.GET('/api/v1/users/me')).catch(
      (caught: unknown) => caught,
    );

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: 'invalid_device_credentials' });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
