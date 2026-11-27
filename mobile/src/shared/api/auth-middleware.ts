import type { Middleware } from 'openapi-fetch';

import { fetchOrThrowNetworkError } from './network-fetch';

export const AUTH_DEVICE_PATH = '/api/v1/auth/device';

export type ApiAuth = {
  getAccessToken: () => string | null;
  refreshSession: () => Promise<void>;
};

const NULL_BODY_STATUSES: readonly number[] = [101, 204, 205, 304];

type ResponseLike = Pick<Response, 'status' | 'statusText' | 'headers' | 'arrayBuffer'>;

async function toStandardResponse(response: ResponseLike): Promise<Response> {
  if (response instanceof Response) {
    return response;
  }
  const body = NULL_BODY_STATUSES.includes(response.status) ? null : await response.arrayBuffer();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

function isSignInRequest(request: Request): boolean {
  return new URL(request.url).pathname === AUTH_DEVICE_PATH;
}

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
      const token = isSignInRequest(request) ? null : (getAuth()?.getAccessToken() ?? null);
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
      if (
        response.status !== 401 ||
        auth === null ||
        pristine === undefined ||
        isSignInRequest(request)
      ) {
        return undefined;
      }
      if (auth.getAccessToken() === sentToken) {
        await refreshOnce(auth);
      }
      return toStandardResponse(await retryFetch(withToken(pristine, auth.getAccessToken())));
    },
  };
}
