process.env.EXPO_PUBLIC_API_URL = 'http://localhost:8000';

const mockSecureStore = new Map<string, string>();
let mockRandomCounter = 0;

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn((key: string) => Promise.resolve(mockSecureStore.get(key) ?? null)),
  setItemAsync: jest.fn((key: string, value: string) => {
    mockSecureStore.set(key, value);
    return Promise.resolve();
  }),
  deleteItemAsync: jest.fn((key: string) => {
    mockSecureStore.delete(key);
    return Promise.resolve();
  }),
}));

jest.mock('expo-crypto', () => ({
  randomUUID: jest.fn(() => {
    mockRandomCounter += 1;
    return `00000000-0000-4000-8000-${String(mockRandomCounter).padStart(12, '0')}`;
  }),
  getRandomBytes: jest.fn((length: number) =>
    Uint8Array.from({ length }, (_, index) => (index * 7 + mockRandomCounter * 13 + 200) % 256),
  ),
}));

jest.mock('@/shared/api/report-unexpected-error', () => ({
  reportUnexpectedError: jest.fn(),
}));

jest.mock('expo-splash-screen', () => ({
  preventAutoHideAsync: jest.fn(() => Promise.resolve(true)),
  hideAsync: jest.fn(() => Promise.resolve()),
}));

beforeEach(() => {
  mockSecureStore.clear();
});
