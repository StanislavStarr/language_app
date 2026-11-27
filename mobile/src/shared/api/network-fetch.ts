import { ApiError, NETWORK_ERROR_CODE } from './api-error';

export async function fetchOrThrowNetworkError(request: Request): Promise<Response> {
  try {
    return await fetch(request);
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : 'Network request failed';
    throw new ApiError(NETWORK_ERROR_CODE, message, null, null);
  }
}
