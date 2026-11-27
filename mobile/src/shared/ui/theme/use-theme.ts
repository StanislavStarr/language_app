import { useColorScheme } from 'react-native';

import { COLORS, type Colors } from './colors';
import { RADII } from './radii';
import { SPACING } from './spacing';
import { TYPOGRAPHY } from './typography';

export type Theme = {
  colors: Colors;
  spacing: typeof SPACING;
  radii: typeof RADII;
  typography: typeof TYPOGRAPHY;
};

export function useTheme(): Theme {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  return { colors: COLORS[scheme], spacing: SPACING, radii: RADII, typography: TYPOGRAPHY };
}
