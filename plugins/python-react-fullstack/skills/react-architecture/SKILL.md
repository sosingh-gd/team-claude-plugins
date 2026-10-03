---
name: react-architecture
description: Folder structure, architecture rules and coding standards for React + TypeScript + Vite single-page apps, using a hybrid layout where atomic-design UI components (atoms, molecules, organisms, templates) live in shared type-based folders and business logic lives in self-contained feature modules. The design system is wrapped behind atoms so it can be swapped. Use this skill whenever the user writes, scaffolds, refactors, reviews or asks where to put React code — components, hooks, pages, features, API calls, state, tests, or project setup — even if they only paste a .tsx/.jsx file or mention JSX, hooks, Vite, or a component name without asking about structure.
---

# React Architecture (Vite + TypeScript, plug-and-play)

The goal of this architecture is **plug-and-play**: any piece (a design system, a feature, an API client) should be replaceable by touching one well-defined place. Every rule below serves that goal — when a situation isn't covered, choose the option that keeps the swap surface smallest.

## The layout at a glance

```
src/
├── app/                 # Bootstrapping only: App.tsx, providers/, router/
├── pages/               # Route-level screens. Thin: compose features + templates
├── features/            # Self-contained business modules (plug-and-play units)
│   └── <feature>/
│       ├── components/  # Feature-specific components (compose shared UI)
│       ├── hooks/
│       ├── api/         # Requests + query hooks for this feature
│       ├── store/       # Feature client state (only if needed)
│       ├── types.ts
│       ├── utils.ts
│       └── index.ts     # PUBLIC API — the only file others may import
├── components/          # Shared, business-agnostic UI (atomic design)
│   ├── atoms/           # ONLY layer allowed to import the design-system library
│   ├── molecules/       # Compose atoms
│   ├── organisms/       # Compose molecules/atoms (e.g. DataTable)
│   └── templates/       # Page layouts with slots, no data
├── hooks/               # Shared, generic hooks (useDebounce, useMediaQuery)
├── lib/                 # Configured third-party clients (http, queryClient)
├── services/            # Cross-feature API clients, if any
├── config/              # env parsing, constants, route paths
├── styles/              # tokens.css / theme, global styles
├── types/               # Truly global types
├── utils/               # Pure helper functions
└── main.tsx
```

Read `references/structure-and-boundaries.md` for the full rules on what goes where and the import-direction rules (including an ESLint config that enforces them).

## The five rules that matter most

1. **Imports flow one way:** `app → pages → features → components / hooks / lib / utils / types`. Shared layers never import from features; features never import from pages or app. A molecule never imports an organism (lower atomic levels never import higher ones).
2. **Features are sealed.** Other code imports a feature only through its `index.ts`. Features should not import each other; if two features need to cooperate, compose them in a page, or lift the shared piece into `components/` (if UI) or `lib`/`services` (if logic).
3. **Atoms are the design-system adapter.** Only `components/atoms/*` may import the UI library (MUI, shadcn/Radix, Chakra, AntD…). Atoms expose *our own* prop API — never re-export or spread vendor prop types — so swapping the library means rewriting atoms only. Details and examples: `references/design-system-adapter.md`.
4. **Shared components are business-agnostic.** A `DataTable` organism takes columns + rows + callbacks; it never knows what a "User" or "Order" is. Anything that knows the domain belongs in a feature.
5. **Pages are thin.** A page reads route params, picks a template, and drops feature components into slots. No data fetching logic or heavy JSX in pages.

## Where does this file go? (decision order)

1. Does it know about a business concept (user, invoice, cart)? → `features/<feature>/…`
2. Is it reusable UI with no business knowledge? → `components/<atomic level>/`
   - Wraps a single design-system primitive → atom
   - Small combination of atoms with one purpose (SearchField = Input + Icon + Button) → molecule
   - Larger self-sufficient section (DataTable, Navbar, Modal with header/footer) → organism
   - Layout skeleton with slots → template
3. Is it a generic hook with no UI and no domain? → `hooks/`
4. Is it a configured third-party client? → `lib/`
5. Pure function? → `utils/`

If the user's existing project already follows a different convention, follow theirs for consistency and mention (briefly) where it diverges from this skill.

## Component folder convention

Every component — shared or feature — gets its own folder:

```
DataTable/
├── DataTable.tsx          # the component (named export)
├── DataTable.types.ts     # props + public types
├── DataTable.test.tsx     # Vitest + React Testing Library
├── DataTable.stories.tsx  # optional, if Storybook is used
└── index.ts               # export { DataTable } from './DataTable'; export type * from './DataTable.types'
```

Each atomic level also has an `index.ts` barrel so consumers write `import { Button, DataTable } from '@/components'`. Templates for these files: `assets/templates/`.

## Stack defaults (use unless the project already chose otherwise)

- **Build/lang:** Vite, TypeScript `strict: true`, path alias `@/` → `src/`
- **Routing:** React Router (route paths centralized in `config/routes.ts`), lazy-load pages with `React.lazy`
- **Server state:** TanStack Query; query hooks live in `features/<f>/api/`
- **Client state:** local `useState`/`useReducer` first; React Context for low-frequency app-wide values (theme, auth session); Zustand only when real shared client state exists
- **Forms:** React Hook Form + Zod schemas (schemas double as types via `z.infer`)
- **Testing:** Vitest + React Testing Library + MSW for API mocking
- **Lint/format:** ESLint (with boundary rules) + Prettier

## Coding standards

Read `references/coding-standards.md` when writing or reviewing component code. Short version: function components with named exports, explicit props types, no `any`, no business logic in JSX, derive state instead of syncing it, custom hooks for reusable logic, colocated tests, accessible markup.

## How to respond

- When **creating** code: show the file tree for what you're adding first, then each file with its full path as a heading. Include the `index.ts` barrel updates.
- When **scaffolding a new project**: produce the full `src/` tree, `vite.config.ts` and `tsconfig` alias config, the ESLint boundary config, and one example feature end-to-end.
- When **reviewing/refactoring**: list boundary violations first (wrong-direction imports, vendor imports outside atoms, domain logic in shared components), then other issues, then the corrected structure.
- Keep explanations short; the structure should speak for itself.
