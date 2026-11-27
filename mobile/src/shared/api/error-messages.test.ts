import { ApiError, NETWORK_ERROR_CODE } from './api-error';
import { getErrorMessage } from './error-messages';

describe('getErrorMessage', () => {
  it('returns a specific Russian text for a known backend code', () => {
    const error = new ApiError('rate_limited', 'Too many requests', 429, null);

    expect(getErrorMessage(error)).toBe('Слишком много запросов. Подождите немного.');
  });

  it('returns a text for network failures', () => {
    const error = new ApiError(NETWORK_ERROR_CODE, 'offline', null, null);

    expect(getErrorMessage(error)).toContain('Нет связи с сервером');
  });

  it('falls back to the generic text for an unknown code', () => {
    const error = new ApiError('brand_new_code', 'x', 400, null);

    expect(getErrorMessage(error)).toBe('Что-то пошло не так. Попробуйте ещё раз.');
  });

  it('never shows the technical message of the backend', () => {
    const error = new ApiError('internal_error', 'Traceback: secret details', 500, null);

    expect(getErrorMessage(error)).not.toContain('Traceback');
  });

  it('handles values that are not ApiError', () => {
    expect(getErrorMessage(new Error('boom'))).toBe('Что-то пошло не так. Попробуйте ещё раз.');
  });

  it.each([
    'validation_error',
    'not_found',
    'method_not_allowed',
    'http_error',
    'internal_error',
    'database_unavailable',
    'invalid_device_credentials',
    'token_missing',
    'token_invalid',
    'token_expired',
    'language_not_found',
    'usage_limit_exceeded',
    'rate_limited',
  ])('has a dedicated text for the documented backend code %s', (code) => {
    const specific = getErrorMessage(new ApiError(code, 'x', 400, null));

    expect(specific).not.toBe(getErrorMessage(new ApiError('unlisted_code', 'x', 400, null)));
  });
});
