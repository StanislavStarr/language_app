import { toApiError } from './api-error';

const ERROR_MESSAGES = {
  network_error: 'Нет связи с сервером. Проверьте подключение к интернету.',
  unknown_error: 'Что-то пошло не так. Попробуйте ещё раз.',
  validation_error: 'Проверьте введённые данные.',
  not_found: 'Ничего не найдено.',
  method_not_allowed: 'Это действие недоступно.',
  http_error: 'Сервер не смог обработать запрос.',
  internal_error: 'Ошибка на сервере. Попробуйте позже.',
  database_unavailable: 'Сервер временно недоступен. Попробуйте через минуту.',
  invalid_device_credentials: 'Не удалось войти на этом устройстве.',
  token_missing: 'Нужно войти заново.',
  token_invalid: 'Нужно войти заново.',
  token_expired: 'Сессия истекла. Входим заново…',
  language_not_found: 'Язык не найден.',
  usage_limit_exceeded: 'Достигнут дневной лимит. Попробуйте завтра.',
  rate_limited: 'Слишком много запросов. Подождите немного.',
} as const;

type KnownErrorCode = keyof typeof ERROR_MESSAGES;

function isKnownErrorCode(code: string): code is KnownErrorCode {
  return Object.hasOwn(ERROR_MESSAGES, code);
}

export function getErrorMessage(error: unknown): string {
  const { code } = toApiError(error);
  return isKnownErrorCode(code) ? ERROR_MESSAGES[code] : ERROR_MESSAGES.unknown_error;
}
