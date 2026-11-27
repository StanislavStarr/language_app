import { z } from 'zod';

export const NETWORK_ERROR_CODE = 'network_error';
export const UNKNOWN_ERROR_CODE = 'unknown_error';

const backendErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).nullish(),
  }),
});

type ApiErrorDetails = Record<string, unknown>;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly details: ApiErrorDetails | null;

  constructor(
    code: string,
    message: string,
    status: number | null,
    details: ApiErrorDetails | null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function toApiError(error: unknown, status?: number): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (status !== undefined) {
    return responseBodyToApiError(error, status);
  }
  const message = error instanceof Error ? error.message : 'Unexpected error';
  return new ApiError(UNKNOWN_ERROR_CODE, message, null, null);
}

function responseBodyToApiError(body: unknown, status: number): ApiError {
  const parsed = backendErrorSchema.safeParse(body);
  if (!parsed.success) {
    return new ApiError(UNKNOWN_ERROR_CODE, `Unexpected response (HTTP ${status})`, status, null);
  }
  const { code, message, details } = parsed.data.error;
  return new ApiError(code, message, status, details ?? null);
}
