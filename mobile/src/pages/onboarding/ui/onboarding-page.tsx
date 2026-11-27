import { useCurrentUser } from '@/entities/user';
import { LoadingState } from '@/shared/ui';

import { OnboardingForm } from './onboarding-form';

export function OnboardingPage() {
  const { data: user } = useCurrentUser();

  if (user === undefined) {
    return <LoadingState />;
  }
  return <OnboardingForm user={user} />;
}
