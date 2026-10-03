---
name: python-architecture
description: Standards and scaffolding for Python projects using uv for environment and dependency management, a Makefile as the single command entrypoint, and ruff/mypy/pytest configured in pyproject.toml. Covers FastAPI services (layer-based, modular/domain-based, and clean/hexagonal layouts), libraries, CLIs and workers. Use this skill whenever the user starts, scaffolds, bootstraps, restructures or reviews a Python project, asks how to organize a FastAPI or Python codebase, wants a pyproject.toml, Makefile, ruff/linting/formatting config, pre-commit, Dockerfile or CI for Python, or mentions uv, even if they only say "new Python service", "set up my repo" or "make this FastAPI app scalable".
---

# Python Architecture

This skill encodes a house standard for Python projects. The goal is that every project looks and behaves the same way: `uv` owns the environment, `pyproject.toml` owns all configuration, and `make` is the one command surface humans, CI and Claude all use. Consistency matters more than any individual choice, because it lets anyone (including you, later) clone a repo and know immediately how to install, run, test and lint it.

## Core conventions

**uv manages everything.** Python version, virtualenv, dependencies and lockfile all go through uv. Never use `pip install`, `requirements.txt`, Poetry or manual venvs in a project that follows this standard. The commands you need:

| Task | Command |
|---|---|
| New project | `uv init --package <name>` (or use the scaffold script below) |
| Pin Python | `uv python pin 3.12` (writes `.python-version`) |
| Add runtime dep | `uv add fastapi` |
| Add dev dep | `uv add --dev pytest` (goes into `[dependency-groups].dev`) |
| Install from lock | `uv sync` (CI: `uv sync --locked`) |
| Run anything | `uv run <cmd>` |
| Upgrade deps | `uv lock --upgrade` then `uv sync` |

Commit `uv.lock` and `.python-version`. They are what make builds reproducible.

**The Makefile is the interface.** Every routine action has a make target that wraps `uv run`. People should never need to remember tool flags, and CI should call the same targets developers do so "works on my machine" and "passes in CI" mean the same thing. Required targets: `help` (default), `install`, `run` or `dev`, `format`, `lint`, `typecheck`, `test`, `cov`, `check` (format-check + lint + typecheck + test, the gate before any commit or PR), and `clean`. Services add `migrate`, `docker-build`, etc. Template: `assets/templates/Makefile.<type>`.

**pyproject.toml holds all tool config.** Ruff (lint + format), mypy, pytest and coverage are configured there, not in `setup.cfg`, `.flake8`, `pytest.ini` or `mypy.ini`. One file to read, one file to review. Template: `assets/templates/pyproject.<type>.toml`. Read `references/tooling.md` for why each ruff rule set and mypy option is chosen, and how to relax them for legacy code.

**src layout.** Packages live under `src/<package_name>/`. This prevents tests from accidentally importing the working directory instead of the installed package, and it keeps the repo root for config.

## Workflow: starting a new project

1. **Pin down the project type** from the request: `fastapi` (HTTP service), `library` (importable package), or `cli` (command-line tool). Workers and data pipelines usually start from `library` plus extra dependencies. If the request is ambiguous, infer from context; ask only if a wrong guess would waste real work.

2. **Scaffold with the script** rather than hand-writing boilerplate, so output is identical across projects:

   ```bash
   python <skill-dir>/scripts/scaffold.py --name my-service --type fastapi --dest ./my-service
   # installed as a Claude Code plugin, <skill-dir> is ${CLAUDE_PLUGIN_ROOT}/skills/python-architecture
   # options: --type fastapi|library|cli  --python 3.12  --layout modular|layered (fastapi only)
   ```

   It writes `pyproject.toml`, `Makefile`, `.python-version`, `.gitignore`, `.pre-commit-config.yaml`, `.env.example` (services), `Dockerfile` (services), a GitHub Actions workflow, a README, a working package skeleton and passing tests. Placeholder text in templates is `{{project_name}}`, `{{package_name}}`, `{{python_version}}`, `{{python_short}}`.

3. **Add dependencies with uv** (the scaffold declares them in pyproject; run `uv sync` to lock and install). Add anything else with `uv add` so versions get locked.

4. **Verify**: run `make check`. A fresh scaffold must pass cleanly. Do not hand back a project where `make check` fails, because the first thing the user will do is run it.

5. **Explain briefly** what was created and the 4–5 make targets they will use most. Don't walk through every file.

If the environment has no uv and you cannot install it, still generate the files, and tell the user to run `make install` locally.

## Workflow: an existing project

Respect what's there before imposing the standard. Look for `pyproject.toml`, `Makefile`, `uv.lock`, `requirements*.txt`, `setup.py`, `poetry.lock`.

- If it already follows this standard, use its make targets (`make check` before finishing any change) and its existing structure.
- If the user asks to migrate, do it incrementally: move to uv (`uv init` in place, then `uv add -r requirements.txt` and `uv add --dev -r requirements-dev.txt`), then consolidate tool config into pyproject, then add the Makefile, then tighten lint rules. Turning on the full ruff rule set on a large legacy codebase produces thousands of errors; start with `E, F, I, UP, B` and use `ruff check --statistics` to plan the rest (see `references/tooling.md`).
- Never silently restructure an existing codebase's layout. Propose it.

## Choosing a structure

Pick the lightest structure that fits the expected size, and say why:

- **FastAPI service**: read `references/fastapi.md`. Default to the **modular (domain-based)** layout with a thin router → service → repository split inside each module. Use **layered** only for very small services (a few endpoints, one domain). Use **clean/hexagonal** only when business rules are complex and must be testable without infrastructure, since it adds real mapping boilerplate.
- **Library, CLI, worker, data/ML project**: read `references/project-types.md`.

## Code standards that apply to every project

These are the defaults that keep code maintainable as it grows. Explain them to the user if they push back, rather than just insisting.

- **Type everything.** Full annotations on public functions, `mypy --strict` in new projects. Types are documentation that the tooling checks, and they make FastAPI/Pydantic validation and editor support work.
- **Configuration through `pydantic-settings`**, loaded from environment variables and an optional `.env`, exposed via a cached `get_settings()`. No hardcoded secrets, no scattered `os.getenv` calls. Commit `.env.example`, never `.env`.
- **Logging, not print.** Use the `logging` module with one configuration point at startup (structured JSON in production is a good default for services). Ruff's `T20` rule enforces no stray prints.
- **Explicit errors.** Define domain exceptions per module; translate them to HTTP/exit codes at the edge, not deep inside business logic.
- **Tests mirror the source tree** under `tests/`, use pytest fixtures, and run against real infrastructure where behavior matters (e.g. Testcontainers Postgres instead of SQLite). Aim for meaningful coverage of business logic rather than a number; the template sets a modest `fail_under` the user can raise.
- **Pure functions where possible**, side effects at the edges. This is what makes code easy to test and to reuse from CLIs, workers and APIs alike.

## Before you finish

Run through this list for any project you create or substantially change:

- `make check` passes (format check, lint, typecheck, tests).
- `uv.lock` exists and is up to date (`uv lock --check`).
- No secrets or `.env` committed; `.env.example` documents every setting.
- README states how to install and run in three commands or fewer (`make install`, `make run`, `make test`).
- New tool config went into `pyproject.toml`, new commands into the `Makefile`.

## Bundled files

- `scripts/scaffold.py`: generates a complete project from the templates.
- `assets/templates/`: config templates (`pyproject.<type>.toml`, `Makefile.<type>`, `Dockerfile`, `dockerignore`, `pre-commit-config.yaml`, `gitignore`, `env.example`, `ci.yml`).
- `assets/skeletons/`: package source and tests for each project type (`fastapi-modular`, `fastapi-layered`, `library`, `cli`).
- `references/tooling.md`: uv, ruff, mypy, pytest, coverage, pre-commit, Docker and CI details and rationale.
- `references/fastapi.md`: FastAPI layouts, layering, dependency injection, settings, DB sessions, error handling, testing and scaling.
- `references/project-types.md`: layouts and conventions for libraries, CLIs, workers and data/ML projects.
