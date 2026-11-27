import { z } from 'zod';

import { useSessionStore } from '@/entities/session';
import { ApiError } from '@/shared/api';

import { signInWithDevice } from './sign-in-with-device';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const postedCredentialsSchema = z.object({ install_id: z.string(), device_secret: z.string() });

type PostedCredentials = z.infer<typeof postedCredentialsSchema>;

async function postedCredentials(request: Request): Promise<PostedCredentials> {
  return postedCredentialsSchema.parse(JSON.parse(await request.clone().text()));
}

describe('signInWithDevice', () => {
  beforeEach(() => {
    useSessionStore.setState({ accessToken: null });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('creates credentials, signs in and keeps the token in memory', async () => {
    const posted: PostedCredentials[] = [];
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const request = new Request(input);
      posted.push(await postedCredentials(request));
      return jsonResponse(200, { access_token: 'token-1' });
    });

    await signInWithDevice();

    expect(useSessionStore.getState().accessToken).toBe('token-1');
    expect(posted).toHaveLength(1);
    expect(posted[0]?.device_secret).toHaveLength(43);
  });

  it('signs in with the same credentials after a restart', async () => {
    const posted: PostedCredentials[] = [];
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      posted.push(await postedCredentials(new Request(input)));
      return jsonResponse(200, { access_token: 'token-1' });
    });

    await signInWithDevice();
    useSessionStore.setState({ accessToken: null });
    await signInWithDevice();

    expect(posted).toHaveLength(2);
    expect(posted[1]).toEqual(posted[0]);
  });

  it('rejects with an ApiError and keeps no token when the backend refuses the device', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        jsonResponse(401, { error: { code: 'invalid_device_credentials', message: 'Invalid' } }),
      );

    await expect(signInWithDevice()).rejects.toMatchObject({
      code: 'invalid_device_credentials',
      status: 401,
    });
    await expect(signInWithDevice()).rejects.toBeInstanceOf(ApiError);
    expect(useSessionStore.getState().accessToken).toBeNull();
  });
});
