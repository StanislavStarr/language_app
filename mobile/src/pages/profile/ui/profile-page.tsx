import { useCurrentUser } from '@/entities/user';
import { LoadingState } from '@/shared/ui';

import { ProfileForm } from './profile-form';

export function ProfilePage() {
  const { data: user } = useCurrentUser();

  if (user === undefined) {
    return <LoadingState />;
  }
  return <ProfileForm user={user} />;
}
