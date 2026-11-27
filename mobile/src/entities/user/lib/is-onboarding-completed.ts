import type { UserProfile } from '../model/types';

export function isOnboardingCompleted(user: UserProfile): boolean {
  return user.onboarding_completed_at !== null;
}
