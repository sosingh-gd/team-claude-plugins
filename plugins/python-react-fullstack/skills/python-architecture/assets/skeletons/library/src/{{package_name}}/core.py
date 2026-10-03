"""Example module. Replace with your library's functionality."""

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, separator: str = "-") -> str:
    """Convert text into a URL-friendly slug.

    >>> slugify("Hello, World!")
    'hello-world'
    """
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _NON_WORD.sub(separator, normalized.lower()).strip(separator)
