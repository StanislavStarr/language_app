import { ApiError, UNKNOWN_ERROR_CODE } from './api-error';
import { unwrap } from './unwrap';

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function failure<E>(error: E, status: number) {
  return Promise.resolve({ error, response: new Response(null, { status }) });
}

describe('unwrap', () => {
  it('returns the data of a successful response', async () => {
    await expect(unwrap(ok({ id: 'user-1' }))).resolves.toEqual({ id: 'user-1' });
  });

  it('throws an ApiError built from the backend error body', async () => {
    const body = { error: { code: 'rate_limited', message: 'Too many requests' } };

    const thrown = await unwrap(failure(body, 429)).catch((caught: unknown) => caught);

    expect(thrown).toBeInstanceOf(ApiError);
    expect(thrown).toMatchObject({ code: 'rate_limited', status: 429 });
  });

  it('throws an unknown ApiError for an HTML error page', async () => {
    const thrown = await unwrap(failure('<html>Bad Gateway</html>', 502)).catch(
      (caught: unknown) => caught,
    );

    expect(thrown).toMatchObject({ code: UNKNOWN_ERROR_CODE, status: 502 });
  });

  it('passes through an ApiError thrown by the request', async () => {
    const original = new ApiError('network_error', 'offline', null, null);

    await expect(unwrap(Promise.reject(original))).rejects.toBe(original);
  });
});
