const MAX_DETAILS_LENGTH = 300;
const MAX_STACK_LINES = 6;

function describe(details: unknown): string {
  if (details instanceof Error) {
    const stack = details.stack?.split('\n').slice(0, MAX_STACK_LINES).join('\n') ?? '';
    return `${details.name}: ${details.message}\n${stack}`;
  }
  const serialized = typeof details === 'string' ? details : JSON.stringify(details);
  return (serialized ?? String(details)).slice(0, MAX_DETAILS_LENGTH);
}

export function reportUnexpectedError(context: string, details: unknown): void {
  if (__DEV__) {
    console.warn(`[api] ${context}: ${describe(details)}`);
  }
}
