# python-react-fullstack plugin

One plugin with three skills for React + Python projects. Each skill triggers on its own kind of work, so install once and use whichever fits.

| Skill | Use it for | Explicit call |
|---|---|---|
| `react-architecture` | React + TypeScript + Vite apps: atomic-design + feature-module folder structure, import boundaries, swappable design-system layer, coding standards | `/python-react-fullstack:react-architecture` |
| `python-architecture` | Python projects: uv, Makefile, pyproject-configured ruff/mypy/pytest/coverage, FastAPI modular and layered layouts, libraries, CLIs, plus a project scaffolder | `/python-react-fullstack:python-architecture` |
| `python-react-fullstack` | FastAPI ↔ React contract: Pydantic schemas → OpenAPI → generated TypeScript types, typed client, TanStack Query, RFC 9457 errors, auth, SSE streaming, dev setup | `/python-react-fullstack:python-react-fullstack` |

## Layout

```
.claude-plugin/plugin.json
CLAUDE.example.md                # optional global CLAUDE.md for React stack detection
skills/
├── react-architecture/
│   ├── SKILL.md
│   ├── references/              # coding-standards, design-system-adapter, structure-and-boundaries
│   └── assets/templates/        # component and feature templates
├── python-architecture/
│   ├── SKILL.md
│   ├── references/              # tooling.md, fastapi.md, project-types.md (loaded on demand)
│   ├── assets/templates/        # pyproject, Makefile, Dockerfile, pre-commit, CI, gitignore, env templates
│   ├── assets/skeletons/        # starter code + tests: fastapi-modular, fastapi-layered, library, cli
│   └── scripts/scaffold.py      # generates a project from the templates (stdlib only)
└── python-react-fullstack/
    ├── SKILL.md
    ├── references/              # api-contract, auth, streaming, backend-structure, dev-setup, other-patterns
    └── assets/templates/        # backend/, frontend/, project/ ({{placeholder}} templates)
```

## Install

```bash
claude plugin marketplace add sosingh-gd/team-claude-plugins
claude plugin install python-react-fullstack@engineering-team
```

For a team repo, add `--scope project` to both commands to write `.claude/settings.json` for teammates. See the [root README](../../README.md#install) for details.

## Usage

Ask Claude naturally and the matching skill activates:

- "add a ProductCard component to the catalog feature" → `react-architecture`
- "start a new FastAPI service called order-service" → `python-architecture`
- "wire the orders endpoint into the React app with generated types" → `python-react-fullstack`

### Python standard at a glance

- **uv** manages Python version, virtualenv, dependencies and `uv.lock`. No pip, no requirements.txt.
- **Makefile** is the single command surface: `make install`, `make dev`, `make format`, `make lint`, `make typecheck`, `make test`, `make cov`, `make check`. CI runs `make check`.
- **pyproject.toml** holds all tool config: ruff (lint + format), mypy (strict), pytest, coverage.
- **src layout**, typed code, pydantic-settings for config, thin routers → services → repositories for FastAPI.

The scaffold script also works without Claude:

```bash
python plugins/python-react-fullstack/skills/python-architecture/scripts/scaffold.py --name order-service --type fastapi --layout modular
cd order-service && make check
```

Types: `fastapi` (`--layout modular|layered`), `library`, `cli`. Options: `--python 3.12`, `--dest`, `--no-sync`, `--no-git`, `--force`.

## Customizing for your org

Edit the skill's `references/` or `assets/templates/` (line length, coverage threshold, rule sets, component templates) and bump `version` in `.claude-plugin/plugin.json`. Teams pick up changes with `/plugin marketplace update engineering-team`.
