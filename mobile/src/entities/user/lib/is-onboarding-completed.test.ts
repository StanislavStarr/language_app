import type { UserProfile } from '../model/types';
import { isOnboardingCompleted } from './is-onboarding-completed';

const USER: UserProfile = {
  id: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001',
  native_language_id: 1,
  learning_language_id: 2,
  cefr_level: 'A1',
  answer_language: 'en_simple',
  onboarding_completed_at: null,
};

describe('isOnboardingCompleted', () => {
  it('is false until the backend stores the completion time', () => {
    expect(isOnboardingCompleted(USER)).toBe(false);
  });

  it('is true once the completion time is set', () => {
    expect(
      isOnboardingCompleted({ ...USER, onboarding_completed_at: '2026-11-27T10:00:00Z' }),
    ).toBe(true);
  });
});
