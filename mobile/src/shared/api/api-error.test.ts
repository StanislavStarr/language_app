import { ApiError, toApiError, UNKNOWN_ERROR_CODE } from './api-error';

describe('toApiError', () => {
  it('maps the backend error format', () => {
    const body = {
      error: {
        code: 'usage_limit_exceeded',
        message: 'Daily usage limit exceeded',
        details: { kind: 'ai_lookup', limit: 100 },
      },
    };

    const error = toApiError(body, 429);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe('usage_limit_exceeded');
    expect(error.message).toBe('Daily usage limit exceeded');
    expect(error.status).toBe(429);
    expect(error.details).toEqual({ kind: 'ai_lookup', limit: 100 });
  });

  it('uses null details when the backend sends none', () => {
    const error = toApiError({ error: { code: 'not_found', message: 'Not Found' } }, 404);

    expect(error.details).toBeNull();
  });

  it('maps an HTML proxy page to an unknown error keeping the status', () => {
    const error = toApiError('<html>Bad Gateway</html>', 502);

    expect(error.code).toBe(UNKNOWN_ERROR_CODE);
    expect(error.status).toBe(502);
  });

  it('maps an empty or malformed body to an unknown error', () => {
    expect(toApiError(undefined, 500).code).toBe(UNKNOWN_ERROR_CODE);
    expect(toApiError({ error: { code: 1 } }, 500).code).toBe(UNKNOWN_ERROR_CODE);
  });

  it('does not mistake programming errors for network failures', () => {
    expect(toApiError(new TypeError('undefined is not a function')).code).toBe(UNKNOWN_ERROR_CODE);
  });

  it('maps unexpected thrown values to an unknown error', () => {
    expect(toApiError(new Error('boom')).code).toBe(UNKNOWN_ERROR_CODE);
    expect(toApiError('weird').code).toBe(UNKNOWN_ERROR_CODE);
  });

  it('returns an existing ApiError unchanged', () => {
    const original = new ApiError('token_expired', 'Expired', 401, null);

    expect(toApiError(original)).toBe(original);
  });
});
