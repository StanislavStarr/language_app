import { getItemAsync, setItemAsync } from 'expo-secure-store';

import { DEVICE_CREDENTIALS_STORAGE_KEY } from '../config/device-credentials';
import {
  loadDeviceCredentials,
  saveDeviceCredentials,
  StoredDeviceCredentialsInvalidError,
} from './device-credentials-storage';

const CREDENTIALS = {
  installId: '5b1b9d52-7a6e-4c6a-a7d4-1f1b8b8a0001',
  deviceSecret: 's'.repeat(43),
};

describe('device credentials storage', () => {
  it('returns null when nothing is stored', async () => {
    await expect(loadDeviceCredentials()).resolves.toBeNull();
  });

  it('reads back what was saved', async () => {
    await saveDeviceCredentials(CREDENTIALS);

    await expect(loadDeviceCredentials()).resolves.toEqual(CREDENTIALS);
  });

  it('refuses to guess when the stored value is not valid JSON', async () => {
    await setItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY, 'not json');

    await expect(loadDeviceCredentials()).rejects.toBeInstanceOf(
      StoredDeviceCredentialsInvalidError,
    );
    await expect(getItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY)).resolves.toBe('not json');
  });

  it('keeps stored credentials that fail validation instead of replacing the account', async () => {
    const invalid = JSON.stringify({ installId: 'not-a-uuid', deviceSecret: 'short' });
    await setItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY, invalid);

    await expect(loadDeviceCredentials()).rejects.toBeInstanceOf(
      StoredDeviceCredentialsInvalidError,
    );
    await expect(getItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY)).resolves.toBe(invalid);
  });
});
