import { getItemAsync, setItemAsync } from 'expo-secure-store';
import { z } from 'zod';

import {
  DEVICE_CREDENTIALS_STORAGE_KEY,
  DEVICE_SECRET_MAX_LENGTH,
  DEVICE_SECRET_MIN_LENGTH,
} from '../config/device-credentials';
import type { DeviceCredentials } from '../model/device-credentials';

const storedCredentialsSchema = z.object({
  installId: z.uuid(),
  deviceSecret: z.string().min(DEVICE_SECRET_MIN_LENGTH).max(DEVICE_SECRET_MAX_LENGTH),
});

export class StoredDeviceCredentialsInvalidError extends Error {
  constructor() {
    super('Stored device credentials are unreadable');
    this.name = 'StoredDeviceCredentialsInvalidError';
  }
}

export async function loadDeviceCredentials(): Promise<DeviceCredentials | null> {
  const raw = await getItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY);
  if (raw === null) {
    return null;
  }
  const parsed = storedCredentialsSchema.safeParse(parseJson(raw));
  if (!parsed.success) {
    throw new StoredDeviceCredentialsInvalidError();
  }
  return parsed.data;
}

export async function saveDeviceCredentials(credentials: DeviceCredentials): Promise<void> {
  await setItemAsync(DEVICE_CREDENTIALS_STORAGE_KEY, JSON.stringify(credentials));
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}
