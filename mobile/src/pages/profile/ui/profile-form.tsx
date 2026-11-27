import { AnswerLanguagePicker, CefrLevelPicker, type UserProfile } from '@/entities/user';
import { useUpdateProfile } from '@/features/update-profile';
import { getErrorMessage } from '@/shared/api';
import { AppText, FormError, Screen } from '@/shared/ui';

type Props = {
  user: UserProfile;
};

export function ProfileForm({ user }: Props) {
  const { mutate, isPending, error } = useUpdateProfile();

  return (
    <Screen scrollable>
      <AppText variant="title">Профиль</AppText>
      <CefrLevelPicker
        value={user.cefr_level}
        onChange={(cefrLevel) => {
          mutate({ cefr_level: cefrLevel });
        }}
        disabled={isPending}
      />
      <AnswerLanguagePicker
        value={user.answer_language}
        onChange={(answerLanguage) => {
          mutate({ answer_language: answerLanguage });
        }}
        disabled={isPending}
      />
      {error ? <FormError message={getErrorMessage(error)} /> : null}
    </Screen>
  );
}
