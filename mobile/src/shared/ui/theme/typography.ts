export type TextVariant = 'title' | 'body' | 'caption';

type TextStyleToken = {
  fontSize: number;
  lineHeight: number;
  fontWeight: '400' | '600' | '700';
};

export const TYPOGRAPHY: Record<TextVariant, TextStyleToken> = {
  title: { fontSize: 24, lineHeight: 32, fontWeight: '700' },
  body: { fontSize: 16, lineHeight: 24, fontWeight: '400' },
  caption: { fontSize: 13, lineHeight: 18, fontWeight: '400' },
};
