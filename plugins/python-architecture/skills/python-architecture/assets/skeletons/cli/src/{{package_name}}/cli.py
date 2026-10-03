"""CLI layer: argument parsing and output only. Logic lives in core.py."""

from typing import Annotated

import typer

from {{package_name}}.core import build_greeting

app = typer.Typer(help="{{project_name}} command-line tool.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """{{project_name}} command-line tool."""


@app.command()
def hello(
    name: Annotated[str, typer.Argument(help="Who to greet.")],
    shout: Annotated[bool, typer.Option("--shout", help="Uppercase the greeting.")] = False,
) -> None:
    """Print a greeting."""
    typer.echo(build_greeting(name, shout=shout))


if __name__ == "__main__":
    app()
