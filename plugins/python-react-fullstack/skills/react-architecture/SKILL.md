---
name: react-architecture
description: Folder structure, architecture rules and coding standards for React + TypeScript + Vite single-page apps, using a hybrid layout where atomic-design UI components (atoms, molecules, organisms, templates) live in shared type-based folders and business logic lives in self-contained feature modules. The design system is wrapped behind atoms so it can be swapped. Scales down for small projects. Use this skill whenever the user writes, scaffolds, refactors, reviews or asks where to put React code — components, hooks, pages, features, API calls, state, tests, or project setup — even if they only paste a .tsx/.jsx file or mention JSX, hooks, Vite, or a component name without asking about structure.
---

# React Architecture (Vite + TypeScript, plug-and-play)

The first goal is **code that is easy to read**. The second is **plug-and-play**: a piece (a design system, a feature, an API client) can be replaced by touching one well-defined place. When the two conflict, readability wins. When a situation isn't covered, choose the option a newcomer would understand fastest.

## Readability comes first

When readability and abstraction pull in different directions, choose readability. Someone new to the code should be able to read a file from top to bottom and understand it without jumping through layers.

- **Add an abstraction only for a second real use that exists today.** That covers base classes, Protocols and interfaces, generic helpers, factories, wrappers, and extra layers or files. "We might need it later" is not a reason; adding it later is cheap.
- **A few repeated lines beat a shared helper that hides what the code does.**
- **Call things directly.** Use the library or function you need instead of an indirection built for flexibility nobody asked for.
- **No clever tricks.** Name things for what they do. If a pattern needs a comment to explain how it works, choose a plainer one.
- **This outranks the rest of this skill.** If a rule below would make this project's code harder to read, favor readability and say in one line which rule you relaxed.

## Before anything else

**The project's own rules come first.** Read the project's `CLAUDE.md` before applying this skill. If it says to keep things simple, favor readable code over abstractions, skip tests, or use fewer files, follow it. The structure and defaults below are a starting point for teams that haven't decided, not rules that override the project.

**Small or large project?** Decide once, from the project's size and the `CLAUDE.md`, and say which you chose in one line.

| | Small (default for learning projects, prototypes, one or two developers, under ~10 screens) | Large (several developers or teams, long-lived product) |
|---|---|---|
| Shared components | One file each (`components/atoms/Button.tsx`), props interface inline | Folder per component (`Button/Button.tsx`, `Button.types.ts`, `index.ts`) |
| Barrel files | None except each feature's `index.ts`; import from the file path | `index.ts` per component and per atomic level |
| Atoms | Only for primitives you customize or reuse; with no plan to switch UI libraries, components may use the library directly | Full design-system wrapper set |
| Feature API | One `<feature>.api.ts` | Split into `api/` (calls, keys, hooks) when a file passes ~150 lines |
| ESLint boundary rules | Optional | Recommended |
| Tests | Only if the project wants them | Vitest + Testing Library + MSW |

Everything else (the layers, the import direction, sealed features, atoms as the only design-system importers) applies to both.

## The layout at a glance

```
src/
├── app/                 # Bootstrapping only: App.tsx, providers/, router/
├── pages/               # Route-level screens. Thin: compose features + templates
├── features/            # Self-contained business modules (plug-and-play units)
│   └── <feature>/
│       ├── components/  # Feature components: one file each, props inline
│       ├── <feature>.api.ts  # Server calls, query keys and query hooks
│       ├── use<Feature>.ts   # The screen's hook, if it needs one
│       ├── types.ts
│       └── index.ts     # PUBLIC API — the only file others may import
├── components/          # Shared, business-agnostic UI (atomic design)
│   ├── atoms/           # ONLY layer allowed to import the design-system library
│   ├── molecules/       # Compose atoms
│   ├── organisms/       # Compose molecules/atoms (e.g. DataTable)
│   └── templates/       # Page layouts with slots, no data
├── hooks/               # Shared, generic hooks (useDebounce, useMediaQuery)
├── lib/                 # Configured third-party clients (http, queryClient)
├── config/              # env parsing, constants, route paths
├── styles/              # tokens.css / theme, global styles
├── utils/               # Pure helper functions
└── main.tsx
```

Add folders only when there is something to put in them: `features/<f>/hooks/` once a feature has several hooks, `store/` only for real client state, `services/` and `types/` only when more than one feature needs them. Empty or one-file folders are noise.

Read `references/structure-and-boundaries.md` for what goes where and the import-direction rules (including an optional ESLint config that enforces them).

## The five rules that matter most

1. **Imports flow one way:** `app → pages → features → components / hooks / lib / utils / types`. Shared layers never import from features; features never import from pages or app. A molecule never imports an organism (lower atomic levels never import higher ones).
2. **Features are sealed.** Other code imports a feature only through its `index.ts`. Features should not import each other; if two features need to cooperate, compose them in a page, or lift the shared piece into `components/` (if UI) or `lib`/`services` (if logic).
3. **Atoms are the design-system adapter** (large projects, or any project that may switch UI libraries). Only `components/atoms/*` may import the UI library (MUI, shadcn/Radix, Chakra, AntD…). Atoms expose *our own* prop API — never re-export or spread vendor prop types — so swapping the library means rewriting atoms only. Details and examples: `references/design-system-adapter.md`.
4. **Shared components are business-agnostic.** A `DataTable` organism takes columns + rows + callbacks; it never knows what a "User" or "Order" is. Anything that knows the domain belongs in a feature.
5. **Pages are thin.** A page reads route params, picks a template, and drops feature components into slots. No data fetching logic or heavy JSX in pages.

## Keep it plain

These rules stop the code from getting clever. They matter as much as the structure.

- **Reset a screen's state with a `key`.** When a screen must start fresh for a new item (another conversation, another order), the page renders `<OrderScreen key={orderId} … />`. Don't write effects or custom hooks that watch an id and reset state.
- **Aim for one hook per screen.** A screen usually needs one `useXxx` hook that returns everything it uses. Hooks calling hooks calling hooks are hard to follow; inline small pieces instead of extracting them.
- **If a pattern needs a comment to explain how it works, choose a plainer one.** Comments should say *why*, not decode *how*. Ref-juggling tricks, "latest callback" refs, generic state helpers and similar patterns are a sign to step back.
- **Fewer files beats more files** until a file is genuinely long (~150 lines). Don't create a file just to hold one type or re-export one thing.

## Where does this file go? (decision order)

1. Does it know about a business concept (user, invoice, cart)? → `features/<feature>/…`
2. Is it reusable UI with no business knowledge, used in more than one feature? → `components/<atomic level>/`
   - Wraps a single design-system primitive → atom
   - Small combination of atoms with one purpose (SearchField = Input + Icon + Button) → molecule
   - Larger self-sufficient section (DataTable, Navbar, Modal with header/footer) → organism
   - Layout skeleton with slots → template
3. Is it a generic hook with no UI and no domain? → `hooks/`
4. Is it a configured third-party client? → `lib/`
5. Pure function? → `utils/`

UI used by only one feature stays in that feature's `components/` until a second feature needs it.

If the user's existing project already follows a different convention, follow theirs for consistency and mention (briefly) where it diverges from this skill.

## Component files

**Feature components** (in `features/<f>/components/`) are one file each, with the props interface at the top of the same file:

```tsx
// features/orders/components/OrderRow.tsx
interface OrderRowProps {
  order: Order;
  onSelect: (id: string) => void;
}

export function OrderRow({ order, onSelect }: OrderRowProps) { … }
```

**Shared components** (in `components/`) follow the small/large table above. In a large project each gets a folder:

```
DataTable/
├── DataTable.tsx          # the component (named export)
├── DataTable.types.ts     # props + public types
├── DataTable.test.tsx     # if the project has tests
└── index.ts               # export { DataTable } from './DataTable'; export type * from './DataTable.types'
```

Templates: `assets/templates/` (`FeatureComponent.tsx` for feature components; the `Component.*` and `component-index` files for large-project shared components).

## Stack defaults (use unless the project already chose otherwise)

- **Build/lang:** Vite, TypeScript `strict: true`, path alias `@/` → `src/`
- **Routing:** React Router (route paths centralized in `config/routes.ts`), lazy-load pages with `React.lazy`
- **Server state:** TanStack Query; query hooks live in the feature's `<feature>.api.ts`
- **Client state:** local `useState` first; React Context for low-frequency app-wide values (theme, auth session); Zustand only when real shared client state exists
- **Forms:** React Hook Form + Zod schemas (schemas double as types via `z.infer`)
- **Testing (when the project has tests):** Vitest + React Testing Library + MSW for API mocking
- **Lint/format:** ESLint + Prettier; boundary rules for large projects

## Coding standards

Read `references/coding-standards.md` when writing or reviewing component code. Short version: function components with named exports, explicit props types, no `any`, no business logic in JSX, derive state instead of syncing it, reset with `key`, one hook per screen, plain patterns over clever ones, accessible markup.

## How to respond

- When **creating** code: show the file tree for what you're adding first, then each file with its full path as a heading. Include barrel updates only if the project uses barrels.
- When **scaffolding a new project**: say whether you're using the small or large setup and why. Produce the `src/` tree, `vite.config.ts` and `tsconfig` alias config, and one example feature end-to-end. Add the ESLint boundary config for large projects.
- When **reviewing/refactoring**: list boundary violations first (wrong-direction imports, vendor imports outside atoms, domain logic in shared components), then readability issues (needless files, hook chains, clever patterns), then the rest, then the corrected structure.
- When **explaining to the user**: describe what changed and why in everyday words. Explain a technical term in a short phrase the first time you use it, or leave it out.
- Keep explanations short; the structure should speak for itself.
