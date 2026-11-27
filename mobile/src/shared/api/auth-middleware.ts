import type { Middleware } from 'openapi-fetch';

import { fetchOrThrowNetworkError } from './network-fetch';

export const AUTH_DEVICE_PATH = '/api/v1/auth/device';

export type ApiAuth = {
  getAccessToken: () => string | null;
  refreshSession: () => Promise<void>;
};

type RetryFetch = (request: Request) => Promise<Response>;

export function createAuthMiddleware(
  getAuth: () => ApiAuth | null,
  retryFetch: RetryFetch = fetchOrThrowNetworkError,
): Middleware {
  const pristineRequests = new WeakMap<Request, Request>();
  const sentTokens = new WeakMap<Request, string | null>();
  let refreshInFlight: Promise<void> | null = null;

  function refreshOnce(auth: ApiAuth): Promise<void> {
    refreshInFlight ??= auth.refreshSession().finally(() => {
      refreshInFlight = null;
    });
    return refreshInFlight;
  }

  function withToken(request: Request, token: string | null): Request {
    if (token !== null) {
      request.headers.set('Authorization', `Bearer ${token}`);
    }
    return request;
  }

  return {
    onRequest({ request }) {
      const token = getAuth()?.getAccessToken() ?? null;
      pristineRequests.set(request, request.clone());
      sentTokens.set(request, token);
      return withToken(request, token);
    },
    async onResponse({ request, response }) {
      const auth = getAuth();
      const pristine = pristineRequests.get(request);
      const sentToken = sentTokens.get(request);
      pristineRequests.delete(request);
      sentTokens.delete(request);
      const isSignIn = new URL(request.url).pathname === AUTH_DEVICE_PATH;
      if (response.status !== 401 || auth === null || pristine === undefined || isSignIn) {
        return response;
      }
      if (auth.getAccessToken() === sentToken) {
        await refreshOnce(auth);
      }
      return retryFetch(withToken(pristine, auth.getAccessToken()));
    },
  };
}
