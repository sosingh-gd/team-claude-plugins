#!/usr/bin/env python3
"""Scaffold a Python project following the python-architecture standard.

Usage:
    python scaffold.py --name my-service --type fastapi [--layout modular|layered]
                       [--python 3.12] [--dest ./my-service] [--no-sync] [--no-git] [--force]

Creates pyproject.toml (ruff/mypy/pytest/coverage config), Makefile, .python-version,
.gitignore, .pre-commit-config.yaml, CI workflow, README, a package skeleton with
passing tests and, for services, Dockerfile/.dockerignore/.env.example.
Only uses the standard library so it runs before any environment exists.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
TEMPLATES = ASSETS / "templates"
SKELETONS = ASSETS / "skeletons"

NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

README = {
    "fastapi": """# {{project_name}}

FastAPI service. Managed with [uv](https://docs.astral.sh/uv/); all routine commands go through `make`.

## Quick start

```bash
make install   # create .venv from uv.lock and install git hooks
cp .env.example .env
make dev       # http://localhost:8000/docs
```

## Common commands

| Command | What it does |
|---|---|
| `make dev` | Run with auto-reload |
| `make format` | Format code and apply safe lint fixes |
| `make check` | Format check, lint, typecheck, tests (what CI runs) |
| `make cov` | Tests with coverage report |
| `make docker-build` | Build the container image |
| `make help` | List every target |

## Layout

{{layout_notes}}

Add dependencies with `uv add <pkg>` (or `uv add --dev <pkg>`), never pip.
""",
    "library": """# {{project_name}}

Python library. Managed with [uv](https://docs.astral.sh/uv/); all routine commands go through `make`.

```bash
make install   # create .venv from uv.lock and install git hooks
make check     # format check, lint, typecheck, tests (what CI runs)
make build     # build sdist + wheel
make help      # list every target
```

Public API is exported from `src/{{package_name}}/__init__.py`. Add dependencies with `uv add <pkg>`.
""",
    "cli": """# {{project_name}}

Command-line tool built with Typer. Managed with [uv](https://docs.astral.sh/uv/); all routine commands go through `make`.

```bash
make install                 # create .venv from uv.lock and install git hooks
make run args="hello Ada"    # run the CLI
make check                   # format check, lint, typecheck, tests (what CI runs)
make help                    # list every target
```

Install globally with `uv tool install .`. Logic lives in `core.py`, the CLI layer in `cli.py`.
""",
}

LAYOUT_NOTES = {
    "modular": """Domain-based (modular): each feature is a self-contained package.

```
src/{{package_name}}/
├── main.py            # app factory, lifespan, router registration
├── config.py          # pydantic-settings
├── exceptions.py      # base domain errors -> HTTP error envelope
├── api.py             # aggregates feature routers under /api/v1
├── health/            # /health and /ready
└── items/             # example feature: copy this folder for new domains
    ├── router.py      # HTTP only
    ├── schemas.py     # request/response models
    ├── service.py     # business logic
    ├── repository.py  # data access (a plain class)
    ├── models.py      # domain/ORM model
    ├── dependencies.py
    └── exceptions.py
```""",
    "layered": """Layer-based: code grouped by technical role. Good for small services.

```
src/{{package_name}}/
├── main.py
├── core/          # config, exceptions, logging
├── api/           # health, deps, v1 routers
├── schemas/       # request/response models
├── models/        # domain/ORM models
├── services/      # business logic
└── repositories/  # data access
```""",
}


def render(text: str, ctx: dict[str, str]) -> str:
    for key, value in ctx.items():
        text = text.replace("{{" + key + "}}", value)
    return text


LIGHT_LINT = '''select = [
    "E", "W",   # pycodestyle
    "F",        # pyflakes
    "I",        # isort
    "UP",       # pyupgrade
    "B",        # flake8-bugbear
    "SIM",      # flake8-simplify
    "RUF",      # ruff-specific{async_rule}
]'''


def use_light_lint(pyproject: str, *, fastapi: bool) -> str:
    """Swap the strict ruff rule set for the light preset (see references/tooling.md)."""
    async_rule = '\n    "ASYNC",    # blocking calls in async def' if fastapi else ""
    light = LIGHT_LINT.format(async_rule=async_rule)
    return re.sub(r"(?ms)^\[tool\.ruff\.lint\]\nselect = \[.*?^\]", "[tool.ruff.lint]\n" + light, pyproject, count=1)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_skeleton(skeleton: Path, dest: Path, ctx: dict[str, str]) -> None:
    for src in sorted(skeleton.rglob("*")):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        rel = render(str(src.relative_to(skeleton)), ctx)
        write(dest / rel, render(src.read_text(encoding="utf-8"), ctx))


def run(cmd: list[str], cwd: Path) -> bool:
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, check=False)  # noqa: S603
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="Project/distribution name, kebab-case (e.g. order-service)")
    parser.add_argument("--type", choices=["fastapi", "library", "cli"], default="fastapi")
    parser.add_argument("--layout", choices=["modular", "layered"], default="modular", help="FastAPI only")
    parser.add_argument("--python", default="3.12", help="Python version, e.g. 3.12")
    parser.add_argument(
        "--lint",
        choices=["strict", "light"],
        default="strict",
        help="Ruff rule set: strict (default) or light for small/learning projects",
    )
    parser.add_argument("--dest", help="Target directory (default: ./<name>)")
    parser.add_argument("--force", action="store_true", help="Write into a non-empty directory")
    parser.add_argument("--no-sync", action="store_true", help="Skip `uv sync` (lock + install)")
    parser.add_argument("--no-git", action="store_true", help="Skip `git init`")
    args = parser.parse_args()

    if not NAME_RE.match(args.name):
        parser.error("--name must be lowercase kebab-case, e.g. 'order-service'")
    if not re.fullmatch(r"3\.\d{1,2}", args.python):
        parser.error("--python must look like 3.12")

    dest = Path(args.dest or args.name).resolve()
    if dest.exists() and any(dest.iterdir()) and not args.force:
        parser.error(f"{dest} is not empty (use --force to write into it)")

    ctx = {
        "project_name": args.name,
        "package_name": args.name.replace("-", "_"),
        "python_version": args.python,
        "python_short": args.python.replace(".", ""),
    }
    ptype = args.type
    print(f"Scaffolding {ptype} project '{args.name}' in {dest}")

    files = {
        f"pyproject.{ptype}.toml": "pyproject.toml",
        f"Makefile.{ptype}": "Makefile",
        "gitignore": ".gitignore",
        "pre-commit-config.yaml": ".pre-commit-config.yaml",
        "ci.yml": ".github/workflows/ci.yml",
    }
    if ptype == "fastapi":
        files |= {"Dockerfile": "Dockerfile", "dockerignore": ".dockerignore", "env.example": ".env.example"}
    for src_name, dest_name in files.items():
        content = render((TEMPLATES / src_name).read_text(encoding="utf-8"), ctx)
        if dest_name == "pyproject.toml" and args.lint == "light":
            content = use_light_lint(content, fastapi=ptype == "fastapi")
        write(dest / dest_name, content)

    write(dest / ".python-version", args.python + "\n")
    readme_ctx = ctx | {"layout_notes": render(LAYOUT_NOTES.get(args.layout, ""), ctx)}
    write(dest / "README.md", render(README[ptype], readme_ctx))

    skeleton = SKELETONS / (f"fastapi-{args.layout}" if ptype == "fastapi" else ptype)
    copy_skeleton(skeleton, dest, ctx)

    if not args.no_git and shutil.which("git") and not (dest / ".git").exists():
        run(["git", "init", "-q"], dest)

    synced = False
    if not args.no_sync:
        if shutil.which("uv"):
            synced = run(["uv", "sync", "--all-groups"], dest)
        else:
            print("  uv not found - install it (https://docs.astral.sh/uv/) then run `make install`")

    print("\nDone. Next steps:")
    print(f"  cd {dest}")
    print("  make install" + ("   # already synced; this also installs git hooks" if synced else ""))
    print("  make check")
    if ptype == "fastapi":
        print("  make dev       # http://localhost:8000/docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
