# Project Instructions

## 1. Detect the stack first

Before writing, moving, or reviewing frontend code, determine whether this project (or the package you are working in, for monorepos) uses React. Treat it as a React project if ANY of these are true:

- `package.json` lists `react` or `react-dom` in `dependencies` or `devDependencies`
- The source tree contains `.tsx` or `.jsx` files that import from `react`
- `vite.config.*` uses `@vitejs/plugin-react` (or `plugin-react-swc`)

In a monorepo, check the nearest `package.json` to the files being changed, not only the root.

Do this check once per session (or when switching packages) and state the result in one line, e.g. `Detected: React 18 + Vite + TypeScript`.

## 2. If it IS React

Use the **react-architecture** skill for all React work: scaffolding, new components or features, refactors, and code reviews. It defines the folder structure, import boundaries, design-system adapter rules, and coding standards.

How strictly to apply it:

| Situation | What to do |
|---|---|
| Vite + React + TypeScript SPA | Apply the skill in full. |
| New/empty project | Scaffold using the skill's full structure. |
| Other React setup (Next.js, Remix, React Native, CRA) | Keep the skill's principles (atomic shared UI, sealed features, atoms as the only design-system importers, one-way imports), but follow the framework's own routing and file conventions (e.g. Next.js `app/` directory). |
| JavaScript instead of TypeScript | Follow the same structure; skip TS-specific rules. |
| Existing project with a different, consistent structure | Follow the existing structure for consistency. Briefly note where it diverges from the skill. Do not restructure unless asked. |

Never perform a large folder restructure or move many files without confirming with me first.

## 3. If it is NOT React

Ignore the react-architecture skill entirely and follow the conventions already present in the codebase.

## 4. Always

- Read existing code near the change before adding new files; match its patterns.
- After making changes, run the project's lint, type-check, and test scripts if they exist (`npm run lint`, `npm run typecheck` / `tsc --noEmit`, `npm test`) and fix what you broke.
- Keep explanations short; show the file tree for new files before the code.
