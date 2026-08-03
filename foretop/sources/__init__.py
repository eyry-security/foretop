"""Source registry.

Sources register here by name. Adding a feed later (DNS, subdomain enum, an
API, a wordlist) is a matter of dropping a module beside this one and adding a
line to ``_REGISTRY``.
"""

from __future__ import annotations

from .base import Source
from .certstream import CertstreamSource

_REGISTRY: dict[str, type[Source]] = {
    CertstreamSource.name: CertstreamSource,
}


def available() -> list[str]:
    return sorted(_REGISTRY)


def get_source(name: str, **opts) -> Source:
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown source {name!r}; available: {', '.join(available())}"
        ) from None
    return cls(**opts)


__all__ = ["Source", "get_source", "available"]
