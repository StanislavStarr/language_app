import createClient from 'openapi-fetch';

import { env } from '@/shared/config';

import { type ApiAuth, createAuthMiddleware } from './auth-middleware';
import { fetchOrThrowNetworkError } from './network-fetch';
import type { paths } from './schema';

let configuredAuth: ApiAuth | null = null;

export function configureApiAuth(auth: ApiAuth): void {
  configuredAuth = auth;
}

export const apiClient = createClient<paths>({
  baseUrl: env.apiUrl,
  fetch: fetchOrThrowNetworkError,
});
apiClient.use(createAuthMiddleware(() => configuredAuth));
