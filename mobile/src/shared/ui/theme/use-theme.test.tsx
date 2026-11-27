import { renderHook } from '@testing-library/react-native';
import * as ReactNative from 'react-native';

import { COLORS } from './colors';
import { useTheme } from './use-theme';

describe('useTheme', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('returns the dark palette for the dark color scheme', async () => {
    jest.spyOn(ReactNative, 'useColorScheme').mockReturnValue('dark');

    const { result } = await renderHook(() => useTheme());

    expect(result.current.colors).toEqual(COLORS.dark);
  });

  it('falls back to the light palette when the scheme is unknown', async () => {
    jest.spyOn(ReactNative, 'useColorScheme').mockReturnValue(null);

    const { result } = await renderHook(() => useTheme());

    expect(result.current.colors).toEqual(COLORS.light);
  });
});
