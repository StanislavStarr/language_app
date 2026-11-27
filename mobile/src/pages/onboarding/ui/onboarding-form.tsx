import { useState } from 'react';

import {
  type AnswerLanguage,
  AnswerLanguagePicker,
  type CefrLevel,
  CefrLevelPicker,
  type UserProfile,
} from '@/entities/user';
import { useUpdateProfile } from '@/features/update-profile';
import { getErrorMessage } from '@/shared/api';
import { AppText, Button, FormError, Screen } from '@/shared/ui';

import {
  DEVICE_BINDING_WARNING,
  LEARNING_LANGUAGE_LINE,
  NATIVE_LANGUAGE_LINE,
  ONBOARDING_SUBTITLE,
  ONBOARDING_TITLE,
  OPENAI_NOTICE,
  START_LABEL,
} from '../config/copy';

type Props = {
  user: UserProfile;
};

export function OnboardingForm({ user }: Props) {
  const [cefrLevel, setCefrLevel] = useState<CefrLevel>(user.cefr_level);
  const [answerLanguage, setAnswerLanguage] = useState<AnswerLanguage>(user.answer_language);
  const { mutate, isPending, error } = useUpdateProfile();

  const start = () => {
    mutate({
      cefr_level: cefrLevel,
      answer_language: answerLanguage,
      complete_onboarding: true,
    });
  };

  return (
    <Screen scrollable>
      <AppText variant="title">{ONBOARDING_TITLE}</AppText>
      <AppText tone="muted">{ONBOARDING_SUBTITLE}</AppText>
      <AppText>{NATIVE_LANGUAGE_LINE}</AppText>
      <AppText>{LEARNING_LANGUAGE_LINE}</AppText>
      <CefrLevelPicker value={cefrLevel} onChange={setCefrLevel} disabled={isPending} />
      <AnswerLanguagePicker
        value={answerLanguage}
        onChange={setAnswerLanguage}
        disabled={isPending}
      />
      <AppText variant="caption" tone="muted">
        {DEVICE_BINDING_WARNING}
      </AppText>
      <AppText variant="caption" tone="muted">
        {OPENAI_NOTICE}
      </AppText>
      {error ? <FormError message={getErrorMessage(error)} /> : null}
      <Button label={START_LABEL} onPress={start} loading={isPending} />
    </Screen>
  );
}
