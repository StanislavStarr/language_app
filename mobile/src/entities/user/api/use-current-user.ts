import { useQuery } from '@tanstack/react-query';

import { apiClient, unwrap } from '@/shared/api';

import { userKeys } from './query-keys';

export function useCurrentUser() {
  return useQuery({
    queryKey: userKeys.me(),
    queryFn: () => unwrap(apiClient.GET('/api/v1/users/me')),
    staleTime: Infinity,
  });
}
