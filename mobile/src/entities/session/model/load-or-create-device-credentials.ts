import { loadDeviceCredentials, saveDeviceCredentials } from '../api/device-credentials-storage';
import { generateDeviceCredentials } from '../lib/generate-device-credentials';
import type { DeviceCredentials } from './device-credentials';

let inFlight: Promise<DeviceCredentials> | null = null;

async function loadOrCreate(): Promise<DeviceCredentials> {
  const stored = await loadDeviceCredentials();
  if (stored !== null) {
    return stored;
  }
  const created = generateDeviceCredentials();
  await saveDeviceCredentials(created);
  return created;
}

export function loadOrCreateDeviceCredentials(): Promise<DeviceCredentials> {
  inFlight ??= loadOrCreate().finally(() => {
    inFlight = null;
  });
  return inFlight;
}
