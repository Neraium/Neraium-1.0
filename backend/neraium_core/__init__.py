"""Core package for Neraium - SII-only."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("neraium-core")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "sii",
    "__version__",
]
