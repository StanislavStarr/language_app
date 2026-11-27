import { ANSWER_LANGUAGE_OPTIONS, CEFR_LEVEL_OPTIONS } from './profile-options';

describe('profile options', () => {
  it('offers all six CEFR levels in ascending order', () => {
    expect(CEFR_LEVEL_OPTIONS.map((option) => option.value)).toEqual([
      'A1',
      'A2',
      'B1',
      'B2',
      'C1',
      'C2',
    ]);
  });

  it('labels every level with its code and a Russian caption', () => {
    expect(CEFR_LEVEL_OPTIONS[3]?.label).toBe('B2 — Выше среднего');
  });

  it('offers simple English and Russian as answer languages', () => {
    expect(ANSWER_LANGUAGE_OPTIONS.map((option) => option.value)).toEqual(['en_simple', 'ru']);
  });
});
