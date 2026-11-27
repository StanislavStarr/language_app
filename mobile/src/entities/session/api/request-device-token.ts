import { apiClient, unwrap } from '@/shared/api';

import type { DeviceCredentials } from '../model/device-credentials';

export async function requestDeviceToken(credentials: DeviceCredentials): Promise<string> {
  const response = await unwrap(
    apiClient.POST('/api/v1/auth/device', {
      body: { install_id: credentials.installId, device_secret: credentials.deviceSecret },
    }),
  );
  return response.access_token;
}
