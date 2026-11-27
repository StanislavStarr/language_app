export type ColorScheme = 'light' | 'dark';

export type Colors = {
  background: string;
  surface: string;
  border: string;
  text: string;
  textMuted: string;
  primary: string;
  onPrimary: string;
  danger: string;
};

export const COLORS: Record<ColorScheme, Colors> = {
  light: {
    background: '#FFFFFF',
    surface: '#F3F4F6',
    border: '#D1D5DB',
    text: '#111827',
    textMuted: '#6B7280',
    primary: '#2563EB',
    onPrimary: '#FFFFFF',
    danger: '#DC2626',
  },
  dark: {
    background: '#0B0F19',
    surface: '#161B26',
    border: '#374151',
    text: '#F9FAFB',
    textMuted: '#9CA3AF',
    primary: '#60A5FA',
    onPrimary: '#0B0F19',
    danger: '#F87171',
  },
};
