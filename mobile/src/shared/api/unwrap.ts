import { ApiError, toApiError, UNKNOWN_ERROR_CODE } from './api-error';
import { reportUnexpectedError } from './report-unexpected-error';

type ClientResult = { data?: unknown; error?: unknown; response: Response };
type SuccessOf<R extends ClientResult> = Extract<R, { error?: never }>;

function isSuccess<R extends ClientResult>(result: R): result is SuccessOf<R> {
  return result.error === undefined;
}

export async function unwrap<R extends ClientResult>(
  request: Promise<R>,
): Promise<SuccessOf<R>['data']> {
  let result: R;
  try {
    result = await request;
  } catch (caught) {
    const apiError = toApiError(caught);
    if (!(caught instanceof ApiError)) {
      reportUnexpectedError('request threw', caught);
    }
    throw apiError;
  }
  if (!isSuccess(result)) {
    const apiError = toApiError(result.error, result.response.status);
    if (apiError.code === UNKNOWN_ERROR_CODE) {
      reportUnexpectedError(`unexpected response (HTTP ${result.response.status})`, result.error);
    }
    throw apiError;
  }
  return result.data;
}
