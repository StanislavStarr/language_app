import { OptionList } from '@/shared/ui';

import { CEFR_LEVEL_OPTIONS } from '../config/profile-options';
import type { CefrLevel } from '../model/types';

type Props = {
  value: CefrLevel;
  onChange: (level: CefrLevel) => void;
  disabled?: boolean;
};

export function CefrLevelPicker({ value, onChange, disabled }: Props) {
  return (
    <OptionList
      title="Ваш уровень английского"
      options={CEFR_LEVEL_OPTIONS}
      value={value}
      onChange={onChange}
      disabled={disabled}
    />
  );
}
