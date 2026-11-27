import { getRandomBytes, randomUUID } from 'expo-crypto';

import { DEVICE_SECRET_BYTES } from '../config/device-credentials';
import type { DeviceCredentials } from '../model/device-credentials';

const BASE64_URL_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

export function toBase64Url(bytes: Uint8Array): string {
  let result = '';
  for (let index = 0; index < bytes.length; index += 3) {
    const first = bytes[index] ?? 0;
    const second = bytes[index + 1];
    const third = bytes[index + 2];
    const chunk = (first << 16) | ((second ?? 0) << 8) | (third ?? 0);
    result += BASE64_URL_ALPHABET.charAt((chunk >> 18) & 63);
    result += BASE64_URL_ALPHABET.charAt((chunk >> 12) & 63);
    if (second !== undefined) {
      result += BASE64_URL_ALPHABET.charAt((chunk >> 6) & 63);
    }
    if (third !== undefined) {
      result += BASE64_URL_ALPHABET.charAt(chunk & 63);
    }
  }
  return result;
}

export function generateDeviceCredentials(): DeviceCredentials {
  return {
    installId: randomUUID(),
    deviceSecret: toBase64Url(getRandomBytes(DEVICE_SECRET_BYTES)),
  };
}
