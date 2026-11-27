import { toApiError } from './api-error';

type SuccessResult<T> = { data: T; error?: undefined; response: Response };
type FailureResult<E> = { data?: undefined; error: E; response: Response };
type ClientResult<T, E> = SuccessResult<T> | FailureResult<E>;

function isFailure<T, E>(result: ClientResult<T, E>): result is FailureResult<E> {
  return result.error !== undefined;
}

export async function unwrap<T, E>(request: Promise<ClientResult<T, E>>): Promise<T> {
  let result: ClientResult<T, E>;
  try {
    result = await request;
  } catch (caught) {
    throw toApiError(caught);
  }
  if (isFailure(result)) {
    throw toApiError(result.error, result.response.status);
  }
  return result.data;
}
