import { parseEnv } from './env';

describe('parseEnv', () => {
  it('returns the API url when valid', () => {
    expect(parseEnv('http://192.168.1.10:8000')).toEqual({ apiUrl: 'http://192.168.1.10:8000' });
  });

  it('throws when the API url is missing', () => {
    expect(() => parseEnv(undefined)).toThrow('EXPO_PUBLIC_API_URL');
  });

  it('throws when the API url is not a URL', () => {
    expect(() => parseEnv('not a url')).toThrow('EXPO_PUBLIC_API_URL');
  });
});
