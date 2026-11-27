import { useMutation, useQueryClient } from '@tanstack/react-query';

import { userKeys } from '@/entities/user';
import { apiClient, type components, unwrap } from '@/shared/api';

type UserUpdate = components['schemas']['UserUpdate'];

export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (update: UserUpdate) =>
      unwrap(apiClient.PATCH('/api/v1/users/me', { body: update })),
    onSuccess: (user) => {
      queryClient.setQueryData(userKeys.me(), user);
    },
  });
}
