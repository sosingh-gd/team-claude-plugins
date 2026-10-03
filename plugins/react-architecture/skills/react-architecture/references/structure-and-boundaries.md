# Structure and Boundaries

## Layer responsibilities

| Folder | Contains | May import from | Must NOT import from |
|---|---|---|---|
| `app/` | `App.tsx`, `providers/` (QueryClientProvider, ThemeProvider, AuthProvider), `router/` | everything | — |
| `pages/` | One folder per route screen | features (via index), components, hooks, lib, config, utils, types | app, other pages |
| `features/<f>/` | Domain UI, hooks, API, state, types | components, hooks, lib, services, config, utils, types | app, pages, **other features' internals** |
| `components/` | Atomic-design shared UI | lower atomic levels, hooks, utils, types, styles | features, pages, app, lib/services (no data fetching) |
| `hooks/` | Generic hooks | utils, types | features, components |
| `lib/` | Configured clients (`http.ts`, `queryClient.ts`) | config, utils, types | features, components |
| `services/` | API clients used by more than one feature | lib, types, config | features, components |
| `utils/`, `types/`, `config/` | Pure code | each other | anything with React or domain modules |

Atomic levels inside `components/`: `atoms ← molecules ← organisms ← templates`. A level may import only from levels to its left.

## Feature module anatomy

```
features/orders/
├── components/
│   ├── OrdersTable/          # composes <DataTable/> organism with order columns
│   └── OrderStatusBadge/     # composes <Badge/> atom
├── hooks/
│   └── useOrderFilters.ts
├── api/
│   ├── orders.api.ts         # raw requests using lib/http
│   ├── orders.queries.ts     # useOrdersQuery, useCreateOrderMutation
│   └── orders.keys.ts        # query key factory
├── store/                    # only if client state is needed
├── types.ts                  # Order, OrderStatus (or schemas.ts with Zod)
├── utils.ts
└── index.ts
```

`index.ts` exposes only what pages need:

```ts
export { OrdersTable } from './components/OrdersTable';
export { useOrdersQuery } from './api/orders.queries';
export type { Order, OrderStatus } from './types';
```

Removing a feature = delete its folder + remove its usages in pages/router. If removing it breaks other features, a boundary was violated.

## Cross-feature needs

- Two features need the same **UI** → generalize it into `components/` (strip domain knowledge, pass data via props).
- Two features need the same **data/logic** → move it to `services/` or `lib/`, or create a small shared feature (e.g. `features/session`) that others consume through its index.
- A page needs data from two features → the page composes both; features stay unaware of each other.

## Pages

```
pages/
└── OrdersPage/
    ├── OrdersPage.tsx
    └── index.ts
```

```tsx
export function OrdersPage() {
  return (
    <DashboardTemplate header={<PageHeader title="Orders" />}>
      <OrderFilters />
      <OrdersTable />
    </DashboardTemplate>
  );
}
```

## Enforcing boundaries with ESLint

Use `eslint-plugin-boundaries` (flat config):

```js
// eslint.config.js (excerpt)
import boundaries from 'eslint-plugin-boundaries';

export default [
  {
    plugins: { boundaries },
    settings: {
      'boundaries/elements': [
        { type: 'app', pattern: 'src/app/*' },
        { type: 'pages', pattern: 'src/pages/*' },
        { type: 'feature', pattern: 'src/features/*', capture: ['feature'] },
        { type: 'atoms', pattern: 'src/components/atoms/*' },
        { type: 'molecules', pattern: 'src/components/molecules/*' },
        { type: 'organisms', pattern: 'src/components/organisms/*' },
        { type: 'templates', pattern: 'src/components/templates/*' },
        { type: 'shared', pattern: 'src/(hooks|lib|services|utils|types|config|styles)/*' },
      ],
    },
    rules: {
      'boundaries/element-types': ['error', {
        default: 'disallow',
        rules: [
          { from: 'app', allow: ['app', 'pages', 'feature', 'atoms', 'molecules', 'organisms', 'templates', 'shared'] },
          { from: 'pages', allow: ['feature', 'atoms', 'molecules', 'organisms', 'templates', 'shared'] },
          { from: 'feature', allow: [['feature', { feature: '${from.feature}' }], 'atoms', 'molecules', 'organisms', 'templates', 'shared'] },
          { from: 'templates', allow: ['organisms', 'molecules', 'atoms', 'shared'] },
          { from: 'organisms', allow: ['molecules', 'atoms', 'shared'] },
          { from: 'molecules', allow: ['atoms', 'shared'] },
          { from: 'atoms', allow: ['atoms', 'shared'] },
          { from: 'shared', allow: ['shared'] },
        ],
      }],
      // Only atoms may touch the design-system library (adjust package names):
      'no-restricted-imports': ['error', {
        patterns: [{ group: ['@mui/*', '@radix-ui/*', 'antd', '@chakra-ui/*'], message: 'Import UI primitives from @/components, not the design-system library.' }],
      }],
    },
  },
  {
    files: ['src/components/atoms/**'],
    rules: { 'no-restricted-imports': 'off' },
  },
];
```

## Path aliases

`vite.config.ts`:

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
});
```

`tsconfig.app.json`: `"baseUrl": ".", "paths": { "@/*": ["src/*"] }`.

Use `@/` for cross-layer imports; use relative imports only inside the same component or feature folder.
