import { OptionList } from '@/shared/ui';

import { ANSWER_LANGUAGE_OPTIONS } from '../config/profile-options';
import type { AnswerLanguage } from '../model/types';

type Props = {
  value: AnswerLanguage;
  onChange: (language: AnswerLanguage) => void;
  disabled?: boolean;
};

export function AnswerLanguagePicker({ value, onChange, disabled }: Props) {
  return (
    <OptionList
      title="Язык ответов «Спроси книгу»"
      options={ANSWER_LANGUAGE_OPTIONS}
      value={value}
      onChange={onChange}
      disabled={disabled}
    />
  );
}
