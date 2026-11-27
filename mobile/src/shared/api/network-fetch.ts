import { ApiError, NETWORK_ERROR_CODE } from './api-error';

export async function fetchOrThrowNetworkError(request: Request): Promise<Response> {
  try {
    return await fetch(request);
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : 'Network request failed';
    if (__DEV__) {
      const { origin, pathname } = new URL(request.url);
      console.warn(`[api] ${request.method} ${origin}${pathname} failed: ${message}`);
    }
    throw new ApiError(NETWORK_ERROR_CODE, message, null, null);
  }
}
