import { ApiError, NETWORK_ERROR_CODE } from './api-error';
import { isRetryableError, RETRY_DELAYS_MS, retryDelayMs, shouldRetryQuery } from './retry-policy';

const networkError = new ApiError(NETWORK_ERROR_CODE, 'offline', null, null);

function httpError(status: number): ApiError {
  return new ApiError('http_error', 'failure', status, null);
}

describe('retry policy', () => {
  it.each([502, 503, 504])('retries HTTP %i', (status) => {
    expect(shouldRetryQuery(0, httpError(status))).toBe(true);
  });

  it('retries network errors', () => {
    expect(shouldRetryQuery(0, networkError)).toBe(true);
  });

  it.each([400, 401, 404, 422, 429, 500])('does not retry HTTP %i', (status) => {
    expect(shouldRetryQuery(0, httpError(status))).toBe(false);
  });

  it('does not retry errors that are not ApiError', () => {
    expect(isRetryableError(new Error('boom'))).toBe(false);
  });

  it('stops retrying after the last delay', () => {
    expect(shouldRetryQuery(RETRY_DELAYS_MS.length - 1, networkError)).toBe(true);
    expect(shouldRetryQuery(RETRY_DELAYS_MS.length, networkError)).toBe(false);
  });

  it('waits about 90 seconds in total to cover a server cold start', () => {
    const total = RETRY_DELAYS_MS.reduce((sum, delay) => sum + delay, 0);

    expect(total).toBe(90_000);
  });

  it('backs off exponentially and caps the delay', () => {
    expect([0, 1, 2, 3, 4, 5].map(retryDelayMs)).toEqual([
      2_000, 4_000, 8_000, 16_000, 30_000, 30_000,
    ]);
    expect(retryDelayMs(99)).toBe(30_000);
  });
});
