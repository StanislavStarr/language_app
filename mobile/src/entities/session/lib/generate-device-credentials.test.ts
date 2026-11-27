import { DEVICE_SECRET_MAX_LENGTH, DEVICE_SECRET_MIN_LENGTH } from '../config/device-credentials';
import { generateDeviceCredentials, toBase64Url } from './generate-device-credentials';

describe('toBase64Url', () => {
  it('encodes bytes like base64url without padding', () => {
    expect(toBase64Url(Uint8Array.from([]))).toBe('');
    expect(toBase64Url(Uint8Array.from([0x66]))).toBe('Zg');
    expect(toBase64Url(Uint8Array.from([0x66, 0x6f]))).toBe('Zm8');
    expect(toBase64Url(Uint8Array.from([0x66, 0x6f, 0x6f]))).toBe('Zm9v');
  });

  it('uses the URL-safe alphabet', () => {
    expect(toBase64Url(Uint8Array.from([0xfb, 0xff, 0xfe]))).toBe('-__-');
  });
});

describe('generateDeviceCredentials', () => {
  it('creates a uuid install id and a URL-safe secret of the length the backend accepts', () => {
    const { installId, deviceSecret } = generateDeviceCredentials();

    expect(installId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(deviceSecret).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(deviceSecret.length).toBeGreaterThanOrEqual(DEVICE_SECRET_MIN_LENGTH);
    expect(deviceSecret.length).toBeLessThanOrEqual(DEVICE_SECRET_MAX_LENGTH);
  });

  it('creates different credentials on every call', () => {
    expect(generateDeviceCredentials()).not.toEqual(generateDeviceCredentials());
  });
});
