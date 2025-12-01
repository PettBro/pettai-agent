"""Backfill missing typing_extensions features for constrained environments."""

from __future__ import annotations


def _ensure_sentinel() -> None:
    """Provide typing_extensions.Sentinel when running with older releases."""
    import typing_extensions as te

    if hasattr(te, "Sentinel"):
        return

    class _SentinelValue:
        """Minimal Sentinel stand-in sufficient for pydantic-core."""

        __slots__ = ("_name", "_repr")

        def __init__(
            self, name: str, *, repr: str | None = None, module: str | None = None
        ) -> None:
            self._name = name
            self._repr = repr or name
            if module:
                self.__module__ = module

        def __repr__(self) -> str:
            return self._repr

    def Sentinel(
        name: str, /, *, repr: str | None = None, module: str | None = None
    ) -> _SentinelValue:
        """Return a singleton-like sentinel value."""
        return _SentinelValue(name, repr=repr, module=module)

    te.Sentinel = Sentinel  # type: ignore[attr-defined]


_ensure_sentinel()
