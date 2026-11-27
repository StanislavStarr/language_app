import { z } from 'zod';

const envSchema = z.object({
  apiUrl: z.url(),
});

export type Env = z.infer<typeof envSchema>;

export function parseEnv(apiUrl: string | undefined): Env {
  const result = envSchema.safeParse({ apiUrl });
  if (!result.success) {
    throw new Error(
      'EXPO_PUBLIC_API_URL is missing or is not a valid URL. Set it in mobile/.env, e.g. http://192.168.1.10:8000',
    );
  }
  return result.data;
}

export const env = parseEnv(process.env.EXPO_PUBLIC_API_URL);
