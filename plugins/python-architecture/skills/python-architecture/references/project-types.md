# Other project types

The tooling (uv, Makefile, pyproject config, pre-commit, CI) is identical across types. What changes is the package layout and a few conventions.

## Library (`--type library`)

```
src/<pkg>/
├── __init__.py   # public API: re-export what users import, define __all__ and __version__
├── py.typed      # marks the package as typed (PEP 561) so users get your annotations
├── core.py
└── _internal/    # leading underscore = private, free to change
tests/
```

- The public API is whatever `__init__.py` exports; everything else is private. This lets you refactor internals without breaking users.
- Runtime dependencies: as few as possible, lower bounds only (no upper caps), since every dependency constrains your users' environments.
- Support the oldest Python version you need via `requires-python`, and test the range with a CI matrix.
- Version from metadata (`importlib.metadata.version`) so it lives in one place (pyproject). Bump with `uv version --bump minor`.
- `make build` / `make publish` use `uv build` and `uv publish` (token in `UV_PUBLISH_TOKEN`, or trusted publishing from CI).
- Consider adding `D` (docstrings) to ruff rules and MkDocs + mkdocstrings for docs.

## CLI (`--type cli`)

```
src/<pkg>/
├── cli.py   # Typer app: arguments, options, output formatting only
└── core.py  # logic, importable and testable without the CLI
```

- Typer gives type-hint-driven arguments and help text. Click is fine if the team already uses it; argparse when zero dependencies matters.
- Entry point in `[project.scripts]` (`mytool = "pkg.cli:app"`), so `uv run mytool` works in dev and `uv tool install .` installs it globally.
- Keep `cli.py` thin: parse, call `core`, print. Tests cover `core` directly and the CLI with `typer.testing.CliRunner`.
- `print`/`typer.echo` is allowed in `cli.py` only (T20 per-file ignore); everywhere else use logging. Use `rich` for tables/progress if output is rich.
- Exit codes: `raise typer.Exit(code=1)` on failure; write errors to stderr (`typer.echo(msg, err=True)`).
- Configuration precedence: CLI flags > environment variables > config file > defaults. `pydantic-settings` handles env + file.

## Worker / background service

Start from `library` and add the queue client (`uv add celery[redis]`, `dramatiq`, `arq`, or `taskiq`):

```
src/<pkg>/
├── config.py
├── worker.py      # broker/app setup, task registration
├── tasks/         # thin task functions: deserialize args, call services
└── services/      # business logic shared with any API
```

Tasks should be idempotent (safe to retry), take IDs rather than large objects as arguments, and set explicit timeouts and retry policies. Add `make worker` to run it. If the worker and an API share logic, put both in one repo with the modular layout and run them as separate processes from the same image.

## Data / ML project

```
src/<pkg>/        # reusable code: loading, features, training, evaluation
notebooks/        # exploration only; move anything reused into src/
data/             # git-ignored (raw/, processed/); track with DVC or object storage
configs/          # experiment configs (YAML or pydantic models)
tests/
```

- Notebooks are for exploration; promote code into `src/` once it's used twice. `nbstripout` (as a pre-commit hook) keeps outputs out of git; ruff can lint notebooks (`extend-include = ["*.ipynb"]`).
- Pin heavy dependencies through the lockfile; use uv's `[tool.uv.sources]` / indexes for CUDA-specific PyTorch wheels.
- Make data paths configurable (settings), never hardcoded; use `pathlib`.
- Add make targets for pipeline steps (`make data`, `make train`, `make evaluate`) so runs are reproducible.

## Monorepo with several packages

Use a uv workspace: root `pyproject.toml` with `[tool.uv.workspace] members = ["packages/*", "services/*"]`, one shared `uv.lock`, internal dependencies declared as `shared-lib = { workspace = true }` under `[tool.uv.sources]`. Keep shared ruff/mypy config in the root pyproject and a root Makefile that runs checks across members (`uv run --package <name> ...`).
