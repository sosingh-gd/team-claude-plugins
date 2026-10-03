"""{{project_name}}: public API is re-exported here."""

from importlib.metadata import version

from {{package_name}}.core import slugify

__all__ = ["__version__", "slugify"]
__version__ = version("{{project_name}}")
