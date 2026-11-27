import { setItemAsync } from 'expo-secure-store';

import { DEVICE_CREDENTIALS_STORAGE_KEY } from '../config/device-credentials';
import { loadOrCreateDeviceCredentials } from './load-or-create-device-credentials';

describe('loadOrCreateDeviceCredentials', () => {
  it('creates credentials on first launch and reuses them afterwards', async () => {
    const first = await loadOrCreateDeviceCredentials();
    const second = await loadOrCreateDeviceCredentials();

    expect(second).toEqual(first);
  });

  it('creates a single set of credentials for concurrent callers', async () => {
    const [first, second] = await Promise.all([
      loadOrCreateDeviceCredentials(),
      loadOrCreateDeviceCredentials(),
    ]);

    expect(second).toEqual(first);
    await expect(loadOrCreateDeviceCredentials()).resolves.toEqual(first);
  });

  it('does not create a new account when the stored credentials are unreadable', async () => {
    await setItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY, 'garbage');

    await expect(loadOrCreateDeviceCredentials()).rejects.toThrow('unreadable');
    await expect(loadOrCreateDeviceCredentials()).rejects.toThrow('unreadable');
  });
});
