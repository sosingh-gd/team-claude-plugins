# python-architecture plugin

Contains one skill, `python-architecture`, that teaches Claude the team standard for Python projects and can scaffold new ones.

## What the standard is

- **uv** manages Python version, virtualenv, dependencies and `uv.lock`. No pip, no requirements.txt.
- **Makefile** is the single command surface: `make install`, `make dev`, `make format`, `make lint`, `make typecheck`, `make test`, `make cov`, `make check`. CI runs `make check`.
- **pyproject.toml** holds all tool config: ruff (lint + format), mypy (strict), pytest, coverage.
- **src layout**, typed code, pydantic-settings for config, thin routers → services → repositories for FastAPI.

## Layout

```
skills/python-architecture/
├── SKILL.md                 # instructions Claude follows
├── assets/
│   ├── templates/           # pyproject, Makefile, Dockerfile, pre-commit, CI, gitignore, env templates
│   └── skeletons/           # starter code + tests: fastapi-modular, fastapi-layered, library, cli
├── references/              # tooling.md, fastapi.md, project-types.md (loaded on demand)
└── scripts/scaffold.py      # generates a project from the templates (stdlib only)
```

## Install

```bash
claude plugin marketplace add sosingh-gd/team-claude-plugins
claude plugin install python-architecture@engineering-team
```

## Usage

Ask Claude naturally ("start a new FastAPI service called order-service", "add ruff config to this repo", "how should I structure this FastAPI app?") and the skill activates. You can also call it explicitly with `/python-architecture:python-architecture`.

The scaffold script also works without Claude:

```bash
python plugins/python-architecture/skills/python-architecture/scripts/scaffold.py --name order-service --type fastapi --layout modular
cd order-service && make check
```

Types: `fastapi` (`--layout modular|layered`), `library`, `cli`. Options: `--python 3.12`, `--dest`, `--no-sync`, `--no-git`, `--force`.

## Customizing for your org

Edit the templates in `assets/templates/` (line length, coverage threshold, rule sets) and bump `version` in `.claude-plugin/plugin.json`. Teams pick up changes with `/plugin marketplace update engineering-team`.
