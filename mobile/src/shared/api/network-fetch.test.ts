import { ApiError, NETWORK_ERROR_CODE } from './api-error';
import { fetchOrThrowNetworkError } from './network-fetch';

describe('fetchOrThrowNetworkError', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('returns the response when fetch succeeds', async () => {
    const response = new Response('{}', { status: 200 });
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(response);

    await expect(fetchOrThrowNetworkError(new Request('http://api.test/x'))).resolves.toBe(
      response,
    );
  });

  it('turns a failed fetch into a network ApiError', async () => {
    jest.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Network request failed'));

    const thrown = await fetchOrThrowNetworkError(new Request('http://api.test/x')).catch(
      (caught: unknown) => caught,
    );

    expect(thrown).toBeInstanceOf(ApiError);
    expect(thrown).toMatchObject({ code: NETWORK_ERROR_CODE, message: 'Network request failed' });
  });
});
