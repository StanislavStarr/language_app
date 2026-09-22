# Ликбез: Angular 22

Читать перед шагом 19. Здесь объясняется современный Angular — тот, который вы получите командой
`ng new` в версии 22. Это важная оговорка: большинство статей и ответов в интернете описывают Angular
версий 8–16, где почти всё делалось иначе. Если найденный в поиске пример содержит `NgModule`,
`@Input()`, `*ngIf` или `constructor(private http: HttpClient)` — это устаревший стиль, и в нашем
проекте он не применяется.

---

## 1. Что изменилось в Angular 22 и почему это важно

Версия 22 поменяла несколько значений по умолчанию. Это влияет на то, как вы пишете код с первого дня.

| Что | Как было | Как в 22 |
| --- | --- | --- |
| Стратегия обнаружения изменений | `Default` (проверять всё) | **`OnPush`** по умолчанию; старое поведение переименовано в `Eager` |
| zone.js | подключался всегда | **zoneless** по умолчанию для новых приложений |
| Тест-раннер | Karma | **Vitest**; Karma, Jest и Web Test Runner удалены |
| `resource()`, `httpResource()`, Signal Forms | экспериментальные | стабильные |
| Суффиксы в именах файлов | `word-card.component.ts` | `word-card.ts` |
| Модули | `NgModule` | standalone-компоненты |

Практическое следствие пары «OnPush + zoneless»: Angular перерисовывает компонент, когда изменился
**сигнал, прочитанный в его шаблоне**, изменился входной параметр, или сработал обработчик события.
Если вы положите состояние в обычное поле класса и измените его из колбэка `setTimeout`, шаблон не
обновится. Поэтому в этом проекте состояние компонента живёт в сигналах — не «потому что модно»,
а потому что иначе UI не будет реагировать.

Последняя строка таблицы совпадает с правилом проекта об именах файлов, так что генератор CLI будет
создавать файлы уже в нужном виде.

---

## 2. Standalone-компонент

Компонент — класс с декоратором. Модули больше не нужны.

`word-card.ts`:

```typescript
import { Component, input, output } from '@angular/core';
import { VocabularyItemSummary } from '../models/vocabulary-item-summary';

@Component({
  selector: 'app-word-card',
  templateUrl: './word-card.html',
  styleUrl: './word-card.scss',
})
export class WordCard {
  readonly item = input.required<VocabularyItemSummary>();
  readonly opened = output<string>();

  protected open(): void {
    this.opened.emit(this.item().id);
  }
}
```

`word-card.html`:

```html
<button class="word-card" type="button" (click)="open()">
  <span class="word-card__text">{{ item().text }}</span>
  <span class="word-card__translation">{{ item().translation }}</span>

  @if (item().enrichmentStatus === 'PENDING') {
    <span class="word-card__status">Подготавливаем карточку…</span>
  }
</button>
```

Что здесь принципиально:

* `input.required<T>()` — входной параметр, сигнал. В шаблоне читается **с вызовом**: `item()`.
  `required` означает, что родитель обязан передать значение, иначе будет ошибка. Для необязательного:
  `input<string | null>(null)`;
* `output<T>()` — исходящее событие, замена `@Output() new EventEmitter()`;
* `protected` у метода — он нужен только шаблону, не внешнему коду. Правило проекта требует такой
  маркировки;
* `@if` — встроенный синтаксис управления потоком. Не требует импорта `CommonModule`, в отличие от
  старого `*ngIf`;
* три файла с одним базовым именем: `word-card.ts`, `word-card.html`, `word-card.scss`. Стили только
  в отдельном файле — правила проекта запрещают инлайновые стили и `style=""`.

Полный набор синтаксиса шаблонов, который нужен в проекте:

```html
@if (loading()) {
  <app-spinner />
} @else if (error()) {
  <p class="error">{{ error() }}</p>
} @else {
  <ul>
    @for (item of items(); track item.id) {
      <li>{{ item.text }}</li>
    } @empty {
      <li class="empty">Пока нет слов</li>
    }
  </ul>
}

@switch (stage()) {
  @case ('INTRODUCTION') { <app-study-introduction /> }
  @case ('MATCHING') { <app-study-matching /> }
  @default { <app-study-summary /> }
}
```

`track item.id` обязателен в `@for`. Он говорит Angular, как сопоставлять элементы между
перерисовками. Без корректного `track` список будет пересоздаваться целиком, а поля ввода — терять
фокус и содержимое.

---

## 3. Сигналы

Сигнал — значение-контейнер, который умеет сообщать о своём изменении. Читается вызовом, меняется
методом.

```typescript
import { computed, signal } from '@angular/core';

const attempts = signal(0);
attempts();                      // чтение: 0
attempts.set(1);                 // установка
attempts.update((n) => n + 1);   // изменение относительно текущего
```

`computed` — производное значение. Пересчитывается автоматически и только при обращении:

```typescript
const items = signal<StudySessionItem[]>([]);
const currentIndex = signal(0);

const currentItem = computed(() => items()[currentIndex()] ?? null);
const isLastItem = computed(() => currentIndex() === items().length - 1);
```

Правило, которое сильно упрощает жизнь: **всё производное — через `computed`, никогда не дублируется
в отдельный сигнал**. Если у вас есть `items` и рядом `itemsCount`, который вы обновляете вручную, они
однажды разойдутся.

Массивы и объекты в сигналах заменяются целиком, а не мутируются:

```typescript
selectedIds.update((ids) => [...ids, newId]);   // правильно
selectedIds().push(newId);                      // не вызовет обновление шаблона
```

`effect` — для настоящих побочных эффектов (запись в `localStorage`, логирование). Не для вычислений:

```typescript
effect(() => {
  const session = this.session();
  if (session) {
    localStorage.setItem('activeSessionId', session.id);
  }
});
```

Если вы пишете `effect`, который вычисляет значение и кладёт его в другой сигнал — почти наверняка
нужен `computed` или `linkedSignal`.

---

## 4. Внедрение зависимостей через `inject()`

Сервис — класс с декоратором `@Injectable`:

```typescript
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class VocabularyApi {
  // ...
}
```

`providedIn: 'root'` означает единственный экземпляр на приложение.

Получение зависимости — функцией `inject()` в поле класса:

```typescript
import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';

@Component({ /* ... */ })
export class CollectionsPage {
  private readonly vocabularyApi = inject(VocabularyApi);
  private readonly router = inject(Router);
}
```

Правило проекта: для нового кода используем `inject()`, а не параметры конструктора. Это короче,
работает в функциях-хелперах и не требует декораторов параметров. `readonly` — потому что
зависимость не переназначается.

---

## 5. HTTP: слой API

Главное правило проекта: `HttpClient` вызывается только в сервисах слоя API. Компонент не знает
ни одного URL.

Подключение в `app.config.ts`:

```typescript
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth-interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
  ],
};
```

В Angular 22 `HttpClient` использует `fetch` по умолчанию, отдельный `withFetch()` не нужен.

Сервис API:

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { VocabularyItemDetail } from './models/vocabulary-item-detail';
import { VocabularyItemSummary } from './models/vocabulary-item-summary';

@Injectable({ providedIn: 'root' })
export class VocabularyApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/vocabulary`;

  listItems(collectionId?: string): Observable<VocabularyItemSummary[]> {
    const params = collectionId ? { collection_id: collectionId } : {};
    return this.http.get<VocabularyItemSummary[]>(this.baseUrl, { params });
  }

  getItem(id: string): Observable<VocabularyItemDetail> {
    return this.http.get<VocabularyItemDetail>(`${this.baseUrl}/${id}`);
  }

  createItem(request: CreateVocabularyItemRequest): Observable<VocabularyItemDetail> {
    return this.http.post<VocabularyItemDetail>(this.baseUrl, request);
  }
}
```

`HttpClient` возвращает `Observable`. Важное отличие от `Promise`: Observable **ленивый** — запрос не
отправится, пока нет подписки. Забыли `subscribe()` — запроса просто не будет, и никакой ошибки вы не
увидите.

### Interceptor для токена

Перехватчик — обычная функция, которая добавляет заголовок ко всем запросам:

```typescript
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthSessionStore } from './auth-session-store';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const token = inject(AuthSessionStore).accessToken();
  if (!token) {
    return next(request);
  }
  return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
```

Благодаря этому ни один сервис API не занимается токенами.

### Три способа получить данные в компонент

**Вариант A — `httpResource`**, стабилен с версии 22. Подходит для «загрузить и показать»:

```typescript
import { httpResource } from '@angular/common/http';

export class CollectionsPage {
  protected readonly collections = httpResource<CollectionResponse[]>(
    () => `${environment.apiBaseUrl}/collections`,
  );
}
```

```html
@if (collections.isLoading()) {
  <app-spinner />
} @else if (collections.error()) {
  <p class="error">Не удалось загрузить темы</p>
} @else {
  @for (collection of collections.value() ?? []; track collection.id) { ... }
}
```

Готовые `isLoading`, `error`, `value` и защита от гонок — бесплатно. Минус: URL оказывается в
компоненте, что противоречит правилу «компонент не знает эндпоинтов». Поэтому в проекте используем
его только через фабрику из слоя API, либо не используем вовсе.

**Вариант B — `resource` с загрузчиком из сервиса.** Компромисс, который соблюдает правила:

```typescript
protected readonly collections = resource({
  loader: () => firstValueFrom(this.collectionsApi.listCollections()),
});
```

**Вариант C — подписка внутри store.** Для состояния, которое переживает один экран, например
учебной сессии:

```typescript
loadSession(sessionId: string): void {
  this.loading.set(true);
  this.studyApi.getSession(sessionId).subscribe({
    next: (session) => {
      this.session.set(session);
      this.loading.set(false);
    },
    error: () => {
      this.error.set('Не удалось загрузить занятие');
      this.loading.set(false);
    },
  });
}
```

В этом проекте: вариант B для экранов-списков, вариант C для `StudySessionStore` (шаг 50).

### Утечки подписок

Если вы подписываетесь в компоненте вручную, подписку надо закрывать при уничтожении:

```typescript
import { DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

export class WordStatusPoller {
  private readonly destroyRef = inject(DestroyRef);

  start(): void {
    interval(2000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.refresh());
  }
}
```

`takeUntilDestroyed` без аргумента работает только в контексте внедрения (в поле класса);
в методе ему нужно передать `DestroyRef`. Запросы через `HttpClient` завершаются сами, поэтому
одиночный `subscribe` на запрос отписывать не требуется — но бесконечные потоки вроде `interval`
обязательно.

---

## 6. Роутинг

`app.routes.ts`:

```typescript
import { Routes } from '@angular/router';
import { onboardingGuard } from './core/auth/onboarding-guard';

export const routes: Routes = [
  {
    path: 'onboarding',
    loadComponent: () => import('./features/onboarding/onboarding-page').then((m) => m.OnboardingPage),
  },
  {
    path: '',
    canActivate: [onboardingGuard],
    children: [
      {
        path: '',
        loadComponent: () => import('./features/collections/collections-page').then((m) => m.CollectionsPage),
      },
      {
        path: 'collections/:collectionId',
        loadComponent: () => import('./features/collections/collection-page').then((m) => m.CollectionPage),
      },
      {
        path: 'study/:sessionId',
        loadComponent: () => import('./features/study/study-page').then((m) => m.StudyPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
```

`loadComponent` — ленивая загрузка: код экрана скачивается при первом переходе. Для Mini App это
заметно: первый экран открывается быстрее.

Чтение параметра маршрута как сигнала:

```typescript
import { input } from '@angular/core';

export class CollectionPage {
  readonly collectionId = input.required<string>();
}
```

Это работает, если включена привязка параметров. Она включается в `provideRouter`:

```typescript
provideRouter(routes, withComponentInputBinding());
```

Навигация:

```typescript
private readonly router = inject(Router);

protected openCollection(collectionId: string): void {
  void this.router.navigate(['/collections', collectionId]);
}
```

Guard — функция, возвращающая `boolean` или редирект:

```typescript
import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';

export const onboardingGuard: CanActivateFn = () => {
  const session = inject(AuthSessionStore);
  const router = inject(Router);
  return session.isOnboardingCompleted() ? true : router.createUrlTree(['/onboarding']);
};
```

---

## 7. Формы

Правила проекта требуют Reactive Forms для нетривиальных форм. В Angular 22 стабильны и Signal Forms,
но два подхода в одном проекте смешивать не нужно — остаёмся на Reactive Forms.

```typescript
import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
  selector: 'app-collection-form',
  imports: [ReactiveFormsModule],
  templateUrl: './collection-form.html',
  styleUrl: './collection-form.scss',
})
export class CollectionForm {
  private readonly formBuilder = inject(FormBuilder);

  protected readonly form = this.formBuilder.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(60)]],
    description: ['', [Validators.maxLength(300)]],
  });

  protected submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { name, description } = this.form.getRawValue();
    // передать в сервис
  }
}
```

`formBuilder.nonNullable` важен: без него типы полей будут `string | null`, и вы получите лишние
проверки на `null` по всему коду.

Шаблон:

```html
<form [formGroup]="form" (ngSubmit)="submit()">
  <label for="name">Название темы</label>
  <input id="name" type="text" formControlName="name" />

  @if (form.controls.name.touched && form.controls.name.errors?.['required']) {
    <p class="field-error">Укажите название</p>
  }

  <button type="submit" [disabled]="form.invalid">Сохранить</button>
</form>
```

`imports: [ReactiveFormsModule]` в декораторе — так standalone-компонент подключает нужную
функциональность шаблона. Импортируется только то, что реально используется этим компонентом.

---

## 8. Стили

Правила проекта: только файлы `.scss`, компонентная область видимости, без `!important`, без
инлайновых стилей.

Стили компонента по умолчанию изолированы: селектор `.word-card` в `word-card.scss` не повлияет на
другие компоненты. Глобально (`src/styles.scss`) живут только токены дизайна, сброс, типографика и
общие примитивы layout.

Токены удобно завести сразу, чтобы не разносить произвольные значения по файлам:

```scss
:root {
  --color-surface: #ffffff;
  --color-text: #1c1c1e;
  --color-muted: #8e8e93;
  --color-accent: #2481cc;
  --radius-card: 12px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
}
```

Telegram передаёт тему оформления в CSS-переменных (`--tg-theme-bg-color` и другие). На шаге 20 мы
свяжем их с собственными токенами, чтобы Mini App выглядел родным в светлой и тёмной теме.

Имена классов — семантические, от смысла блока. Вложенность селекторов минимальная: привязка к
структуре DOM ломается при любом изменении шаблона.

---

## 9. Тесты на Vitest

С версии 22 Vitest — тест-раннер по умолчанию, Karma удалена.

```bash
ng test                # watch-режим
ng test --watch=false  # один прогон, для CI
```

Тест чистой функции:

```typescript
import { describe, expect, it } from 'vitest';
import { buildSentenceOptions } from './sentence-options';

describe('buildSentenceOptions', () => {
  it('includes all session words as options', () => {
    const options = buildSentenceOptions([
      { id: '1', text: 'clarify' },
      { id: '2', text: 'avoid' },
    ]);

    expect(options).toEqual(['clarify', 'avoid']);
  });
});
```

Тест сервиса с состоянием (наш `StudySessionStore`) — через `TestBed`:

```typescript
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { StudySessionStore } from './study-session-store';

describe('StudySessionStore', () => {
  it('reveals the answer after three failed attempts', () => {
    const store = TestBed.inject(StudySessionStore);

    store.submitAnswer('wrong');
    store.submitAnswer('wrong');
    store.submitAnswer('wrong');

    expect(store.answerRevealed()).toBe(true);
  });
});
```

Что тестировать обязательно (раздел 36 правил проекта): состояние занятия, переходы между этапами,
логика трёх попыток, пропуск этапа для фраз, сопоставление, восстановление сессии. Чистые функции
предпочтительнее тестов компонентов — их и писать, и читать легче.

---

## 10. Структура frontend

```text
src/app/
├── app.ts                       корневой компонент
├── app.config.ts                провайдеры приложения
├── app.routes.ts                маршруты
├── core/                        инфраструктура, один экземпляр на приложение
│   ├── auth/
│   │   ├── auth-api.ts
│   │   ├── auth-session-store.ts
│   │   ├── auth-interceptor.ts
│   │   └── onboarding-guard.ts
│   ├── telegram/
│   │   └── telegram-web-app-bridge.ts
│   └── api/
│       └── api-error.ts
├── shared/                      переиспользуемые презентационные элементы
│   ├── spinner/
│   ├── app-button/
│   └── empty-state/
└── features/
    ├── onboarding/
    ├── collections/
    │   ├── collections-api.ts
    │   ├── collections-page.ts
    │   ├── collection-page.ts
    │   └── collection-form/
    ├── vocabulary/
    │   ├── vocabulary-api.ts
    │   ├── add-word-page.ts
    │   ├── meaning-selector/
    │   └── word-card/
    ├── study/
    │   ├── study-api.ts
    │   ├── study-session-store.ts
    │   ├── study-page.ts
    │   └── stages/
    ├── irregular-verbs/
    └── profile/
```

Принцип: файл лежит рядом с той функциональностью, которой принадлежит. Папок вида `components/`,
`services/`, `models/` на уровне приложения нет — они собирают вместе несвязанные вещи и заставляют
прыгать по дереву при работе над одной задачей.

`core/` — то, что существует в единственном экземпляре и не относится ни к одной функции
(аутентификация, мост к Telegram). `shared/` — то, что переиспользуется в нескольких функциях и не
содержит бизнес-логики.

---

## 11. Частые ошибки новичка в Angular

| Симптом | Причина | Решение |
| --- | --- | --- |
| Шаблон не обновляется | состояние в обычном поле, а не в сигнале | перенести в `signal()` |
| `item is not a function` | забыли вызвать сигнал: `item.text` вместо `item().text` | добавить `()` |
| Запрос не уходит | нет подписки на Observable | `subscribe()`, `resource`, или `httpResource` |
| Список «мигает», ввод теряет фокус | неверный `track` в `@for` | использовать стабильный id |
| `NullInjectorError` | сервис не помечен `providedIn: 'root'` | добавить |
| `@if` не работает | пытаетесь использовать `*ngIf` из старых примеров | перейти на `@if` |
| Стили не применяются | селектор пытается достать элемент дочернего компонента | стилизовать внутри самого дочернего компонента |
| Ошибка сборки про Node | версия Node ниже требуемой CLI | шаг 1 |

---

## Что читать дальше

* Шаг 19 и далее — [03-week1-foundation.md](03-week1-foundation.md)
* Контракты, под которые пишутся модели на фронте — [08-api-reference.md](08-api-reference.md)
* Официальная документация: [angular.dev](https://angular.dev) — она обновлена под версии 20+,
  в отличие от большинства сторонних материалов
* Документация Telegram Mini Apps: [core.telegram.org/bots/webapps](https://core.telegram.org/bots/webapps)
