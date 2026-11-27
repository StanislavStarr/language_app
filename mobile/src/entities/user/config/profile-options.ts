import type { Option } from '@/shared/ui';

import type { AnswerLanguage, CefrLevel } from '../model/types';

const CEFR_LEVEL_DESCRIPTIONS: Record<CefrLevel, { title: string; hint: string }> = {
  A1: { title: 'Начальный', hint: 'Знаю базовые слова и фразы' },
  A2: { title: 'Элементарный', hint: 'Понимаю простые тексты' },
  B1: { title: 'Средний', hint: 'Читаю несложные книги со словарём' },
  B2: { title: 'Выше среднего', hint: 'Свободно читаю большинство текстов' },
  C1: { title: 'Продвинутый', hint: 'Понимаю сложные тексты и нюансы' },
  C2: { title: 'В совершенстве', hint: 'Владею языком почти как носитель' },
};

const CEFR_LEVELS_IN_ORDER: readonly CefrLevel[] = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

export const CEFR_LEVEL_OPTIONS: readonly Option<CefrLevel>[] = CEFR_LEVELS_IN_ORDER.map(
  (level) => ({
    value: level,
    label: `${level} — ${CEFR_LEVEL_DESCRIPTIONS[level].title}`,
    hint: CEFR_LEVEL_DESCRIPTIONS[level].hint,
  }),
);

export const ANSWER_LANGUAGE_OPTIONS: readonly Option<AnswerLanguage>[] = [
  {
    value: 'en_simple',
    label: 'Простой английский',
    hint: 'Ответы подстраиваются под ваш уровень',
  },
  { value: 'ru', label: 'Русский' },
];
