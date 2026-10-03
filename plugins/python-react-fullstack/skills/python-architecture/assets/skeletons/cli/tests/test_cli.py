from typer.testing import CliRunner

from {{package_name}}.cli import app
from {{package_name}}.core import build_greeting

runner = CliRunner()


def test_build_greeting() -> None:
    assert build_greeting("Ada") == "Hello, Ada!"
    assert build_greeting("Ada", shout=True) == "HELLO, ADA!"


def test_hello_command() -> None:
    result = runner.invoke(app, ["hello", "Ada", "--shout"])
    assert result.exit_code == 0
    assert "HELLO, ADA!" in result.output
