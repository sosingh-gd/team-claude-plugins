# Coding Standards

## Components

- Function components with **named exports** (`export function UserCard`). Default exports only where a tool requires them (e.g. `React.lazy` wrapper files).
- Props typed with an `interface`. For feature components (and shared components in small projects) it sits at the top of the component file; large-project shared components put it in `<Name>.types.ts`. Destructure props in the signature with defaults.
- No `React.FC`; type `children` explicitly as `ReactNode` when accepted.
- One exported component per file. A small private sub-component used only by that file can live in the same file.
- Keep components under ~150 lines; extract hooks or sub-components when larger.
- Keep JSX declarative: compute values above the `return`, avoid nested ternaries (use early returns or a small lookup map).
- Lists use stable keys from data (`item.id`), never array index for dynamic lists.

## Hooks and state

- **Aim for one hook per screen.** Extract a `useXxx` hook when a screen's logic gets long or is reused, and have it return everything the screen needs. Avoid chains of hooks calling hooks; inline small pieces instead.
- **Reset state with a `key`, not with code.** To start a screen fresh for another item, render it with `key={itemId}`. Don't watch an id in an effect to reset state, and don't build helper hooks for it.
- **Prefer plain patterns.** If a pattern needs a comment to explain how it works (refs holding the "latest" callback, generic keyed-state helpers, effects that sync one state into another), choose a plainer one, even if it is a few lines longer.
- **Derive, don't sync:** if a value can be computed from props/state, compute it during render (with `useMemo` only if measurably expensive) instead of storing it with `useEffect`.
- `useEffect` is for synchronizing with external systems (subscriptions, DOM APIs). Not for data fetching (use TanStack Query) and not for reacting to user events (do it in the handler).
- Server data lives in TanStack Query, not in Zustand/Context. Use a query-key factory per feature.
- Lift state only as high as needed; prefer composition (passing `children`/slots) over prop drilling and over Context.
- `useMemo`/`useCallback`/`memo` only with a reason (stable dependency for a memoized child, expensive computation).

## TypeScript

- `strict: true`; no `any` (use `unknown` and narrow). No non-null `!` except where provably safe.
- Validate external data at the boundary (API responses, URL params, env vars) with Zod; infer types from schemas.
- Prefer union string literals over enums.
- Use `import type` for type-only imports.

## Naming

| Thing | Convention | Example |
|---|---|---|
| Component & folder | PascalCase | `DataTable/DataTable.tsx` |
| Hook | camelCase, `use` prefix | `useOrderFilters.ts` |
| Feature folder | kebab-case or camelCase (pick one, be consistent) | `features/user-profile` |
| API file | `<domain>.api.ts` (split into `api/<domain>.{api,keys,queries}.ts` only when long) | `orders.api.ts` |
| Types file | `types.ts` per feature; `<Name>.types.ts` only for large-project shared components | `types.ts` |
| Event props / handlers | `onX` props, `handleX` implementations | `onSelect` / `handleSelect` |
| Booleans | `is/has/should/can` prefix | `isLoading`, `hasError` |

## Data fetching

```ts
// features/orders/orders.api.ts — calls, keys and hooks together until the file gets long
export const orderKeys = {
  all: ['orders'] as const,
  list: (filters: OrderFilters) => [...orderKeys.all, 'list', filters] as const,
  detail: (id: string) => [...orderKeys.all, 'detail', id] as const,
};

export function useOrdersQuery(filters: OrderFilters) {
  return useQuery({ queryKey: orderKeys.list(filters), queryFn: () => fetchOrders(filters) });
}
```

All HTTP goes through `lib/http.ts` (base URL from `config/env.ts`, auth header, error normalization).

## Styling

- Use design tokens (CSS variables in `styles/tokens.css`) for color, spacing, radius, typography. No hard-coded hex values or magic pixel numbers in features.
- Styling details belong to atoms and organisms; features arrange components and rarely need their own styles.

## Accessibility

- Semantic elements first (`button`, `nav`, `main`, `label`). Interactive elements must be keyboard reachable.
- Every input has a label; icon-only buttons have `aria-label`.
- Atoms own a11y behavior so features inherit it.

## Testing

Follow the project: if its `CLAUDE.md` says to skip tests or keep them minimal, do that. When the project has tests:

- Colocate `*.test.tsx`. Test behavior through the UI with React Testing Library (`getByRole` first), not implementation details.
- Mock network with MSW handlers in `src/test/mocks/`; shared render helper with providers in `src/test/utils.tsx`.
- Atoms: render + interaction + a11y attributes. Features: user flows with mocked API.

## Performance

- Lazy-load route pages (`React.lazy` + `Suspense`) in `app/router`.
- Virtualize long lists/tables (inside the organism, so features get it for free).
- Avoid creating new objects/functions in props only when the child is memoized and it matters.

## Error handling

- Route-level error boundaries in `app/router`; feature-level boundaries around independent widgets.
- Query errors rendered via a shared `ErrorState` molecule; loading via `Skeleton`/`Spinner` atoms.
