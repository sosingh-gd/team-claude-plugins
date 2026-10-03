import pytest

from {{package_name}} import __version__, slugify


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello, World!", "hello-world"),
        ("  spaces  everywhere ", "spaces-everywhere"),
        ("Crème brûlée", "creme-brulee"),
        ("", ""),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_custom_separator() -> None:
    assert slugify("a b c", separator="_") == "a_b_c"


def test_version_is_set() -> None:
    assert __version__
