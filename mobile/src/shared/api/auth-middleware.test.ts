import createClient from 'openapi-fetch';

import { ApiError } from './api-error';
import { type ApiAuth, createAuthMiddleware } from './auth-middleware';
import type { paths } from './schema';
import { unwrap } from './unwrap';

const USER_BODY = { id: 'user-1' };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function setup(auth: ApiAuth | null, validToken = 'new') {
  const seenTokens: (string | null)[] = [];
  const seenBodies: string[] = [];
  const fakeFetch = jest.fn(async (request: Request) => {
    const header = request.headers.get('Authorization');
    seenTokens.push(header);
    seenBodies.push(await request.clone().text());
    const status = header === `Bearer ${validToken}` ? 200 : 401;
    return jsonResponse(
      status,
      status === 200 ? USER_BODY : { error: { code: 'token_expired', message: 'x' } },
    );
  });
  const client = createClient<paths>({ baseUrl: 'http://api.test', fetch: fakeFetch });
  client.use(createAuthMiddleware(() => auth, fakeFetch));
  return { client, fakeFetch, seenTokens, seenBodies };
}

function createAuth(initialToken: string | null) {
  let token = initialToken;
  const refreshSession = jest.fn(async () => {
    await Promise.resolve();
    token = 'new';
  });
  const auth: ApiAuth = { getAccessToken: () => token, refreshSession };
  return { auth, refreshSession };
}

describe('auth middleware', () => {
  it('sends the access token as a bearer header', async () => {
    const { auth } = createAuth('new');
    const { client, seenTokens } = setup(auth);

    const result = await client.GET('/api/v1/users/me');

    expect(result.response.status).toBe(200);
    expect(seenTokens).toEqual(['Bearer new']);
  });

  it('refreshes the session once and retries the request on 401', async () => {
    const { auth, refreshSession } = createAuth('old');
    const { client, fakeFetch, seenTokens } = setup(auth);

    const result = await client.GET('/api/v1/users/me');

    expect(result.response.status).toBe(200);
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(fakeFetch).toHaveBeenCalledTimes(2);
    expect(seenTokens).toEqual(['Bearer old', 'Bearer new']);
  });

  it('does not retry a second time when the retry is also unauthorized', async () => {
    const { auth, refreshSession } = createAuth('old');
    const { client, fakeFetch } = setup(auth, 'never-valid');

    const result = await client.GET('/api/v1/users/me');

    expect(result.response.status).toBe(401);
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(fakeFetch).toHaveBeenCalledTimes(2);
  });

  it('shares one refresh between concurrent unauthorized requests', async () => {
    const { auth, refreshSession } = createAuth('old');
    const { client } = setup(auth);

    const results = await Promise.all([
      client.GET('/api/v1/users/me'),
      client.GET('/api/v1/users/me'),
    ]);

    expect(results.map((result) => result.response.status)).toEqual([200, 200]);
    expect(refreshSession).toHaveBeenCalledTimes(1);
  });

  it('does not refresh when the sign-in request itself is unauthorized', async () => {
    const { auth, refreshSession } = createAuth(null);
    const { client, fakeFetch } = setup(auth);

    const result = await client.POST('/api/v1/auth/device', {
      body: { install_id: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001', device_secret: 's'.repeat(43) },
    });

    expect(result.response.status).toBe(401);
    expect(refreshSession).not.toHaveBeenCalled();
    expect(fakeFetch).toHaveBeenCalledTimes(1);
  });

  it('does not send the access token to the sign-in endpoint', async () => {
    const { auth } = createAuth('old');
    const { client, seenTokens } = setup(auth);

    await client.POST('/api/v1/auth/device', {
      body: { install_id: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001', device_secret: 's'.repeat(43) },
    });

    expect(seenTokens).toEqual([null]);
  });

  it('sends requests without a token when auth is not configured', async () => {
    const { client, fakeFetch, seenTokens } = setup(null);

    const result = await client.GET('/api/v1/users/me');

    expect(result.response.status).toBe(401);
    expect(seenTokens).toEqual([null]);
    expect(fakeFetch).toHaveBeenCalledTimes(1);
  });

  it('surfaces a failed refresh as an ApiError', async () => {
    const failure = new ApiError('invalid_device_credentials', 'Invalid', 401, null);
    const auth: ApiAuth = {
      getAccessToken: () => 'old',
      refreshSession: jest.fn(async () => {
        await Promise.resolve();
        throw failure;
      }),
    };
    const { client } = setup(auth);

    await expect(unwrap(client.GET('/api/v1/users/me'))).rejects.toBe(failure);
  });

  it('resends the same body when retrying a request that has one', async () => {
    const { auth } = createAuth('old');
    const { client, seenBodies } = setup(auth);

    const result = await client.PATCH('/api/v1/users/me', { body: { cefr_level: 'B2' } });

    expect(result.response.status).toBe(200);
    expect(seenBodies).toEqual(['{"cefr_level":"B2"}', '{"cefr_level":"B2"}']);
  });

  it('does not refresh again when the session was already refreshed after the request was sent', async () => {
    const { auth, refreshSession } = createAuth('old');
    let releaseStaleResponse: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      releaseStaleResponse = resolve;
    });
    const seenTokens: (string | null)[] = [];
    const fakeFetch = jest.fn(async (request: Request) => {
      const header = request.headers.get('Authorization');
      seenTokens.push(header);
      if (header === 'Bearer old') {
        await gate;
        return jsonResponse(401, { error: { code: 'token_expired', message: 'x' } });
      }
      return jsonResponse(200, USER_BODY);
    });
    const client = createClient<paths>({ baseUrl: 'http://api.test', fetch: fakeFetch });
    client.use(createAuthMiddleware(() => auth, fakeFetch));

    const staleRequest = client.GET('/api/v1/users/me');
    await auth.refreshSession();
    releaseStaleResponse();
    const result = await staleRequest;

    expect(result.response.status).toBe(200);
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(seenTokens).toEqual(['Bearer old', 'Bearer new']);
  });

  describe('when the runtime fetch returns its own Response class, as React Native does', () => {
    const RealResponse = Response;

    class RuntimeResponse extends RealResponse {}

    beforeEach(() => {
      globalThis.Response = RuntimeResponse;
    });

    afterEach(() => {
      globalThis.Response = RealResponse;
    });

    function setupRuntimeFetch(auth: ApiAuth) {
      const fakeFetch = jest.fn((request: Request) => {
        const authorized = request.headers.get('Authorization') === 'Bearer new';
        const response = authorized
          ? new RealResponse(JSON.stringify(USER_BODY), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            })
          : new RealResponse(JSON.stringify({ error: { code: 'token_expired', message: 'x' } }), {
              status: 401,
              headers: { 'Content-Type': 'application/json' },
            });
        return Promise.resolve(response);
      });
      const client = createClient<paths>({ baseUrl: 'http://api.test', fetch: fakeFetch });
      client.use(createAuthMiddleware(() => auth, fakeFetch));
      return client;
    }

    it('passes a successful response through untouched', async () => {
      const { auth } = createAuth('new');

      const result = await setupRuntimeFetch(auth).GET('/api/v1/users/me');

      expect(result.response.status).toBe(200);
      expect(result.data).toEqual(USER_BODY);
    });

    it('returns a standard Response for the retried request', async () => {
      const { auth } = createAuth('old');

      const result = await setupRuntimeFetch(auth).GET('/api/v1/users/me');

      expect(result.response.status).toBe(200);
      expect(result.data).toEqual(USER_BODY);
    });
  });
});
