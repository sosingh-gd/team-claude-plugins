# Tooling reference

Contents: uv · pyproject.toml layout · ruff · mypy · pytest & coverage · Makefile · pre-commit · Docker · CI · migrating legacy projects

## uv

uv replaces pip, pip-tools, virtualenv, pyenv and Poetry with one fast tool. The project contract is three files: `pyproject.toml` (what you want), `uv.lock` (exactly what you get, cross-platform), `.python-version` (which interpreter).

- `uv sync --all-groups` installs runtime and dev dependencies into `.venv`. In CI and Docker use `--locked` so a stale lockfile fails loudly instead of silently re-resolving.
- Dev tools go into PEP 735 dependency groups (`[dependency-groups] dev = [...]`) via `uv add --dev`. Additional groups (e.g. `docs`, `lint`) are added with `uv add --group docs mkdocs`. Use `[project.optional-dependencies]` only for extras that end users of a published library install (`pip install mylib[postgres]`).
- `uv run <cmd>` runs inside the project env and syncs first, so nobody needs to activate a venv. The Makefile relies on this.
- Version constraints: use lower bounds (`fastapi>=0.115`) in pyproject; the lockfile provides exact pins. Upper bounds on libraries cause resolution pain for downstream users, so avoid them unless a known break exists.
- Global CLIs (not project deps): `uv tool install ruff`. One-off: `uvx ruff check`.
- Workspaces (monorepo with several packages sharing one lock): `[tool.uv.workspace] members = ["packages/*"]`. Reach for this when several services share an internal library.

## pyproject.toml layout

Keep sections in a stable order so diffs are readable: `[project]` → `[project.scripts]` → `[dependency-groups]` → `[build-system]` → `[tool.hatch...]` → `[tool.ruff]` → `[tool.mypy]` → `[tool.pytest.ini_options]` → `[tool.coverage]`. The templates use hatchling as the build backend because it is stable, fast and supports src layout with one line; uv's own `uv_build` backend is a fine alternative.

## ruff

Ruff is both linter and formatter (replacing flake8, isort, pyupgrade, black and dozens of plugins). Configuration choices in the templates and their reasons:

- `line-length = 100`: a common compromise for modern screens; the formatter enforces it, so `E501` is ignored to avoid double reporting.
- `target-version` matches `requires-python` so `UP` rules modernize syntax only as far as the minimum supported version allows.
- `src = ["src", "tests"]` tells isort which imports are first-party.

Rule sets selected and what they buy:

| Code | Plugin | Why |
|---|---|---|
| E, W, F | pycodestyle, pyflakes | Baseline correctness: undefined names, unused imports |
| I | isort | Deterministic import order, no merge conflicts over imports |
| N | pep8-naming | Consistent naming |
| UP | pyupgrade | Modern syntax (`X \| None`, builtin generics) |
| B | bugbear | Real bugs: mutable defaults, loop-variable closures |
| S | bandit | Security: hardcoded passwords, `subprocess` with shell, `assert` in prod code |
| C4, SIM, RET | comprehensions, simplify, return | Simpler, more idiomatic code |
| PT | pytest-style | Consistent pytest usage |
| ARG | unused-arguments | Dead parameters |
| PTH | use-pathlib | `pathlib` over `os.path` |
| T20 | print | No stray `print` (use logging); disabled for CLI entry modules |
| ERA | eradicate | No commented-out code |
| ASYNC | async | Blocking calls inside `async def` (FastAPI templates) |
| FAST | FastAPI | Redundant `response_model`, non-Annotated dependencies (FastAPI templates) |
| RUF | ruff | Misc correctness, e.g. mutable class defaults |

### Light preset (small or learning projects)

The full rule set above suits team codebases. For small projects, prototypes, learning apps, or when the project's `CLAUDE.md` asks for simplicity, use the light preset (`scaffold.py --lint light`, or edit `select` by hand):

```toml
[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM", "RUF", "ASYNC"]   # ASYNC for FastAPI services
```

It keeps the rules that catch real bugs and keep imports tidy, and drops the ones that mostly produce `# noqa` noise in small code (`S`, `ARG`, `ERA`, `T20`, `FAST`, `PTH`, `N`, `RET`, `C4`, `PT`). Rules can be added back one at a time as the project grows.

**Avoid `# noqa` clutter.** A `# noqa` should be rare and carry a reason. If the same rule needs several of them, the rule doesn't fit the project: remove it from `select` instead.

Common optional additions: `D` (pydocstyle, with `convention = "google"`) for published libraries; `PL` (pylint) for teams that want stricter complexity limits; `TCH` to move type-only imports under `TYPE_CHECKING`; `DTZ` to forbid naive datetimes in services that handle time zones.

Per-file ignores: tests allow `assert` (`S101`), unused fixture args (`ARG`) and dummy secrets (`S105/S106`). Prefer narrow per-file ignores or inline `# noqa: CODE` with a reason over removing a rule globally.

## mypy

`strict = true` for new projects: it turns on disallow-untyped-defs, no-implicit-optional, warn-return-any and the rest. Tests are relaxed with an override (`disallow_untyped_defs = false`) so fixtures don't need full annotations, though annotating them is still encouraged. FastAPI/Pydantic projects add `plugins = ["pydantic.mypy"]` so model constructors are type-checked.

For untyped third-party libraries, add a targeted override instead of loosening everything:

```toml
[[tool.mypy.overrides]]
module = ["some_untyped_lib.*"]
ignore_missing_imports = true
```

Pyright/basedpyright is an acceptable alternative if the team prefers it (faster, better editor integration); configure it under `[tool.pyright]` and swap the `typecheck` target. Don't run both.

## pytest & coverage

- `addopts = "-ra --strict-markers --strict-config"`: summary of skips/failures, typos in markers or config become errors.
- Async projects: `pytest-asyncio` with `asyncio_mode = "auto"` so `async def test_...` just works.
- Mark slow or infrastructure-dependent tests (`@pytest.mark.integration`) and add a make target such as `test-unit: $(RUN) pytest -m "not integration"` when the suite grows.
- Coverage is configured with `branch = true` and `fail_under = 80`. Treat the number as a floor, not a goal; it is in pyproject so the user can raise it as the project matures.
- Useful extras when needed: `pytest-xdist` (`-n auto`) for parallel runs, `pytest-randomly` to catch order-dependent tests, `testcontainers` for real Postgres/Redis, `hypothesis` for property-based tests, `polyfactory` for building Pydantic test data.

## Makefile

Principles: every target is self-documenting with `## comment` (parsed by `make help`), grouped with `##@ Section` headers, declared `.PHONY`, and runs tools through `$(RUN)` = `uv run`. `make check` is the contract: CI runs exactly it, the pre-commit hooks run a fast subset, developers run it before pushing.

Variables like `PORT ?= 8000` can be overridden: `make dev PORT=9000`. Pass arguments through a variable: `make run args="--help"`.

Typical additions as a project grows:

```make
.PHONY: migrate migration
migrate: ## Apply database migrations
	$(RUN) alembic upgrade head
migration: ## New migration: make migration m="add users"
	$(RUN) alembic revision --autogenerate -m "$(m)"

.PHONY: up down
up: ## Start local infrastructure (db, cache)
	docker compose up -d
down: ## Stop local infrastructure
	docker compose down

.PHONY: test-unit
test-unit: ## Fast tests only
	$(RUN) pytest -m "not integration"
```

Recipes must be indented with a real tab character. Windows users without make can use the same commands via `uv run` directly, or a `justfile` if the team prefers `just`; keep target names identical.

## pre-commit

The template uses `repo: local` hooks with `language: system` and `entry: uv run ...` for ruff and mypy. This means hook versions come from `uv.lock`, so pre-commit, `make lint` and CI can never disagree because of tool version drift (the classic failure with pinned `ruff-pre-commit` revs). Generic file hygiene hooks come from `pre-commit-hooks`. `make install` installs the git hook automatically when the directory is a git repo.

## Docker

The template Dockerfile is a two-stage uv build:

1. Builder copies the uv binary from `ghcr.io/astral-sh/uv`, installs dependencies only (`--no-install-project`) using bind-mounted `pyproject.toml`/`uv.lock` so this layer is cached until dependencies change, then copies source and installs the project.
2. Runtime is a clean slim image with just `/app` (including `.venv`), running as a non-root user.

`UV_COMPILE_BYTECODE=1` speeds startup; `--no-dev` keeps test tooling out of the image. Pin the uv image tag (e.g. `uv:0.8`) for fully reproducible builds once the project stabilizes.

## CI (GitHub Actions)

`astral-sh/setup-uv` installs uv and caches downloads; then `uv sync --locked --all-groups` and `make check`. To test several Python versions, add a matrix and pass `--python ${{ matrix.python }}` to `uv sync`. GitLab CI follows the same shape: an image with uv (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), then `make check`.

## Migrating a legacy project

Do it in small, reviewable steps, running the test suite after each:

1. `uv init --bare` (adds a minimal pyproject without touching code) or edit the existing one; `uv add -r requirements.txt`; `uv add --dev -r requirements-dev.txt`; delete the requirements files once the lockfile works.
2. Move tool config from `setup.cfg`, `.flake8`, `pytest.ini`, `mypy.ini`, `.isort.cfg` into pyproject.
3. Add the Makefile and CI calling `make check`.
4. Adopt ruff formatting in one dedicated commit (add its hash to `.git-blame-ignore-revs`).
5. Enable lint rules gradually: start with `E, F, I, UP, B`, run `ruff check --statistics`, fix or `--fix` one family at a time. For a huge backlog, `ruff check --add-noqa` records existing violations so new code is held to the standard immediately.
6. Introduce mypy non-strict first, then tighten per package via overrides (`strict` itself is global-only, so set the individual flags such as `disallow_untyped_defs = true` and `disallow_incomplete_defs = true` for `module = "pkg.new_module.*"`), and flip global `strict = true` once most modules comply.
